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

    npass = sum(1 for x in results if x.passed)
    nskip = sum(1 for x in results if x.skipped)
    print(f"checks={len(results)} pass={npass} fail={len(results)-npass-nskip} "
          f"skip={nskip}")
    for x in results:
        mark = {"pass": "✅", "fail": "❌", "skipped": "⬜"}[x.status()]
        print(f"  {mark} [{x.modality}] {x.group} :: {x.test} — {x.evidence}")

    if args.live:
        update_matrix(results)
    if args.out:
        Path(args.out).write_text(_to_md(results), encoding="utf-8")
    return 0 if npass == len(results) - nskip else 1


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
