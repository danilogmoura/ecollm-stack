"""S90 · B1 — Agregador dos eventos do MCP ``rag_search`` (latência + SLO).

O ``mcpsrv/rag_server.py`` EMITE eventos estruturados (uma linha JSON por evento)
em stderr, mas até aqui nada os lia — o dado era emitido e descartado. Este módulo
lê esse log e produz um RELATÓRIO com:

  - distribuição de ``latency_ms`` (p50/p90/p95/max) da busca;
  - taxa de ``slo_breach`` (latência > ``SLO_LATENCY_MS`` = 200ms);
  - distribuição por ``kind`` (code/doc/config) e por ``profile``;
  - custo do diagnóstico de staleness (``rag_search_staleness`` → ``staleness_ms``).

Formato do evento (emitido por ``_log_line`` em ``rag_server.py``):
  {"event": "rag_search", "ts": ..., "repo": ..., "profile": ..., "query": ...,
   "k": ..., "kind": ..., "path_prefix": ..., "n_results": ..., "latency_ms": ...,
   "slo_ms": 200, "slo_breach": bool, "status": "ok"|"error:..."}
  {"event": "rag_search_staleness", "ts": ..., "staleness_ms": ..., "stale": bool}

O log é texto (uma linha JSON por evento). Linhas não-JSON são ignoradas (o log
pode conter ruído de outras fontes). A fonte é injetável (``line_source``) p/ testes.

Uso:
    .venv/bin/python -m eval.mcp_report                       # lê o log canônico
    .venv/bin/python -m eval.mcp_report --log <arquivo>       # log alternativo
    .venv/bin/python -m eval.mcp_report --out reports/mcp-report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

# SLO de latência da busca (espelha SLO_LATENCY_MS em mcpsrv/rag_server.py).
SLO_LATENCY_MS = 200

# Caminho canônico do log do MCP (S90/B2). O hook/entrypoint redireciona o stderr
# do servidor MCP para cá. Antes era `.planning/h4-mcp-stderr.log` (nome de
# experimento H4, sem rotação). S101: movido de `.planning/` (governança) para
# `reports/logs/` (diagnóstico local, gitignored).
DEFAULT_LOG = "reports/logs/mcp-stderr.log"


@dataclass
class SearchEvent:
    """Uma chamada ``rag_search`` (campos que importam p/ latência/SLO)."""

    ts: float
    repo: str
    profile: str
    kind: str | None
    latency_ms: float
    slo_ms: float
    slo_breach: bool
    status: str
    n_results: int


@dataclass
class StalenessEvent:
    """Uma medição do custo do diagnóstico de staleness."""

    ts: float
    staleness_ms: float
    stale: bool


@dataclass
class McpReport:
    """Agregado dos eventos do MCP."""

    searches: list[SearchEvent] = field(default_factory=list)
    staleness: list[StalenessEvent] = field(default_factory=list)
    malformed: int = 0  # linhas não-JSON ou eventos desconhecidos (ruído)


def parse_line(line: str) -> SearchEvent | StalenessEvent | None:
    """Converte UMA linha do log num evento, ou None se não for evento conhecido.

    Nunca levanta: linha vazia/ruído/JSON inválido → None (contabilizado como
    malformed pelo chamador).
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    ev = obj.get("event")
    if ev == "rag_search":
        try:
            return SearchEvent(
                ts=float(obj.get("ts") or 0.0),
                repo=str(obj.get("repo") or ""),
                profile=str(obj.get("profile") or ""),
                kind=obj.get("kind"),
                latency_ms=float(obj.get("latency_ms") or 0.0),
                slo_ms=float(obj.get("slo_ms") or SLO_LATENCY_MS),
                slo_breach=bool(obj.get("slo_breach")),
                status=str(obj.get("status") or "ok"),
                n_results=int(obj.get("n_results") or 0),
            )
        except (TypeError, ValueError):
            return None
    if ev == "rag_search_staleness":
        try:
            return StalenessEvent(
                ts=float(obj.get("ts") or 0.0),
                staleness_ms=float(obj.get("staleness_ms") or 0.0),
                stale=bool(obj.get("stale")),
            )
        except (TypeError, ValueError):
            return None
    return None


def aggregate(lines: Iterable[str]) -> McpReport:
    """Agrega as linhas do log num :class:`McpReport`."""
    rep = McpReport()
    for line in lines:
        ev = parse_line(line)
        if ev is None:
            if line.strip():
                rep.malformed += 1
            continue
        if isinstance(ev, SearchEvent):
            rep.searches.append(ev)
        else:
            rep.staleness.append(ev)
    return rep


def percentile(values: Sequence[float], p: float) -> float:
    """Percentil nearest-rank (mesma convenção do cache_report). 0 se vazio."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(len(ordered) * p)
    if idx >= len(ordered):
        idx = len(ordered) - 1
    return ordered[idx]


def _latency_stats(events: Sequence[SearchEvent]) -> dict:
    """p50/p90/p95/max + taxa de breach de um conjunto de eventos."""
    lat = [e.latency_ms for e in events]
    breaches = sum(1 for e in events if e.slo_breach)
    return {
        "calls": len(events),
        "p50": percentile(lat, 0.50),
        "p90": percentile(lat, 0.90),
        "p95": percentile(lat, 0.95),
        "max": max(lat) if lat else 0.0,
        "breaches": breaches,
        "breach_rate": (breaches / len(events)) if events else 0.0,
    }


def build_report(
    *,
    line_source: Callable[[], Iterable[str]] | None = None,
    log_path: str = DEFAULT_LOG,
) -> str:
    """Produz o relatório markdown. ``line_source`` injetável p/ testes."""
    if line_source is None:
        def line_source() -> Iterable[str]:  # noqa: E306 — closure simples
            try:
                with open(log_path, encoding="utf-8") as fh:
                    return fh.readlines()
            except FileNotFoundError:
                return []

    rep = aggregate(line_source())
    lines: list[str] = []
    lines.append("# MCP · Relatório de latência + SLO (`rag_search`)")
    lines.append("")
    lines.append(f"> Fonte: `{log_path}` (eventos JSON emitidos por `mcpsrv/rag_server.py`).")
    lines.append(f"> SLO de latência = **{SLO_LATENCY_MS} ms** (`SLO_LATENCY_MS`).")
    lines.append("")

    if not rep.searches:
        lines.append("_Nenhum evento `rag_search` encontrado._")
        if rep.malformed:
            lines.append("")
            lines.append(f"({rep.malformed} linha(s) não reconhecida(s) ignorada(s).)")
        return "\n".join(lines) + "\n"

    overall = _latency_stats(rep.searches)
    lines.append("## Totais")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("| --- | --- |")
    lines.append(f"| Chamadas | {overall['calls']:,} |")
    lines.append(f"| Latência p50 | {overall['p50']:.1f} ms |")
    lines.append(f"| Latência p90 | {overall['p90']:.1f} ms |")
    lines.append(f"| Latência p95 | {overall['p95']:.1f} ms |")
    lines.append(f"| Latência max | {overall['max']:.1f} ms |")
    lines.append(f"| **Breaches de SLO (> {SLO_LATENCY_MS} ms)** | "
                 f"**{overall['breaches']:,} ({overall['breach_rate']*100:.1f}%)** |")
    lines.append("")

    # Por kind.
    lines.append("## Por kind")
    lines.append("")
    lines.append("| Kind | Calls | p50 | p95 | max | Breach% |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for kind, evs in sorted(_group(rep.searches, lambda e: e.kind or "(null)").items()):
        s = _latency_stats(evs)
        lines.append(f"| `{kind}` | {s['calls']:,} | {s['p50']:.1f} | {s['p95']:.1f} | "
                     f"{s['max']:.1f} | {s['breach_rate']*100:.1f}% |")
    lines.append("")

    # Por profile.
    lines.append("## Por profile")
    lines.append("")
    lines.append("| Profile | Calls | p50 | p95 | max | Breach% |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for prof, evs in sorted(_group(rep.searches, lambda e: e.profile or "(null)").items()):
        s = _latency_stats(evs)
        lines.append(f"| `{prof}` | {s['calls']:,} | {s['p50']:.1f} | {s['p95']:.1f} | "
                     f"{s['max']:.1f} | {s['breach_rate']*100:.1f}% |")
    lines.append("")

    # Erros.
    errors = [e for e in rep.searches if e.status != "ok"]
    if errors:
        lines.append("## Chamadas com erro")
        lines.append("")
        lines.append("| Status | Calls |")
        lines.append("| --- | ---: |")
        for st, evs in sorted(_group(errors, lambda e: e.status).items()):
            lines.append(f"| `{st}` | {len(evs):,} |")
        lines.append("")

    # Staleness (custo do diagnóstico).
    if rep.staleness:
        st_ms = [e.staleness_ms for e in rep.staleness]
        stale_n = sum(1 for e in rep.staleness if e.stale)
        lines.append("## Diagnóstico de staleness (custo separado do SLO)")
        lines.append("")
        lines.append("| Métrica | Valor |")
        lines.append("| --- | --- |")
        lines.append(f"| Medições | {len(rep.staleness):,} |")
        lines.append(f"| staleness_ms p50 | {percentile(st_ms, 0.50):.2f} ms |")
        lines.append(f"| staleness_ms p95 | {percentile(st_ms, 0.95):.2f} ms |")
        lines.append(f"| Índice defasado (stale=true) | {stale_n:,} |")
        lines.append("")

    if rep.malformed:
        lines.append(f"_{rep.malformed} linha(s) não reconhecida(s) ignorada(s)._")
        lines.append("")

    return "\n".join(lines) + "\n"


def _group(items: Sequence, key: Callable) -> dict:
    """Agrupa preservando ordem de inserção (dict)."""
    out: dict = {}
    for it in items:
        out.setdefault(key(it), []).append(it)
    return out


# S90/B3: limiar de alerta da taxa de breach do SLO. Acima disto, o `main` emite
# um alerta (stderr) — fecha o loop: o evento já marca `slo_breach`, mas ninguém
# era notificado. Default 50% (o SLO de 200ms é aspiracional; a latência real
# inclui a ida ao embedder da query — ver relatório).
SLO_BREACH_ALERT_PCT = 50.0


def slo_alert(rep: McpReport, *, threshold_pct: float = SLO_BREACH_ALERT_PCT) -> str | None:
    """S90/B3: linha de alerta se a taxa de breach exceder ``threshold_pct``.

    Retorna None se não há eventos ou a taxa está abaixo do limiar. Nunca levanta.
    """
    if not rep.searches:
        return None
    stats = _latency_stats(rep.searches)
    rate_pct = stats["breach_rate"] * 100
    if rate_pct <= threshold_pct:
        return None
    return (
        f"[mcp][ALERTA] taxa de breach do SLO = {rate_pct:.1f}% "
        f"(> {threshold_pct:.0f}%) — {stats['breaches']}/{stats['calls']} chamadas "
        f"acima de {SLO_LATENCY_MS}ms (p50={stats['p50']:.0f}ms p95={stats['p95']:.0f}ms)"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relatório de latência/SLO do MCP (S90).")
    ap.add_argument("--log", default=DEFAULT_LOG, help="Caminho do log de eventos MCP.")
    ap.add_argument("--out", default=None, help="Escrever markdown neste arquivo.")
    ap.add_argument("--alert-threshold", type=float, default=SLO_BREACH_ALERT_PCT,
                    help="S90/B3: %% de breach acima do qual emite alerta (default 50).")
    args = ap.parse_args(argv)
    report = build_report(log_path=args.log)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"[mcp] relatório escrito em {args.out}", file=sys.stderr)
    else:
        print(report)
    # S90/B3: alerta de SLO (stderr, nunca no stdout do relatório).
    alert = slo_alert(aggregate(_read_lines(args.log)),
                      threshold_pct=args.alert_threshold)
    if alert:
        print(alert, file=sys.stderr)
    return 0


def _read_lines(path: str) -> Iterable[str]:
    """Lê as linhas do log (vazio se ausente). Helper do alerta B3."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.readlines()
    except FileNotFoundError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
