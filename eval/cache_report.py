"""FASE 6 · C6 — Instrumentar hit-rate + custo de context cache (T-CACHE-6).

Le os SpendLogs do proxy LiteLLM (tabela ``LiteLLM_SpendLogs``), extrai os campos
de cache que o Token Plan já devolve no usage e produz um RELATÓRIO com:

  - % de prompt-tokens que caíram em HIT de cache (economia REAL medida, não projetada);
  - custo estimado COM cache (o ``spend`` que o LiteLLM já cobra) vs SEM cache
    (reprecificar todos os tokens de entrada ao preço cheio de input);
  - distribuição por modelo-group e por dia;
  - **cauda NÃO-cacheada por chamada (H1)** — ``uncached = prompt − cached`` com
    média e percentis (p50/p90/p95) e custo a preço cheio. É o único alvo das
    alavancas de compactação/janela: a zona em HIT já custa ~0 (break-even quente
    0,5% — ver ``10-STATE.md`` §5 "FASE 8 / headroom").

Onde vivem os campos (mapeado empiricamente em 2026-09-27):
  metadata->usage_object->prompt_tokens_details->cached_tokens   (hit implícito)
  metadata->additional_usage_values->cache_read_input_tokens      (hit explícito)
  metadata->cost_breakdown->cache_read_cost                       (custo do hit)

Acesso ao banco: o container ``litellm-db`` NÃO expõe porta no host (só a rede
interna docker). Por isso o acesso padrão é via ``docker compose exec -T litellm-db
psql``. Pode-se injetar outra fonte de linhas (testes, API HTTP futura) passando
um ``row_source`` para :func:`build_report`.

Uso:
    .venv/bin/python -m eval.cache_report                 # janela toda, markdown p/ stdout
    .venv/bin/python -m eval.cache_report --days 7        # últimos 7 dias
    .venv/bin/python -m eval.cache_report --out .planning/c6-cache-report.md
    .venv/bin/python -m eval.cache_report --model qwen3.8-flash

Ressalva S30: o endpoint real é Token Plan (Créditos), então o ``$`` aqui é
CUSTO-EQUIVALENTE PAYG (preços de C2). A métrica canônica de economia é em TOKENS
(% prompt-tok em hit); a ordem de grandeza do $ vale também em créditos.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

# ---------------------------------------------------------------------------
# Preços PAYG (C2), USD por 1M tokens → por token (÷ 1e6). Fonte:
# .planning/PLANO-FASE6-CACHE.md §C2. Usados só para o "sem cache" ilustrativo;
# o "com cache" vem direto do campo ``spend`` (já calculado pelo LiteLLM c/ estes preços).
# ---------------------------------------------------------------------------
PRICE_PER_MTOKEN = {
    "qwen3.8-flash": {"input": 0.15, "output": 0.47},
    "qwen3.8-max": {"input": 2.00, "output": 6.00},
}
DEFAULT_INPUT_PRICE = PRICE_PER_MTOKEN["qwen3.8-flash"]["input"]  # fallback conservador


def price_for(model_group: str | None) -> dict[str, float]:
    """Resolve o preço de input (USD/1M) para um model_group, tratando aliases.

    Aliases ``*-fast`` compartilham o preço do modelo real (mesmo upstream — C3).
    Desconhecido cai no DEFAULT_INPUT_PRICE (flash, o mais barato → subestima o
    ganho, escolha conservadora).
    """
    key = (model_group or "").replace("-fast", "")
    return PRICE_PER_MTOKEN.get(key, {"input": DEFAULT_INPUT_PRICE})


# ---------------------------------------------------------------------------
# Modelo de dados + métricas PURAS (testáveis sem DB/rede)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallRow:
    """Uma chamada agregada dos SpendLogs (campos que importam p/ cache)."""

    model_group: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    spend: float
    day: str  # YYYY-MM-DD (UTC)

    @property
    def uncached(self) -> int:
        """H1: prompt-tokens desta chamada que NÃO caíram em hit (custo cheio).

        É a única grandeza que as alavancas de compactação/janela atacam: reduzir
        ``cached`` não economiza nada (preço de hit ≈ 0). Chão em 0 por robustez —
        um ``cached`` maior que ``prompt`` (resposta anômala do upstream) não pode
        produzir cauda negativa nem inflar a economia.
        """
        return max(0, self.prompt_tokens - self.cached_tokens)


@dataclass(frozen=True)
class Metrics:
    """Totais + frações derivadas de um conjunto de chamadas."""

    calls: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    spend_with_cache: float
    cost_no_cache: float

    @property
    def hit_rate(self) -> float:
        """Fração dos prompt-tokens servidos por HIT de cache (0 se sem prompt)."""
        if self.prompt_tokens <= 0:
            return 0.0
        return self.cached_tokens / self.prompt_tokens

    @property
    def savings(self) -> float:
        """Economia em USD = (sem cache) − (com cache). Positiva = cache ajudou."""
        return self.cost_no_cache - self.spend_with_cache

    @property
    def savings_pct(self) -> float:
        if self.cost_no_cache <= 0:
            return 0.0
        return self.savings / self.cost_no_cache


def _safe_int(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def parse_row(raw: dict) -> CallRow:
    """Converte um dicionário (linha JSON vinda do SQL) num :class:`CallRow`.

    Aceita as chaves na forma quote-case do Postgres (``"startTime"``,
    ``"model_group"``, ``"prompt_tokens"`` …) tolerando ausências → 0.
    """
    start = raw.get("startTime") or raw.get("starttime") or ""
    day = str(start)[:10]  # ISO date prefixo; vira "" se ausente
    return CallRow(
        model_group=str(raw.get("model_group") or raw.get("modelGroup") or ""),
        prompt_tokens=_safe_int(raw.get("prompt_tokens")),
        completion_tokens=_safe_int(raw.get("completion_tokens")),
        cached_tokens=_safe_int(raw.get("cached_tokens")),
        spend=float(raw.get("spend") or 0.0),
        day=day,
    )


def compute_metrics(rows: Sequence[CallRow]) -> Metrics:
    """Agrega linhas em totais + projeta o custo SEM cache.

    Custo SEM cache = (prompt_tokens × preço_input_cheio) + (completion × preço_output),
    ambos ÷ 1e6. Assume pessimista que TODOS os tokens de entrada seriam cobrados
    cheios (sem nenhum hit) — é o contrafactual honesto p/ medir o ganho do cache.
    O ``spend`` (com cache) já reflete o desconto de ``cached_tokens`` aplicado pelo
    LiteLLM usando exatamente estes preços.
    """
    prompt = sum(r.prompt_tokens for r in rows)
    completion = sum(r.completion_tokens for r in rows)
    cached = sum(r.cached_tokens for r in rows)
    with_cache = sum(r.spend for r in rows)
    no_cache = 0.0
    for r in rows:
        p = price_for(r.model_group)
        no_cache += (r.prompt_tokens * p["input"]) / 1e6
        out_price = p.get("output", DEFAULT_INPUT_PRICE)
        no_cache += (r.completion_tokens * out_price) / 1e6
    return Metrics(
        calls=len(rows),
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_tokens=cached,
        spend_with_cache=with_cache,
        cost_no_cache=no_cache,
    )


def group_by(rows: Sequence[CallRow], key: Callable[[CallRow], str]) -> dict[str, list[CallRow]]:
    buckets: dict[str, list[CallRow]] = {}
    for r in rows:
        buckets.setdefault(key(r), []).append(r)
    return buckets


# ---------------------------------------------------------------------------
# H1 — cauda NÃO-cacheada (uncached = prompt − cached), por chamada
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UncachedStats:
    """Distribuição da cauda não-cacheada de um conjunto de chamadas.

    ``mean`` e percentis são em TOKENS por chamada; ``cost`` é o custo PAYG dessa
    cauda (o que se paga a preço cheio de input por ela). É o número que o H6
    precisa baixar — não o hit-rate, que já está no teto (95,6%, C6).
    """

    calls: int
    total: int
    mean: float
    p50: int
    p90: int
    p95: int
    max: int
    cost: float


def percentile_nearest_rank(sorted_values: Sequence[int], pct: float) -> int:
    """Percentil por nearest-rank: determinístico, sem interpolação fracionária,
    ⇒ devolve SEMPRE o valor de uma linha real (nada inventado entre pontos).

    Exige ``sorted_values`` ordenado. ``pct`` em [0, 100]; vazio → 0.
    """
    if not sorted_values:
        return 0
    rank = max(1, math.ceil((pct / 100.0) * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def compute_uncached(rows: Sequence[CallRow]) -> UncachedStats:
    """Resume a cauda não-cacheada (tokens + custo a preço cheio) de ``rows``.

    Custo por linha = ``uncached`` × preço_input(model_group) ÷ 1e6 — exatamente o
    trecho que reduzir `k` / cap de chunk / podar histórico atacaria. Vazio → zeros.
    """
    if not rows:
        return UncachedStats(calls=0, total=0, mean=0.0, p50=0, p90=0, p95=0, max=0, cost=0.0)
    values = sorted(r.uncached for r in rows)
    total = sum(values)
    cost = sum((r.uncached * price_for(r.model_group)["input"]) / 1e6 for r in rows)
    return UncachedStats(
        calls=len(values),
        total=total,
        mean=total / len(values),
        p50=percentile_nearest_rank(values, 50),
        p90=percentile_nearest_rank(values, 90),
        p95=percentile_nearest_rank(values, 95),
        max=values[-1],
        cost=cost,
    )


# ---------------------------------------------------------------------------
# SQL + acesso via docker compose exec
# ---------------------------------------------------------------------------

SQL_TEMPLATE = """\
SELECT
  json_build_object(
    'startTime', to_char("startTime", 'YYYY-MM-DD'),
    'model_group', model_group,
    'prompt_tokens', prompt_tokens,
    'completion_tokens', completion_tokens,
    'cached_tokens', COALESCE(
      NULLIF(metadata->'usage_object'->'prompt_tokens_details'->>'cached_tokens','')::int,
      NULLIF(metadata->'additional_usage_values'->>'cache_read_input_tokens','')::int,
      0),
    'spend', spend
  )::text AS row
FROM "LiteLLM_SpendLogs"
WHERE model_group LIKE 'qwen3.8%'
  {where_extra}
ORDER BY "startTime";
"""


def build_sql(days: int | None, model: str | None) -> str:
    where = []
    if days is not None:
        where.append(f'AND "startTime" >= now() - interval \'{int(days)} days\'')
    if model:
        safe = model.replace("'", "''")
        where.append(f"AND model_group = '{safe}'")
    return SQL_TEMPLATE.format(where_extra=" ".join(where))


def fetch_rows_via_docker(sql: str, service: str = "litellm-db") -> list[dict]:
    """Executa ``sql`` via ``docker compose exec -T <service> psql`` e decodifica JSON."""
    cmd = [
        "docker", "compose", "exec", "-T", service,
        "psql", "-U", "litellm", "-d", "litellm", "-P", "pager=off", "-tA", "-c", sql,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"psql falhou (rc={proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    rows: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # ignora cabeçalhos/ruído não-JSON
    return rows


def build_report(
    days: int | None = None,
    model: str | None = None,
    *,
    row_source: Callable[[str], list[dict]] | None = None,
) -> str:
    """Produz o relatório markdown. ``row_source`` injetável p/ testes."""
    source = row_source or fetch_rows_via_docker
    raws = source(build_sql(days, model))
    rows = [parse_row(r) for r in raws]
    overall = compute_metrics(rows)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    window = f"últimos {days} dias" if days else "janela completa"
    scope = f"model_group = {model}" if model else "todos qwen3.8-*"

    lines: list[str] = []
    lines.append("# C6 · Relatório de context cache (hit-rate + custo)")
    lines.append("")
    lines.append(f"> Gerado em {now}. Janela: **{window}** · Escopo: `{scope}`.")
    lines.append("> Fonte: `LiteLLM_SpendLogs` (proxy :4000). Campos de cache em "
                 "`metadata.usage_object.prompt_tokens_details.cached_tokens`.")
    lines.append("> **Ressalva S30:** `$` = custo-EQUIVALENTE PAYG (Token Plan cobra "
                 "em Créditos). Métrica canônica = % prompt-tok em hit.")
    lines.append("")
    if overall.calls == 0:
        lines.append("_Nenhuma chamada encontrada para essa janela/escopo._")
        return "\n".join(lines) + "\n"

    lines.append("## Totais")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("| --- | --- |")
    lines.append(f"| Chamadas | {overall.calls:,} |")
    lines.append(f"| Prompt-tokens | {overall.prompt_tokens:,} |")
    lines.append(f"| Completion-tokens | {overall.completion_tokens:,} |")
    lines.append(f"| Cached-tokens (hit) | {overall.cached_tokens:,} |")
    lines.append(f"| **% prompt-tok em HIT** | **{overall.hit_rate*100:.1f}%** |")
    unc = compute_uncached(rows)
    lines.append(f"| Cauda NÃO-cacheada (total tok) | {unc.total:,} |")
    lines.append(f"| **Cauda Não-cacheada por chamada (média)** | **{unc.mean:,.0f} tok** |")
    lines.append(f"| Cauda Não-cacheada p50/p90/p95/max | "
                 f"{unc.p50:,}/{unc.p90:,}/{unc.p95:,}/{unc.max:,} tok |")
    lines.append(f"| Custo da cauda não-cacheada (preço cheio) | ${unc.cost:,.4f} |")
    lines.append(f"| Custo COM cache (spend real) | ${overall.spend_with_cache:,.4f} |")
    lines.append(f"| Custo SEM cache (projeção) | ${overall.cost_no_cache:,.4f} |")
    lines.append(f"| **Economia** | **${overall.savings:,.4f} ({overall.savings_pct*100:.1f}%)** |")
    lines.append("")

    lines.append("## Por modelo-group")
    lines.append("")
    lines.append("| Model group | Calls | Prompt-tok | Hit% | Com cache $ | Sem cache $ | Economia $ |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for grp, brows in sorted(group_by(rows, lambda r: r.model_group).items()):
        m = compute_metrics(brows)
        lines.append(
            f"| `{grp}` | {m.calls:,} | {m.prompt_tokens:,} | {m.hit_rate*100:.1f}% | "
            f"{m.spend_with_cache:,.4f} | {m.cost_no_cache:,.4f} | {m.savings:,.4f} |"
        )
    lines.append("")

    lines.append("## Cauda não-cacheada por chamada (H1 — alvo das alavancas)")
    lines.append("")
    lines.append("`uncached = prompt − cached`, por chamada. Só esta cauda responde a")
    lines.append("reduzir `k` / cap de chunk / podar histórico: a zona em HIT já custa ~0")
    lines.append("(break-even quente 0,5% — `10-STATE.md` §5). Percentis nearest-rank.")
    lines.append("")
    lines.append("| Recorte | Calls | Uncached média | p50 | p90 | p95 | max | Custo $ |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    lines.append(f"| **TODAS** | {unc.calls:,} | {unc.mean:,.0f} | {unc.p50:,} | "
                 f"{unc.p90:,} | {unc.p95:,} | {unc.max:,} | {unc.cost:,.4f} |")
    for grp, brows in sorted(group_by(rows, lambda r: r.model_group).items()):
        u = compute_uncached(brows)
        lines.append(f"| `{grp}` | {u.calls:,} | {u.mean:,.0f} | {u.p50:,} | {u.p90:,} | "
                     f"{u.p95:,} | {u.max:,} | {u.cost:,.4f} |")
    for day, drows in sorted(group_by(rows, lambda r: r.day).items()):
        u = compute_uncached(drows)
        lines.append(f"| dia {day or '?'} | {u.calls:,} | {u.mean:,.0f} | {u.p50:,} | "
                     f"{u.p90:,} | {u.p95:,} | {u.max:,} | {u.cost:,.4f} |")
    lines.append("")

    lines.append("## Por dia (UTC)")
    lines.append("")
    lines.append("| Dia | Calls | Prompt-tok | Hit% | Com cache $ | Economia $ |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for day, drows in sorted(group_by(rows, lambda r: r.day).items()):
        m = compute_metrics(drows)
        lines.append(
            f"| {day or '?'} | {m.calls:,} | {m.prompt_tokens:,} | {m.hit_rate*100:.1f}% | "
            f"{m.spend_with_cache:,.4f} | {m.savings:,.4f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relatório de context cache (C6).")
    ap.add_argument("--days", type=int, default=None, help="Janela: últimos N dias.")
    ap.add_argument("--model", default=None, help="Filtrar por model_group exato.")
    ap.add_argument("--out", default=None, help="Escrever markdown neste arquivo.")
    args = ap.parse_args(argv)
    report = build_report(days=args.days, model=args.model)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"[c6] relatório escrito em {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
