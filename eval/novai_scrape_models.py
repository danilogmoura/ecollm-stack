"""Scraper das páginas de modelo do NovAI (links "Try" do marketplace).

Baixa `https://aiapi-pro.com/models/<slug>.html` para cada slug e extrai:
  - nome de exibição, vendor/tags, badges
  - preço (input/output por 1M tokens)
  - parâmetros de configuração presentes nos exemplos de código
    (temperature, top_p, max_tokens, seed, thinking, ...)
  - seções (h2/h3) presentes na página
  - exemplos de código (cURL/Python/Node/LangChain)

Uso:
    python -m eval.novai_scrape_models --out reports/novai-model-configs.json
    python -m eval.novai_scrape_models --slugs-file /tmp/slugs.txt --sleep 0.3

Design: transporte injetável (`fetcher`) para testes offline; rede só com --live.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable

BASE = "https://aiapi-pro.com/models/{slug}.html"

# Tags de categoria usadas nas páginas de chat (não são vendor).
_CATEGORY_TAGS = {
    "coding assistant",
    "math / reasoning",
    "agent orchestration",
    "long-context qa",
    "data extraction",
    "synthetic data",
}

# Parâmetros de geração que interessam (nome canônico -> regex no JSON de exemplo)
PARAM_KEYS = [
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "max_completion_tokens",
    "seed",
    "presence_penalty",
    "frequency_penalty",
    "repetition_penalty",
    "stop",
    "stream",
    "thinking",
    "reasoning_effort",
    "enable_thinking",
    "extra_body",
    # vídeo / imagem / 3D
    "duration",
    "resolution",
    "aspect_ratio",
    "size",
    "n",
    "quality",
    "style",
    "prompt",
    "negative_prompt",
    "image",
    "image_url",
    "fps",
    "mode",
    "response_format",
    "voice",
    "speed",
]


@dataclass
class ModelPage:
    slug: str
    url: str
    ok: bool = False
    http_status: int | None = None
    error: str | None = None
    title: str | None = None
    vendor: str | None = None
    subtitle: str | None = None
    badges: list[str] = field(default_factory=list)
    price_input: str | None = None
    price_output: str | None = None
    sections: list[str] = field(default_factory=list)
    code_langs: list[str] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    specs: dict[str, str] = field(default_factory=dict)
    use_cases: list[str] = field(default_factory=list)
    overview: str | None = None
    bytes: int = 0


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _section_html(html: str, title: str) -> str | None:
    """Retorna o HTML interno da seção cujo <h2>/<h3> casa com `title` (case-insensitive)."""
    m = re.search(
        r"<h[23]>\s*" + re.escape(title) + r"\s*</h[23]>(.*?)(?=<h[23]>|$)",
        html,
        re.S | re.I,
    )
    return m.group(1) if m else None


def _parse_specs(html: str) -> dict[str, str]:
    """Extrai especificações técnicas de dois formatos:

    1. Tabela 'Technical specifications' (Property/Value) — páginas de chat ricas.
    2. <div class="spec-item"><div class="spec-label">K</div><div class="spec-value">V</div>
       — páginas de vídeo/imagem/3D (card 'Specifications & Pricing').
    """
    specs: dict[str, str] = {}

    # formato 1: tabela
    sec = _section_html(html, "Technical specifications")
    if sec:
        for row in re.findall(r"<tr>(.*?)</tr>", sec, re.S):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
            if len(cells) >= 2:
                k = _strip_tags(cells[0])
                v = _strip_tags(cells[1])
                if k and v and k.lower() not in ("property", "value"):
                    specs[k] = v

    # formato 2: spec-item (label/value)
    for m in re.finditer(
        r'<div class="spec-item">\s*<div class="spec-label">(.*?)</div>\s*'
        r'<div class="spec-value">(.*?)</div>',
        html,
        re.S,
    ):
        k = _strip_tags(m.group(1))
        v = _strip_tags(m.group(2))
        if k and v:
            specs[k] = v

    return specs


def _parse_use_cases(html: str) -> list[str]:
    """Extrai os itens de 'Best use cases' (lista ou subtítulos)."""
    sec = _section_html(html, "Best use cases")
    if not sec:
        return []
    items = [_strip_tags(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", sec, re.S)]
    items = [i for i in items if i]
    if not items:
        # fallback: subtítulos h4/h5 dentro da seção
        items = [_strip_tags(h) for h in re.findall(r"<h[45][^>]*>(.*?)</h[45]>", sec, re.S)]
    return items


def _parse_overview(html: str) -> str | None:
    sec = _section_html(html, "Model overview")
    if not sec:
        return None
    txt = _strip_tags(sec)
    return txt[:1200] if txt else None


def _parse_code_blocks(html: str) -> list[dict]:
    """Extrai todos os blocos de código com a linguagem inferida.

    Formatos suportados:
      - <pre><code>...</code></pre>  (páginas de chat)
      - <code>...</code> inline      (páginas de chat, exemplos curtos)
      - <div class="code-block">...</div>  (páginas de vídeo/imagem/3D)

    A linguagem vem do <h3> imediatamente anterior ao bloco (ex.: cURL, Python,
    Node.js / TypeScript, LangChain integration). É aqui que ficam as
    configurações de uso sugeridas pela NovAI (model ID + parâmetros).
    """
    blocks: list[dict] = []
    last_h3: str | None = None
    pat = re.compile(
        r"<h3[^>]*>([^<]+)</h3>"
        r"|<pre><code>(.*?)</code></pre>"
        r"|<div class=\"code-block\">(.*?)</div>"
        r"|<code>(.*?)</code>",
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
        if code:
            blocks.append({"lang": last_h3, "code": code})
    return blocks


def parse_page(slug: str, html: str, http_status: int | None = None) -> ModelPage:
    """Parse puro (sem rede) de uma página de modelo."""
    p = ModelPage(slug=slug, url=BASE.format(slug=slug), ok=True, http_status=http_status)
    p.bytes = len(html)

    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        p.title = _strip_tags(m.group(1)).replace(" - NovAI API", "").strip()

    # vendor: <div class="vendor"> (páginas de vídeo/imagem/3D).
    # Nas páginas de chat o <span class="tag"> é categoria (ex.: "Coding
    # assistant"), não vendor — nesse caso deixamos None.
    m = re.search(r'<div class="vendor">(.*?)</div>', html, re.S)
    if m:
        p.vendor = _strip_tags(m.group(1))
    else:
        m = re.search(r'<span class="tag">([^<]+)</span>', html)
        if m:
            cand = _strip_tags(m.group(1))
            if cand.lower() not in _CATEGORY_TAGS:
                p.vendor = cand

    # subtitle/descrição: <p class="subtitle"> (chat) ou <p class="desc"> (vídeo)
    m = re.search(r'<p class="subtitle">(.*?)</p>', html, re.S)
    if not m:
        m = re.search(r'<p class="desc">(.*?)</p>', html, re.S)
    if m:
        p.subtitle = _strip_tags(m.group(1))

    # badges
    p.badges = [_strip_tags(b) for b in re.findall(r'<span class="badge[^"]*">([^<]+)</span>', html)]

    # preço: dois formatos
    #  1. <div class="price-cell"><div class="num">$X</div><div class="label">Input / 1M tokens</div>
    #  2. <span class="price-label">Input</span><span class="price-value">$X</span>
    for m in re.finditer(
        r'<div class="price-cell">\s*<div class="num">([^<]+)</div>\s*'
        r'<div class="label">([^<]+)</div>',
        html,
        re.S,
    ):
        num = _strip_tags(m.group(1))
        label = _strip_tags(m.group(2)).lower()
        # só preço por token; ignora "Context window" / "Max output" (não são preço)
        if "input" in label and "1m" in label:
            p.price_input = num
        elif "output" in label and "1m" in label:
            p.price_output = num
    for label, attr in (("Input", "price_input"), ("Output", "price_output")):
        if getattr(p, attr):
            continue
        m = re.search(
            r'<span class="price-label">' + label + r'</span>\s*<span class="price-value">([^<]+)</span>',
            html,
        )
        if m:
            setattr(p, attr, _strip_tags(m.group(1)))
    # normaliza "$$0.00" (typo na origem) -> "$0.00"
    for attr in ("price_input", "price_output"):
        v = getattr(p, attr)
        if v and v.startswith("$$"):
            setattr(p, attr, v[1:])

    # seções h2/h3
    p.sections = [_strip_tags(s) for s in re.findall(r"<h[23]>([^<]+)</h[23]>", html)]

    # linguagens de exemplo: <h3>cURL</h3> etc. já caem em sections; detecta blocos <pre><code>
    p.code_langs = [_strip_tags(s) for s in re.findall(r"<h3>([^<]+)</h3>", html)
                    if re.search(r"(cURL|Python|Node|LangChain|TypeScript|JavaScript|Go|Java|PHP|Ruby|Rust)", s, re.I)]

    # parâmetros: procura "key": value dentro de blocos de código
    for key in PARAM_KEYS:
        m = re.search(r'"' + re.escape(key) + r'"\s*:\s*("?[^,}\n]+"?)', html)
        if m:
            val = m.group(1).strip().strip('"')
            # ignora falsos positivos do ld+json (og-cover)
            if "og-cover" in val:
                continue
            p.params[key] = val

    # seções ricas (só existem em algumas páginas)
    p.specs = _parse_specs(html)
    p.use_cases = _parse_use_cases(html)
    p.overview = _parse_overview(html)
    p.code_blocks = _parse_code_blocks(html)

    # fallback de preço para vídeo/imagem/3D: spec-item "Token Price"
    if not p.price_input:
        tp = p.specs.get("Token Price")
        if tp:
            p.price_input = tp

    return p


def scrape(
    slugs: Iterable[str],
    fetcher: Callable[[str], tuple[int, str]],
    sleep: float = 0.0,
    progress: Callable[[int, int, ModelPage], None] | None = None,
) -> list[ModelPage]:
    slugs = list(slugs)
    out: list[ModelPage] = []
    for i, slug in enumerate(slugs, 1):
        try:
            status, html = fetcher(slug)
            page = parse_page(slug, html, status)
            if status != 200:
                page.ok = False
                page.error = f"HTTP {status}"
        except Exception as e:  # noqa: BLE001
            page = ModelPage(slug=slug, url=BASE.format(slug=slug), ok=False, error=str(e))
        out.append(page)
        if progress:
            progress(i, len(slugs), page)
        if sleep and i < len(slugs):
            time.sleep(sleep)
    return out


def _http_fetcher(timeout: float = 20.0) -> Callable[[str], tuple[int, str]]:
    import requests

    def fetch(slug: str) -> tuple[int, str]:
        r = requests.get(BASE.format(slug=slug), timeout=timeout,
                         headers={"User-Agent": "ecollm-stack/1.0 (+novai-scrape)"})
        return r.status_code, r.text

    return fetch


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape NovAI model pages (Try links).")
    ap.add_argument("--slugs-file", default="/tmp/slugs.txt", help="arquivo com 1 slug por linha")
    ap.add_argument("--out", default="reports/novai-model-configs.json", help="JSON de saída")
    ap.add_argument("--sleep", type=float, default=0.3, help="pausa entre requests (s)")
    ap.add_argument("--live", action="store_true", help="faz requests de rede (senão só valida)")
    args = ap.parse_args(argv)

    with open(args.slugs_file, encoding="utf-8") as f:
        slugs = [ln.strip() for ln in f if ln.strip()]
    print(f"slugs: {len(slugs)}", flush=True)

    if not args.live:
        print("(dry-run) use --live para baixar de verdade", flush=True)
        return 0

    def prog(i: int, n: int, p: ModelPage) -> None:
        tag = "ok" if p.ok else f"FAIL({p.error})"
        print(f"[{i:3d}/{n}] {p.slug:32s} {tag:20s} {p.bytes:6d}B "
              f"params={len(p.params)} specs={len(p.specs)} "
              f"cases={len(p.use_cases)} code={len(p.code_blocks)} "
              f"sections={len(p.sections)}", flush=True)

    pages = scrape(slugs, _http_fetcher(), sleep=args.sleep, progress=prog)

    ok = sum(1 for p in pages if p.ok)
    print(f"\nresumo: {ok}/{len(pages)} ok", flush=True)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in pages], f, ensure_ascii=False, indent=2)
    print(f"salvo: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
