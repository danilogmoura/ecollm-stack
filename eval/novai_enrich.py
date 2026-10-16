"""Enriquece o catálogo NovAI com TODAS as fontes disponíveis.

Combina, por modelo, o máximo de informação extraível:

  1. ``GET /v1/models`` do **gateway NovAI direto** (não o proxy) — metadados
     reais: ``owned_by`` (provedor), ``pricing``, ``type`` (video/image/audio/
     threed/embedding). O proxy LiteLLM mascara tudo como ``owned_by: openai``.
  2. **Listas autoritativas por modalidade** — cada endpoint revela, no erro 400
     ("Available: ..."), a lista de modelos daquela modalidade. Serve para
     classificar modalidade sem depender do ``config.yaml``.
  3. **JSON-LD schema.org** das páginas ``/models/<slug>.html`` — dados
     estruturados que o scrape HTML não captura: ``brand``, ``price``,
     ``priceCurrency``, ``availability``, ``priceValidUntil``, ``description``.
  4. **Modelos fantasma** — páginas que existem mas não aparecem no
     ``/v1/models`` (ex.: ``doubao-seedream-4.0``/``4.5``).
  5. **Comandos da tag code** — extrai e (opcionalmente) executa os exemplos
     cURL/Python/Node de cada página para validar que funcionam.

Padrão do repo: parse PURO + transporte INJETÁVEL (getter/sender) para testes
offline. Rede só com ``--live``.

Uso:
    python -m eval.novai_enrich --live --out reports/novai-enriched.json
    python -m eval.novai_enrich --live --test-code --sleep 1.1
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

OUT_DEFAULT = "reports/novai-enriched.json"

# Gateway NovAI direto (NÃO o proxy LiteLLM): só ele devolve metadados reais
# (owned_by/pricing/type). O proxy mascara tudo como owned_by=openai.
GATEWAY_BASE_URL = "https://aiapi-pro.com/v1"


def gateway_config() -> dict:
    """Base URL + chave do gateway NovAI direto, lidas do ambiente (.env).

    Diferente de ``novai_test.proxy_config`` (que aponta para o proxy local
    ``:4000`` com a master key ``sk-``), aqui usamos o upstream real
    ``https://aiapi-pro.com/v1`` com a chave ``NOVAI_API_KEY`` (prefixo
    ``nvai-``). É o único endpoint que expõe ``owned_by``/``pricing``/``type``.
    """
    from ingest.embed import load_dotenv

    load_dotenv()
    return {
        "base_url": os.environ.get("NOVAI_BASE_URL", GATEWAY_BASE_URL).rstrip("/"),
        "api_key": os.environ.get("NOVAI_API_KEY", ""),
    }


# endpoint -> modalidade (para capturar a lista "Available:" do erro 400).
# ATENÇÃO: no gateway direto os endpoints NÃO têm o prefixo ``/v1`` (com ele
# devolvem 405 Method Not Allowed). O proxy LiteLLM é que usa ``/v1/...``.
MODALITY_ENDPOINTS = {
    "chat": ("/chat/completions",
             {"model": "__nope__", "messages": [{"role": "user", "content": "x"}],
              "max_tokens": 5}),
    "image": ("/images/generations", {"model": "__nope__", "prompt": "x"}),
    "embedding": ("/embeddings", {"model": "__nope__", "input": "x"}),
    "audio": ("/audio/speech",
              {"model": "__nope__", "input": "x", "voice": "alloy"}),
    "video": ("/video/generations", {"model": "__nope__", "prompt": "x"}),
}


@dataclass
class EnrichedModel:
    """Um modelo com todas as fontes cruzadas."""

    id: str
    # gateway /v1/models
    owned_by: str | None = None
    pricing: str | None = None
    type: str | None = None
    # classificação por modalidade (via erro 400)
    modalities: list[str] = field(default_factory=list)
    # JSON-LD da página
    brand: str | None = None
    ld_price: str | None = None
    ld_currency: str | None = None
    ld_description: str | None = None
    availability: str | None = None
    price_valid_until: str | None = None
    # página
    has_page: bool = False
    page_slug: str | None = None
    # comandos da tag code
    code_commands: list[dict] = field(default_factory=list)
    code_tests: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsers PUROS (sem rede)
# ---------------------------------------------------------------------------


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse_available(text: str) -> list[str]:
    """Extrai a lista após 'Available:' de uma mensagem de erro 400."""
    m = re.search(r"Available:\s*(.+)", text)
    if not m:
        return []
    raw = m.group(1).rstrip('"}').strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_jsonld(html: str) -> dict:
    """Extrai brand/price/availability/description do JSON-LD schema.org."""
    out: dict = {}
    m = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if not m:
        return out
    try:
        data = json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return out
    graph = data.get("@graph", [data]) if isinstance(data, dict) else data
    for node in graph if isinstance(graph, list) else [graph]:
        if not isinstance(node, dict):
            continue
        if node.get("@type") == "Product":
            brand = node.get("brand")
            if isinstance(brand, dict):
                out["brand"] = brand.get("name")
            elif isinstance(brand, str):
                out["brand"] = brand
            if node.get("description"):
                out["description"] = node["description"]
            offers = node.get("offers")
            if isinstance(offers, dict):
                if offers.get("price"):
                    out["price"] = offers["price"]
                if offers.get("priceCurrency"):
                    out["currency"] = offers["priceCurrency"]
                if offers.get("availability"):
                    out["availability"] = offers["availability"].rsplit("/", 1)[-1]
                if offers.get("priceValidUntil"):
                    out["price_valid_until"] = offers["priceValidUntil"]
    return out


def parse_code_commands(html: str) -> list[dict]:
    """Extrai os comandos de cada bloco de código (cURL/Python/Node).

    Devolve ``[{lang, code, kind}]`` onde ``kind`` ∈ {curl, python, node, other}.
    """
    blocks: list[dict] = []
    last_h3: str | None = None
    pat = re.compile(
        r"<h3[^>]*>([^<]+)</h3>"
        r"|<pre><code>(.*?)</code></pre>"
        r"|<div class=\"code-block\">(.*?)</div>",
        re.S,
    )
    for m in pat.finditer(html):
        if m.group(1) is not None:
            last_h3 = _strip_tags(m.group(1))
            continue
        raw = next((g for g in m.groups()[1:] if g is not None), None)
        if raw is None:
            continue
        code = html_mod.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if not code:
            continue
        kind = _classify_code(code, last_h3)
        blocks.append({"lang": last_h3, "code": code, "kind": kind})
    return blocks


def _classify_code(code: str, lang: str | None) -> str:
    low = (lang or "").lower()
    if "curl" in low or code.lstrip().startswith("curl"):
        return "curl"
    if "python" in low or "import requests" in code or "openai" in code.lower():
        return "python"
    if "node" in low or "typescript" in low or "javascript" in low or "fetch(" in code:
        return "node"
    return "other"


def parse_page_enrich(slug: str, html: str) -> dict:
    """Parse puro de uma página: JSON-LD + comandos de código."""
    ld = parse_jsonld(html)
    return {
        "slug": slug,
        "brand": ld.get("brand"),
        "ld_price": ld.get("price"),
        "ld_currency": ld.get("currency"),
        "ld_description": ld.get("description"),
        "availability": ld.get("availability"),
        "price_valid_until": ld.get("price_valid_until"),
        "code_commands": parse_code_commands(html),
    }


# ---------------------------------------------------------------------------
# Transporte (rede) — injetável
# ---------------------------------------------------------------------------


def make_gateway_getter(cfg: dict):
    """GET autenticado ao gateway NovAI direto (base_url do cfg)."""
    import requests

    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _get(path: str, **kwargs):
        url = f"{cfg['base_url']}/{path.lstrip('/')}"
        return requests.get(url, headers=headers, timeout=60)

    return _get


def make_gateway_poster(cfg: dict):
    """POST autenticado ao gateway NovAI direto."""
    import requests

    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _post(path: str, json_body=None, **kwargs):
        url = f"{cfg['base_url']}/{path.lstrip('/')}"
        return requests.post(url, headers=headers, json=json_body, timeout=60)

    return _post


def make_site_getter(cfg: dict):
    """GET às páginas HTML do site (raiz, SEM o prefixo ``/v1``).

    As páginas de modelo vivem em ``https://aiapi-pro.com/models/<slug>.html``;
    o ``base_url`` do gateway inclui ``/v1``, então removemos esse sufixo.
    """
    import requests

    root = cfg["base_url"]
    if root.endswith("/v1"):
        root = root[:-3]
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _get(path: str, **kwargs):
        url = f"{root}/{path.lstrip('/')}"
        return requests.get(url, headers=headers, timeout=60)

    return _get


def fetch_gateway_models(getter) -> list[dict]:
    """GET /models do gateway direto (metadados reais).

    Atenção: o gateway expõe a lista em ``/models`` (SEM o prefixo ``/v1``);
    ``/v1/models`` devolve 404. O proxy LiteLLM é que usa ``/v1/models``.
    """
    r = getter("/models")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return (r.json() or {}).get("data", [])


def fetch_modality_lists(poster) -> dict[str, list[str]]:
    """Captura a lista 'Available:' de cada endpoint (erro 400)."""
    out: dict[str, list[str]] = {}
    for mod, (path, body) in MODALITY_ENDPOINTS.items():
        try:
            r = poster(path, json_body=body)
            out[mod] = parse_available(r.text)
        except Exception as exc:  # noqa: BLE001
            out[mod] = []
    return out


def fetch_page(slug: str, getter) -> str | None:
    """Baixa a página HTML de um modelo (via gateway)."""
    try:
        r = getter(f"/models/{slug}.html")
        if r.status_code == 200:
            return r.text
    except Exception:  # noqa: BLE001
        return None
    return None


# ---------------------------------------------------------------------------
# Execução dos comandos da tag code
# ---------------------------------------------------------------------------

# flags de cURL que escrevem/lêem arquivos ou fazem upload — bloqueadas
_DANGEROUS_CURL_FLAGS = {
    "-o", "--output", "-O", "--remote-name", "-T", "--upload-file",
    "-D", "--dump-header", "-c", "--cookie-jar", "-K", "--config",
    "--data-binary", "--data-urlencode",
}

# placeholders de chave que aparecem nos exemplos
_KEY_PLACEHOLDERS = ("$KEY", "$NOVAI_API_KEY", "$API_KEY", "YOUR_API_KEY",
                     "<YOUR_API_KEY>", "sk-xxx", "nvai-xxx")


def _sanitize_curl_args(args: list[str], api_key: str | None) -> tuple[list[str], str | None]:
    """Substitui placeholders de chave e bloqueia flags perigosas.

    Devolve ``(args_sanitizados, motivo_bloqueio)``. Se bloqueado, o motivo
    é não-None e os args não devem ser executados.
    """
    out: list[str] = []
    for a in args:
        if a in _DANGEROUS_CURL_FLAGS:
            return args, f"flag perigosa bloqueada: {a}"
        # bloqueia upload via @file em --data
        if a.startswith("@") or (a.startswith("--data") and "@" in a):
            return args, "upload de arquivo bloqueado"
        # substitui placeholder de chave
        if api_key:
            for ph in _KEY_PLACEHOLDERS:
                if ph in a:
                    a = a.replace(ph, api_key)
        out.append(a)
    return out, None


def run_code_command(cmd: dict, *, api_key: str | None = None,
                     timeout: float = 30.0) -> dict:
    """Executa um comando cURL extraído e devolve o resultado.

    Só executa ``kind == 'curl'`` (sem shell). Python/Node são apenas
    registrados (não executados) para evitar efeitos colaterais. Placeholders
    de chave são substituídos por ``api_key``; flags que escrevem/lêem arquivos
    ou fazem upload são bloqueadas.
    """
    kind = cmd.get("kind")
    if kind != "curl":
        return {"kind": kind, "executed": False,
                "reason": "só cURL é executado (segurança)"}
    import shlex
    import subprocess

    code = cmd["code"]
    # normaliza continuações de linha
    code = code.replace("\\\n", " ")
    try:
        args = shlex.split(code)
    except ValueError as exc:
        return {"kind": kind, "executed": False, "reason": f"parse: {exc}"}
    if not args or args[0] != "curl":
        return {"kind": kind, "executed": False, "reason": "não é curl"}
    args, blocked = _sanitize_curl_args(args, api_key)
    if blocked:
        return {"kind": kind, "executed": False, "reason": blocked}
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout)
        return {
            "kind": kind,
            "executed": True,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "stdout": proc.stdout[:500],
            "stderr": proc.stderr[:300],
        }
    except subprocess.TimeoutExpired:
        return {"kind": kind, "executed": True, "ok": False,
                "reason": "timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"kind": kind, "executed": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def enrich(getter, poster, *, pages: dict[str, str] | None = None,
           slugs: list[str] | None = None, test_code: bool = False,
           api_key: str | None = None, sleep: float = 0.0,
           progress=None, page_getter=None) -> list[EnrichedModel]:
    """Cruza todas as fontes num registro por modelo.

    ``getter``/``poster``: transporte ao gateway (API). ``page_getter``:
    transporte às páginas HTML do site (raiz, sem ``/v1``); se omitido, usa
    ``getter``. ``pages``: cache opcional slug->html (para testes offline; se
    fornecido, NÃO baixa páginas). ``slugs``: slugs adicionais a incluir (ex.:
    páginas do marketplace, que contêm modelos fantasma ausentes do
    ``/models``). ``test_code``: executa os cURL.
    """
    api_models = fetch_gateway_models(getter)
    by_id = {m.get("id"): m for m in api_models}

    mod_lists = fetch_modality_lists(poster)
    # id -> modalidades
    id_mods: dict[str, list[str]] = {}
    for mod, ids in mod_lists.items():
        for mid in ids:
            id_mods.setdefault(mid, []).append(mod)

    # universo de ids: /models ∪ listas de modalidade ∪ slugs ∪ cache
    universe = set(by_id) | set(id_mods) | set(slugs or []) | set(pages or {})
    ordered = sorted(universe)

    page_getter = page_getter or getter
    out: list[EnrichedModel] = []
    for i, mid in enumerate(ordered):
        meta = by_id.get(mid, {})
        em = EnrichedModel(
            id=mid,
            owned_by=meta.get("owned_by"),
            pricing=meta.get("pricing"),
            type=meta.get("type"),
            modalities=id_mods.get(mid, []),
        )
        if progress:
            progress(i, len(ordered), mid)
        if sleep > 0 and i > 0:
            time.sleep(sleep)

        # página: do cache (offline) ou baixa (live)
        if pages is not None:
            html = pages.get(mid)
        else:
            html = fetch_page(mid, page_getter)
        if html:
            em.has_page = True
            em.page_slug = mid
            info = parse_page_enrich(mid, html)
            em.brand = info["brand"]
            em.ld_price = info["ld_price"]
            em.ld_currency = info["ld_currency"]
            em.ld_description = info["ld_description"]
            em.availability = info["availability"]
            em.price_valid_until = info["price_valid_until"]
            em.code_commands = info["code_commands"]
            if test_code:
                for cmd in em.code_commands:
                    em.code_tests.append(run_code_command(cmd, api_key=api_key))
        out.append(em)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="pausa (s) entre modelos no modo --live")
    ap.add_argument("--test-code", action="store_true",
                    help="executa os comandos cURL extraídos das páginas")
    ap.add_argument("--slugs-file", default=None,
                    help="arquivo com 1 slug por linha (páginas do marketplace)")
    ap.add_argument("--live", action="store_true", help="faz requests de rede")
    args = ap.parse_args(argv)

    if not args.live:
        print("modo offline: use --live para consultar a API", file=sys.stderr)
        return 2

    cfg = gateway_config()
    if not cfg.get("api_key"):
        print("NOVAI_API_KEY ausente no ambiente (.env)", file=sys.stderr)
        return 2
    getter = make_gateway_getter(cfg)
    poster = make_gateway_poster(cfg)
    page_getter = make_site_getter(cfg)

    slugs: list[str] = []
    if args.slugs_file:
        with open(args.slugs_file, encoding="utf-8") as f:
            slugs = [ln.strip() for ln in f if ln.strip()]
        print(f"slugs do marketplace: {len(slugs)}", flush=True)

    def _prog(i, n, mid):
        print(f"[{i+1}/{n}] {mid}", flush=True)

    models = enrich(getter, poster, slugs=slugs, test_code=args.test_code,
                    api_key=cfg.get("api_key"), sleep=args.sleep,
                    progress=_prog, page_getter=page_getter)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps([asdict(x) for x in models], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n_page = sum(1 for m in models if m.has_page)
    n_ld = sum(1 for m in models if m.ld_price)
    n_code = sum(len(m.code_commands) for m in models)
    n_tested = sum(len(m.code_tests) for m in models)
    print(f"modelos={len(models)} com_pagina={n_page} com_jsonld_preco={n_ld} "
          f"comandos={n_code} testados={n_tested}")
    print(f"salvo: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
