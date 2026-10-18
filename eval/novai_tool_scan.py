"""S119 — Sweep de contrato de TOOLS (tool_calls) em TODOS os modelos NovAI.

Foco declarado pelo usuário (2026-10-17): **encontrar inconsistências** — não
pass/fail binário. O S118 mediu 2 modelos-canônico e achou a assimetria stream
(``delta.content`` antes de ``delta.tool_calls`` com ``finish_reason=tool_calls``
— "deveria ser `.` / vem ` .`"). Este módulo percorre o catálogo inteiro e
classifica cada modelo por família/alvo.

Calibração JÁ MEDIDA (não re-medir, ver ``20-BACKLOG.md`` S118/S119):
  - non-stream glm-5/glm-4.7-flash: CONFORME
    (``message.tool_calls[0] = {id, type, index, function{name, arguments}}``).
  - stream dos mesmos: fala ANTES da chamada → ``FALA_ANTES``.
  - gateway manda ``arguments`` num chunk só; proxy fragmenta → ambas formas
    válidas, registradas como ``CHUNK_UNICO``/``FRAGMENTADO``.

DESIGN (mesmo padrão do harness):
  - vereditos são funções PURAS sobre dicts/strings → testáveis offline;
  - transport injetável (``sender`` de ``make_capturing_sender``);
  - saída: CSV por modelo + relatório markdown datado em ``reports/``.

Uso:
    .venv/bin/python -m eval.novai_tool_scan --list-models [--target proxy]
    .venv/bin/python -m eval.novai_tool_scan --live [--target proxy|gateway|both] \\
        [--limit N] [--sleep 1.5] [--out reports/...]
"""
from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import time as _time

from eval.novai_test import (
    TARGETS,
    Sender,
    _elapsed_ms,
    detect_sse_framing,
    make_capturing_sender,
    resolve_targets,
    target_config,
)

# ---------------------------------------------------------------------------
# Corpus de teste: prompt curto + tool obrigatória na prática. max_tokens
# pequeno limita o gasto; reasoning models podem estourar (registrado no notes).
# ---------------------------------------------------------------------------

TOOL = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Returna o clima de uma cidade.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "Cidade"}},
            "required": ["city"],
        },
    },
}]

SCAN_BODY = {
    "messages": [{
        "role": "user",
        "content": "Qual o clima em Tokyo? Use a ferramenta get_weather.",
    }],
    "tools": TOOL,
    "max_tokens": 256,
}

MATRIX_CSV = Path("reports/novai-test-matrix.csv")

# ---------------------------------------------------------------------------
# Catálogo de modelos
# ---------------------------------------------------------------------------


def chat_groups_from_matrix(path: Path = MATRIX_CSV) -> list[str]:
    """Grupos chat (chat + chat-fast) declarados na matriz-mãe (alvo proxy)."""
    rows = csv.DictReader(path.open(encoding="utf-8"))
    groups = {r["group"] for r in rows if r["modality"].startswith("chat")}
    return sorted(groups)


_NON_CHAT_HINTS = ("embed", "image", "flux", "wan", "cogview", "cogvideo",
                   "tts", "asr", "audio", "speech", "rerank")


def chat_models_from_inventory(data: list[dict]) -> list[str]:
    """Ids de chat a partir de um payload ``GET /models`` (heurística de nome).

    Modelos de visão (``*-v*`` tipo glm-4.6v) ficam DENTRO — aceitam chat e
    tools; apenas modais não-chat (embed/img/tts/asr) são excluídos.
    """
    out = []
    for m in data:
        mid = m.get("id", "")
        low = mid.lower()
        if any(h in low for h in _NON_CHAT_HINTS):
            continue
        out.append(mid)
    return sorted(out)


# ---------------------------------------------------------------------------
# Veredites puros
# ---------------------------------------------------------------------------

# non-stream
NS_CONFORME = "conforme"
NS_IRREGULAR = "irregular_content_e_tool"
NS_SEM_TOOLCALL = "sem_tool_call"
NS_ERRO = "erro"

# stream — ordem content x tool_calls
ST_SO_TOOLS = "so_tools"          # canônico OpenAI
ST_FALA_ANTES = "fala_antes"      # irregularidade S118
ST_FALA_DEPOIS = "fala_depois"
ST_AMBIOS = "ambos_intercalados"
ST_SEM_TOOLCALL = "sem_tool_call"
ST_ERRO = "erro"

# fragmentação de arguments
ARG_CHUNK_UNICO = "chunk_unico"
ARG_FRAGMENTADO = "fragmentado"
ARG_AUSENTE = "ausente"


@dataclass
class ToolCallInfo:
    """Resumo extraído de um array ``tool_calls`` (non-stream ou agregado)."""

    n: int = 0
    ids_ok: bool = False
    types_function: bool = False
    names: list[str] = field(default_factory=list)
    args_parseavel: bool = False
    args_vazios: bool = False


def inspect_tool_calls(tool_calls: object) -> ToolCallInfo:
    """Valida shape OpenAI de ``message.tool_calls`` (puro)."""
    info = ToolCallInfo()
    if not isinstance(tool_calls, list) or not tool_calls:
        return info
    info.n = len(tool_calls)
    ok_id = ok_type = ok_args = True
    names, empty = [], False
    for tc in tool_calls:
        if not isinstance(tc, dict):
            ok_id = ok_type = ok_args = False
            break
        fn = tc.get("function") or {}
        names.append(fn.get("name", ""))
        raw = fn.get("arguments")
        if not isinstance(raw, str) or not raw.strip():
            empty = True
        else:
            try:
                json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                ok_args = False
        if not isinstance(tc.get("id"), str) or not tc.get("id"):
            ok_id = False
        if tc.get("type") != "function":
            ok_type = False
    info.ids_ok = ok_id
    info.types_function = ok_type
    info.names = names
    info.args_parseavel = ok_args and not empty
    info.args_vazios = empty
    return info


def verdict_tool_nonstream(resp: object, status_code: int = 200) -> tuple[str, str]:
    """Classifica resposta non-stream com tools. Retorna (codigo, evidencia)."""
    if status_code != 200 or not isinstance(resp, dict) or "choices" not in resp:
        return NS_ERRO, f"http={status_code}"
    ch = (resp.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    fr = ch.get("finish_reason")
    content = (msg.get("content") or "").strip()
    tcs = msg.get("tool_calls")
    if not tcs:
        return NS_SEM_TOOLCALL, f"finish={fr!r} content={content[:40]!r}"
    info = inspect_tool_calls(tcs)
    if not (info.ids_ok and info.types_function and info.args_parseavel):
        return NS_ERRO, (f"shape invalido: ids={info.ids_ok} type={info.types_function} "
                         f"args={info.args_parseavel}")
    if content:
        return NS_IRREGULAR, f"content+tool_calls: {content[:40]!r}"
    return NS_CONFORME, f"names={info.names} finish={fr!r}"


def parse_stream_deltas(raw_text: str) -> dict:
    """Extrai a sequência de deltas de um corpo SSE bruto (puro).

    Retorna dict com: ``events`` (n de data-json parseados), ``has_done``,
    ``content_parts`` (lista de strings nao-vazias na ordem),
    ``tool_chunks`` (lista de dicts delta.tool_calls brutos),
    ``finish_reasons``, ``arg_chunks_por_index`` (dict idx->n chunks),
    ``error`` (str|None).
    """
    out: dict = {"events": 0, "has_done": False, "content_parts": [],
                 "tool_chunks": [], "finish_reasons": [],
                 "arg_chunks_por_index": {}, "error": None}
    for line in (raw_text or "").split("\n"):
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            out["has_done"] = True
            continue
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            out["error"] = f"linha nao-JSON: {payload[:40]!r}"
            return out
        out["events"] += 1
        for ch in obj.get("choices") or []:
            if ch.get("finish_reason"):
                out["finish_reasons"].append(ch["finish_reason"])
            delta = ch.get("delta") or {}
            c = delta.get("content")
            if isinstance(c, str) and c:
                out["content_parts"].append(c)
            for tc in delta.get("tool_calls") or []:
                out["tool_chunks"].append(tc)
                fn = (tc or {}).get("function") or {}
                a = fn.get("arguments")
                if isinstance(a, str) and a:
                    idx = tc.get("index", 0)
                    out["arg_chunks_por_index"][idx] = \
                        out["arg_chunks_por_index"].get(idx, 0) + 1
    return out


def classify_stream_sequence(info: dict) -> str:
    """Código de sequência content×tool_calls a partir de ``parse_stream_deltas``."""
    if info["error"] is not None or info["events"] == 0 or not info["has_done"]:
        return ST_ERRO
    has_content = bool(info["content_parts"])
    has_tools = bool(info["tool_chunks"])
    if not has_tools:
        return ST_SEM_TOOLCALL
    if not has_content:
        return ST_SO_TOOLS
    # primeira aparição de tool_call vs primeiro content
    first_tool_at = next((i for i, tc in enumerate(info["tool_chunks"])), None)
    # posição relativa: reconstrói ordem global varrendo de novo é caro; usamos
    # heurística determinista: tools aparecem depois de todo o content?
    # Os tool_chunks foram coletados em ordem; se o ultimo evento tinha tool e
    # content existiu antes => fala antes. Detectamos via contagem simples:
    del first_tool_at
    tail_fr = info["finish_reasons"][-1] if info["finish_reasons"] else None
    if tail_fr != "tool_calls":
        return ST_AMBIOS
    # content presente E finish=tool_calls => fala acompanhou a chamada.
    # Sem offsets globais não distinguimos antes/depois com 100% certeza;
    # o formato do gateway/proxy observado emite content primeiro — mantemos
    # granularidade real: usa offsets gravados nos chunks quando possível.
    return ST_FALA_ANTES


def _classify_stream_sequence_with_offsets(raw_text: str, info: dict) -> str:
    """Versão refinada: refaz o parse guardando offset de cada evento.

    Separada de ``classify_stream_sequence`` para manter o primeiro puro e
    trivial; esta usa a posição das linhas no texto original.
    """
    base = classify_stream_sequence(info)
    if base in (ST_ERRO, ST_SEM_TOOLCALL, ST_SO_TOOLS):
        return base
    first_content_off = None
    first_tool_off = None
    off = 0
    for line in (raw_text or "").split("\n"):
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            try:
                obj = json.loads(line[5:].strip())
            except (json.JSONDecodeError, ValueError):
                off += len(line) + 1
                continue
            for ch in obj.get("choices") or []:
                d = ch.get("delta") or {}
                if d.get("content") and first_content_off is None:
                    first_content_off = off
                if d.get("tool_calls") and first_tool_off is None:
                    first_tool_off = off
        off += len(line) + 1
    if first_content_off is None:
        return ST_SO_TOOLS
    if first_tool_off is None:
        return ST_SEM_TOOLCALL
    if first_content_off < first_tool_off:
        last_content_off = first_content_off
        off = 0
        for line in (raw_text or "").split("\n"):
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                try:
                    obj = json.loads(line[5:].strip())
                except (json.JSONDecodeError, ValueError):
                    off += len(line) + 1
                    continue
                for ch in obj.get("choices") or []:
                    if (ch.get("delta") or {}).get("content"):
                        last_content_off = off
            off += len(line) + 1
        if last_content_off > first_tool_off:
            return ST_AMBIOS
        return ST_FALA_ANTES
    return ST_FALA_DEPOIS


def aggregate_arguments(info: dict) -> tuple[str, bool, str]:
    """(fragmentacao, parseavel_final, args_concatenados) por tool_call index 0."""
    if not info["tool_chunks"]:
        return ARG_AUSENTE, False, ""
    parts: dict[int, list[str]] = {}
    for tc in info["tool_chunks"]:
        fn = (tc or {}).get("function") or {}
        a = fn.get("arguments")
        if isinstance(a, str) and a:
            parts.setdefault(tc.get("index", 0), []).append(a)
    joined = "".join(parts.get(0, []))
    nchunks = len(parts.get(0, []))
    frag = ARG_CHUNK_UNICO if nchunks <= 1 else ARG_FRAGMENTADO
    parseavel = False
    try:
        json.loads(joined)
        parseavel = bool(joined.strip())
    except (json.JSONDecodeError, ValueError):
        parseavel = False
    return frag, parseavel, joined


def verdict_tool_stream(info: dict, raw_text: str = "") -> tuple[str, str]:
    """Classifica stream com tools. Retorna (codigo, evidencia)."""
    code = _classify_stream_sequence_with_offsets(raw_text, info) if raw_text \
        else classify_stream_sequence(info)
    if code == ST_ERRO:
        return code, info["error"] or f"events={info['events']} done={info['has_done']}"
    frag, parseavel, joined = aggregate_arguments(info)
    ev = (f"fala={sum(len(p) for p in info['content_parts'])}ch "
          f"args={frag}/{('ok' if parseavel else 'INVALID')}"
          f" finish={info['finish_reasons'][-1:] or '?'}")
    if code in (ST_SO_TOOLS, ST_FALA_ANTES, ST_FALA_DEPOIS, ST_AMBIOS) and not parseavel:
        return ST_ERRO, f"args nao-parseaveis ({joined[:40]!r})"
    return code, ev


# ---------------------------------------------------------------------------
# Execução live (transport injetável)
# ---------------------------------------------------------------------------


@dataclass
class ScanRow:
    target: str
    model: str
    ns_code: str = "-"
    ns_ev: str = ""
    st_code: str = "-"
    st_ev: str = ""
    framing: str = ""
    ns_ms: float = 0.0
    st_ms: float = 0.0
    error: str = ""

    @property
    def irregular(self) -> bool:
        return self.ns_code in (NS_IRREGULAR, NS_SEM_TOOLCALL, NS_ERRO) or \
            self.st_code in (ST_FALA_ANTES, ST_FALA_DEPOIS, ST_AMBIOS,
                             ST_SEM_TOOLCALL, ST_ERRO)


def scan_model(sender: Sender, model: str, *, stream_raw_sink: dict | None = None
               ) -> ScanRow:
    """2 chamadas (non-stream + stream) para ``model`` via ``sender`` já autenticado."""
    row = ScanRow(target="", model=model)
    body = {"model": model, **SCAN_BODY}
    try:
        t0 = _time.monotonic()
        r = sender("/chat/completions", json_body=body)
        row.ns_ms = _elapsed_ms(t0)
        row.ns_code, row.ns_ev = verdict_tool_nonstream(r.json(), r.status_code)
    except Exception as exc:  # noqa: BLE001 - registro, não engano
        row.ns_code, row.ns_ev = NS_ERRO, f"transport: {type(exc).__name__}"
    try:
        t0 = _time.monotonic()
        rs = sender("/chat/completions", json_body={**body, "stream": True},
                    stream=True)
        raw = rs.text or ""
        row.st_ms = _elapsed_ms(t0)
        row.framing = repr(detect_sse_framing(raw))
        info = parse_stream_deltas(raw)
        row.st_code, row.st_ev = verdict_tool_stream(info, raw)
        if stream_raw_sink is not None:
            stream_raw_sink["raw"] = raw[:4000]
    except Exception as exc:  # noqa: BLE001
        row.st_code, row.st_ev = ST_ERRO, f"transport: {type(exc).__name__}"
    return row


def run_scan(targets: list[str], *, sleep: float = 1.5,
             limit: int | None = None,
             progress: Callable[[str], None] = print,
             sender_factory: Callable[[str], Sender] | None = None
             ) -> list[ScanRow]:
    """Varredura completa: catálogo por alvo, 2 chamadas por modelo.

    ``sender_factory``/``models_provider`` injetáveis para teste offline; o
    default usa o harness real (S119).
    """
    rows: list[ScanRow] = []
    for t in targets:
        cfg = target_config(t)
        sender = sender_factory(t) if sender_factory else make_capturing_sender(cfg, {})
        if t == "proxy":
            models = chat_groups_from_matrix()
        else:
            inv = sender("/models", method="GET")
            models = chat_models_from_inventory(inv.json().get("data", []))
        if limit:
            models = models[:limit]
        progress(f"[{t}] {len(models)} modelos chat")
        for i, m in enumerate(models):
            row = scan_model(sender, m)
            row.target = t
            rows.append(row)
            progress(f"  [{t} {i + 1}/{len(models)}] {m}: ns={row.ns_code} "
                     f"st={row.st_code}")
            if i < len(models) - 1 and sleep:
                time.sleep(sleep)
    return rows


# ---------------------------------------------------------------------------
# Saídas: CSV + relatório
# ---------------------------------------------------------------------------

CSV_COLUMNS = ("target", "model", "ns_code", "ns_ev", "st_code", "st_ev",
               "framing", "ns_ms", "st_ms", "irregular")


def rows_to_csv(rows: list[ScanRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for r in rows:
            w.writerow([r.target, r.model, r.ns_code, r.ns_ev, r.st_code,
                        r.st_ev, r.framing, f"{r.ns_ms:.0f}", f"{r.st_ms:.0f}",
                        "sim" if r.irregular else "nao"])


_LABELS_NS = {NS_CONFORME: "✅ conforme", NS_IRREGULAR: "⚠️ content+tool",
              NS_SEM_TOOLCALL: "❌ sem tool_call", NS_ERRO: "❌ erro"}
_LABELS_ST = {ST_SO_TOOLS: "✅ só tools", ST_FALA_ANTES: "⚠️ fala antes",
              ST_FALA_DEPOIS: "⚠️ fala depois", ST_AMBIOS: "⚠️ intercalado",
              ST_SEM_TOOLCALL: "❌ sem tool_call", ST_ERRO: "❌ erro"}


def build_report(rows: list[ScanRow], *, out_path: Path) -> str:
    from collections import Counter
    ns = Counter(r.ns_code for r in rows)
    st = Counter(r.st_code for r in rows)
    irr = [r for r in rows if r.irregular]
    lines = [
        f"# S119 — Sweep de contrato de tools ({date.today().isoformat()})",
        "",
        f"- Modelo-alvo: **{len({(r.target, r.model) for r in rows})}** "
        f"(chamadas non-stream + stream cada)",
        f"- Irregularidades encontradas: **{len(irr)} linhas** "
        f"({len({r.model for r in irr})} modelos distintos)",
        "",
        "## Distribuição non-stream",
        "",
        "| codigo | n |", "| --- | --- |",
    ]
    for k, v in ns.most_common():
        lines.append(f"| {_LABELS_NS.get(k, k)} | {v} |")
    lines += ["", "## Distribuição stream", "", "| codigo | n |", "| --- | --- |"]
    for k, v in st.most_common():
        lines.append(f"| {_LABELS_ST.get(k, k)} | {v} |")
    lines += ["", "## Tabela por modelo", "",
              "| alvo | modelo | non-stream | stream | evidência stream |",
              "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r.target} | `{r.model}` | {_LABELS_NS.get(r.ns_code, r.ns_code)} "
                     f"| {_LABELS_ST.get(r.st_code, r.st_code)} | {r.st_ev} |")
    lines += ["", "_Gerado por `eval/novai_tool_scan.py` (S119). "
              "Foco: mapear inconsistências do contrato de tools NovAI vs OpenAI._", ""]
    text = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI live
    import argparse
    from ingest.embed import load_dotenv
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="executa as chamadas reais")
    ap.add_argument("--target", default="both", choices=[*TARGETS, "both"])
    ap.add_argument("--limit", type=int, default=None, help="so N primeiros modelos")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--out", default=None)
    ap.add_argument("--list-models", action="store_true")
    args = ap.parse_args(argv)

    targets = resolve_targets(args.target)
    if args.list_models:
        for t in targets:
            if t == "proxy":
                ms = chat_groups_from_matrix()
            else:
                sink: dict = {}
                ms = chat_models_from_inventory(
                    make_capturing_sender(target_config(t), {})("/models", method="GET")
                    .json().get("data", []))
            print(f"{t}: {len(ms)}")
            for m in ms:
                print(f"  {m}")
        return 0
    if not args.live:
        print("# modo dry — use --live para a varredura real")
        return 0
    rows = run_scan(targets, sleep=args.sleep, limit=args.limit)
    today = date.today().isoformat()
    out = Path(args.out) if args.out else Path(f"reports/{today}-novai-tool-scan.md")
    rows_to_csv(rows, out.with_suffix(".csv"))
    build_report(rows, out_path=out)
    n_irr = sum(1 for r in rows if r.irregular)
    print(f"OK: {len(rows)} modelos × 2 alvos? -> {len(rows)} linhas; "
          f"irregulares={n_irr}; relatorio={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
