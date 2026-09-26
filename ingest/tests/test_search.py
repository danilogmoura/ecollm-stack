"""Testes da FASE 3 — busca híbrida (search.py).

Sem rede/DB: o caminho denso recebe `qvec` injetado e a conexão é um FakeConn
que devolve linhas pré-fabricadas por SQL. Foco na LÓGICA que importa:
  - RRF: soma de 1/(k+rank), fusão das duas listas, ids deduplicados;
  - ordenação FINAL determinística (score desc + tie-break path/symbol/id);
  - filtros kind/path propagados nos params;
  - Hit.source() e mapeamento de linha -> Hit.
A matemática do ts_rank/HNSW é do Postgres (coberta na validação real), não aqui.
"""

from __future__ import annotations

import pytest

from ingest import search


# linha na ordem de _COLS: id, repo, path, lang, kind, symbol, content, content_hash
def _row(i, path, kind="code", symbol=None, content="c"):
    return (f"id{i}", "repo", path, "py", kind, symbol, content, f"h{i}")


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    """Devolve filas distintas conforme o SQL executado (denso vs léxico vs léxico-pt)."""

    def __init__(self, vec_rows, lex_rows, lex_pt_rows=None):
        self.vec_rows = vec_rows
        self.lex_rows = lex_rows
        self.lex_pt_rows = lex_pt_rows if lex_pt_rows is not None else []
        self.calls = []  # (sql, params)

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "<=>" in sql:  # operador cosine => caminho denso
            return FakeCursor(self.vec_rows)
        if "tsv_pt" in sql:  # S20: terceira lista, léxico pt-BR (kind='doc')
            return FakeCursor(self.lex_pt_rows)
        return FakeCursor(self.lex_rows)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# reciprocal_rank_fusion — matemática pura
# ---------------------------------------------------------------------------

def test_rrf_score_de_uma_lista():
    fused = search.reciprocal_rank_fusion([[_row(1, "a"), _row(2, "b")]], k=60)
    # rank1 -> 1/61, rank2 -> 1/62
    assert fused["id1"][1] == pytest.approx(1 / 61)
    assert fused["id2"][1] == pytest.approx(1 / 62)
    assert fused["id1"][2] == 1   # vec_rank
    assert fused["id1"][3] is None  # só estava na 1ª lista (densa)


def test_rrf_soma_das_duas_listas_e_marca_ranks():
    shared = _row(2, "b")  # MESMO id nas duas listas -> soma dos dois ranks
    dense = [_row(1, "a"), shared]
    lexical = [shared, _row(7, "c")]  # id2 aparece nos dois
    fused = search.reciprocal_rank_fusion([dense, lexical], k=60)
    # id2: 1/(60+2) [densa] + 1/(60+1) [léxica]
    assert fused["id2"][1] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["id2"][2] == 2   # vec_rank=2
    assert fused["id2"][3] == 1   # lex_rank=1
    # id1 só densa, id7 só léxica (na posição 2 da lista léxica)
    assert fused["id1"][3] is None
    assert fused["id7"][2] is None
    assert fused["id7"][3] == 2


def test_rrf_pesos_aplicam_por_lista():
    dense = [_row(1, "a")]
    lexical = [_row(1, "a")]
    fused = search.reciprocal_rank_fusion([dense, lexical], weights=[2.0, 1.0], k=60)
    # 2*(1/61) + 1*(1/61) = 3/61
    assert fused["id1"][1] == pytest.approx(3 / 61)


# ---------------------------------------------------------------------------
# search() — integração com FakeConn + qvec injetado
# ---------------------------------------------------------------------------

def test_search_combina_ordena_e_limita():
    shared = _row(2, "y.py")  # aparece nas duas listas -> maior score combinado
    dense = [_row(1, "z.py"), shared, _row(3, "x.py")]
    lexical = [shared, _row(9, "w.py")]
    conn = FakeConn(dense, lexical)
    hits = search.search("q", repo="repo", conn=conn, qvec=[0.1, 0.2], final_k=2)
    assert len(hits) == 2
    # id2 está nos dois rankings (rank2 denso + rank1 léxico) => melhor RRF
    assert hits[0].id == "id2"
    assert hits[0].score >= hits[1].score
    assert isinstance(hits[0], search.Hit)


def test_search_passa_filtros_nos_params():
    conn = FakeConn([], [])
    search.search("qq", repo="meu", conn=conn, qvec=[0.0],
                  kind="config", path_prefix="litellm/")
    # duas chamadas: densa e léxica; ambas com kind/path_like/repo corretos
    for _, params in conn.calls:
        assert params["repo"] == "meu"
        assert params["kind"] == "config"
        assert params["path_like"] == "litellm/%"


def test_search_deterministico_empate_por_path():
    # dois chunks com MESMO score (cada um em posição espelhada) -> desempate por path
    a = _row(1, "aaa.py")
    b = _row(2, "bbb.py")
    conn = FakeConn([a, b], [b, a])  # simétrico => scores iguais
    hits = search.search("q", repo="r", conn=conn, qvec=[0.0])
    assert hits[0].score == pytest.approx(hits[1].score)
    assert hits[0].path == "aaa.py"  # tie-break alfabético determinístico
    assert hits[1].path == "bbb.py"


def test_search_vetor_serializado_no_param():
    conn = FakeConn([], [])
    search.search("q", repo="r", conn=conn, qvec=[1.0, 2.5, 3.0])
    dense_call = next(p for s, p in conn.calls if "<=>" in s)
    assert dense_call["qvec"] == "[1,2.5,3]"


# ---------------------------------------------------------------------------
# S20 — caminho léxico pt-BR (tsv_pt) na fusão
# ---------------------------------------------------------------------------

def test_s20_default_desligado():
    """Default do módulo é 0.0 → nenhum SQL tsv_pt roda sem pedir explicitamente."""
    assert search.LEXICAL_PT_WEIGHT == 0.0
    conn = FakeConn([], [])
    search.search("q", repo="r", conn=conn, qvec=[0.0])
    assert not any("tsv_pt" in s for s, _ in conn.calls)


def test_s20_lexical_pt_weight_posivo_liga_caminho():
    """Passar peso >0 dispara o SQL de tsv_pt além dos outros dois caminhos."""
    conn = FakeConn([], [])
    search.search("q", repo="r", conn=conn, qvec=[0.0], lexical_pt_weight=0.5)
    sqls = [s for s, _ in conn.calls]
    assert any("<=>" in s for s in sqls)          # denso
    assert any("tsv_pt" in s for s in sqls)        # léxico pt (S20)
    assert any("websearch_to_tsquery('simple'" in s for s in sqls)  # léxico simple


def test_s20_doc_reforcado_pelo_lexico_pt_sobe_no_ranking():
    """Um doc resgatado só pelo léxico-pt ganha score extra quando o caminho liga."""
    doc = _row(5, "README.md", kind="doc")
    code = _row(6, "a.py", kind="code")
    # denso: code melhor; simple: nada; pt: só o doc casa (stemming)
    conn = FakeConn([code, doc], [], [doc])
    hits_on = {h.id: h.score for h in
               search.search("índice", repo="r", conn=conn, qvec=[0.0], final_k=2,
                             lexical_pt_weight=0.5)}
    # com peso 0 (default/A-B off), o doc perde o reforço do caminho pt → score menor
    conn_off = FakeConn([code, doc], [], [doc])
    hits_off = {h.id: h.score for h in
                search.search("índice", repo="r", conn=conn_off, qvec=[0.0],
                              final_k=2, lexical_pt_weight=0.0)}
    assert hits_on["id5"] > hits_off["id5"]      # reforço pt somou no RRF do doc
    assert hits_on["id6"] == pytest.approx(hits_off["id6"])  # code não usa tsv_pt


def test_s20_predicado_kind_doc_explicito_no_sql_pt():
    """O SQL pt deve fixar kind='doc' p/ casar com o índice GIN parcial."""
    conn = FakeConn([], [], [_row(1, "README.md", kind="doc")])
    search.search("q", repo="r", conn=conn, qvec=[0.0], lexical_pt_weight=0.5)
    pt_sql = next(s for s, _ in conn.calls if "tsv_pt" in s)
    assert "kind = 'doc'" in pt_sql


# ---------------------------------------------------------------------------
# Hit.source
# ---------------------------------------------------------------------------

def test_hit_source_com_simbolo():
    h = search.Hit(id="x", repo="r", path="p/y.py", lang="py", kind="code",
                   symbol="func", content="c", score=0.1, vec_rank=1, lex_rank=None)
    assert h.source() == "p/y.py::func [code]"


def test_hit_source_sem_simbolo():
    h = search.Hit(id="x", repo="r", path="README.md", lang=None, kind="doc",
                   symbol=None, content="c", score=0.1, vec_rank=None, lex_rank=2)
    assert h.source() == "README.md [doc]"
