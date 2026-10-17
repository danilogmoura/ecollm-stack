"""S102 — Harness de smoke por modalidade contra o proxy LiteLLM (:4000).

Testa as rotas ``novai-*`` DE PONTA A PONTA através do NOSSO proxy (não só "o
upstream responde"): chat (texto/stream/thinking/tool), embeddings, image, tts,
asr e os passthrough video/3d. Cada teste devolve um ``CheckResult`` com
``passed`` + evidência; a planilha-mãe (``reports/novai-test-matrix.csv``) é
preenchida com status/evidência.

DESIGN (mesmo padrão de ``ingest/embed.py`` e ``eval/mcp_report.py``):
  - funções PURAS de verificação (``verdict_chat`` etc.) → testáveis SEM rede;
  - transport injetável (``sender``) → testes unitários sem tocar :4000;
  - só chama rede quando ``--live`` for passado (respeita saldo ≈ $0).

Uso:
    .venv/bin/python -m eval.novai_test --list                 # inventário (offline)
    .venv/bin/python -m eval.novai_test --family embed [--live]
    .venv/bin/python -m eval.novai_test --id novai-glm-4.6 --live
    .venv/bin/python -m eval.novai_test --all --live --out reports/novai-run.md
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

# load_dotenv é a função LOCAL de ingest.embed (mínima, sem dependência externa),
# não o pacote python-dotenv — seguir o padrão canônico da casa.
from ingest.embed import load_dotenv

from . import novai_inventory as inv
from .novai_enrich import redact_signed_urls

# ---------------------------------------------------------------------------
# Config do proxy (lê .env, mesmo padrão de ingest/embed.py)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:4000/v1"
MATRIX_CSV = Path("reports/novai-test-matrix.csv")
# S103 / P3: colunas opcionais da matriz. Se existirem no header, são preenchidas;
# se não existirem (matriz Fase A), o update_matrix ignora — formato antigo intacto.
MATRIX_EXTRA_COLUMNS = ("target", "test_id", "latency_ms", "notes")

# S103 / P2 — alvos. O gateway é o upstream DIRETO (isola o LiteLLM); o proxy é
# o caminho real do agente. Divergência entre os dois classifica o bug.
GATEWAY_BASE_URL = "https://aiapi-pro.com/v1"
TARGETS = ("gateway", "proxy")


def proxy_config() -> dict:
    """Base URL + master key do proxy, lidas do ambiente (.env no repo root)."""
    load_dotenv()
    return {
        "base_url": os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "api_key": os.environ.get("LITELLM_MASTER_KEY", ""),
    }


def gateway_config() -> dict:
    """Base URL + chave do gateway NovAI direto (``NOVAI_API_KEY``).

    ``NOVAI_BASE_URL`` é opcional (default = ``https://aiapi-pro.com/v1``, a URL
    fixa do ``config.yaml``); existe só para apontar a um espelho em testes.
    """
    load_dotenv()
    return {
        "base_url": os.environ.get("NOVAI_BASE_URL", GATEWAY_BASE_URL).rstrip("/"),
        "api_key": os.environ.get("NOVAI_API_KEY", ""),
    }


def target_config(target: str) -> dict:
    """Config do alvo pedido (``gateway`` | ``proxy``)."""
    if target == "gateway":
        return gateway_config()
    if target == "proxy":
        return proxy_config()
    raise ValueError(f"alvo desconhecido: {target!r} (use gateway|proxy)")


def resolve_targets(target: str) -> list[str]:
    """Expande ``--target`` em lista de alvos concretos, na ordem canônica."""
    if target == "both":
        return list(TARGETS)
    if target not in TARGETS:
        raise ValueError(f"--target inválido: {target!r} (gateway|proxy|both)")
    return [target]


# ---------------------------------------------------------------------------
# Resultado de um check
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Veredito de um smoke: passed + evidência legível + custo opcional."""

    group: str
    modality: str
    test: str
    passed: bool
    evidence: str
    skipped: bool = False
    cost_usd: float | None = None
    # S103 / P2–P3: alvo medido, latência e nota livre (colunas novas da matriz).
    target: str = "proxy"
    latency_ms: float | None = None
    notes: str = ""
    # S103 / P3b: captura bruta para o jsonl (spec §12). Tudo passa por redact()
    # antes de ir ao disco; aqui fica o valor já sanitizado.
    request: dict | None = None
    headers: dict | None = None
    body_raw: str = ""
    sse_framing: str = ""
    error: str = ""

    def status(self) -> str:
        if self.skipped:
            return "skipped"
        return "pass" if self.passed else "fail"


# ---------------------------------------------------------------------------
# S103 / P2 — classificador de divergência gateway × proxy
# ---------------------------------------------------------------------------

DIVERGENCE_CLASSES = {
    "same_pass": "ambos passam ⇒ comportamento do gateway NovAI",
    "same_fail": "ambos falham ⇒ bug do gateway NovAI (não é o LiteLLM)",
    "divergent": "um passa e o outro falha ⇒ bug do LiteLLM (nosso)",
    "gateway_only": "só o gateway passou ⇒ bug do LiteLLM (nosso)",
    "proxy_only": "só o proxy passou ⇒ bug do gateway NovAI",
    "incomplete": "faltou um dos alvos ⇒ não classifica",
}


def classify_divergence(gateway: CheckResult | None,
                        proxy: CheckResult | None) -> tuple[str, str]:
    """Classifica o par (gateway, proxy) do MESMO teste.

    Regra travada (S103): **divergência ⇒ bug LiteLLM; igualdade ⇒ bug NovAI.**
    ``skipped`` conta como ausência de evidência (não como pass/fail).
    """
    def _state(r: CheckResult | None) -> str:
        if r is None or r.skipped:
            return "missing"
        return "pass" if r.passed else "fail"

    g, p = _state(gateway), _state(proxy)
    ev = f"gateway={g} proxy={p}"
    if "missing" in (g, p):
        return "incomplete", ev
    if g == p == "pass":
        return "same_pass", ev
    if g == p == "fail":
        return "same_fail", ev
    if g == "pass":
        return "gateway_only", ev
    return "proxy_only", ev


def divergence_is_ours(cls: str) -> bool:
    """True quando a divergência aponta para o NOSSO LiteLLM (bug nosso)."""
    return cls in ("divergent", "gateway_only")


def pair_results_by_test(results: list[CheckResult]) -> dict[tuple[str, str],
                                                             dict[str, CheckResult]]:
    """Agrupa resultados por ``(group, test)`` → ``{target: CheckResult}``.

    Ordem determinística (dict de inserção preserva a ordem de entrada) — não
    reordenar ao citar (invariante de prompt-cache).
    """
    out: dict[tuple[str, str], dict[str, CheckResult]] = {}
    for r in results:
        out.setdefault((r.group, r.test), {})[r.target] = r
    return out


def classify_all(results: list[CheckResult]) -> list[tuple[str, str, str]]:
    """Classifica todos os pares de um run ``--target both``.

    Retorna ``[(group, test, classe)]`` na ordem de primeira aparição.
    """
    out: list[tuple[str, str, str]] = []
    for (group, test), by_target in pair_results_by_test(results).items():
        cls, _ = classify_divergence(by_target.get("gateway"), by_target.get("proxy"))
        out.append((group, test, cls))
    return out


# ---------------------------------------------------------------------------
# Funções PURAS de verificação (sem rede) — cada uma decide passed/evidence
# ---------------------------------------------------------------------------


def verdict_chat(resp: dict) -> tuple[bool, str]:
    """chat/completions não-stream: 200-shape + content não-vazio + finish_reason."""
    try:
        choice = resp["choices"][0]
    except (KeyError, IndexError):
        return False, f"sem choices: {str(resp)[:120]}"
    msg = choice.get("message", {}) or {}
    content = (msg.get("content") or "").strip()
    finish = choice.get("finish_reason")
    if not content:
        # thinking ON pode consumir todo o orçamento → finish=length, NÃO é rota morta.
        return False, f"content vazio (finish={finish})"
    return True, f"finish={finish} len(content)={len(content)}"


def verdict_thinking_on(resp: dict) -> tuple[bool, str]:
    """thinking ON: reasoning_content presente OU reasoning_tokens > 0."""
    msg = (resp.get("choices") or [{}])[0].get("message", {}) or {}
    reasoning = (msg.get("reasoning_content") or "").strip()
    usage = resp.get("usage", {}) or {}
    det = usage.get("completion_tokens_details", {}) or {}
    rtok = det.get("reasoning_tokens", 0) or 0
    if reasoning or rtok > 0:
        return True, f"reasoning_chars={len(reasoning)} reasoning_tokens={rtok}"
    return False, "sem reasoning (esperado ON)"


def verdict_thinking_off(resp: dict) -> tuple[bool, str]:
    """thinking OFF (-fast): reasoning≈0 (ausente ou 0 tokens)."""
    msg = (resp.get("choices") or [{}])[0].get("message", {}) or {}
    reasoning = (msg.get("reasoning_content") or "").strip()
    usage = resp.get("usage", {}) or {}
    det = usage.get("completion_tokens_details", {}) or {}
    rtok = det.get("reasoning_tokens", 0) or 0
    content = (msg.get("content") or "").strip()
    if content and not reasoning and rtok == 0:
        return True, f"no-reasoning OK len(content)={len(content)}"
    return False, f"reasoning_chars={len(reasoning)} reasoning_tokens={rtok}"


def extract_reasoning(resp: dict) -> tuple[int, int]:
    """Extrai (chars de reasoning_content, reasoning_tokens) de uma resposta chat.

    Soma reasoning_tokens das duas posições em que o LiteLLM pode reportá-lo
    (``completion_tokens_details`` e ``output_tokens_details``), para não
    subcontar modelos que só preenchem uma delas. Função PURA — base do sonda
    de thinking (``verdict_thinking_sense`` / ``run_thinking_probe``).
    """
    msg = (resp.get("choices") or [{}])[0].get("message", {}) or {}
    chars = len((msg.get("reasoning_content") or "").strip())
    usage = resp.get("usage", {}) or {}
    det = usage.get("completion_tokens_details", {}) or {}
    odet = usage.get("output_tokens_details", {}) or {}
    tok = int(det.get("reasoning_tokens", 0) or 0) + int(odet.get("reasoning_tokens", 0) or 0)
    return chars, tok


def verdict_thinking_sense(on_resp: dict, off_resp: dict) -> tuple[str, str]:
    """Classifica se a dualidade thinking-ON/OFF *realmente faz sentido* num modelo.

    Recebe as respostas cruas dos dois modos (base=ON sem extra_body; -fast=OFF com
    ``thinking:{type:disabled}``) e decide por evidência medida, não pela convenção
    declarada no config. Categorias (fail-closed — nunca inventa capability):

      - ``nao-suporta``  : ON e OFF idênticos (ambos reasoning==0) → flag não tem
                           efeito; ter rota -fast separada é redundante.
      - ``so-on``        : ON tem reasoning mas OFF NÃO zera → alavanca OFF não
                           funciona aqui; só o modo ON é distinto.
      - ``so-off``       : OFF tem reasoning mas ON não → comportamento invertido
                           (upstream default ligado); sinalizar para revisar.
      - ``funciona``     : ON>0 e OFF==0 → thinking real E desligável → dual faz sentido.
      - ``erro``         : qualquer lado sem shape válido de choices.

    Retorna ``(categoria, evidencia)``.
    """
    on_c, on_t = extract_reasoning(on_resp)
    off_c, off_t = extract_reasoning(off_resp)

    def _valid(resp: dict) -> bool:
        choices = resp.get("choices")
        return bool(choices) and isinstance(choices[0], dict) \
            and isinstance(choices[0].get("message"), dict)

    ev = f"ON(chars={on_c},tok={on_t}) OFF(chars={off_c},tok={off_t})"
    if not _valid(on_resp) or not _valid(off_resp):
        return "erro", ev + " [sem choices]"
    on_has = on_c > 0 or on_t > 0
    off_has = off_c > 0 or off_t > 0
    if on_has and not off_has:
        return "funciona", ev
    if not on_has and not off_has:
        return "nao-suporta", ev
    if on_has and off_has:
        return "so-on", ev
    return "so-off", ev


def verdict_tool_calls(resp: dict) -> tuple[bool, str]:
    """tool-calling: finish_reason=tool_calls + arguments JSON parseável."""
    choice = (resp.get("choices") or [{}])[0]
    finish = choice.get("finish_reason")
    tcs = (choice.get("message", {}) or {}).get("tool_calls") or []
    if finish != "tool_calls" or not tcs:
        return False, f"finish={finish} n_tool_calls={len(tcs)}"
    try:
        json.loads(tcs[0]["function"]["arguments"])
    except (KeyError, ValueError):
        return False, "arguments não-JSON"
    return True, f"tool={tcs[0]['function'].get('name')} args_json_ok"


def split_sse_events(raw_text: str) -> list[str]:
    """Corta um corpo SSE em eventos por '\\n\\n' (regra travada S41/S42)."""
    return [chunk for chunk in raw_text.split("\n\n") if chunk.strip()]


def parse_sse_lines(raw_text: str) -> dict:
    """Parser SSE TOLERANTE a ambos os framings (conforme WHATWG e o gateway NovAI).

    O gateway NovAI emite eventos separados por UM '\\n' em vez do blank line
    '\\n\\n' exigido pela spec (bug documentado em
    ``reports/2026-10-14-novai-sse-streaming.md``). Um parser estrito colapsa tudo
    num único evento multi-linha e morre em ``json.loads`` com 'Extra data'. Este
    parser trata cada linha ``data:`` como um evento próprio, então funciona nos
    DOIS framings e ainda MEDIE qual o gateway usou.

    Retorna dict com:
      payloads   : lista dos strings após 'data:' (inclui '[DONE]' se presente)
      json_ok    : nº de payloads JSON-parseáveis
      json_bad   : nº de payloads NÃO-parseáveis (exclui '[DONE]')
      done       : True se algum payload == '[DONE]'
      sep_blank  : nº de terminadores '\\n\\n' entre eventos (framing CONFORME)
      sep_single : nº de terminadores '\\n' simples entre eventos (framing BUGADO)
    """
    payloads: list[str] = []
    for line in raw_text.splitlines():
        s = line.strip()
        if s.startswith("data:"):
            payloads.append(s[len("data:"):].strip())
    json_ok = 0
    json_bad = 0
    done = False
    for p in payloads:
        if p == "[DONE]":
            done = True
            continue
        try:
            json.loads(p)
            json_ok += 1
        except ValueError:
            json_bad += 1
    # Medição de framing sobre o texto bruto (independente do parsing tolerante).
    # Um evento CONFORME termina com blank line; no wire isso aparece como o
    # terminador '\\n\\n' (antes do próximo 'data:' ou antes de EOF). Contamos
    # terminadores, não ocorrências de '}\ndata:' — assim um único evento grande
    # (ex.: [DONE] isolado) também é medido corretamente.
    sep_blank = raw_text.count("\n\n")
    n_data = len(payloads)
    # Eventos sem blank line entre si = '\\n' simples (framing bugado/regressão).
    sep_single = max(0, (n_data - 1) - sep_blank) if n_data > 1 else 0
    return {"payloads": payloads, "json_ok": json_ok, "json_bad": json_bad,
            "done": done, "sep_blank": sep_blank, "sep_single": sep_single}


def assemble_stream_text(payloads: list[str]) -> str:
    """Concatena ``choices[].delta.content`` dos chunks SSE (monta a resposta real)."""
    out: list[str] = []
    for p in payloads:
        if p == "[DONE]":
            continue
        try:
            obj = json.loads(p)
        except ValueError:
            continue
        for ch in obj.get("choices") or []:
            piece = ((ch.get("delta") or {}).get("content")) or ""
            if piece:
                out.append(piece)
    return "".join(out)


def verdict_stream(events: list[str]) -> tuple[bool, str]:
    """streaming: ≥1 evento 'data:' JSON válido + marcador [DONE]."""
    data_lines = [e for e in events if e.startswith("data:")]
    parsed = 0
    bad = 0
    done = False
    for e in data_lines:
        payload = e[len("data:"):].strip()
        if payload == "[DONE]":
            done = True
            continue
        try:
            json.loads(payload)
            parsed += 1
        except ValueError:
            bad += 1
    ok = parsed >= 1 and done and bad == 0
    return ok, f"events_data={len(data_lines)} parsed={parsed} bad={bad} done={done}"


def verdict_stream_strong(info: dict, *, expect_substr: str | None = None
                          ) -> tuple[bool, str]:
    """Veredito SSE FORTALECIDO: valida payload E diagnostica o framing do gateway.

    Passa somente se: ≥1 chunk JSON válido + [DONE] presente + zero JSON inválido
    (+ substring esperada no texto montado, quando pedida). Quando falha por
    payload, diz exatamente o quê; quando o payload está OK mas o framing é
    bugado ('\\n' simples sem '\\n\\n'), marca explicitamente o bug NovAI na
    evidência — para não confundir 'gateway devolve lixo' com 'gateway devolve
    JSON bom mas não-conforme'.
    """
    assembled = assemble_stream_text(info["payloads"])
    base = (f"chunks_json={info['json_ok']} bad={info['json_bad']} "
            f"done={info['done']} text_len={len(assembled)} "
            f"framing(blank={info['sep_blank']},single={info['sep_single']})")
    if info["json_bad"] > 0:
        return False, f"{base} :: {info['json_bad']} chunk(s) JSON inválido"
    if info["json_ok"] < 1:
        return False, f"{base} :: nenhum chunk JSON"
    if not info["done"]:
        return False, f"{base} :: faltou [DONE]"
    if not assembled.strip():
        return False, f"{base} :: texto montado vazio"
    if expect_substr is not None and expect_substr.lower() not in assembled.lower():
        return False, f"{base} :: esperado {expect_substr!r} ausente no texto"
    # Payload íntegro; agora checa CONFORMIDADE do framing (padrão corrigido NovAI).
    # Desde 2026-10 reportado→resolvido pela NovAI: eventos DEVEM vir separados por
    # blank line (\n\n). '\\n' simples entre eventos = REGRESSÃO do bug antigo.
    if info["sep_single"] > 0 and info["sep_blank"] == 0:
        return False, (f"{base} :: FRAMING NAO-CONFORME — eventos sep. por \\n "
                       f"simples sem \\n\\n (REGRESSÃO do bug NovAI já corrigido)")
    if info["sep_blank"] == 0 and len(info["payloads"]) > 1:
        return False, f"{base} :: sem \\n\\n entre eventos (framing ausente)"
    return True, f"{base} :: texto={assembled[:40]!r}"


def verdict_embeddings(resp: dict, expected_dim: int | None = None) -> tuple[bool, str]:
    """/embeddings: data[0].embedding lista numérica (+ dim se esperada)."""
    try:
        emb = resp["data"][0]["embedding"]
    except (KeyError, IndexError):
        return False, f"sem data[].embedding: {str(resp)[:120]}"
    if not isinstance(emb, list) or not emb:
        return False, "embedding vazio"
    dim = len(emb)
    if expected_dim is not None and dim != expected_dim:
        return False, f"dim={dim} esperado={expected_dim}"
    return True, f"dim={dim}"


def verdict_image(resp: dict) -> tuple[bool, str]:
    """/images/generations: b64_json decodificável OU url http(s)."""
    items = resp.get("data") or []
    if not items:
        return False, f"sem data[]: {str(resp)[:120]}"
    item = items[0]
    if item.get("b64_json"):
        try:
            raw = base64.b64decode(item["b64_json"])
            return len(raw) > 0, f"b64 bytes={len(raw)}"
        except Exception as exc:  # noqa: BLE001
            return False, f"b64 inválido: {exc}"
    url = item.get("url") or ""
    if url.startswith(("http://", "https://")):
        return True, f"url={url[:80]}"
    return False, "sem b64_json nem url"


def verdict_audio(content: bytes) -> tuple[bool, str]:
    """/audio/speech: bytes não-vazios + header plausível (RIFF/ID3/ftyp/Ogg)."""
    if not content:
        return False, "0 bytes"
    head = content[:12]
    magic = {
        b"RIFF": "wav",
        b"ID3": "mp3(id3)",
        b"\xff\xfb": "mp3",
        b"OggS": "ogg",
    }.get(head[:4], None)
    if magic is None and head[4:8] == b"ftyp":
        magic = "mp4"
    if magic:
        return True, f"{magic} bytes={len(content)}"
    return len(content) > 1000, f"bytes={len(content)} header={head!r}"


def verdict_asr(resp: dict) -> tuple[bool, str]:
    """/audio/transcriptions: campo 'text' não-vazio."""
    text = (resp.get("text") or "").strip()
    if text:
        return True, f"text_len={len(text)}"
    return False, f"sem text: {str(resp)[:120]}"


# S103 / Fase G (T22) — vision/OCR. Cores aceitas por fixture (PT + EN + zh).
VISION_COLORS = {
    "red": ("vermelh", "red", "红"),
    "blue": ("azul", "blue", "蓝"),
}


def verdict_vision(resp: dict, expected_color: str) -> tuple[bool, str]:
    """T22 — vision/OCR: a resposta descreve a cor esperada da imagem.

    Puro. Aceita PT/EN/zh (``VISION_COLORS``) porque o upstream é chinês e pode
    responder em qualquer um dos três. ``expected_color`` é a chave
    (``"red"``/``"blue"``). Devolve fail se o conteúdo estiver vazio ou se
    nenhum sinônimo da cor aparecer — evidência traz o texto para auditoria.
    """
    try:
        content = resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return False, f"sem choices[0].message.content: {str(resp)[:120]}"
    text = content.strip()
    if not text:
        return False, "content vazio"
    needles = VISION_COLORS.get(expected_color, (expected_color,))
    low = text.lower()
    hit = next((n for n in needles if n in low), None)
    if hit is None:
        return False, f"cor '{expected_color}' ausente: {text[:80]!r}"
    return True, f"cor={expected_color} match={hit!r} len={len(text)}"


def verdict_passthrough(resp: dict) -> tuple[bool, str]:
    """video/3d passthrough: task id + status aceito (queued/processing/completed)."""
    tid = resp.get("id") or resp.get("task_id") or resp.get("request_id")
    status = resp.get("status", "")
    if tid:
        return True, f"id={tid} status={status}"
    return False, f"sem task id: {str(resp)[:120]}"


# ---------------------------------------------------------------------------
# S103 / P1 — vereditos novos (contrato, TTFT, JSON estrito, erros, params)
# ---------------------------------------------------------------------------


def verdict_ttft(ttft_ms: float | None, total_ms: float | None = None) -> tuple[bool, str]:
    """TTFT: primeiro token medido, finito, ≥0 e ≤ tempo total.

    ``ttft_ms=None`` = nenhum chunk com ``delta.content`` chegou ⇒ fail (stream
    que só manda ``[DONE]`` não prova geração). Função PURA: a medição acontece
    em ``measure_stream_timing``; aqui só se julga o número.
    """
    if ttft_ms is None:
        return False, "sem primeiro token (nenhum delta.content)"
    if ttft_ms < 0:
        return False, f"ttft_ms={ttft_ms} negativo"
    if total_ms is not None and ttft_ms > total_ms:
        return False, f"ttft_ms={ttft_ms} > total_ms={total_ms}"
    tail = f" total_ms={total_ms}" if total_ms is not None else ""
    return True, f"ttft_ms={ttft_ms:.1f}{tail}"


def measure_stream_timing(payloads: list[str], *, t0: float,
                          stamps: list[float] | None = None) -> dict:
    """Mede TTFT/total de um stream já recebido (PURA — sem relógio próprio).

    ``t0`` = instante (s) do envio; ``stamps`` = instante de chegada de cada
    payload, na MESMA ordem de ``payloads``. Sem ``stamps`` (corpo recebido de
    uma vez, como no ``requests`` não-stream) o TTFT não é observável ⇒
    ``ttft_ms=None`` (fail-closed: não inventa número).

    Retorna ``{ttft_ms, total_ms, n_content_chunks}``.
    """
    n_content = 0
    first_idx: int | None = None
    for i, p in enumerate(payloads):
        if p == "[DONE]":
            continue
        try:
            obj = json.loads(p)
        except ValueError:
            continue
        has = any(((ch.get("delta") or {}).get("content")) for ch in obj.get("choices") or [])
        if has:
            n_content += 1
            if first_idx is None:
                first_idx = i
    total_ms = None
    if stamps:
        total_ms = (stamps[-1] - t0) * 1000.0
    ttft_ms = None
    if stamps and first_idx is not None and first_idx < len(stamps):
        ttft_ms = (stamps[first_idx] - t0) * 1000.0
    return {"ttft_ms": ttft_ms, "total_ms": total_ms, "n_content_chunks": n_content}


def verdict_json_strict(resp: dict) -> tuple[bool, str]:
    """JSON estrito (``response_format=json_object``): content parseia E é objeto.

    Array/escalar não conta: ``json_object`` promete um OBJETO. Content vazio ou
    cercado por ``` (markdown) = fail — o cliente pediu JSON puro.
    """
    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return False, f"sem choices[0].message.content: {str(resp)[:120]}"
    text = (content or "").strip()
    if not text:
        return False, "content vazio"
    try:
        obj = json.loads(text)
    except ValueError as exc:
        return False, f"content não-JSON: {exc} :: {text[:60]!r}"
    if not isinstance(obj, dict):
        return False, f"JSON não é objeto (tipo={type(obj).__name__})"
    return True, f"json_object keys={sorted(obj)[:5]}"


def verdict_error_contract(status_code: int, headers: dict | None,
                           body: dict | None) -> tuple[bool, str]:
    """Contrato de erro: status esperado + corpo ``error`` legível (+ Retry-After).

    Regras (fail-closed):
      - 404/400: corpo precisa ter ``error`` (dict ou str) — 500/timeout = fail.
      - 429: além do ``error``, exige ``Retry-After`` numérico ≥ 0 (header ou
        ``error.retry_after``). Sem ele o cliente não sabe quando voltar.
    """
    headers = headers or {}
    body = body or {}
    err = body.get("error")
    if status_code not in (400, 404, 429):
        return False, f"status={status_code} fora do contrato (esperado 400/404/429)"
    if not err:
        return False, f"HTTP {status_code} sem campo 'error': {str(body)[:100]}"
    msg = err.get("message") if isinstance(err, dict) else str(err)
    if not (msg or "").strip():
        return False, f"HTTP {status_code} error sem message"
    if status_code == 429:
        ra = headers.get("Retry-After") or headers.get("retry-after")
        if ra is None and isinstance(err, dict):
            ra = err.get("retry_after")
        try:
            ra_num = float(ra) if ra is not None else None
        except (TypeError, ValueError):
            ra_num = None
        if ra_num is None or ra_num < 0:
            return False, f"HTTP 429 sem Retry-After numérico (ra={ra!r})"
        return True, f"HTTP 429 error+Retry-After={ra_num:g}"
    return True, f"HTTP {status_code} error={str(msg)[:60]!r}"


def verdict_param_forwarding(sent: dict, resp: dict) -> tuple[bool, str]:
    """Param forwarding: os params enviados chegaram ao upstream (evidência no corpo).

    Só julga o que é OBSERVÁVEL na resposta (não inventa eco que o gateway não
    devolve):
      - ``content``: precisa ser NÃO-VAZIO. Sem isso o teste passa **vacuamente**
        (achado A7 da Fase F: o gateway devolvia ``content=""`` com
        ``finish_reason=length``, todo o ``max_tokens`` consumido pelo reasoning,
        e o ``stop`` nunca era exercitado — o veredito antigo dava pass);
      - ``stop``: o texto NÃO pode conter a sequência de parada;
      - ``max_tokens``: ``usage.completion_tokens`` ≤ ``max_tokens``;
      - ``temperature``/``top_p``: sem evidência no corpo ⇒ não julga (registra).
    """
    problems: list[str] = []
    notes: list[str] = []
    try:
        content = (resp["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError):
        return False, f"sem choices[0].message.content: {str(resp)[:120]}"
    # A7 (Fase I): content vazio = teste vacuamente aprovado. Fail-closed.
    if not content.strip():
        fr = (resp["choices"][0].get("finish_reason")
              if isinstance(resp.get("choices"), list) and resp["choices"] else None)
        return False, (f"content vazio (finish_reason={fr!r}) — stop/max_tokens "
                       f"não exercitados (A7)")
    stop = sent.get("stop")
    if stop:
        stops = [stop] if isinstance(stop, str) else list(stop)
        hit = [s for s in stops if s and s in content]
        if hit:
            problems.append(f"stop {hit!r} apareceu no texto")
        else:
            notes.append(f"stop={stops!r} respeitado")
    mt = sent.get("max_tokens")
    usage = resp.get("usage") or {}
    ct = usage.get("completion_tokens")
    if isinstance(mt, int) and isinstance(ct, int):
        if ct > mt:
            problems.append(f"completion_tokens={ct} > max_tokens={mt}")
        else:
            notes.append(f"completion_tokens={ct}<=max_tokens={mt}")
    for k in ("temperature", "top_p"):
        if k in sent:
            notes.append(f"{k}={sent[k]} (sem eco no corpo)")
    if problems:
        return False, "; ".join(problems)
    return True, "; ".join(notes) or "nada observável"


def verdict_needle(assembled: str, needle: str, *, max_chars: int | None = None
                   ) -> tuple[bool, str]:
    """Needle-in-haystack: a agulha aparece no texto montado (case-insensitive).

    ``max_chars`` (opcional) limita a janela de busca — útil para provar que a
    agulha veio do MEIO do contexto e não de um eco do início.
    """
    if not needle:
        return False, "agulha vazia (teste inválido)"
    hay = assembled[:max_chars] if max_chars else assembled
    pos = hay.lower().find(needle.lower())
    if pos < 0:
        return False, f"agulha {needle!r} ausente (len={len(assembled)})"
    return True, f"agulha em pos={pos} len={len(assembled)}"


# ---------------------------------------------------------------------------
# S103 / Fase I — contexto longo + stress (T19 estendido, T20 estendido)
# ---------------------------------------------------------------------------

# Posições relativas da agulha no contexto (fração do preenchimento). A Fase F
# só testava o MEIO; a Fase I varre início/meio/fim para pegar o "lost in the
# middle" (modelos recuperam bem nas pontas e mal no centro).
NEEDLE_POSITIONS = (0.0, 0.5, 1.0)


def build_needle_context(needle: str, *, filler_tokens: int,
                         position: float = 0.5,
                         filler: str = "O rato roeu a roupa do rei de Roma. "
                         ) -> str:
    """Monta um contexto longo com a agulha numa posição relativa (PURA).

    ``position`` ∈ [0,1]: 0 = início, 0.5 = meio, 1 = fim. ``filler_tokens`` é
    aproximado (1 "token" ≈ 10 chars do preenchimento, mesma convenção do
    ``run_needle`` da Fase F). Determinístico: mesma entrada ⇒ mesma string.
    """
    if not 0.0 <= position <= 1.0:
        raise ValueError(f"position fora de [0,1]: {position}")
    reps = max(1, filler_tokens // 10)
    body = filler * reps
    cut = int(len(body) * position)
    return f"{body[:cut]}\n{needle}\n{body[cut:]}"


def verdict_needle_position(assembled: str, needle: str, *,
                            position: float) -> tuple[bool, str]:
    """Veredito de needle com a POSIÇÃO esperada na evidência (PURA).

    Igual a ``verdict_needle`` mas registra a posição relativa pedida, para o
    relatório mostrar a curva início/meio/fim. Fail-closed: agulha ausente ou
    vazia = fail.
    """
    ok, ev = verdict_needle(assembled, needle)
    return ok, f"pos={position:g} :: {ev}"


def summarize_stress(results: list[dict]) -> dict:
    """Agrega um stress de N chamadas: sucesso, p50/p95/p99, erros, throughput.

    ``results`` = lista de ``{status_code, latency_ms, error?}``. PURA. Diferente
    de ``summarize_concurrency`` (N=4, só p50/p95), aqui interessa a CAUDA: p99,
    taxa de erro e se houve degradação (p95 ≫ p50).
    """
    n = len(results)
    ok = [r for r in results if r.get("status_code") == 200]
    lat = sorted(float(r.get("latency_ms") or 0.0) for r in ok)

    def _pct(p: float) -> float | None:
        if not lat:
            return None
        idx = min(len(lat) - 1, max(0, math.ceil(p * len(lat)) - 1))
        return lat[idx]

    errs: dict[str, int] = {}
    for r in results:
        if r.get("status_code") != 200:
            key = str(r.get("status_code"))
            errs[key] = errs.get(key, 0) + 1
    total_ms = sum(float(r.get("latency_ms") or 0.0) for r in results)
    p50, p95 = _pct(0.50), _pct(0.95)
    # Degradação = p95 mais que o dobro do p50 (cauda longa sob carga).
    degraded = bool(p50 and p95 and p95 > 2 * p50)
    return {"n": n, "ok": len(ok), "p50_ms": p50, "p95_ms": p95,
            "p99_ms": _pct(0.99), "errors": errs,
            "error_rate": (n - len(ok)) / n if n else 0.0,
            "throughput_rps": (n / (total_ms / 1000.0)) if total_ms else None,
            "degraded": degraded}


def verdict_stress(summary: dict, *, max_error_rate: float = 0.0,
                   allow_degraded: bool = True) -> tuple[bool, str]:
    """Stress: taxa de erro dentro do limite e cauda registrada (PURA).

    ``max_error_rate=0.0`` (default) exige 100% de sucesso — stress é para provar
    que o grupo aguenta, não para tolerar falha. ``allow_degraded=False`` também
    reprova quando p95 > 2×p50 (cauda longa).
    """
    n, ok = summary.get("n", 0), summary.get("ok", 0)
    er = summary.get("error_rate", 0.0)
    ev = (f"n={n} ok={ok} err={er:.0%} p50={summary.get('p50_ms')} "
          f"p95={summary.get('p95_ms')} p99={summary.get('p99_ms')} "
          f"rps={summary.get('throughput_rps')} errors={summary.get('errors')}")
    if n == 0:
        return False, "nenhuma chamada executada"
    if er > max_error_rate:
        return False, ev
    if not allow_degraded and summary.get("degraded"):
        return False, f"cauda longa (p95 > 2×p50) :: {ev}"
    return True, ev


def summarize_concurrency(results: list[dict]) -> dict:
    """Agrega N chamadas concorrentes: sucesso, latências p50/p95, erros por status.

    ``results`` = lista de ``{status_code, latency_ms, error?}``. PURA.
    """
    n = len(results)
    ok = [r for r in results if r.get("status_code") == 200]
    lat = sorted(float(r.get("latency_ms") or 0.0) for r in ok)

    def _pct(p: float) -> float | None:
        if not lat:
            return None
        # Nearest-rank (mesma convenção do eval/mcp_report): ceil(p*n)-1.
        idx = min(len(lat) - 1, max(0, math.ceil(p * len(lat)) - 1))
        return lat[idx]

    errs: dict[str, int] = {}
    for r in results:
        if r.get("status_code") != 200:
            key = str(r.get("status_code"))
            errs[key] = errs.get(key, 0) + 1
    return {"n": n, "ok": len(ok), "p50_ms": _pct(0.50), "p95_ms": _pct(0.95),
            "errors": errs}


def verdict_concurrency(summary: dict, *, expect_all_ok: bool = True) -> tuple[bool, str]:
    """Concorrência: todas as N chamadas 200 (ou, se ``expect_all_ok=False``, ≥1)."""
    n, ok = summary.get("n", 0), summary.get("ok", 0)
    ev = (f"n={n} ok={ok} p50={summary.get('p50_ms')} p95={summary.get('p95_ms')} "
          f"errors={summary.get('errors')}")
    if n == 0:
        return False, "nenhuma chamada executada"
    if expect_all_ok and ok != n:
        return False, ev
    if not expect_all_ok and ok < 1:
        return False, ev
    return True, ev



# ---------------------------------------------------------------------------
# Transport injetável (só usado em modo --live)
# ---------------------------------------------------------------------------

Sender = Callable[..., requests.Response]

# S103 / P3b: limite de bytes do corpo bruto guardado no jsonl (spec §12).
BODY_RAW_LIMIT = 4000


def make_sender(cfg: dict) -> Sender:
    """Fecha base_url/api_key num callable que faz POST ao proxy."""
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _send(path: str, *, json_body=None, data=None, files=None, stream=False):
        url = f"{cfg['base_url']}/{path.lstrip('/')}"
        return requests.post(url, headers=headers, json=json_body, data=data,
                             files=files, stream=stream, timeout=120)

    return _send


def make_capturing_sender(cfg: dict, sink: dict) -> Sender:
    """Sender que também registra request/response em ``sink`` (para o jsonl).

    ``sink`` recebe ``request`` (método, url, body), ``headers`` (resposta, já
    redigidos), ``body_raw`` (truncado em ``BODY_RAW_LIMIT``) e ``sse_framing``
    (``"\\n\\n"`` | ``"\\n"`` | ``""``). O sink é limpo a cada chamada, então o
    orquestrador lê o último valor depois de rodar o check.
    """
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _send(path: str, *, json_body=None, data=None, files=None, stream=False):
        url = f"{cfg['base_url']}/{path.lstrip('/')}"
        sink.clear()
        sink["request"] = {"method": "POST", "url": url, "body": json_body}
        r = requests.post(url, headers=headers, json=json_body, data=data,
                          files=files, stream=stream, timeout=120)
        sink["headers"] = dict(getattr(r, "headers", {}) or {})
        text = getattr(r, "text", "") or ""
        # S103 / Fase G: respostas de imagem trazem URL PRÉ-ASSINADA (OSS/COS)
        # com AccessKeyId/SecretId de terceiros na query. Sem redigir, o jsonl
        # versionado em ``reports/`` sobe credencial e o GitHub Push Protection
        # bloqueia o push (GH013). Reusa a redação do S106.
        text, _ = redact_signed_urls(text)
        sink["body_raw"] = text[:BODY_RAW_LIMIT]
        sink["sse_framing"] = detect_sse_framing(text) if stream else ""
        return r

    return _send


def detect_sse_framing(text: str) -> str:
    """Classifica o separador de eventos SSE observado no corpo.

    ``"\\n\\n"`` = canônico; ``"\\n"`` = regressão conhecida (S41→S42); ``""`` =
    não parece SSE. Puro — usado no jsonl e testável offline.
    """
    if not text or "data:" not in text:
        return ""
    if "\n\n" in text:
        return "\\n\\n"
    return "\\n"


def attach_capture(result: CheckResult, sink: dict) -> CheckResult:
    """Copia a captura do ``sink`` para o ``CheckResult`` (já redigida)."""
    from eval.novai_log import redact_obj

    if not sink:
        return result
    result.request = redact_obj(sink.get("request"))
    result.headers = redact_obj(sink.get("headers"))
    result.body_raw = redact_obj(sink.get("body_raw", ""))
    result.sse_framing = sink.get("sse_framing", "")
    return result


# ---------------------------------------------------------------------------
# Testes por modalidade (orquestram sender + verdict puro)
# ---------------------------------------------------------------------------


def run_chat(sender: Sender, group: str, *, stream=False, tools=False,
             thinking=None) -> CheckResult:
    body: dict = {
        "model": group,
        "messages": [{"role": "user", "content": "Diga apenas: OK"}],
        "max_tokens": 512,
    }
    if stream:
        body["stream"] = True
    if tools:
        body["tools"] = [{
            "type": "function",
            "function": {
                "name": "noop",
                "description": "chame esta função",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        body["tool_choice"] = "auto"
    if thinking == "disabled":
        body["extra_body"] = {"thinking": {"type": "disabled"}}

    label = "chat.stream" if stream else "chat.tools" if tools else "chat"
    try:
        r = sender("/chat/completions", json_body=body, stream=stream)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", label, False, f"erro rede: {exc}")

    if r.status_code != 200:
        return CheckResult(group, "chat", label, False,
                           f"HTTP {r.status_code}: {r.text[:120]}")

    if stream:
        info = parse_sse_lines(r.text)
        ok, ev = verdict_stream_strong(info, expect_substr="OK")
        return CheckResult(group, "chat", label, ok, ev)

    resp = r.json()
    if tools:
        ok, ev = verdict_tool_calls(resp)
    elif thinking == "disabled":
        ok, ev = verdict_thinking_off(resp)
    elif thinking == "on":
        ok, ev = verdict_thinking_on(resp)
    else:
        ok, ev = verdict_chat(resp)
    return CheckResult(group, "chat", label, ok, ev,
                       cost_usd=_cost_from_usage(resp))


def _cost_from_usage(resp: dict) -> float | None:
    """Custo aproximado se o proxy devolver x_litellm_cost; senão None (informativo)."""
    c = resp.get("x_litellm_cost") or (resp.get("usage", {}) or {}).get("x_litellm_cost")
    return float(c) if isinstance(c, (int, float)) else None


def _chat_raw(sender: Sender, group: str, *, thinking_off: bool) -> tuple[dict | None, str]:
    """Dispara um chat mínimo e devolve (json_cru, erro). Erro='' quando OK.

    ``thinking_off=True`` injeta ``extra_body.thinking:{type:disabled}`` (o mesmo
    mecanismo que a rota -fast usa no config); ``False`` deixa herdar o default do
    upstream (= ON). Usado por ``run_thinking_probe`` para medir reasoning cru.
    """
    body: dict = {
        "model": group,
        "messages": [{"role": "user", "content": "Diga apenas: OK"}],
        "max_tokens": 512,
    }
    if thinking_off:
        body["extra_body"] = {"thinking": {"type": "disabled"}}
    try:
        r = sender("/chat/completions", json_body=body)
    except requests.RequestException as exc:
        return None, f"erro rede: {exc}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:120]}"
    try:
        return r.json(), ""
    except ValueError:
        return None, "resposta não-JSON"


def run_thinking_probe(sender: Sender, base_group: str, fast_group: str) -> CheckResult:
    """Sonda se thinking-ON/OFF *realmente faz sentido* num modelo de raciocínio.

    Manda a mesma pergunta mínima nos dois modos (base=ON, -fast=OFF via extra_body),
    mede reasoning em cada lado e classifica com ``verdict_thinking_sense``. O veredito
    é **evidência medida**, não a convenção declarada no config — responde exatamente
    "em quais modelos ter as duas rotas vale a pena". ``passed=True`` só na categoria
    ``funciona`` (ON raciocina E OFF zera de fato).
    """
    on_resp, on_err = _chat_raw(sender, base_group, thinking_off=False)
    off_resp, off_err = _chat_raw(sender, fast_group, thinking_off=True)
    if on_resp is None or off_resp is None:
        detail = on_err or off_err
        return CheckResult(base_group, "chat", "thinking-sense", False,
                           f"sonda falhou: {detail}")
    cat, ev = verdict_thinking_sense(on_resp, off_resp)
    return CheckResult(base_group, "chat", "thinking-sense", cat == "funciona",
                       f"{cat} :: {ev}")


def pair_chat_models(rows: list[dict]) -> list[tuple[str, str]]:
    """Emparelha grupos chat (base=ON) com seu -fast (OFF) pelo slug comum.

    Só retorna pares COMPLETOS (base E -fast presentes). Base sem -fast correspondente
    é descartada aqui (não tem o segundo modo para comparar). Ordem determinística pela
    lista de entrada (preserva economia de prompt-cache ao citar).
    """
    by_slug: dict[str, dict[str, str]] = {}
    for r in rows:
        grp = r["group"]
        if r["modality"] not in ("chat", "chat-fast"):
            continue
        if grp.endswith("-fast"):
            slug = grp[: -len("-fast")]
            by_slug.setdefault(slug, {})["off"] = grp
        else:
            by_slug.setdefault(grp, {})["on"] = grp
    pairs: list[tuple[str, str]] = []
    for slug, ends in by_slug.items():
        if "on" in ends and "off" in ends:
            pairs.append((ends["on"], ends["off"]))
    return pairs


# S103 / Fase H (T23): modelos VL (vision-language) do gateway NÃO aceitam
# ``input`` como lista de strings — o upstream Tencent (Kinfra) devolve
# ``400 "The request parameter input is invalid or missing"``. Eles exigem o
# formato multimodal ``[{"type":"text","text":...}]``. Detectado por sufixo do
# ``upstream_id`` (``*-vl-embedding-*``), que é o mesmo nome no gateway e no proxy.
VL_EMBEDDING_MARKER = "-vl-embedding-"


def embedding_input(model: str, text: str = "texto de teste") -> list:
    """Payload de ``input`` correto para o modelo (string puro vs multimodal).

    Puro e determinístico: só olha o nome do modelo. Modelos VL recebem
    ``[{"type":"text","text":...}]``; os demais recebem ``[text]`` (formato
    OpenAI clássico, aceito por todos os text-embedding do gateway).
    """
    if VL_EMBEDDING_MARKER in model:
        return [{"type": "text", "text": text}]
    return [text]


def run_embedding(sender: Sender, group: str) -> CheckResult:
    body = {"model": group, "input": embedding_input(group)}
    try:
        r = sender("/embeddings", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "embedding", "embed", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "embedding", "embed", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_embeddings(r.json())
    return CheckResult(group, "embedding", "embed", ok, ev)


# ---------------------------------------------------------------------------
# S103 / Fase H (T23) — embeddings + pgvector ISOLADO (chunks_novai_<slug>)
#
# INVARIANTE 7: esta sonda NÃO é o índice do RAG. A tabela ``chunks_novai_<slug>``
# é criada aqui, fora do registry ``ingest/profiles.py``, e nunca é lida por
# ``ingest/search.py``. Testar ≠ adotar.
# ---------------------------------------------------------------------------

# Tolerância do round-trip. ``halfvec`` é fp16 (11 bits de mantissa): o vetor
# lido de volta não é bit-idêntico ao enviado, então a distância consigo mesmo
# não é exatamente 0. 1e-3 é ~2 ordens de grandeza acima do erro fp16 esperado
# (~1e-4) e ~3 ordens abaixo de qualquer distância entre vetores distintos.
PGVECTOR_RT_TOLERANCE = 1e-3

# Teto do pgvector para ``halfvec`` (4000 dims). Acima disso o INSERT falha.
PGVECTOR_HALFVEC_MAX_DIM = 4000

# Nome da tabela de sonda: prefixo fixo + slug do grupo (sem ``novai-embed-``).
PGVECTOR_TABLE_PREFIX = "chunks_novai_"


def pgvector_column_type(dim: int) -> str:
    """Tipo da coluna para ``dim``: ``halfvec`` até 4000, ``vector`` acima.

    ``halfvec`` é o default (fp16, aceita HNSW até 4000 dims — BUG-001). Acima
    disso só ``vector`` (float4) comporta o vetor; o índice HNSW fica de fora
    (teto de 2000 dims em float4), mas a sonda T23 não precisa de índice — ela
    faz ``ORDER BY embedding <=> $1 LIMIT 1`` numa tabela de 1 linha.
    """
    if not isinstance(dim, int) or dim <= 0:
        raise ValueError(f"dim inválida: {dim!r}")
    return "halfvec" if dim <= PGVECTOR_HALFVEC_MAX_DIM else "vector"


def pgvector_table_for(group: str) -> str:
    """Nome da tabela de sonda para um grupo (``chunks_novai_<slug>``).

    O slug é derivado do grupo removendo ``novai-embed-`` e trocando qualquer
    caractere fora de ``[a-z0-9_]`` por ``_``. Puro — testável offline. O
    resultado SEMPRE começa com ``chunks_novai_``, então nunca colide com
    ``chunks``/``chunks_qwen37``/``chunks_bgem3`` (invariante 7).
    """
    slug = group
    if slug.startswith("novai-embed-"):
        slug = slug[len("novai-embed-"):]
    slug = "".join(c if (c.isalnum() and c.isascii()) or c == "_" else "_"
                   for c in slug.lower())
    slug = slug.strip("_") or "probe"
    return f"{PGVECTOR_TABLE_PREFIX}{slug}"


def pgvector_ddl(table: str, dim: int) -> str:
    """DDL mínimo da tabela de sonda (idempotente, ``halfvec(dim)`` + HNSW).

    Espelha a FORMA de ``ingest/store.py::_PROFILE_DDL_TEMPLATE`` (halfvec +
    ``halfvec_cosine_ops``), mas SEM ``tsv``/``gen``/``repo``: a sonda só precisa
    de ``id``, ``content`` e ``embedding``. ``table`` deve vir de
    ``pgvector_table_for`` (nunca de input cru).

    Acima de 4000 dims a coluna vira ``vector`` e o índice HNSW é omitido (o
    pgvector não indexa float4 acima de 2000 dims); a busca por distância
    continua exata por seq scan numa tabela de 1 linha.
    """
    if not table.startswith(PGVECTOR_TABLE_PREFIX):
        raise ValueError(f"tabela de sonda deve começar com {PGVECTOR_TABLE_PREFIX!r}")
    col = pgvector_column_type(dim)
    ddl = f"""
CREATE TABLE IF NOT EXISTS {table} (
    id         bigserial PRIMARY KEY,
    content    text NOT NULL,
    embedding  {col}({dim}) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""
    if col == "halfvec":
        ddl += f"""
CREATE INDEX IF NOT EXISTS {table}_embedding_hnsw
    ON {table} USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""
    return ddl


def verdict_pgvector_roundtrip(origin: list[float], readback: list[float],
                               distance: float | None, *,
                               expected_dim: int | None = None,
                               tolerance: float = PGVECTOR_RT_TOLERANCE
                               ) -> tuple[bool, str]:
    """T23 — veredito PURO do round-trip embed → INSERT → SELECT por distância.

    Aceite (matriz §10): **dim bate** E **a busca por distância retorna o próprio
    vetor** (distância ≈ 0). ``halfvec`` é fp16, então a comparação usa
    ``tolerance`` explícita (nunca ``== 0``).

    ``distance`` é o valor de ``embedding <=> $1`` devolvido pelo Postgres
    (cosine distance, 0 = idêntico). ``None`` ⇒ não houve leitura ⇒ fail.
    """
    if not isinstance(origin, list) or not origin:
        return False, "vetor de origem vazio/inválido"
    if not isinstance(readback, list) or not readback:
        return False, "vetor lido do banco vazio/inválido"
    dim = len(origin)
    if expected_dim is not None and dim != expected_dim:
        return False, f"dim origem={dim} esperado={expected_dim}"
    if len(readback) != dim:
        return False, f"dim origem={dim} lido={len(readback)} (round-trip truncou)"
    if distance is None:
        return False, f"dim={dim} :: sem distância (SELECT não retornou linha)"
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return False, f"dim={dim} :: distância não numérica: {distance!r}"
    if d != d:  # NaN
        return False, f"dim={dim} :: distância NaN"
    if d > tolerance:
        return False, f"dim={dim} :: distância={d:.6g} > tol={tolerance:g}"
    return True, f"dim={dim} :: distância={d:.6g} ≤ tol={tolerance:g}"


def _pg_connect(db_url: str | None = None):
    """Abre conexão psycopg no rag-db (``RAG_DB_URL`` do .env por default)."""
    import psycopg

    from ingest.store import db_url_from_env

    return psycopg.connect(db_url or db_url_from_env())


def run_embedding_pgvector(sender: Sender, group: str, *, dim: int | None = None,
                           table: str | None = None,
                           connect: Callable[[], object] | None = None
                           ) -> CheckResult:
    """T23 — embed + INSERT/SELECT em ``chunks_novai_<slug>`` (tabela ISOLADA).

    Fluxo: ``POST /embeddings`` → ``CREATE TABLE IF NOT EXISTS`` (idempotente) →
    ``INSERT`` do vetor como ``halfvec`` → ``SELECT ... ORDER BY embedding <=> $1
    LIMIT 1`` → ``verdict_pgvector_roundtrip``.

    ``connect`` é injetável (testes offline usam uma conexão fake); por default
    abre ``psycopg`` no ``RAG_DB_URL``. ``dim`` omitido ⇒ usa a dim observada no
    próprio vetor (a tabela é criada com ela). Erro de banco ⇒ fail com a causa
    (achado é DADO, nunca aborta o run).
    """
    from ingest.embed import vector_to_halfvec_text

    tbl = table or pgvector_table_for(group)
    body = {"model": group, "input": embedding_input(group)}
    try:
        r = sender("/embeddings", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    try:
        vec = r.json()["data"][0]["embedding"]
    except (KeyError, IndexError, ValueError):
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           f"sem data[].embedding: {r.text[:120]}")
    if not isinstance(vec, list) or not vec:
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           "embedding vazio")
    observed_dim = len(vec)
    target_dim = dim or observed_dim
    if observed_dim != target_dim:
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           f"dim={observed_dim} esperado={target_dim}")

    literal = vector_to_halfvec_text(vec)
    col = pgvector_column_type(target_dim)
    try:
        conn = (connect or _pg_connect)()
        try:
            with conn.cursor() as cur:
                cur.execute(pgvector_ddl(tbl, target_dim))
                cur.execute(f"DELETE FROM {tbl}")  # sonda idempotente
                cur.execute(
                    f"INSERT INTO {tbl} (content, embedding) "
                    f"VALUES (%s, %s::{col}({target_dim}))",
                    ("texto de teste", literal),
                )
                cur.execute(
                    f"SELECT embedding::text, embedding <=> %s::{col}({target_dim}) "
                    f"FROM {tbl} ORDER BY embedding <=> %s::{col}({target_dim}) "
                    f"LIMIT 1",
                    (literal, literal),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — banco fora ⇒ fail com causa
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           f"pgvector: {type(exc).__name__}: {str(exc)[:120]}",
                           notes=f"tabela={tbl}")

    if not row:
        return CheckResult(group, "embedding", "embed.pgvector", False,
                           f"dim={observed_dim} :: SELECT vazio", notes=f"tabela={tbl}")
    readback_text, distance = row[0], row[1]
    readback = _parse_pgvector_text(readback_text)
    ok, ev = verdict_pgvector_roundtrip(vec, readback, distance,
                                        expected_dim=target_dim)
    return CheckResult(group, "embedding", "embed.pgvector", ok, ev,
                       notes=f"tabela={tbl} tipo={col}")


def _parse_pgvector_text(text: str) -> list[float]:
    """Converte ``"[1,2,3]"`` (saída de ``halfvec::text``) em lista de floats."""
    if not isinstance(text, str):
        return []
    s = text.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if not s:
        return []
    try:
        return [float(x) for x in s.split(",")]
    except ValueError:
        return []


def run_image(sender: Sender, group: str) -> CheckResult:
    # S103 / Fase G: ``1024x1024`` é o menor tamanho aceito por TODOS os
    # provedores de imagem do gateway. Com ``512x512`` os modelos Seedream
    # devolvem 400 ("image area must be ..."), o que mascarava o teste como
    # falha de modelo quando era só parâmetro inválido.
    body = {"model": group, "prompt": "um gato azul", "size": "1024x1024",
            "n": 1}
    try:
        r = sender("/images/generations", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "image", "image", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "image", "image", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_image(r.json())
    return CheckResult(group, "image", "image", ok, ev)


def run_tts(sender: Sender, group: str) -> CheckResult:
    body = {"model": group, "input": "Olá mundo", "voice": "alloy",
            "response_format": "mp3"}
    try:
        r = sender("/audio/speech", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "tts", "tts", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "tts", "tts", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_audio(r.content)
    return CheckResult(group, "tts", "tts", ok, ev)


def run_asr(sender: Sender, group: str) -> CheckResult:
    # S103 / Fase G: fixture de FALA (espeak-ng, "Hello world. This is a test of
    # speech recognition."). O antigo ``hello.wav`` era um TOM PURO de 440 Hz —
    # o ASR devolvia ``text: ""`` corretamente e o teste acusava o modelo por um
    # bug NOSSO (fixture inadequada). ``speech.wav`` tem formantes (razão
    # tom/total ≈ 0,02), então ``text`` vazio agora é falha real do upstream.
    sample = Path("eval/fixtures/speech.wav")
    if not sample.exists():
        return CheckResult(group, "asr", "asr", False,
                           "fixture ausente (eval/fixtures/speech.wav)", skipped=True)
    try:
        with sample.open("rb") as fh:
            r = sender("/audio/transcriptions",
                       data={"model": group},
                       files={"file": ("speech.wav", fh, "audio/wav")})
    except requests.RequestException as exc:
        return CheckResult(group, "asr", "asr", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "asr", "asr", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_asr(r.json())
    return CheckResult(group, "asr", "asr", ok, ev)


# S103 / Fase G (T22) — fixture de vision: PNG sólido de cor conhecida.
VISION_FIXTURE = Path("eval/fixtures/red.png")
VISION_EXPECTED_COLOR = "red"


def run_vision(sender: Sender, group: str, *,
               fixture: Path | None = None,
               expected_color: str = VISION_EXPECTED_COLOR) -> CheckResult:
    """T22 — vision/OCR: manda a imagem em base64 e pergunta a cor.

    Usa ``/chat/completions`` com ``content`` multimodal (``image_url`` data-URI),
    que é o formato OpenAI que o LiteLLM repassa. Fixture ausente ⇒ skip (não
    fail): o teste não pode acusar o modelo por falta de arquivo local.
    """
    path = fixture or VISION_FIXTURE
    if not path.exists():
        return CheckResult(group, "chat", "vision", False,
                           f"fixture ausente ({path})", skipped=True)
    b64 = base64.b64encode(path.read_bytes()).decode()
    body = {
        "model": group,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": "Qual é a cor predominante desta imagem? "
                         "Responda em uma palavra."},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "max_tokens": 64,
    }
    try:
        r = sender("/chat/completions", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", "vision", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "chat", "vision", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_vision(r.json(), expected_color)
    return CheckResult(group, "chat", "vision", ok, ev)


def run_passthrough(cfg: dict, kind: str) -> CheckResult:
    """video/3d via passthrough: POST <host>/novai/<kind> (fora do /v1)."""
    path = f"/novai/{kind}"
    body = {"model": "default", "prompt": "bola girando"} if kind == "video" \
        else {"model": "default", "prompt": "uma cadeira"}
    url_base = cfg["base_url"].rsplit("/v1", 1)[0]
    try:
        r = requests.post(f"{url_base}{path}",
                          headers={"Authorization": f"Bearer {cfg['api_key']}"},
                          json=body, timeout=120)
    except requests.RequestException as exc:
        return CheckResult(path, f"{kind}-passthrough", kind, False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(path, f"{kind}-passthrough", kind, False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_passthrough(r.json())
    return CheckResult(path, f"{kind}-passthrough", kind, ok, ev)


# ---------------------------------------------------------------------------
# S103 / P1 — orquestradores dos testes novos (sender injetável, offline-testáveis)
# ---------------------------------------------------------------------------


def _elapsed_ms(t0: float) -> float:
    return (time.monotonic() - t0) * 1000.0


def run_ttft(sender: Sender, group: str) -> CheckResult:
    """T13 — TTFT: stream curto; mede o instante do 1º ``delta.content``.

    O sender devolve o corpo inteiro (``requests`` não-stream); o TTFT real só é
    observável quando o sender expõe ``iter_lines`` (streaming). Sem isso o
    veredito é fail-closed (``ttft_ms=None``) — nunca inventa número.
    """
    body = {"model": group, "messages": [{"role": "user", "content": "Conte até 5"}],
            "max_tokens": 64, "stream": True}
    t0 = time.monotonic()
    try:
        r = sender("/chat/completions", json_body=body, stream=True)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", "ttft", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "chat", "ttft", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    stamps: list[float] = []
    lines: list[str] = []
    it = getattr(r, "iter_lines", None)
    if callable(it):
        for raw in it():
            line = raw.decode() if isinstance(raw, bytes) else raw
            stamps.append(time.monotonic())
            lines.append(line)
        raw_text = "\n".join(lines)
    else:
        raw_text = r.text
    info = parse_sse_lines(raw_text)
    timing = measure_stream_timing(info["payloads"], t0=t0, stamps=stamps or None)
    ok, ev = verdict_ttft(timing["ttft_ms"], timing["total_ms"])
    return CheckResult(group, "chat", "ttft", ok, ev)


def run_json_strict(sender: Sender, group: str) -> CheckResult:
    """T14 — JSON estrito via ``response_format={"type":"json_object"}``."""
    body = {
        "model": group,
        "messages": [{"role": "user",
                      "content": 'Responda só JSON: {"ok": true, "n": 1}'}],
        "max_tokens": 256,
        "response_format": {"type": "json_object"},
    }
    try:
        r = sender("/chat/completions", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", "json_strict", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "chat", "json_strict", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_json_strict(r.json())
    return CheckResult(group, "chat", "json_strict", ok, ev)


def run_error_contract(sender: Sender, group: str, *, case: str) -> CheckResult:
    """T15–T17 — contrato de erro. ``case`` ∈ {``404``, ``400``, ``429``}.

    - 404: modelo inexistente (não gasta token no upstream);
    - 400: payload inválido (``messages`` ausente);
    - 429: payload válido num grupo que o chamador sabe estar em cooldown/rate.
    """
    expected = {"404": 404, "400": 400, "429": 429}[case]
    if case == "404":
        body = {"model": f"{group}-nao-existe-{int(time.time())}",
                "messages": [{"role": "user", "content": "oi"}], "max_tokens": 8}
    elif case == "400":
        body = {"model": group, "max_tokens": 8}  # sem messages
    else:
        body = {"model": group, "messages": [{"role": "user", "content": "oi"}],
                "max_tokens": 8}
    try:
        r = sender("/chat/completions", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", f"error_{case}", False, f"erro rede: {exc}")
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    ok, ev = verdict_error_contract(r.status_code, dict(getattr(r, "headers", {}) or {}),
                                    payload)
    if r.status_code != expected:
        ok, ev = False, f"status={r.status_code} esperado={expected} :: {ev}"
    return CheckResult(group, "chat", f"error_{case}", ok, ev)


def run_param_forwarding(sender: Sender, group: str) -> CheckResult:
    """T18 — param forwarding: ``stop`` + ``max_tokens`` observáveis na resposta.

    S103 / Fase I: ``max_tokens`` subiu de 24 para 256. Com 24 o gateway gastava
    TODO o orçamento em reasoning e devolvia ``content=""`` com
    ``finish_reason=length`` — o ``stop`` nunca era exercitado e o teste passava
    vacuamente (achado A7). 256 dá folga para o reasoning terminar e o texto
    aparecer, que é o que o veredito agora exige.
    """
    body = {
        "model": group,
        "messages": [{"role": "user",
                      "content": "Escreva a sequência: um dois tres quatro cinco seis"}],
        "max_tokens": 256,
        "stop": ["quatro"],
        "temperature": 0.0,
    }
    try:
        r = sender("/chat/completions", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", "param_forwarding", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "chat", "param_forwarding", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_param_forwarding(body, r.json())
    return CheckResult(group, "chat", "param_forwarding", ok, ev)


def run_needle(sender: Sender, group: str, *, filler_tokens: int = 2000) -> CheckResult:
    """T19 — needle-in-haystack: agulha única no MEIO de um contexto longo."""
    needle = "AGULHA-7F3A"
    filler = "O rato roeu a roupa do rei de Roma. " * max(1, filler_tokens // 10)
    half = len(filler) // 2
    context = f"{filler[:half]}\n{needle}\n{filler[half:]}"
    body = {
        "model": group,
        "messages": [{"role": "user",
                      "content": f"{context}\n\nQual é o código único no texto acima? "
                                 f"Responda só o código."}],
        "max_tokens": 64,
    }
    try:
        r = sender("/chat/completions", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "chat", "needle", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "chat", "needle", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    try:
        content = r.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError, ValueError):
        return CheckResult(group, "chat", "needle", False, "resposta sem content")
    ok, ev = verdict_needle(content, needle)
    return CheckResult(group, "chat", "needle", ok, ev)


def run_concurrency(sender: Sender, group: str, *, n: int = 4) -> CheckResult:
    """T20 — concorrência: ``n`` chamadas em paralelo no MESMO grupo.

    Usa ``ThreadPoolExecutor`` (o sender é thread-safe: ``requests.post`` novo por
    chamada). Registra p50/p95 das latências e os status de erro.
    """
    from concurrent.futures import ThreadPoolExecutor

    body = {"model": group, "messages": [{"role": "user", "content": "Diga: OK"}],
            "max_tokens": 16}

    def _one(_i: int) -> dict:
        t0 = time.monotonic()
        try:
            r = sender("/chat/completions", json_body=body)
            return {"status_code": r.status_code, "latency_ms": _elapsed_ms(t0)}
        except requests.RequestException as exc:
            return {"status_code": 0, "latency_ms": _elapsed_ms(t0), "error": str(exc)}

    with ThreadPoolExecutor(max_workers=max(1, n)) as pool:
        results = list(pool.map(_one, range(n)))
    summary = summarize_concurrency(results)
    ok, ev = verdict_concurrency(summary)
    return CheckResult(group, "chat", "concurrency", ok, ev)


def run_needle_positions(sender: Sender, group: str, *, filler_tokens: int = 2000,
                         positions: tuple[float, ...] = NEEDLE_POSITIONS
                         ) -> list[CheckResult]:
    """T19 estendido (Fase I) — needle em início/meio/fim do contexto.

    A Fase F só testava o MEIO. Aqui a mesma agulha é colocada em cada posição
    relativa de ``positions`` e cada uma vira um ``CheckResult`` próprio
    (``needle@0``, ``needle@0.5``, ``needle@1``), para o relatório mostrar a
    curva "lost in the middle". Um fail não aborta os outros.
    """
    needle = "AGULHA-7F3A"
    out: list[CheckResult] = []
    for pos in positions:
        test = f"needle@{pos:g}"
        context = build_needle_context(needle, filler_tokens=filler_tokens,
                                       position=pos)
        body = {
            "model": group,
            "messages": [{"role": "user",
                          "content": f"{context}\n\nQual é o código único no texto "
                                     f"acima? Responda só o código."}],
            # Fase I / classe H: 64 tokens era pouco — o modelo de reasoning
            # gastava o orçamento pensando e o ``content`` saía truncado
            # (``finish_reason=length``, ex.: "AGULHA-7"), reprovando o check
            # por orçamento e não por perda de contexto. 256 dá folga ao
            # reasoning e ainda cabe a resposta de 11 chars.
            "max_tokens": 256,
        }
        try:
            r = sender("/chat/completions", json_body=body)
        except requests.RequestException as exc:
            out.append(CheckResult(group, "chat", test, False, f"erro rede: {exc}"))
            continue
        if r.status_code != 200:
            out.append(CheckResult(group, "chat", test, False,
                                   f"HTTP {r.status_code}: {r.text[:120]}"))
            continue
        try:
            content = r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError):
            out.append(CheckResult(group, "chat", test, False,
                                   "resposta sem content"))
            continue
        # Fase I / classe H: o gateway às vezes devolve ``content=""`` com o
        # texto em ``reasoning_content`` (o modelo "pensou" a resposta e não
        # emitiu o canal final). Sem este fallback o check reprova por um
        # artefato do upstream, não por perda de contexto. Só cai no reasoning
        # quando o content está VAZIO — content preenchido nunca é substituído.
        if not content.strip():
            try:
                content = r.json()["choices"][0]["message"].get(
                    "reasoning_content") or ""
            except (KeyError, IndexError, TypeError, ValueError):
                content = ""
        ok, ev = verdict_needle_position(content, needle, position=pos)
        out.append(CheckResult(group, "chat", test, ok, ev))
    return out


def run_stress(sender: Sender, group: str, *, n: int = 12, workers: int = 6,
               max_error_rate: float = 0.0) -> CheckResult:
    """T20 estendido (Fase I) — stress: ``n`` chamadas com ``workers`` paralelos.

    Diferente de ``run_concurrency`` (N=4, prova que aguenta concorrência
    básica), aqui interessa a CAUDA sob carga sustentada: p99, taxa de erro e
    degradação (p95 > 2×p50). ``max_tokens`` baixo para não gastar.
    """
    from concurrent.futures import ThreadPoolExecutor

    body = {"model": group, "messages": [{"role": "user", "content": "Diga: OK"}],
            "max_tokens": 16}

    def _one(_i: int) -> dict:
        t0 = time.monotonic()
        try:
            r = sender("/chat/completions", json_body=body)
            return {"status_code": r.status_code, "latency_ms": _elapsed_ms(t0)}
        except requests.RequestException as exc:
            return {"status_code": 0, "latency_ms": _elapsed_ms(t0), "error": str(exc)}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(_one, range(n)))
    summary = summarize_stress(results)
    ok, ev = verdict_stress(summary, max_error_rate=max_error_rate)
    return CheckResult(group, "chat", "stress", ok, ev)



# ---------------------------------------------------------------------------
# Seleção de grupos (do inventário travado)
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_groups() -> list[dict]:
    """Inventário travado lido do config real do repo (mesma fonte da Fase A)."""
    cfg = REPO_ROOT / "litellm" / "config.yaml"
    return inv.parse_config(cfg.read_text(encoding="utf-8"))


# Apelidos de --family → modalidade canônica do inventário. Aceita tanto o nome
# da modalidade (embedding) quanto o prefixo de família usado no config (embed).
FAMILY_ALIASES = {
    "chat": "chat",
    "embed": "embedding",
    "embedding": "embedding",
    "image": "image",
    "tts": "tts",
    "asr": "asr",
}


def select(rows: list[dict], family: str | None, only_id: str | None) -> list[dict]:
    if only_id:
        return [r for r in rows if r["group"] == only_id]
    if family:
        if family == "chat":
            return [r for r in rows if r["modality"].startswith("chat")]
        canon = FAMILY_ALIASES.get(family, family)
        return [r for r in rows if r["modality"] == canon]
    return rows


# S103 / Fase G — representantes de mídia (1 por endpoint, escolhidos por
# evidência da matriz: os que já responderam 200 no smoke da Fase A). Vision
# usa um grupo de chat multimodal (rota /chat/completions, não /images).
MEDIA_REPRESENTATIVES = {
    "vision": "novai-qwen3-vl-plus",
    # S103 / Fase G: era ``novai-image-wan2.2-t2i-flash``, mas o upstream
    # ``wan2.2-t2i-flash`` derruba a conexão (RemoteDisconnected) de forma
    # determinística (N=3) enquanto ``wan2.5-t2i-preview`` responde 200 no
    # mesmo instante. Achado documentado no relatório; o representante usa um
    # modelo que exercita o endpoint de verdade.
    "image": "novai-image-wand-vega-image-flash",
    "tts": "novai-tts-minimax-speech-2.8-hd",
    "asr": "novai-asr-hy-asr-3.0-preview",
}


def select_media(rows: list[dict]) -> list[dict]:
    """Seleciona 1 grupo por endpoint de mídia (ordem fixa de ``MEDIA_REPRESENTATIVES``).

    Grupo ausente do inventário é simplesmente omitido (o relatório mostra o que
    rodou). Ordem determinística = ordem do dict, para preservar prompt-cache.
    """
    by_group = {r["group"]: r for r in rows}
    return [by_group[g] for g in MEDIA_REPRESENTATIVES.values() if g in by_group]


# ---------------------------------------------------------------------------
# Runner + relatório
# ---------------------------------------------------------------------------


def run_one(row: dict, sender: Sender | None, live: bool, *, stream: bool = False,
            target: str = "proxy", pgvector: bool = False,
            connect: Callable[[], object] | None = None) -> list[CheckResult]:
    mod = row["modality"]
    grp = row["group"]
    # S103 / Fase F: o gateway NovAI NÃO conhece o nome do grupo LiteLLM
    # (`novai-<slug>[-fast]`); ele só aceita o `upstream_id` (`<slug>`). No proxy
    # o nome do grupo é o correto. Sem isso, todo teste no gateway dá 400.
    model = row.get("upstream_id") or grp if target == "gateway" else grp
    if not live:
        return [CheckResult(grp, mod, "smoke", False, "modo dry (use --live)",
                            skipped=True, target=target)]
    assert sender is not None
    if mod == "embedding":
        out = [run_embedding(sender, model)]
        # S103 / Fase H (T23): round-trip pgvector em tabela ISOLADA. A tabela é
        # derivada do GRUPO (não do upstream), para gateway e proxy caírem na
        # mesma `chunks_novai_<slug>` e o round-trip ser comparável.
        if pgvector:
            out.append(run_embedding_pgvector(sender, model,
                                              table=pgvector_table_for(grp),
                                              connect=connect))
    elif mod == "image":
        out = [run_image(sender, model)]
    elif mod == "tts":
        out = [run_tts(sender, model)]
    elif mod == "asr":
        out = [run_asr(sender, model)]
    elif mod == "vision":
        # S103 / Fase G (T22): grupo de chat multimodal, rota /chat/completions.
        out = [run_vision(sender, model)]
    else:
        # chat: texto + thinking conforme ON/OFF. Com --stream, roda também o SSE.
        thinking = "disabled" if mod == "chat-fast" else "on"
        out = [run_chat(sender, model, thinking=thinking)]
        if stream and mod.startswith("chat"):
            out.append(run_chat(sender, model, stream=True))
    for r in out:
        r.group = grp  # o relatório sempre fala do grupo, não do upstream
        r.target = target
    return out


def run_contract_suite(sender: Sender, group: str, *, target: str = "proxy",
                       concurrency: int = 4, model: str | None = None,
                       sink: dict | None = None, stress: bool = False,
                       needle_positions: bool = False) -> list[CheckResult]:
    """S103 — bateria de CONTRATO num grupo de chat (T13–T20).

    Roda os testes novos em sequência: TTFT, JSON estrito, param forwarding,
    needle, concorrência e os 3 contratos de erro. Cada um devolve um
    ``CheckResult`` independente (um fail não aborta os outros — achado é DADO).

    ``model`` é o nome enviado ao upstream (no gateway = ``upstream_id``); se
    omitido usa ``group`` (correto para o proxy).

    ``sink`` (opcional) é o dicionário do ``make_capturing_sender``. Quando
    fornecido, a captura é anexada **imediatamente após cada check** — o sink é
    limpo a cada chamada, então ler depois do batch inteiro gravaria o request
    do ÚLTIMO check em todos os registros (bug S103/Fase F).

    ``stress`` (Fase I) acrescenta o stress de N=12 com 6 workers.
    ``needle_positions`` (Fase I) troca o needle único do meio pela varredura
    início/meio/fim.
    """
    m = model or group
    steps = [
        lambda: run_ttft(sender, m),
        lambda: run_json_strict(sender, m),
        lambda: run_param_forwarding(sender, m),
    ]
    if needle_positions:
        steps.append(lambda: run_needle_positions(sender, m))
    else:
        steps.append(lambda: run_needle(sender, m))
    steps.append(lambda: run_concurrency(sender, m, n=concurrency))
    if stress:
        steps.append(lambda: run_stress(sender, m))
    steps.extend([
        lambda: run_error_contract(sender, m, case="404"),
        lambda: run_error_contract(sender, m, case="400"),
    ])
    out: list[CheckResult] = []
    for step in steps:
        r = step()
        # Fase I: alguns steps devolvem LISTA (needle em N posições).
        batch = r if isinstance(r, list) else [r]
        for item in batch:
            item.group = group  # relatório fala do grupo, não do upstream
            item.target = target
            if sink is not None:
                attach_capture(item, sink)
            out.append(item)
    return out


def update_matrix(results: list[CheckResult]) -> None:
    """Escreve status/evidência na planilha-mãe (por grupo+test).

    S103 / P3: se a matriz já tiver as colunas novas (``target``, ``test_id``,
    ``latency_ms``, ``notes``), elas também são preenchidas. Matriz no formato
    Fase A (sem essas colunas) continua funcionando — nada quebra.
    """
    if not MATRIX_CSV.exists():
        return
    by_group: dict[str, tuple[str, str]] = {}
    for r in results:
        by_group[r.group] = (r.status(), f"{r.test}: {r.evidence}")
    lines = list(csv.reader(MATRIX_CSV.open(encoding="utf-8")))
    header = lines[0]
    gi, si, ei = header.index("group"), header.index("status"), header.index("evidence")
    extra = {name: header.index(name) for name in MATRIX_EXTRA_COLUMNS
             if name in header}
    last_by_group: dict[str, CheckResult] = {}
    for r in results:
        last_by_group[r.group] = r
    for line in lines[1:]:
        if line[gi] in by_group:
            line[si], line[ei] = by_group[line[gi]]
            r = last_by_group[line[gi]]
            if "target" in extra:
                line[extra["target"]] = r.target
            if "test_id" in extra:
                line[extra["test_id"]] = r.test
            if "latency_ms" in extra:
                line[extra["latency_ms"]] = ("" if r.latency_ms is None
                                             else f"{r.latency_ms:.1f}")
            if "notes" in extra:
                line[extra["notes"]] = r.notes
    with MATRIX_CSV.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--family", help="chat|embedding|image|tts|asr")
    ap.add_argument("--id", dest="only_id", help="um único grupo")
    ap.add_argument("--all", action="store_true", help="todos os grupos")
    ap.add_argument("--live", action="store_true", help="de fato chama o proxy")
    ap.add_argument("--stream", action="store_true",
                    help="chat: roda também o caso SSE (stream:true) com veredito forte")
    ap.add_argument("--thinking", action="store_true",
                    help="chat: sonda dual thinking-ON/OFF por modelo e classifica se "
                         "a rota -fast realmente faz sentido (mede reasoning nos 2 modos)")
    ap.add_argument("--list", action="store_true", help="só imprime seleção")
    ap.add_argument("--target", default="proxy", choices=list(TARGETS) + ["both"],
                    help="alvo do smoke: gateway (NovAI direto) | proxy (LiteLLM) | "
                         "both (roda os dois e classifica divergência)")
    ap.add_argument("--contract", action="store_true",
                    help="chat: roda a bateria de contrato T13–T20 (TTFT, JSON "
                         "estrito, param forwarding, needle, concorrência, erros)")
    ap.add_argument("--media", action="store_true",
                    help="Fase G: roda 1 representante por endpoint de mídia "
                         "(vision T22, image, tts, asr)")
    ap.add_argument("--pgvector", action="store_true",
                    help="Fase H (T23): além do embed, faz round-trip INSERT/SELECT "
                         "em chunks_novai_<slug> (tabela ISOLADA, invariante 7)")
    ap.add_argument("--context", action="store_true",
                    help="Fase I: contexto longo (needle em início/meio/fim) + stress "
                         "de concorrência (N=12, 6 workers) na bateria de contrato")
    ap.add_argument("--out", help="grava markdown de resultado aqui")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="pausa (s) ENTRE grupos no modo --live; respeita rate 60 rpm "
                         "(use ~1.1 p/ varreduras grandes)")
    args = ap.parse_args(argv)

    rows = load_groups()
    sel = select(rows, args.family, args.only_id)
    # Sem seletor nenhum (--family/--id/--all) => nada roda (evita disparo acidental).
    if not (args.family or args.only_id or args.all or args.media):
        sel = []
    elif args.all:
        sel = rows
    elif args.media:
        # S103 / Fase G: 1 representante por endpoint de mídia. O grupo de vision
        # é de chat, mas roda com modalidade "vision" (ver run_one).
        sel = []
        for r in select_media(rows):
            if r["group"] == MEDIA_REPRESENTATIVES["vision"]:
                r = {**r, "modality": "vision"}
            sel.append(r)

    # ---- Sonda de thinking (--thinking): para cada par base/-fast mede reasoning
    # nos dois modos e classifica se a dualidade realmente faz sentido. ----
    if args.thinking:
        pairs = pair_chat_models(sel)
        if args.list:
            for on_g, off_g in pairs:
                print(f"chat         {on_g}  <->  {off_g}")
            print(f"# {len(pairs)} pares thinking-ON/OFF selecionados")
            return 0
        if not pairs:
            print("nenhum par base/-fast de chat selecionado", file=sys.stderr)
            return 2
        cfg = proxy_config()
        sender = make_sender(cfg) if args.live else None
        t_results: list[CheckResult] = []
        for i, (on_g, off_g) in enumerate(pairs):
            if not args.live:
                t_results.append(CheckResult(on_g, "chat", "thinking-sense", False,
                                             "modo dry (use --live)", skipped=True))
                continue
            if args.sleep > 0 and i > 0:
                time.sleep(args.sleep)
            t_results.append(run_thinking_probe(sender, on_g, off_g))
        _print_and_export(t_results, args.live, args.out, write_matrix=False)
        return 0

    if args.list:
        for r in sel:
            print(f"{r['modality']:12s} {r['group']}")
        print(f"# {len(sel)} grupos selecionados")
        print(f"# alvo(s): {', '.join(resolve_targets(args.target))}")
        return 0
    if not sel:
        print("nada selecionado (use --family/--id/--all)", file=sys.stderr)
        return 2

    targets = resolve_targets(args.target)
    results: list[CheckResult] = []
    for target in targets:
        cfg = target_config(target)
        sink: dict = {}
        sender = make_capturing_sender(cfg, sink) if args.live else None
        for i, r in enumerate(sel):
            if args.live and args.sleep > 0 and i > 0:
                time.sleep(args.sleep)
            t0 = time.monotonic()
            batch = run_one(r, sender, args.live, stream=args.stream,
                            target=target, pgvector=args.pgvector)
            for res in batch:
                if args.live and res.latency_ms is None:
                    res.latency_ms = _elapsed_ms(t0)
                attach_capture(res, sink)
            results.extend(batch)
            if args.contract and args.live and r["modality"].startswith("chat"):
                model = (r.get("upstream_id") or r["group"]
                         if target == "gateway" else r["group"])
                # a captura é anexada DENTRO da suíte, check a check
                results.extend(run_contract_suite(sender, r["group"],
                                                  target=target, model=model,
                                                  sink=sink,
                                                  stress=args.context,
                                                  needle_positions=args.context))

    _print_and_export(results, args.live, args.out, write_matrix=True)
    if args.live:
        # S103 / P3b: grava sucesso E falha (skip de dry-run não é registrado).
        from eval.novai_log import log_results
        fam = args.family or ("both" if len(targets) > 1 else targets[0])
        p = log_results(results, family=fam)
        if p:
            print(f"# log: {p}")
    if len(targets) > 1:
        _print_divergence(results)
    npass = sum(1 for x in results if x.passed)
    nskip = sum(1 for x in results if x.skipped)
    return 0 if npass == len(results) - nskip else 1


def _print_divergence(results: list[CheckResult]) -> None:
    """S103 — imprime a classificação gateway × proxy (só em --target both)."""
    pairs = classify_all(results)
    if not pairs:
        return
    counts: dict[str, int] = {}
    for _, _, cls in pairs:
        counts[cls] = counts.get(cls, 0) + 1
    print("\n# divergência gateway × proxy")
    for cls in DIVERGENCE_CLASSES:
        if cls in counts:
            ours = " (NOSSO)" if divergence_is_ours(cls) else ""
            print(f"  {cls:12s} {counts[cls]:3d}{ours} — {DIVERGENCE_CLASSES[cls]}")
    for group, test, cls in pairs:
        if divergence_is_ours(cls):
            print(f"  ⚠️  {group} :: {test} ⇒ {cls}")


def _print_and_export(results: list[CheckResult], live: bool, out: str | None,
                      *, write_matrix: bool) -> None:
    """Imprime resumo + por-check; opcionalmente grava CSV-matriz e markdown."""
    npass = sum(1 for x in results if x.passed)
    nskip = sum(1 for x in results if x.skipped)
    print(f"checks={len(results)} pass={npass} fail={len(results)-npass-nskip} "
          f"skip={nskip}")
    for x in results:
        mark = {"pass": "✅", "fail": "❌", "skipped": "⬜"}[x.status()]
        print(f"  {mark} [{x.modality}] {x.group} :: {x.test} — {x.evidence}")
    if live and write_matrix:
        update_matrix(results)
    if out:
        Path(out).write_text(_to_md(results), encoding="utf-8")


def _to_md(results: list[CheckResult]) -> str:
    lines = ["# NovAI smoke — resultados", "",
             "| grupo | alvo | modalidade | teste | status | latência | evidência |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for x in results:
        lat = "" if x.latency_ms is None else f"{x.latency_ms:.0f} ms"
        lines.append(f"| {x.group} | {x.target} | {x.modality} | {x.test} "
                     f"| {x.status()} | {lat} | {x.evidence} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
