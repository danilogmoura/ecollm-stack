"""C8 · Teste de INTEGRAÇÃO do `eval.cache_report` contra SpendLogs real.

Os unit tests (`test_cache_report.py`) injetam `row_source` e por isso NUNCA
exercitam o caminho de produção: `build_sql` → `fetch_rows_via_docker`
(`docker compose exec -T litellm-db psql`) → decodificação JSON → `parse_row`.
Um bug no SQL ou no parsing sobre dados reais passaria despercebido.

Estes testes fecham essa lacuna rodando o acesso REAL à tabela
`LiteLLM_SpendLogs`. Exigem o container `litellm-db` UP (via docker). Quando o
docker/banco está indisponível, fazem skip — mesma política de
`ingest/tests/test_sync_gen_integration.py`, para não quebrar CI sem infra.

São READ-ONLY: só consultam (SELECT), nunca escrevem no SpendLogs.
"""

from __future__ import annotations

import subprocess

import pytest

from eval import cache_report as cr


def _db_available() -> bool:
    """True se dá para rodar uma query trivial no litellm-db via docker exec."""
    probe = (
        'SELECT json_build_object(\'ok\', 1)::text AS row '
        'FROM "LiteLLM_SpendLogs" LIMIT 1;'
    )
    try:
        rows = cr.fetch_rows_via_docker(probe)
        return isinstance(rows, list)
    except Exception:  # noqa: BLE001 — docker ausente/banco fora ⇒ sem infra p/ integração
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="litellm-db indisponível (docker/SpendLogs) — teste de integração requer infra",
)


def test_fetch_rows_reais_retornam_linhas_parseaveis():
    """build_sql + fetch_rows_via_docker reais produzem ≥1 linha qwen3.8 parseável."""
    sql = cr.build_sql(days=None, model=None)
    raws = cr.fetch_rows_via_docker(sql)
    assert len(raws) >= 1, "esperava ao menos 1 chamada qwen3.8-* nos SpendLogs reais"

    rows = [cr.parse_row(r) for r in raws]
    # Toda linha real tem um model_group qwen3.8-* (WHERE do SQL garante).
    assert all(r.model_group.startswith("qwen3.8") for r in rows)
    # Campos numéricos nunca são negativos.
    assert all(r.prompt_tokens >= 0 and r.cached_tokens >= 0 for r in rows)


def test_compute_metrics_sobre_dados_reais_respeita_invariantes():
    """Invariantes estruturais valem para linhas REAIS, não só fixtures."""
    raws = cr.fetch_rows_via_docker(cr.build_sql(days=None, model=None))
    rows = [cr.parse_row(r) for r in raws]
    m = cr.compute_metrics(rows)

    assert m.calls == len(rows)
    assert m.prompt_tokens == sum(r.prompt_tokens for r in rows)
    # cached é subconjunto dos tokens de entrada; hit_rate é fração válida.
    assert 0 <= m.cached_tokens <= m.prompt_tokens
    assert 0.0 <= m.hit_rate <= 1.0
    # spend real (com cache) jamais excede a projeção pessimista (sem cache).
    assert m.spend_with_cache <= m.cost_no_cache + 1e-6


def test_build_report_end_to_end_contra_banco_real():
    """Pipeline completo (SQL→docker→parse→métricas→markdown) sobre o DB real."""
    report = cr.build_report(days=None, model=None, row_source=cr.fetch_rows_via_docker)

    assert isinstance(report, str) and report.strip()
    assert "# C6 · Relatório de context cache" in report
    # Como há chamadas reais, o relatório traz a seção de totais (não o ramo vazio).
    assert "## Totais" in report
    assert "% prompt-tok em HIT" in report
