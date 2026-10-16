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

# ---------------------------------------------------------------------------
# Config do proxy (lê .env, mesmo padrão de ingest/embed.py)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:4000/v1"
MATRIX_CSV = Path("reports/novai-test-matrix.csv")


def proxy_config() -> dict:
    """Base URL + master key do proxy, lidas do ambiente (.env no repo root)."""
    load_dotenv()
    return {
        "base_url": os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "api_key": os.environ.get("LITELLM_MASTER_KEY", ""),
    }


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

    def status(self) -> str:
        if self.skipped:
            return "skipped"
        return "pass" if self.passed else "fail"


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


def verdict_passthrough(resp: dict) -> tuple[bool, str]:
    """video/3d passthrough: task id + status aceito (queued/processing/completed)."""
    tid = resp.get("id") or resp.get("task_id") or resp.get("request_id")
    status = resp.get("status", "")
    if tid:
        return True, f"id={tid} status={status}"
    return False, f"sem task id: {str(resp)[:120]}"


# ---------------------------------------------------------------------------
# Transport injetável (só usado em modo --live)
# ---------------------------------------------------------------------------

Sender = Callable[..., requests.Response]


def make_sender(cfg: dict) -> Sender:
    """Fecha base_url/api_key num callable que faz POST ao proxy."""
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    def _send(path: str, *, json_body=None, data=None, files=None, stream=False):
        url = f"{cfg['base_url']}/{path.lstrip('/')}"
        return requests.post(url, headers=headers, json=json_body, data=data,
                             files=files, stream=stream, timeout=120)

    return _send


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


def run_embedding(sender: Sender, group: str) -> CheckResult:
    body = {"model": group, "input": ["texto de teste"]}
    try:
        r = sender("/embeddings", json_body=body)
    except requests.RequestException as exc:
        return CheckResult(group, "embedding", "embed", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "embedding", "embed", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_embeddings(r.json())
    return CheckResult(group, "embedding", "embed", ok, ev)


def run_image(sender: Sender, group: str) -> CheckResult:
    body = {"model": group, "prompt": "um gato azul", "size": "512x512", "n": 1}
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
    # amostra mínima WAV mono 8-bit? usa mp3 vazio não — envia wav gerado na mão seria
    # pesado; para smoke usamos um arquivo de áudio pequeno se existir, senão skip.
    sample = Path("eval/fixtures/hello.wav")
    if not sample.exists():
        return CheckResult(group, "asr", "asr", False,
                           "fixture ausente (eval/fixtures/hello.wav)", skipped=True)
    try:
        with sample.open("rb") as fh:
            r = sender("/audio/transcriptions",
                       data={"model": group},
                       files={"file": ("hello.wav", fh, "audio/wav")})
    except requests.RequestException as exc:
        return CheckResult(group, "asr", "asr", False, f"erro rede: {exc}")
    if r.status_code != 200:
        return CheckResult(group, "asr", "asr", False,
                           f"HTTP {r.status_code}: {r.text[:120]}")
    ok, ev = verdict_asr(r.json())
    return CheckResult(group, "asr", "asr", ok, ev)


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


# ---------------------------------------------------------------------------
# Runner + relatório
# ---------------------------------------------------------------------------


def run_one(row: dict, sender: Sender | None, live: bool, *, stream: bool = False
            ) -> list[CheckResult]:
    mod = row["modality"]
    grp = row["group"]
    if not live:
        return [CheckResult(grp, mod, "smoke", False, "modo dry (use --live)",
                            skipped=True)]
    assert sender is not None
    if mod == "embedding":
        return [run_embedding(sender, grp)]
    if mod == "image":
        return [run_image(sender, grp)]
    if mod == "tts":
        return [run_tts(sender, grp)]
    if mod == "asr":
        return [run_asr(sender, grp)]
    # chat: texto + thinking conforme ON/OFF. Com --stream, roda também o caso SSE.
    thinking = "disabled" if mod == "chat-fast" else "on"
    out = [run_chat(sender, grp, thinking=thinking)]
    if stream and mod.startswith("chat"):
        out.append(run_chat(sender, grp, stream=True))
    return out


def update_matrix(results: list[CheckResult]) -> None:
    """Escreve status/evidência na planilha-mãe (por grupo+test)."""
    if not MATRIX_CSV.exists():
        return
    by_group: dict[str, tuple[str, str]] = {}
    for r in results:
        by_group[r.group] = (r.status(), f"{r.test}: {r.evidence}")
    lines = list(csv.reader(MATRIX_CSV.open(encoding="utf-8")))
    header = lines[0]
    gi, si, ei = header.index("group"), header.index("status"), header.index("evidence")
    for line in lines[1:]:
        if line[gi] in by_group:
            line[si], line[ei] = by_group[line[gi]]
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
    ap.add_argument("--out", help="grava markdown de resultado aqui")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="pausa (s) ENTRE grupos no modo --live; respeita rate 60 rpm "
                         "(use ~1.1 p/ varreduras grandes)")
    args = ap.parse_args(argv)

    rows = load_groups()
    sel = select(rows, args.family, args.only_id)
    # Sem seletor nenhum (--family/--id/--all) => nada roda (evita disparo acidental).
    if not (args.family or args.only_id or args.all):
        sel = []
    elif args.all:
        sel = rows

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
        return 0
    if not sel:
        print("nada selecionado (use --family/--id/--all)", file=sys.stderr)
        return 2

    cfg = proxy_config()
    sender = make_sender(cfg) if args.live else None
    results: list[CheckResult] = []
    for i, r in enumerate(sel):
        if args.live and args.sleep > 0 and i > 0:
            time.sleep(args.sleep)
        results.extend(run_one(r, sender, args.live, stream=args.stream))

    _print_and_export(results, args.live, args.out, write_matrix=True)
    npass = sum(1 for x in results if x.passed)
    nskip = sum(1 for x in results if x.skipped)
    return 0 if npass == len(results) - nskip else 1


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
             "| grupo | modalidade | teste | status | evidência |",
             "| --- | --- | --- | --- | --- |"]
    for x in results:
        lines.append(f"| {x.group} | {x.modality} | {x.test} | {x.status()} "
                     f"| {x.evidence} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
