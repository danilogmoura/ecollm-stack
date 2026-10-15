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
    .venv/bin/python -m eval.cache_report --out reports/c6-cache-report.md
    .venv/bin/python -m eval.cache_report --model qwen3.8-flash

Ressalva S30: o endpoint real é Token Plan (Créditos), então o ``$`` aqui é
CUSTO-EQUIVALENTE PAYG (preços de C2). A métrica canônica de economia é em TOKENS
(% prompt-tok em hit); a ordem de grandeza do $ vale também em créditos.
"""

from __future__ import annotations

import argparse
import json
import math
import os
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
    # DeepSeek (S55) — tarifas OFF-PEAK (pico 01:00–04:00 e 06:00–10:00 UTC seg–sex = 2×).
    "deepseek-flash": {"input": 0.15, "output": 0.60},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98},
    # NovAI Doubao (S46) — pago, tarifa declarada no config.yaml.
    "novai-doubao-seed-2.0-pro": {"input": 0.40, "output": 2.00},
    # NovAI GLM (S40/S44) — FREE ($0). Entrada explícita 0.0 é OBRIGATÓRIA: sem ela
    # o fallback conservador (flash $0,15) geraria "economia fantasma" (spend=0 vs
    # projeção>0). Grupo free ⇒ preço 0 ⇒ savings=0.
    "novai-glm-4.7-flash": {"input": 0.0, "output": 0.0},
    "novai-glm-4.1v-flash": {"input": 0.0, "output": 0.0},
    "novai-glm-4.6v-flash": {"input": 0.0, "output": 0.0},
    "novai-glm-4.1v-thinking-flash": {"input": 0.0, "output": 0.0},
}
DEFAULT_INPUT_PRICE = PRICE_PER_MTOKEN["qwen3.8-flash"]["input"]  # fallback conservador


def price_for(model_group: str | None) -> dict[str, float] | None:
    """Resolve o preço (USD/1M) de um model_group, tratando aliases ``*-fast``.

    Aliases ``*-fast`` compartilham o preço do modelo real (mesmo upstream — C3).
    Retorna ``None`` quando o grupo é DESCONHECIDO (não está em ``PRICE_PER_MTOKEN``):
    nesse caso o ``$`` "sem cache" não é confiável (o ``spend`` real pode ser maior
    que a projeção → economia negativa enganosa), então o chamador deve OMITIR o
    ``$`` em vez de inventar um preço. Grupos free têm entrada explícita ``0.0``.
    """
    key = (model_group or "").replace("-fast", "")
    return PRICE_PER_MTOKEN.get(key)


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
    # S74: hit do cache de RESPOSTA (Redis do proxy) — camada DISTINTA do cache
    # implícito upstream (cached_tokens). None = campo ausente (chamada pré-cache).
    cache_hit: bool | None = None

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
        """Economia em USD = (sem cache) − (com cache). Positiva = cache ajudou.

        Quando ``cost_no_cache == 0`` (nenhum grupo com preço conhecido ⇒ projeção
        indisponível), retorna 0 em vez de ``-spend`` — o ``$`` não é confiável nesse
        caso e um valor negativo seria artefato, não economia real.
        """
        if self.cost_no_cache <= 0:
            return 0.0
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
    # S74: cache_hit vem como bool JSON (true/false) ou null; tolera string.
    ch = raw.get("cache_hit")
    if isinstance(ch, str):
        ch = ch.strip().lower() in ("true", "t", "1")
    elif ch is not None:
        ch = bool(ch)
    return CallRow(
        model_group=str(raw.get("model_group") or raw.get("modelGroup") or ""),
        prompt_tokens=_safe_int(raw.get("prompt_tokens")),
        completion_tokens=_safe_int(raw.get("completion_tokens")),
        cached_tokens=_safe_int(raw.get("cached_tokens")),
        spend=float(raw.get("spend") or 0.0),
        day=day,
        cache_hit=ch,
    )


def compute_metrics(rows: Sequence[CallRow]) -> Metrics:
    """Agrega linhas em totais + projeta o custo SEM cache.

    Custo SEM cache = (prompt_tokens × preço_input_cheio) + (completion × preço_output),
    ambos ÷ 1e6. Assume pessimista que TODOS os tokens de entrada seriam cobrados
    cheios (sem nenhum hit) — é o contrafactual honesto p/ medir o ganho do cache.
    O ``spend`` (com cache) já reflete o desconto de ``cached_tokens`` aplicado pelo
    LiteLLM usando exatamente estes preços.

    Grupos com preço DESCONHECIDO (``price_for`` → ``None``) são OMITIDOS da projeção
    ``no_cache`` (não inventamos preço): o ``$`` fica subestimado, mas nunca negativo
    por artefato. O ``spend`` real continua somado em ``with_cache``.
    """
    prompt = sum(r.prompt_tokens for r in rows)
    completion = sum(r.completion_tokens for r in rows)
    cached = sum(r.cached_tokens for r in rows)
    with_cache = sum(r.spend for r in rows)
    no_cache = 0.0
    for r in rows:
        p = price_for(r.model_group)
        if p is None:
            continue  # preço desconhecido → não projeta (evita economia negativa falsa)
        no_cache += (r.prompt_tokens * p["input"]) / 1e6
        no_cache += (r.completion_tokens * p.get("output", p["input"])) / 1e6
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
    cost = 0.0
    for r in rows:
        p = price_for(r.model_group)
        if p is None:
            continue  # preço desconhecido → não projeta custo (evita valor falso)
        cost += (r.uncached * p["input"]) / 1e6
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
# S74 — hit do cache de RESPOSTA (Redis do proxy), camada DISTINTA do implícito
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RedisHitStats:
    """Hit do cache de resposta (Redis) — só faz sentido p/ call_types cacheados."""

    hits: int
    misses: int
    unknown: int  # cache_hit NULL (chamadas pré-cache ou call_type não cacheado)

    @property
    def total(self) -> int:
        return self.hits + self.misses + self.unknown

    @property
    def hit_rate(self) -> float:
        """hits / (hits+misses) — ignora os NULL (não são miss, são 'sem dado')."""
        denom = self.hits + self.misses
        return self.hits / denom if denom else 0.0


def compute_redis_hits(rows: Sequence[CallRow]) -> RedisHitStats:
    """Conta hits/misses do cache de resposta (Redis) a partir de ``cache_hit``.

    Camada SEPARADA do cache implícito upstream (``cached_tokens``): aqui é o cache
    de RESPOSTA do proxy (chave = hash do request). Só embeddings são cacheados
    (``supported_call_types: ["aembedding"]``), então o hit-rate é relevante p/ eles.
    """
    hits = sum(1 for r in rows if r.cache_hit is True)
    misses = sum(1 for r in rows if r.cache_hit is False)
    unknown = sum(1 for r in rows if r.cache_hit is None)
    return RedisHitStats(hits=hits, misses=misses, unknown=unknown)


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
    'cache_hit', cache_hit,
    'spend', spend
  )::text AS row
FROM "LiteLLM_SpendLogs"
WHERE {scope}
  {where_extra}
ORDER BY "startTime";
"""

# Escopo default (preserva o comportamento histórico: só a família qwen3.8-*).
DEFAULT_SCOPE = "model_group LIKE 'qwen3.8%'"


def _sql_literal(value: str) -> str:
    """Escapa um valor para literal SQL (aspas simples dobradas)."""
    return "'" + value.replace("'", "''") + "'"


def build_sql(
    days: int | None,
    model: str | None = None,
    *,
    models: Sequence[str] | None = None,
    all_models: bool = False,
) -> str:
    """Monta o SQL dos SpendLogs.

    Escopo (precedência): ``all_models`` (sem filtro de grupo) > ``models``
    (``model_group IN (...)``) > ``model`` (``model_group = ...``) > default
    (``LIKE 'qwen3.8%'``). O default é byte-idêntico ao histórico.
    """
    if all_models:
        scope = "TRUE"
    elif models:
        scope = "model_group IN (" + ", ".join(_sql_literal(m) for m in models) + ")"
    elif model:
        scope = f"model_group = {_sql_literal(model)}"
    else:
        scope = DEFAULT_SCOPE

    where = []
    if days is not None:
        where.append(f'AND "startTime" >= now() - interval \'{int(days)} days\'')
    return SQL_TEMPLATE.format(scope=scope, where_extra=" ".join(where))


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
    models: Sequence[str] | None = None,
    all_models: bool = False,
    row_source: Callable[[str], list[dict]] | None = None,
) -> str:
    """Produz o relatório markdown. ``row_source`` injetável p/ testes."""
    source = row_source or fetch_rows_via_docker
    raws = source(build_sql(days, model, models=models, all_models=all_models))
    rows = [parse_row(r) for r in raws]
    overall = compute_metrics(rows)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    window = f"últimos {days} dias" if days else "janela completa"
    if all_models:
        scope = "todos os model_group"
    elif models:
        scope = "model_group ∈ {" + ", ".join(models) + "}"
    elif model:
        scope = f"model_group = {model}"
    else:
        scope = "todos qwen3.8-*"

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

    # S74: hit do cache de RESPOSTA (Redis do proxy) — camada DISTINTA do implícito.
    rh = compute_redis_hits(rows)
    lines.append("## Cache de RESPOSTA (Redis do proxy) — camada distinta do implícito")
    lines.append("")
    lines.append("Chave = hash do request INTEIRO (só `aembedding` é cacheado; chat fica")
    lines.append("fora por design). `cache_hit` da SpendLogs. NULL = chamada pré-cache.")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("| --- | --- |")
    lines.append(f"| Hits (Redis) | {rh.hits:,} |")
    lines.append(f"| Misses (Redis) | {rh.misses:,} |")
    lines.append(f"| Sem dado (NULL) | {rh.unknown:,} |")
    lines.append(f"| **Hit-rate (hits/(hits+misses))** | **{rh.hit_rate*100:.1f}%** |")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_cost_snapshot(
    path: str,
    *,
    days: int | None = None,
    model: str | None = None,
    models: Sequence[str] | None = None,
    all_models: bool = False,
    row_source: Callable[[str], list[dict]] | None = None,
) -> dict:
    """S88: persiste um snapshot do custo acumulado (histórico append-only).

    Grava ``{"snapshots": [...]}`` em ``path`` (JSON). Cada entrada registra o
    instante UTC, o escopo e os totais de custo/tokens. Reexecutar faz APPEND —
    o arquivo vira uma série temporal do gasto acumulado (o SpendLogs é a fonte,
    mas o snapshot congela o valor no momento da leitura, imune a poda/rotação).
    """
    source = row_source or fetch_rows_via_docker
    raws = source(build_sql(days, model, models=models, all_models=all_models))
    rows = [parse_row(r) for r in raws]
    overall = compute_metrics(rows)
    unc = compute_uncached(rows)
    rh = compute_redis_hits(rows)

    if all_models:
        scope = "all"
    elif models:
        scope = ",".join(models)
    elif model:
        scope = model
    else:
        scope = "qwen3.8-*"

    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": scope,
        "days": days,
        "calls": overall.calls,
        "prompt_tokens": overall.prompt_tokens,
        "completion_tokens": overall.completion_tokens,
        "cached_tokens": overall.cached_tokens,
        "hit_rate": round(overall.hit_rate, 6),
        "spend_with_cache": round(overall.spend_with_cache, 6),
        "cost_no_cache": round(overall.cost_no_cache, 6),
        "savings": round(overall.savings, 6),
        "uncached_cost": round(unc.cost, 6),
        "redis_hits": rh.hits,
        "redis_misses": rh.misses,
    }

    data: dict = {"snapshots": []}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict) and isinstance(loaded.get("snapshots"), list):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {"snapshots": []}  # arquivo corrompido → recomeça (não perde o novo)
    data["snapshots"].append(entry)
    # S101: o snapshot mora em `reports/logs/` (gitignored) → garante a pasta num
    # clone limpo, senão o `open(..., "w")` abaixo falha com FileNotFoundError.
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relatório de context cache (C6).")
    ap.add_argument("--days", type=int, default=None, help="Janela: últimos N dias.")
    ap.add_argument("--model", default=None, help="Filtrar por model_group exato.")
    ap.add_argument("--models", default=None,
                    help="Lista de model_group separada por vírgula (IN).")
    ap.add_argument("--all", dest="all_models", action="store_true",
                    help="Sem filtro de grupo (todos os model_group).")
    ap.add_argument("--out", default=None, help="Escrever markdown neste arquivo.")
    ap.add_argument("--snapshot", default=None,
                    help="S88: persistir snapshot do custo acumulado neste JSON (append).")
    args = ap.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else None
    if args.snapshot:
        entry = write_cost_snapshot(
            args.snapshot, days=args.days, model=args.model,
            models=models, all_models=args.all_models,
        )
        print(f"[c6] snapshot gravado em {args.snapshot} "
              f"(spend=${entry['spend_with_cache']:.4f}, calls={entry['calls']})",
              file=sys.stderr)
    report = build_report(days=args.days, model=args.model,
                          models=models, all_models=args.all_models)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"[c6] relatório escrito em {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
