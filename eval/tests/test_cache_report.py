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
