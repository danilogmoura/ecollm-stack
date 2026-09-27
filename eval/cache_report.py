"""FASE 6 · C6 — Instrumentar hit-rate + custo de context cache (T-CACHE-6).

Le os SpendLogs do proxy LiteLLM (tabela ``LiteLLM_SpendLogs``), extrai os campos
de cache que o Token Plan já devolve no usage e produz um RELATÓRIO com:

  - % de prompt-tokens que caíram em HIT de cache (economia REAL medida, não projetada);
  - custo estimado COM cache (o ``spend`` que o LiteLLM já cobra) vs SEM cache
    (reprecificar todos os tokens de entrada ao preço cheio de input);
  - distribuição por modelo-group e por dia.

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
