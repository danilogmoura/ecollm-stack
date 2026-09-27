"""Testes unitários do relatório de context cache (eval/cache_report.py) — SEM DB/rede.

Exercitam apenas as funcoes puras: price_for, parse_row, compute_metrics, group_by,
build_sql e build_report (com row_source injetavel). Nada aqui toca docker/psql.
"""

from __future__ import annotations

from eval import cache_report as cr


def _row(mg="qwen3.8-flash", pt=1000, ct=900, cached=800, spend=0.01, day="2026-09-27"):
    return cr.CallRow(model_group=mg, prompt_tokens=pt, completion_tokens=ct,
                      cached_tokens=cached, spend=spend, day=day)


# --- price_for -------------------------------------------------------------

def test_price_for_exatos():
    assert cr.price_for("qwen3.8-flash")["input"] == 0.15
    assert cr.price_for("qwen3.8-max")["input"] == 2.00


def test_price_for_alias_fast_compartilha_preco():
    # *-fast é alias do mesmo upstream → preço do modelo real (C3)
    assert cr.price_for("qwen3.8-flash-fast") == cr.price_for("qwen3.8-flash")


def test_price_for_desconhecido_cai_no_default():
    assert cr.price_for("gpt-9")["input"] == cr.DEFAULT_INPUT_PRICE
    assert cr.price_for(None)["input"] == cr.DEFAULT_INPUT_PRICE


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
