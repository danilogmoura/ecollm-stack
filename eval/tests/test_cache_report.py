"""Testes unitários do relatório de context cache (eval/cache_report.py) — SEM DB/rede.

Exercitam apenas as funcoes puras: price_for, parse_row, compute_metrics, group_by,
build_sql e build_report (com row_source injetavel). Nada aqui toca docker/psql.
"""

from __future__ import annotations

import pytest

from eval import cache_report as cr


def _row(mg="qwen3.8-flash", pt=1000, ct=900, cached=800, spend=0.01, day="2026-09-27",
         cache_hit=None):
    return cr.CallRow(model_group=mg, prompt_tokens=pt, completion_tokens=ct,
                      cached_tokens=cached, spend=spend, day=day, cache_hit=cache_hit)


# --- price_for -------------------------------------------------------------

def test_price_for_exatos():
    assert cr.price_for("qwen3.8-flash")["input"] == 0.15
    assert cr.price_for("qwen3.8-max")["input"] == 2.00


def test_price_for_alias_fast_compartilha_preco():
    # *-fast é alias do mesmo upstream → preço do modelo real (C3)
    assert cr.price_for("qwen3.8-flash-fast") == cr.price_for("qwen3.8-flash")


def test_price_for_desconhecido_retorna_none():
    # S59: preço desconhecido → None (não inventa preço; evita economia negativa falsa).
    assert cr.price_for("gpt-9") is None
    assert cr.price_for(None) is None
    assert cr.price_for("") is None


# --- parse_row -------------------------------------------------------------

def test_parse_row_quote_case():
    raw = {
        "startTime": "2026-09-26",
        "model_group": "qwen3.8-flash",
        "prompt_tokens": 74016,
        "completion_tokens": 120,
        "cached_tokens": 73728,
        "spend": 0.00131,
    }
    r = cr.parse_row(raw)
    assert r.day == "2026-09-26"
    assert r.prompt_tokens == 74016
    assert r.cached_tokens == 73728
    assert r.spend == 0.00131


def test_parse_row_tolera_ausencias():
    r = cr.parse_row({})
    assert r.prompt_tokens == 0
    assert r.cached_tokens == 0
    assert r.spend == 0.0
    assert r.day == ""


# --- compute_metrics -------------------------------------------------------

def test_hit_rate_basico():
    m = cr.compute_metrics([_row(pt=1000, cached=800)])
    assert m.hit_rate == 0.8


def test_hit_rate_sem_prompt_nao_divide_por_zero():
    m = cr.compute_metrics([_row(pt=0, cached=0, ct=0, spend=0.0)])
    assert m.hit_rate == 0.0


def test_custo_no_cache_usa_preco_cheio_de_input():
    # 1000 prompt-tok flash @ 0.15/1M = 0.00015; + 900 completion @ 0.47/1M
    rows = [_row(mg="qwen3.8-flash", pt=1000, ct=900, cached=800, spend=0.0)]
    m = cr.compute_metrics(rows)
    expected = (1000 * 0.15) / 1e6 + (900 * 0.47) / 1e6
    assert abs(m.cost_no_cache - expected) < 1e-12


def test_economia_positiva_quando_spend_menor_que_no_cache():
    rows = [_row(pt=1000, ct=0, cached=900, spend=0.00005)]
    m = cr.compute_metrics(rows)
    assert m.savings > 0
    assert m.savings_pct > 0


def test_agrega_multiplas_linhas():
    rows = [_row(pt=1000, cached=500, spend=0.01), _row(pt=2000, cached=1500, spend=0.02)]
    m = cr.compute_metrics(rows)
    assert m.calls == 2
    assert m.prompt_tokens == 3000
    assert m.cached_tokens == 2000
    assert m.hit_rate == 2000 / 3000
    assert abs(m.spend_with_cache - 0.03) < 1e-9


# --- group_by --------------------------------------------------------------

def test_group_by_modelo():
    rows = [_row(mg="qwen3.8-flash"), _row(mg="qwen3.8-max"), _row(mg="qwen3.8-flash")]
    g = cr.group_by(rows, lambda r: r.model_group)
    assert len(g["qwen3.8-flash"]) == 2
    assert len(g["qwen3.8-max"]) == 1


# --- build_sql -------------------------------------------------------------

def test_build_sql_janela_e_modelo():
    sql = cr.build_sql(days=7, model="qwen3.8-flash")
    assert "interval '7 days'" in sql
    assert "model_group = 'qwen3.8-flash'" in sql
    assert "LiteLLM_SpendLogs" in sql
    assert "cached_tokens" in sql


def test_build_sql_sem_filtros():
    sql = cr.build_sql(days=None, model=None)
    assert "interval" not in sql
    assert "where_extra" not in sql  # template resolvido


# --- build_report (row_source injetável) -----------------------------------

def test_build_report_renderiza_totais():
    def source(_sql):
        return [
            {"startTime": "2026-09-27", "model_group": "qwen3.8-flash",
             "prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 900,
             "spend": 0.0001},
        ]

    md = cr.build_report(days=1, row_source=source)
    assert "% prompt-tok em HIT" in md
    assert "90.0%" in md  # 900/1000
    assert "Ressalva S30" in md
    assert "`qwen3.8-flash`" in md


def test_build_report_vazio_nao_quebra():
    md = cr.build_report(row_source=lambda _sql: [])
    assert "Nenhuma chamada" in md


# --- H1: cauda nao-cacheada (uncached) -------------------------------------

def test_uncached_propriedade_basica():
    assert _row(pt=1000, cached=800).uncached == 200


def test_uncached_chao_zero_quando_cached_maior_que_prompt():
    # Resposta anomala do upstream (cached > prompt) nao pode gerar cauda negativa.
    assert _row(pt=100, cached=250).uncached == 0


def test_uncached_sem_cache_e_prompt_inteiro():
    assert _row(pt=5000, cached=0).uncached == 5000


# --- percentile_nearest_rank -----------------------------------------------

def test_percentile_vazio_e_zero():
    assert cr.percentile_nearest_rank([], 90) == 0


def test_percentile_nearest_rank_valores_conhecidos():
    vals = list(range(1, 101))  # 1..100, ja ordenado
    assert cr.percentile_nearest_rank(vals, 50) == 50
    assert cr.percentile_nearest_rank(vals, 90) == 90
    assert cr.percentile_nearest_rank(vals, 95) == 95
    assert cr.percentile_nearest_rank(vals, 100) == 100
    assert cr.percentile_nearest_rank(vals, 1) == 1


def test_percentile_unico_valor():
    assert cr.percentile_nearest_rank([42], 0) == 42
    assert cr.percentile_nearest_rank([42], 99) == 42


def test_percentile_e_sempre_valor_de_uma_linha_real():
    vals = [10, 20, 30, 40, 50]
    for pct in (10, 25, 50, 75, 90, 95):
        assert cr.percentile_nearest_rank(vals, pct) in vals


# --- compute_uncached ------------------------------------------------------

def test_compute_uncached_conjunto_vazio_zeros():
    u = cr.compute_uncached([])
    assert u.calls == 0 and u.total == 0 and u.mean == 0.0
    assert (u.p50, u.p90, u.p95, u.max, u.cost) == (0, 0, 0, 0, 0.0)


def test_compute_uncached_media_e_percentis():
    rows = [_row(pt=1000, cached=900), _row(pt=2000, cached=500), _row(pt=100, cached=0)]
    # uncached: 100, 1500, 100 -> ordenado [100, 100, 1500]
    u = cr.compute_uncached(rows)
    assert u.calls == 3
    assert u.total == 1700
    assert u.mean == 1700 / 3
    assert u.p50 == 100
    assert u.p90 == 1500
    assert u.max == 1500


def test_compute_uncached_custo_usa_preco_por_modelo():
    # 1000 uncached flash @0.15/1M = 1.5e-4; 1000 uncached max @2.00/1M = 2e-3
    rows = [_row(mg="qwen3.8-flash", pt=1000, cached=0),
            _row(mg="qwen3.8-max", pt=1000, cached=0)]
    u = cr.compute_uncached(rows)
    assert abs(u.cost - (1000 * 0.15 / 1e6 + 1000 * 2.00 / 1e6)) < 1e-12


def test_compute_uncached_total_bate_soma_do_hit_complementar():
    rows = [_row(pt=1000, cached=800), _row(pt=2000, cached=1500)]
    u = cr.compute_uncached(rows)
    m = cr.compute_metrics(rows)
    assert u.total == m.prompt_tokens - m.cached_tokens


# --- build_report com a secao H1 -------------------------------------------

def test_build_report_renderiza_secao_uncached():
    def source(_sql):
        return [
            {"startTime": "2026-09-27", "model_group": "qwen3.8-flash",
             "prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 900,
             "spend": 0.0001},
            {"startTime": "2026-09-27", "model_group": "qwen3.8-flash",
             "prompt_tokens": 500, "completion_tokens": 50, "cached_tokens": 0,
             "spend": 0.0002},
        ]

    md = cr.build_report(days=1, row_source=source)
    assert "Cauda não-cacheada por chamada (H1" in md
    assert "Cauda Não-cacheada por chamada (média)" in md
    assert "**300 tok**" in md  # média (100+500)/2
    # uncached: 100 e 500 -> total 600, média 300
    assert "| **TODAS** | 2 | 300 | 100 | 500 | 500 | 500 |" in md
    assert "| Cauda NÃO-cacheada (total tok) | 600 |" in md  # totais


# --- S59: escopo multi-modelo ----------------------------------------------

def test_build_sql_default_byte_identico():
    # Regressão: sem filtros novos, o SQL é o histórico (LIKE 'qwen3.8%').
    sql = cr.build_sql(days=None, model=None)
    assert "model_group LIKE 'qwen3.8%'" in sql
    assert "WHERE TRUE" not in sql
    assert "IN (" not in sql


def test_build_sql_all_models_sem_filtro_de_grupo():
    sql = cr.build_sql(days=7, all_models=True)
    assert "WHERE TRUE" in sql
    assert "LIKE 'qwen3.8%'" not in sql
    assert "interval '7 days'" in sql


def test_build_sql_models_lista_in_escapada():
    sql = cr.build_sql(days=None, models=["deepseek-flash", "novai-doubao-seed-2.0-pro-fast"])
    assert "model_group IN ('deepseek-flash', 'novai-doubao-seed-2.0-pro-fast')" in sql
    assert "LIKE 'qwen3.8%'" not in sql


def test_build_sql_models_escapa_aspas():
    sql = cr.build_sql(days=None, models=["o'brien"])
    assert "model_group IN ('o''brien')" in sql


def test_build_sql_precedencia_all_sobre_models():
    sql = cr.build_sql(days=None, models=["x"], all_models=True)
    assert "WHERE TRUE" in sql
    assert "IN (" not in sql


def test_price_for_deepseek_e_doubao():
    assert cr.price_for("deepseek-flash")["input"] == 0.15
    assert cr.price_for("deepseek-v4-pro")["input"] == 0.66
    assert cr.price_for("novai-doubao-seed-2.0-pro")["input"] == 0.40
    # alias -fast compartilha o preço do modelo real
    assert cr.price_for("deepseek-flash-fast") == cr.price_for("deepseek-flash")


def test_price_for_free_nao_gera_economia_fantasma():
    # Grupo free ($0): spend=0 e projeção=0 ⇒ savings=0 (sem fantasma).
    for mg in ("novai-glm-4.7-flash", "novai-glm-4.7-flash-fast"):
        assert cr.price_for(mg)["input"] == 0.0
        assert cr.price_for(mg)["output"] == 0.0
    rows = [_row(mg="novai-glm-4.7-flash", pt=1000, ct=100, cached=0, spend=0.0)]
    m = cr.compute_metrics(rows)
    assert m.cost_no_cache == 0.0
    assert m.savings == 0.0


def test_build_report_all_models_rotulo_e_linhas():
    def source(_sql):
        return [
            {"startTime": "2026-10-15", "model_group": "deepseek-flash",
             "prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 660,
             "spend": 0.0001},
            {"startTime": "2026-10-15", "model_group": "novai-doubao-seed-2.0-pro-fast",
             "prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 250,
             "spend": 0.0002},
        ]

    md = cr.build_report(days=1, all_models=True, row_source=source)
    assert "todos os model_group" in md
    assert "`deepseek-flash`" in md
    assert "`novai-doubao-seed-2.0-pro-fast`" in md


def test_build_report_models_rotulo():
    def source(_sql):
        return [{"startTime": "2026-10-15", "model_group": "deepseek-flash",
                 "prompt_tokens": 100, "completion_tokens": 10, "cached_tokens": 50,
                 "spend": 0.0001}]

    md = cr.build_report(days=1, models=["deepseek-flash"], row_source=source)
    assert "model_group ∈ {deepseek-flash}" in md


def test_preco_desconhecido_nao_gera_economia_negativa():
    # Grupo sem preço conhecido: spend real > 0 mas projeção omitida ⇒ savings >= 0
    # (nunca negativo por artefato de fallback).
    rows = [_row(mg="novai-kimi-k2.5", pt=1000, ct=100, cached=0, spend=0.0001)]
    m = cr.compute_metrics(rows)
    assert m.cost_no_cache == 0.0
    assert m.savings == 0.0
    u = cr.compute_uncached(rows)
    assert u.cost == 0.0


def test_preco_desconhecido_nao_quebra_com_conhecido():
    # Mistura conhecido + desconhecido: só o conhecido entra na projeção.
    rows = [_row(mg="qwen3.8-flash", pt=1000, ct=0, cached=0, spend=0.0),
            _row(mg="novai-kimi-k2.5", pt=1000, ct=0, cached=0, spend=0.0)]
    m = cr.compute_metrics(rows)
    assert abs(m.cost_no_cache - (1000 * 0.15 / 1e6)) < 1e-12


# --- S74: hit do cache de RESPOSTA (Redis) ---------------------------------

def test_parse_row_le_cache_hit_bool():
    assert cr.parse_row({"cache_hit": True}).cache_hit is True
    assert cr.parse_row({"cache_hit": False}).cache_hit is False
    assert cr.parse_row({"cache_hit": None}).cache_hit is None
    assert cr.parse_row({}).cache_hit is None  # ausente → None


def test_parse_row_cache_hit_string_tolerada():
    assert cr.parse_row({"cache_hit": "true"}).cache_hit is True
    assert cr.parse_row({"cache_hit": "False"}).cache_hit is False


def test_compute_redis_hits_conta_e_ignora_null():
    rows = [_row(cache_hit=True), _row(cache_hit=True), _row(cache_hit=False),
            _row(cache_hit=None)]
    rh = cr.compute_redis_hits(rows)
    assert rh.hits == 2
    assert rh.misses == 1
    assert rh.unknown == 1
    assert rh.total == 4
    # hit-rate ignora os NULL: 2/(2+1)
    assert rh.hit_rate == pytest.approx(2 / 3)


def test_compute_redis_hits_vazio_nao_divide_por_zero():
    rh = cr.compute_redis_hits([])
    assert rh.hit_rate == 0.0
    assert rh.total == 0


def test_build_report_inclui_secao_redis():
    def source(_sql):
        return [
            {"startTime": "2026-10-15", "model_group": "rag-embeddings-qwen37",
             "prompt_tokens": 10, "completion_tokens": 0, "cached_tokens": 0,
             "cache_hit": True, "spend": 0.0},
            {"startTime": "2026-10-15", "model_group": "rag-embeddings-qwen37",
             "prompt_tokens": 10, "completion_tokens": 0, "cached_tokens": 0,
             "cache_hit": False, "spend": 0.0},
        ]

    md = cr.build_report(days=1, row_source=source)
    assert "Cache de RESPOSTA (Redis do proxy)" in md
    assert "| Hits (Redis) | 1 |" in md
    assert "| Misses (Redis) | 1 |" in md
    assert "**50.0%**" in md  # hit-rate 1/(1+1)
