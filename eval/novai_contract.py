"""S117 — Teste de CONTRATO de API (shape OpenAI/LiteLLM) para as rotas NovAI.

O harness ``eval/novai_test.py`` valida **semântica** (tem content? o SSE
parseia?). Este módulo valida **shape**: se o JSON devolvido tem os campos e
tipos que um cliente tipado (``openai-python``, Copilot BYOK, Roo Code) espera
no padrão OpenAI — mesmo com HTTP 200.

Regras travadas (calibração medida 2026-10-17, ver ``20-BACKLOG.md`` S117):

  - **extra="allow"**: ``openai-python`` usa ``ConfigDict(extra="allow")``;
    validadores NUNCA proíbem campo extra. Valida presença/tipo dos
    ``required``, jamais ``additionalProperties: false``.
  - **Erro é target-aware**: proxy devolve envelope OpenAI
    (``{"error":{message,type,param,code}}``); gateway devolve FastAPI cru
    (``{"detail": "..."}``). No gateway, ``detail`` conforma como
    **divergência documentada**, não ``fail``.
  - **``GET /models``**: POST em ``.../v1/models`` responde 405 nos dois alvos
    — testar só com GET. E no gateway o caminho JSON é ``/v1/models``
    (``/models`` raiz devolve a SPA HTML, não o inventário).
  - **Embeddings**: ``id`` só existe no gateway → não pode ser ``required``.
  - **Chunk SSE**: ``usage`` só aparece no gateway (chunk final) → opcional.

Modos:
  A. **estrutural** — fixtures em memória passam/falham nos validadores. É o
     que roda na suíte de testes, sem rede.
  B. **live** — faz as chamadas reais (proxy LiteLLM e/ou gateway NovAI) e
     valida a resposta. Só com ``--live`` (respeita saldo ≈ $0).
  C. **SDK real** — usa ``openai`` de verdade quando instalado; ``skipif``
     quando ausente (não entra no gate de cobertura).

DESIGN (mesmo padrão de ``eval/novai_test.py``):
  - schemas e validadores são PURAS funções/dados → testáveis sem rede;
  - transport injetável (``sender``) → testes unitários sem tocar :4000;
  - relatório datado em ``reports/`` (markdown + tabela de conformidade).

Uso:
    .venv/bin/python -m eval.novai_contract --list-endpoints
    .venv/bin/python -m eval.novai_contract --live [--target proxy|gateway|both]
    .venv/bin/python -m eval.novai_contract --live --out reports/contrato.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import jsonschema
import requests

from ingest.embed import load_dotenv  # noqa: F401  (padrão canônico da casa)

from .novai_test import (
    TARGETS,
    Sender,
    _elapsed_ms,
    make_capturing_sender,
    parse_sse_lines,
    proxy_config,
    resolve_targets,
    target_config,
)

# ---------------------------------------------------------------------------
# Especificações de endpoint (ordem canônica — não reordenar, prompt-cache)
# ---------------------------------------------------------------------------

# Nome do modelo por alvo, travado na calibração S117 (armadilha 4: os nomes
# antigos novai-glm-4.6-flash / glm-4.6 NÃO existem mais → 400).
CHAT_MODEL = {"proxy": "novai-glm-4.7-flash", "gateway": "glm-5"}
EMBED_MODEL = {"proxy": "novai-embed-text-embedding-v4",
               "gateway": "text-embedding-v4"}
EMBED_DIM = 1024
IMAGE_MODEL = {"proxy": "novai-image-wand-vega-image-flash",
               "gateway": "wand-vega-image-flash"}
BAD_MODEL = {"proxy": "novai-xxx-nao-existe-s117",
             "gateway": "xxx-nao-existe-s117"}

REPORT_DEFAULT_DIR = Path("reports")


@dataclass(frozen=True)
class EndpointSpec:
    """Um endpoint do contrato OpenAI exercitado pelo harness."""

    id: str
    path: str
    method: str  # POST | GET
    modality: str
    uses_model: bool
    doc: str


ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("chat.completion", "/chat/completions", "POST", "chat", True,
                 "Chat completion não-streaming (objeto chat.completion)."),
    EndpointSpec("chat.completion.chunk", "/chat/completions", "POST",
                 "chat-stream", True,
                 "Streaming SSE: cada chunk data: é chat.completion.chunk."),
    EndpointSpec("embeddings", "/embeddings", "POST", "embedding", True,
                 "Resposta de embeddings (data[i].embedding + usage)."),
    EndpointSpec("images.generation", "/images/generations", "POST", "image",
                 True, "Geração de imagem (data[i] com url ou b64_json)."),
    # Caminho relativo ao base_url (que já termina em /v1 nos dois alvos):
    # "/models" resolve para .../v1/models — GET apenas, POST responde 405.
    EndpointSpec("models.list", "/models", "GET", "models", False,
                 "Inventário de modelos (GET apenas — POST responde 405)."),
    EndpointSpec("error.openai", "/chat/completions", "POST", "error", True,
                 "Envelope de erro: OpenAI no proxy, FastAPI no gateway."),
)


def endpoint_by_id(eid: str) -> EndpointSpec:
    for spec in ENDPOINTS:
        if spec.id == eid:
            return spec
    raise KeyError(f"endpoint desconhecido: {eid!r}")


# ---------------------------------------------------------------------------
# Schemas (draft 2020-12, sempre extra="allow" implícito — sem
# additionalProperties:false, armadilha 3). Tipos Python aceitos além dos JSON:
# ``integer`` exclui bool (jsonschema trata bool como int por padrão), então
# usamos not ("boolean", ...) onde o tipo precisa ser estrito.
# ---------------------------------------------------------------------------

_INT_NOT_BOOL = {"type": "integer", "not": {"type": "boolean"}}

SCHEMA_CHAT_COMPLETION: dict = {
    "type": "object",
    "required": ["id", "object", "created", "model", "choices", "usage"],
    "properties": {
        "id": {"type": "string"},
        "object": {"const": "chat.completion"},
        "created": _INT_NOT_BOOL,
        "model": {"type": "string"},
        "choices": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "required": ["index", "message", "finish_reason"],
                "properties": {
                    "index": _INT_NOT_BOOL,
                    "finish_reason": {"type": "string"},
                    "message": {
                        "type": "object",
                        "required": ["role", "content"],
                        "properties": {
                            "role": {"const": "assistant"},
                            # content é str inclusive quando vazio/thinking
                            # (medido: os dois alvos devolvem "" nunca null).
                            "content": {"type": "string"},
                        },
                    },
                },
            },
        },
        "usage": {
            "type": "object",
            "required": ["prompt_tokens", "completion_tokens", "total_tokens"],
            "properties": {
                "prompt_tokens": _INT_NOT_BOOL,
                "completion_tokens": _INT_NOT_BOOL,
                "total_tokens": _INT_NOT_BOOL,
            },
        },
    },
}

SCHEMA_CHUNK: dict = {
    "type": "object",
    "required": ["id", "object", "created", "model", "choices"],
    "properties": {
        "id": {"type": "string"},
        "object": {"const": "chat.completion.chunk"},
        "created": _INT_NOT_BOOL,
        "model": {"type": "string"},
        "choices": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "required": ["index", "delta"],
                "properties": {
                    "index": _INT_NOT_BOOL,
                    "delta": {"type": "object"},
                    # finish_reason chega null nos chunks do meio e str no
                    # último — nullable, não required.
                    "finish_reason": {"type": ["string", "null"]},
                    # usage só foi observado no gateway (chunk final); o proxy
                    # não manda nem com stream_options.include_usage → opcional.
                    "usage": {"type": ["object", "null"]},
                },
            },
        },
    },
}

SCHEMA_EMBEDDINGS: dict = {
    "type": "object",
    # SEM "id" no required: medido — só o gateway devolve id (armadilha do
    # cold-start). object/model podem faltar no proxy? Não: ambos observados.
    "required": ["object", "data", "model", "usage"],
    "properties": {
        "object": {"const": "list"},
        "model": {"type": "string"},
        "data": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "required": ["index", "object", "embedding"],
                "properties": {
                    "index": _INT_NOT_BOOL,
                    "object": {"const": "embedding"},
                    "embedding": {
                        "type": "array", "minItems": 1,
                        "items": {"type": "number"},
                    },
                },
            },
        },
        "usage": {
            "type": "object",
            # gateway devolve só {prompt_tokens,total_tokens} (medido) →
            # completion_tokens NÃO pode ser required aqui.
            "required": ["prompt_tokens", "total_tokens"],
            "properties": {
                "prompt_tokens": _INT_NOT_BOOL,
                "total_tokens": _INT_NOT_BOOL,
            },
        },
    },
}

SCHEMA_IMAGES: dict = {
    "type": "object",
    # created/data conformam nos dois alvos. usage NÃO entra no schema: o
    # gateway devolve {total_tokens} e o proxy {input_tokens,...} — shapes
    # incompatíveis entre si; registrar como divergência, não reprovar.
    "required": ["created", "data"],
    "properties": {
        "created": _INT_NOT_BOOL,
        "data": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                # anyOf (não oneOf): OpenAI ImagesResponse exige OU url OU
                # b64_json por item — e o proxy real manda AMBOS (medido).
                # anyOf aceita os três casos; oneOf reprovaria o proxy.
                "anyOf": [
                    {"required": ["url"],
                     "properties": {"url": {"type": "string"}}},
                    {"required": ["b64_json"],
                     "properties": {"b64_json": {"type": "string"}}},
                ],
            },
        },
    },
}

SCHEMA_MODELS: dict = {
    "type": "object",
    "required": ["object", "data"],
    "properties": {
        "object": {"const": "list"},
        "data": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                # created NÃO é required: gateway não devolve (medido).
                "required": ["id", "object"],
                "properties": {
                    "id": {"type": "string"},
                    "object": {"const": "model"},
                },
            },
        },
    },
}

SCHEMA_ERROR_OPENAI: dict = {
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["message", "type"],
            "properties": {
                "message": {"type": "string"},
                "type": {"type": "string"},
                # param/code chegam null em casos reais (medido no proxy) →
                # nullable, não required.
                "param": {"type": ["string", "null"]},
                "code": {"type": ["string", "integer", "null"]},
            },
        },
    },
}

SCHEMA_ERROR_FASTAPI: dict = {
    "type": "object",
    "required": ["detail"],
    "properties": {
        "detail": {"type": ["string", "object", "array"]},
    },
}

# Mapeamento endpoint → schema (modo A/B usam a mesma fonte — nada duplicado).
SCHEMAS: dict[str, dict] = {
    "chat.completion": SCHEMA_CHAT_COMPLETION,
    "embeddings": SCHEMA_EMBEDDINGS,
    "images.generation": SCHEMA_IMAGES,
    "models.list": SCHEMA_MODELS,
    "error.openai": SCHEMA_ERROR_OPENAI,
}


def validate_payload(payload: dict, schema: dict) -> list[str]:
    """Violações de schema como strings legíveis (vazio = conforme).

    Puro; ordenação estável do jsonschema (ordem das propriedades do schema).
    Nunca proíbe campo extra (extra="allow", armadilha 3).
    """
    validator = jsonschema.Draft202012Validator(schema)
    errs = []
    for e in sorted(validator.iter_errors(payload),
                    key=lambda x: list(x.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "<raiz>"
        errs.append(f"{loc}: {e.message}"[:200])
    return errs


# ---------------------------------------------------------------------------
# Vereditores puros por endpoint (modo A) — testáveis sem rede
# ---------------------------------------------------------------------------


def verdict_chat_completion(payload: dict) -> tuple[bool, str]:
    errs = validate_payload(payload, SCHEMA_CHAT_COMPLETION)
    if errs:
        return False, "; ".join(errs[:3])
    return True, "conforme chat.completion (OpenAI)"


def verdict_chunks(raw_text: str) -> tuple[bool, str]:
    """Valida TODO chunk ``data:`` de um corpo SSE contra chat.completion.chunk.

    Usa o parser tolerante do harness (``parse_sse_lines``) — framing \n vs
    \n\n é problema do S103, aqui interessa o SHAPE de cada objeto.
    """
    info = parse_sse_lines(raw_text)
    total = 0
    errs: list[str] = []
    for p in info["payloads"]:
        if p == "[DONE]":
            continue
        try:
            obj = json.loads(p)
        except ValueError:
            errs.append(f"<payload>: JSON inválido: {p[:60]!r}")
            continue
        total += 1
        got = validate_payload(obj, SCHEMA_CHUNK)
        if got:
            errs.append(got[0])
    if not info["done"]:
        errs.append("<fluxo>: faltou [DONE]")
    if total == 0:
        errs.append("<fluxo>: nenhum chunk JSON")
    if errs:
        return False, f"chunks={total} :: " + "; ".join(errs[:3])
    return True, f"conforme chat.completion.chunk ({total} chunks + [DONE])"


def verdict_embeddings(payload: dict) -> tuple[bool, str]:
    errs = validate_payload(payload, SCHEMA_EMBEDDINGS)
    if errs:
        return False, "; ".join(errs[:3])
    dim = len(payload["data"][0]["embedding"])
    return True, f"conforme embeddings (dim={dim})"


def verdict_images(payload: dict) -> tuple[bool, str]:
    errs = validate_payload(payload, SCHEMA_IMAGES)
    if errs:
        return False, "; ".join(errs[:3])
    item = payload["data"][0]
    kind = "url" if "url" in item else "b64_json"
    return True, f"conforme images (item0 via {kind})"


def verdict_models(payload: dict) -> tuple[bool, str]:
    errs = validate_payload(payload, SCHEMA_MODELS)
    if errs:
        return False, "; ".join(errs[:3])
    return True, f"conforme models list (n={len(payload['data'])})"


# Divergência documentada (armadilha 1): o gateway devolve FastAPI {"detail"}.
DIVERGED = "diverged"


def verdict_error(status_code: int, body: dict, target: str
                  ) -> tuple[bool | str, str]:
    """Contrato de erro ciente do alvo.

    - ``proxy``: exige envelope OpenAI (``error.{message,type}``).
    - ``gateway``: aceita FastAPI ``detail`` → retorna ``DIVERGED`` (achado
      documentado, não falha); se vier OpenAI mesmo assim, conta como conforme.
    """
    if not isinstance(body, dict):
        return False, f"corpo de erro não é objeto ({type(body).__name__})"
    openai_errs = validate_payload(body, SCHEMA_ERROR_OPENAI)
    if not openai_errs:
        msg = body["error"]["message"][:60]
        return True, f"OpenAI error shape (HTTP {status_code}): {msg!r}"
    fastapi_errs = validate_payload(body, SCHEMA_ERROR_FASTAPI)
    if not fastapi_errs:
        if target == "gateway":
            detail = body["detail"]
            text = detail if isinstance(detail, str) else json.dumps(detail)
            return DIVERGED, (f"FastAPI {{detail}} no gateway (HTTP "
                              f"{status_code}) — divergência documentada: "
                              f"{str(text)[:60]!r}")
        return False, ("gateway-shape {'detail'} no PROXY (esperado OpenAI "
                       f"error): {'; '.join(openai_errs[:2])}")
    return False, (f"sem envelope OpenAI nem FastAPI: "
                   f"{'; '.join(openai_errs[:2])} | "
                   f"{'; '.join(fastapi_errs[:2])}")


# ---------------------------------------------------------------------------
# Resultado de um check de contrato
# ---------------------------------------------------------------------------


@dataclass
class ContractResult:
    """Veredito de shape de UM endpoint num ALVO. status ∈ {pass,fail,diverged,skipped}."""

    endpoint: str
    target: str
    model: str
    status: str
    evidence: str
    latency_ms: float | None = None
    violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


# ---------------------------------------------------------------------------
# Modo B — live: orquestra sender + vereditores puros
# ---------------------------------------------------------------------------

CHAT_BODY = {"messages": [{"role": "user", "content": "Diga apenas: OK"}],
             "max_tokens": 512}


def run_live_endpoint(  # pragma: no cover - transporte live
    sender: Sender, spec: EndpointSpec, target: str) -> ContractResult:
    """Chama o endpoint de verdade e valida o SHAPE da resposta."""
    model = CHAT_MODEL[target] if spec.uses_model else ""
    t0 = time.monotonic()
    body: dict | None = None
    if spec.method == "POST":
        if spec.id == "chat.completion":
            body = {"model": model, **CHAT_BODY}
        elif spec.id == "chat.completion.chunk":
            body = {"model": model, "stream": True, **CHAT_BODY}
        elif spec.id == "embeddings":
            body = {"model": EMBED_MODEL[target], "input": "texto de teste"}
        elif spec.id == "images.generation":
            body = {"model": IMAGE_MODEL[target], "prompt": "um gato",
                    "n": 1, "size": "1024x1024"}
        elif spec.id == "error.openai":
            body = {"model": BAD_MODEL[target],
                    "messages": [{"role": "user", "content": "x"}]}
    stream = spec.id == "chat.completion.chunk"
    try:
        if spec.method == "GET":
            resp = sender(spec.path, method="GET")
        else:
            resp = sender(spec.path, json_body=body, stream=stream)
    except TypeError:
        # sender fake sem suporte a method= (testes offline) — refaz sem kwarg.
        resp = sender(spec.path, json_body=body, stream=stream)
    lat = _elapsed_ms(t0)
    err = getattr(resp, "error", "") or ""
    if err:
        return ContractResult(spec.id, target, model, "fail",
                              f"transport: {err}", latency_ms=lat)
    status_code = resp.status_code
    if spec.id == "error.openai":
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        ok, ev = verdict_error(status_code, payload or {}, target)
        status = ("pass" if ok is True else
                  DIVERGED if ok == DIVERGED else "fail")
        return ContractResult(spec.id, target, model, status, ev, latency_ms=lat)
    if status_code != 200:
        return ContractResult(spec.id, target, model, "fail",
                              f"HTTP {status_code}: {resp.text[:120]}",
                              latency_ms=lat)
    if spec.id == "chat.completion.chunk":
        ok, ev = verdict_chunks(resp.text)
        return ContractResult(spec.id, target, model,
                              "pass" if ok else "fail", ev, latency_ms=lat)
    payload = resp.json()
    fn = {
        "chat.completion": verdict_chat_completion,
        "embeddings": verdict_embeddings,
        "images.generation": verdict_images,
        "models.list": verdict_models,
    }[spec.id]
    ok, ev = fn(payload)
    r = ContractResult(spec.id, target, model, "pass" if ok else "fail", ev,
                       latency_ms=lat)
    if not ok:
        r.violations = ev.split("; ")
    return r


def run_live_suite(target: str, *, sender: Sender | None = None,
                   sleep_s: float = 0.0,
                   endpoints: tuple[EndpointSpec, ...] = ENDPOINTS
                   ) -> list[ContractResult]:
    """Roda todos os endpoints contra um alvo, em ordem canônica."""
    out: list[ContractResult] = []
    for i, spec in enumerate(endpoints):
        if sender is None:
            out.append(ContractResult(spec.id, target, "", "skipped",
                                      "modo dry (use --live)"))
            continue
        if sleep_s > 0 and i > 0:
            time.sleep(sleep_s)
        out.append(run_live_endpoint(sender, spec, target))
    return out


# ---------------------------------------------------------------------------
# Tabela de conformidade por grupo (proxy × gateway)
# ---------------------------------------------------------------------------

CONFORME = "✅"
DIVERGENTE = "⚠️"
NAO_CONFORME = "❌"
AUSENTE = "—"


def conformance_mark(results: list[ContractResult]) -> str:
    """Uma célula da tabela: fail > diverged > pass > skipped (nesta ordem)."""
    statuses = {r.status for r in results}
    if "fail" in statuses:
        return NAO_CONFORME
    if DIVERGED in statuses:
        return DIVERGENTE
    if "pass" in statuses:
        return CONFORME
    return AUSENTE


def conformance_table(results: list[ContractResult]) -> list[list[str]]:
    """Tabela determinística: linhas = endpoints (ordem ENDPOINTS), colunas = alvos.

    Uma célula ``⚠️`` significa: ao menos um alvo divergiu (achado documentado,
    ex.: FastAPI ``detail`` no gateway). ``❌`` = violação real de shape.
    """
    targets = list(TARGETS)
    header = ["endpoint", *targets, "veredito"]
    rows = [header]
    by_ep: dict[str, dict[str, list[ContractResult]]] = {}
    for r in results:
        by_ep.setdefault(r.endpoint, {}).setdefault(r.target, []).append(r)
    for spec in ENDPOINTS:
        cols = by_ep.get(spec.id, {})
        cells = [conformance_mark(cols.get(t, [])) for t in targets]
        all_r = [x for lst in cols.values() for x in lst]
        rows.append([spec.id, *cells, conformance_mark(all_r)])
    return rows


# ---------------------------------------------------------------------------
# Relatório datado (markdown)
# ---------------------------------------------------------------------------


def build_report(results: list[ContractResult], *, when: date | None = None,
                 title: str = "S117 — Contrato de API NovAI (shape OpenAI)"
                 ) -> str:
    when = when or date.today()
    lines = [f"# {title}", "",
             f"Data: **{when.isoformat()}** · checks: {len(results)}", ""]
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    lines.append("## resumo")
    lines.append("")
    for st in ("pass", DIVERGED, "fail", "skipped"):
        if st in counts:
            lines.append(f"- `{st}`: {counts[st]}")
    lines.append("")
    lines.append("## conformidade por endpoint × alvo")
    lines.append("")
    table = conformance_table(results)
    lines.append("| " + " | ".join(table[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in table[0]) + " |")
    for row in table[1:]:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## checks")
    lines.append("")
    lines.append("| endpoint | alvo | modelo | status | latência | evidência |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for r in results:
        lat = "" if r.latency_ms is None else f"{r.latency_ms:.0f} ms"
        lines.append(f"| {r.endpoint} | {r.target} | {r.model or '—'} "
                     f"| {r.status} | {lat} | {r.evidence} |")
    diverged = [r for r in results if r.status == DIVERGED]
    if diverged:
        lines += ["", "## divergências documentadas", ""]
        for r in diverged:
            lines.append(f"- **{r.endpoint} @ {r.target}**: {r.evidence}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Modo C — SDK real openai-python (opt-in; skipif quando ausente)
# ---------------------------------------------------------------------------


def sdk_available() -> bool:
    """True se o pacote ``openai`` está instalado (modo C é opt-in)."""
    return importlib.util.find_spec("openai") is not None


def run_sdk_check(  # pragma: no cover - modo C opt-in com SDK real
    cfg: dict, model: str) -> ContractResult:
    """Round-trip com o SDK real: se ``ChatCompletion.model_validate`` passa,

    o shape é compatível com o cliente tipado que os agentes usam. Retorna
    ``skipped`` quando o SDK não está instalado (nunca falha por ausência).
    """
    if not sdk_available():
        return ContractResult("sdk.chat.completion", "proxy", model, "skipped",
                              "pacote 'openai' não instalado (modo C opt-in)")
    from openai import OpenAI

    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    t0 = time.monotonic()
    try:
        completion = client.chat.completions.create(
            model=model, messages=[{"role": "user",
                                    "content": "Diga apenas: OK"}],
            max_tokens=512)
    except Exception as exc:  # noqa: BLE001 — achado é dado
        return ContractResult("sdk.chat.completion", "proxy", model, "fail",
                              f"sdk raised: {type(exc).__name__}: {exc}"[:180],
                              latency_ms=_elapsed_ms(t0))
    # O SDK já validou no parse; checagem explícita de tipos dos required:
    need = [(completion.id, str), (completion.object, str),
            (completion.created, int), (completion.model, str)]
    bad = [f"{v!r} não é {t.__name__}" for v, t in need
           if not isinstance(v, t)]
    if bad or not completion.choices or not isinstance(
            completion.choices[0].message.content, str):
        return ContractResult("sdk.chat.completion", "proxy", model, "fail",
                              "; ".join(bad) or "choices/message.content aus.",
                              latency_ms=_elapsed_ms(t0))
    return ContractResult("sdk.chat.completion", "proxy", model, "pass",
                          "openai-python parseou ChatCompletion",
                          latency_ms=_elapsed_ms(t0))


# ---------------------------------------------------------------------------
# Runner + CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI live
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true",
                    help="faz as chamadas reais (custa tokens)")
    ap.add_argument("--target", default="proxy",
                    choices=list(TARGETS) + ["both"],
                    help="alvo: gateway (NovAI direto) | proxy (LiteLLM) | both")
    ap.add_argument("--endpoint", help="roda só um endpoint (id de --list)")
    ap.add_argument("--sdk", action="store_true",
                    help="modo C: round-trip com o SDK openai real (só proxy)")
    ap.add_argument("--list-endpoints", action="store_true",
                    help="imprime os endpoints exercitados (offline)")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="pausa entre calls live (rate limit 60 rpm)")
    ap.add_argument("--out", help="grava o relatório markdown aqui")
    args = ap.parse_args(argv)

    if args.list_endpoints:
        for spec in ENDPOINTS:
            print(f"{spec.id:24s} {spec.method:4s} {spec.path:22s} {spec.doc}")
        return 0

    specs = ENDPOINTS
    if args.endpoint:
        specs = (endpoint_by_id(args.endpoint),)

    results: list[ContractResult] = []
    for target in resolve_targets(args.target):
        if not args.live:
            results.extend(run_live_suite(target, sender=None,
                                          endpoints=specs))
            continue
        cfg = target_config(target)
        sender = make_capturing_sender(cfg, {})
        results.extend(run_live_suite(target, sender=sender, sleep_s=args.sleep,
                                      endpoints=specs))
    if args.sdk:
        results.append(run_sdk_check(proxy_config(), CHAT_MODEL["proxy"]))

    if not args.live and not args.sdk:
        print("# modo dry — use --live para exercitar os endpoints de verdade")
    md = build_report(results)
    print(md)
    out = args.out
    if out is None and args.live:
        out = str(REPORT_DEFAULT_DIR /
                  f"{date.today():%Y-%m-%d}-novai-contrato-api.md")
    if out:
        Path(out).write_text(md, encoding="utf-8")
        print(f"# relatório gravado em {out}", file=sys.stderr)
    bad = [r for r in results if r.status == "fail"]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
