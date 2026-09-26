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
def _row(i, path, kind="code", symbol=None, content="c", extra=None):
    # Emula a forma real vinda do SQL: 8 colunas de _COLS + 1 extra. Para o caminho
    # denso o extra e a DISTANCIA coseno (float); p/ lexicos e ts_rank. Default usa
    # um valor plausivel so lexicamente; testes densos passam extra=float explicito.
    return (f"id{i}", "repo", path, "py", kind, symbol, content, f"h{i}",
            0.2 if extra is None else extra)


def _drow(i, path, dist, **kw):
    # linha do caminho DENSO com distancia coseno explicita
    return _row(i, path, extra=dist, **kw)


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
    fused = search.reciprocal_rank_fusion([[_drow(1, "a", 0.1), _drow(2, "b", 0.2)]], k=60)
    # rank1 -> 1/61, rank2 -> 1/62
    assert fused["id1"][1] == pytest.approx(1 / 61)
    assert fused["id2"][1] == pytest.approx(1 / 62)
    assert fused["id1"][2] == 1   # vec_rank
    assert fused["id1"][3] is None  # só estava na 1ª lista (densa)
    # S21: a distancia coseno da linha densa e propagada no slot final
    assert fused["id1"][4] == pytest.approx(0.1)


def test_rrf_soma_das_duas_listas_e_marca_ranks():
    shared = _drow(2, "b", 0.3)  # MESMO id nas duas listas -> soma dos dois ranks
    dense = [_drow(1, "a", 0.1), shared]
    lexical = [_row(2, "b"), _row(7, "c")]  # id2 aparece nos dois
    fused = search.reciprocal_rank_fusion([dense, lexical], k=60)
    # id2: 1/(60+2) [densa] + 1/(60+1) [léxica]
    assert fused["id2"][1] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["id2"][2] == 2   # vec_rank=2
    assert fused["id2"][3] == 1   # lex_rank=1
    # id1 só densa, id7 só léxica (na posição 2 da lista léxica)
    assert fused["id1"][3] is None
    assert fused["id7"][2] is None
    assert fused["id7"][3] == 2
    # S21: so o caminho denso carrega distancia; id7 (so lexico) fica None
    assert fused["id2"][4] == pytest.approx(0.3)
    assert fused["id7"][4] is None


def test_rrf_pesos_aplicam_por_lista():
    dense = [_drow(1, "a", 0.1)]
    lexical = [_row(1, "a")]
    fused = search.reciprocal_rank_fusion([dense, lexical], weights=[2.0, 1.0], k=60)
    # 2*(1/61) + 1*(1/61) = 3/61
    assert fused["id1"][1] == pytest.approx(3 / 61)


# ---------------------------------------------------------------------------
# search() — integração com FakeConn + qvec injetado
# ---------------------------------------------------------------------------

def test_search_combina_ordena_e_limita():
    shared = _drow(2, "y.py", 0.15)  # aparece nas duas listas -> maior score combinado
    dense = [_drow(1, "z.py", 0.1), shared, _drow(3, "x.py", 0.4)]
    lexical = [_row(2, "y.py"), _row(9, "w.py")]
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
    # S21: a 1a chamada e o set_config('hnsw.ef_search', ...) (params em formato
    # posicional/tupla), nao uma busca com filtros. Filtra pelas chamadas nomeadas.
    query_calls = [(sql, p) for sql, p in conn.calls if isinstance(p, dict)]
    assert len(query_calls) == 2, "esperado: densa + léxica"
    # ambas com kind/path_like/repo corretos
    for _, params in query_calls:
        assert params["repo"] == "meu"
        assert params["kind"] == "config"
        assert params["path_like"] == "litellm/%"


def test_search_deterministico_empate_por_path():
    # dois chunks com MESMO score (cada um em posição espelhada) -> desempate por path
    a = _drow(1, "aaa.py", 0.1)
    b = _drow(2, "bbb.py", 0.2)
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
# S21 · gate de relevancia por distancia coseno bruta (substitui MIN_SCORE morto)
# ---------------------------------------------------------------------------

def test_s21_hit_carrega_distancia_do_caminho_denso():
    doc = _drow(5, "README.md", 0.18, kind="doc")
    conn = FakeConn([doc], [])
    hits = search.search("q", repo="r", conn=conn, qvec=[0.0])
    assert hits[0].dist == pytest.approx(0.18)


def test_s21_gate_desligado_por_default_nao_filtra():
    # vizinho denso longe (0.9); sem max_top1_dist a saida permanece
    far = _drow(1, "a.py", 0.9)
    conn = FakeConn([far], [])
    hits = search.search("q", repo="r", conn=conn, qvec=[0.0])
    assert len(hits) == 1


def test_s21_gate_filtra_quando_vizinho_denso_aldo_limiar():
    # query fora-de-corpus: melhor candidato denso a 0.37 > limiar 0.34 => vazio
    far = _drow(1, "a.py", 0.37)
    conn = FakeConn([far], [])
    hits = search.search("bolo de cenoura", repo="r", conn=conn, qvec=[0.0],
                         max_top1_dist=search.MAX_TOP1_DIST)
    assert hits == []


def test_s21_gate_preserva_quando_vizinho_denso_perto():
    near = _drow(1, "a.py", 0.20)
    conn = FakeConn([near], [])
    hits = search.search("q", repo="r", conn=conn, qvec=[0.0],
                         max_top1_dist=search.MAX_TOP1_DIST)
    assert len(hits) == 1


def test_s21_gate_usa_o_mais_proximo_entre_densos():
    # um candidato perto (0.2) e outro longe (0.5): min dist <= limiar => mantem
    near = _drow(1, "a.py", 0.2)
    far = _drow(2, "b.py", 0.5)
    conn = FakeConn([near, far], [])
    hits = search.search("q", repo="r", conn=conn, qvec=[0.0],
                         max_top1_dist=search.MAX_TOP1_DIST)
    assert {h.id for h in hits} == {"id1", "id2"}


def test_s21_limiar_medido_esta_entre_corpus_e_fora():
    # calibracao: MAX_TOP1_DIST acima do pior caso legitimo medido (~0.30) e abaixo
    # da zona de nao-relevancia observada (~0.37)
    assert 0.30 < search.MAX_TOP1_DIST < 0.37


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
