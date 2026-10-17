"""S103 / P3b — log estruturado (jsonl) dos smokes NovAI, com redação de segredo.

Regra de ouro: **nenhum segredo sai daqui.** Toda linha passa por ``redact()``
antes de ser serializada; o teste de aceitação é ``grep`` do prefixo da chave no
arquivo = 0 hits.

Formato: uma linha JSON por check, em
``reports/logs/<YYYY-MM-DD>-novai-<family>.jsonl``. Grava **sucesso E falha**
(achado é dado; só o skip de dry-run não é registrado).

Campos por linha:
    ts, group, modality, test, target, status, passed, skipped,
    latency_ms, cost_usd, evidence, notes, run_id
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

# Prefixos de chave conhecidos neste stack. Ordem importa: o mais longo primeiro
# para não deixar sufixo solto (ex.: "nvai-" casando antes de "nvai-sk-").
SECRET_PREFIXES = ("nvai-", "sk-", "sk_live_", "sk_test_", "Bearer ")

REDACTED = "***REDACTED***"

# Padrões genéricos: qualquer token longo colado a um prefixo conhecido, e
# qualquer header Authorization inline.
_PATTERNS = [
    re.compile(r"(?i)\b(nvai-|sk_live_|sk_test_|sk-)[A-Za-z0-9_\-]{4,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{4,}"),
]


def redact(text: str) -> str:
    """Remove qualquer credencial reconhecível de ``text``.

    Puro e idempotente: ``redact(redact(x)) == redact(x)``.
    """
    if not text:
        return text
    out = text
    for pat in _PATTERNS:
        out = pat.sub(lambda m: m.group(1) + REDACTED, out)
    return out


def redact_obj(obj):
    """Aplica ``redact`` recursivamente em str de dicts/listas."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj


def log_path(family: str, *, root: str | Path = "reports/logs",
             when: datetime | None = None) -> Path:
    """Caminho canônico do jsonl do dia/família."""
    when = when or datetime.now(timezone.utc)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", family or "all")
    return Path(root) / f"{when:%Y-%m-%d}-novai-{safe}.jsonl"


def result_to_record(result, *, run_id: str = "",
                     when: datetime | None = None) -> dict:
    """Converte um ``CheckResult`` em dict serializável (já redigido)."""
    when = when or datetime.now(timezone.utc)
    rec = {
        "ts": when.isoformat(timespec="seconds"),
        "run_id": run_id,
        "group": result.group,
        "modality": result.modality,
        "test": result.test,
        "target": result.target,
        "status": result.status(),
        "passed": bool(result.passed),
        "skipped": bool(result.skipped),
        "latency_ms": result.latency_ms,
        "cost_usd": result.cost_usd,
        "evidence": result.evidence,
        "notes": result.notes,
    }
    return redact_obj(rec)


def write_records(records: list[dict], path: str | Path) -> Path:
    """Anexa ``records`` (um JSON por linha) em ``path``, criando o diretório."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(redact_obj(rec), ensure_ascii=False) + "\n")
    return p


def log_results(results, *, family: str, run_id: str = "",
                root: str | Path = "reports/logs") -> Path | None:
    """Grava todos os resultados não-skipped no jsonl do dia/família.

    Retorna o caminho gravado, ou ``None`` se não havia nada a gravar.
    """
    recs = [result_to_record(r, run_id=run_id) for r in results if not r.skipped]
    if not recs:
        return None
    return write_records(recs, log_path(family, root=root))
