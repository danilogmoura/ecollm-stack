"""Testes offline do gerador de relatório do catálogo enriquecido."""
from __future__ import annotations

from eval.novai_enrich_report import build


def _model(**kw):
    base = {
        "id": "x", "owned_by": None, "pricing": None, "type": None,
        "modalities": [], "brand": None, "ld_price": None, "ld_currency": None,
        "ld_description": None, "availability": None, "price_valid_until": None,
        "has_page": False, "page_slug": None, "code_commands": [],
        "code_tests": [], "errors": [],
    }
    base.update(kw)
    return base


def test_build_has_title_and_coverage():
    md = build([_model(id="glm-5", owned_by="zhipu", type="image",
                       modalities=["image"], brand="Zhipu AI",
                       ld_price="0", ld_currency="USD", has_page=True)])
    assert "# NovAI" in md
    assert "## Cobertura" in md
    assert "| Total de modelos | 1 |" in md


def test_build_lists_providers_and_types():
    md = build([
        _model(id="a", owned_by="zhipu"),
        _model(id="b", owned_by="zhipu"),
        _model(id="c", owned_by="alibaba"),
    ])
    assert "| zhipu | 2 |" in md
    assert "| alibaba | 1 |" in md


def test_build_lists_ghosts():
    md = build([
        _model(id="real", owned_by="zhipu"),
        _model(id="ghost", modalities=["chat"], has_page=True),
    ])
    assert "## Modelos fantasma" in md
    assert "`ghost`" in md
    # o modelo real não deve aparecer na seção de fantasmas
    ghost_section = md.split("## Modelos fantasma")[1].split("##")[0]
    assert "`real`" not in ghost_section


def test_build_no_ghosts():
    md = build([_model(id="real", owned_by="zhipu")])
    assert "_Nenhum._" in md


def test_build_full_table_sorted():
    md = build([_model(id="zeta"), _model(id="alpha")])
    table = md.split("## Tabela completa")[1]
    assert table.index("`alpha`") < table.index("`zeta`")


def test_build_counts_code_commands():
    md = build([_model(id="a", code_commands=[
        {"kind": "curl"}, {"kind": "python"}, {"kind": "curl"}])])
    assert "| curl | 2 |" in md
    assert "| python | 1 |" in md


def test_build_handles_empty():
    md = build([])
    assert "| Total de modelos | 0 |" in md
    assert "_Nenhum._" in md
