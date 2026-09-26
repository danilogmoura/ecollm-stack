"""Testes unitários das métricas da FASE 4 (eval/recall.py) — SEM rede/DB.

Exercitam apenas as funcoes puras (matches, first_hit_rank, recall_at_k,
reciprocal_rank, evaluate com retriever fake, aggregate, load_dataset). A
retrieval real e injetavel, entao nada aqui toca LiteLLM ou Postgres.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval import recall as rc


def _q(qid="q1", paths=("a.py",), symbols=(), kinds=()):
    return rc.Query(id=qid, question=f"pergunta {qid}", expect_paths=tuple(paths),
                    expect_symbols=tuple(symbols), expect_kinds=tuple(kinds))


# --------------------------------------------------------------------------
# Query.matches
# --------------------------------------------------------------------------

def test_matches_so_path():
    q = _q(paths=("README.md", "litellm/config.yaml"))
    assert q.matches("README.md", None, "doc")
    assert q.matches("litellm/config.yaml", "model_list#1", "config")
    assert not q.matches("ingest/cli.py", None, "code")


def test_matches_com_symbol_exige_casamento():
    q = _q(paths=["ingest/chunker.py"], symbols=["chunk_code"])
    assert q.matches("ingest/chunker.py", "chunk_code", "code")
    # symbol diferente nao casa, mesmo com path certo
    assert not q.matches("ingest/chunker.py", "chunk_doc", "code")
    # symbol ausente na saida nunca casa com um esperado
    assert not q.matches("ingest/chunker.py", None, "code")


def test_matches_com_kind_filtro():
    q = _q(paths=["x"], kinds=["config"])
    assert q.matches("x", None, "config")
    assert not q.matches("x", None, "code")


# --------------------------------------------------------------------------
# metricas de posicao
# --------------------------------------------------------------------------

def test_first_hit_rank_posicao_1based():
    q = _q(paths=["t.py"])
    results = [("a.py", None, "code"), ("t.py", None, "code"), ("b.py", None, "code")]
    assert rc.first_hit_rank(q, results) == 2


def test_first_hit_rank_usa_primeiro_acerto():
    q = _q(paths=["t.py"])
    results = [("t.py", None, "code"), ("t.py", None, "code")]
    assert rc.first_hit_rank(q, results) == 1


def test_first_hit_rank_miss_retorna_none():
    q = _q(paths=["nao_existe.py"])
    assert rc.first_hit_rank(q, [("a.py", None, "code")]) is None


@pytest.mark.parametrize("rank,k,expected", [
    (1, 1, 1.0), (2, 1, 0.0), (5, 8, 1.0), (9, 8, 0.0), (None, 8, 0.0),
])
def test_recall_at_k(rank, k, expected):
    assert rc.recall_at_k(rank, k) == expected


def test_reciprocal_rank():
    assert rc.reciprocal_rank(1) == 1.0
    assert rc.reciprocal_rank(4) == 0.25
    assert rc.reciprocal_rank(None) == 0.0


# --------------------------------------------------------------------------
# evaluate + aggregate com retriever fake
# --------------------------------------------------------------------------

def _fake_retrieve(mapping):
    """mapping: id -> lista ordenada de (path,symbol,kind)."""
    def _r(q):
        return mapping.get(q.id, [])
    return _r


def test_evaluate_produz_por_pergunta():
    queries = [_q("hit1", ["a.py"]), _q("miss", ["zz.py"])]
    ret = _fake_retrieve({
        "hit1": [("a.py", None, "code")],   # rank 1
        "miss": [("a.py", None, "code")],   # alvo zz nunca aparece
    })
    rows = rc.evaluate(queries, ret, ks=[1, 3])
    by_id = {r.id: r for r in rows}
    assert by_id["hit1"].rank == 1
    assert by_id["hit1"].recall(1) == 1.0
    assert by_id["miss"].rank is None
    assert by_id["miss"].rr == 0.0


def test_aggregate_recall_e_mrr():
    queries = [_q("a", ["a.py"]), _q("b", ["b.py"]), _q("c", ["c.py"])]
    ret = _fake_retrieve({
        "a": [("a.py", None, "code")],           # rank 1
        "b": [("x.py", None, "code"), ("b.py", None, "code")],  # rank 2
        "c": [("x.py", None, "code")],           # miss
    })
    rows = rc.evaluate(queries, ret, ks=[1, 2])
    agg = rc.aggregate(rows, ks=[1, 2])
    o = agg["overall"]
    assert o["n"] == 3
    # aggregate arredonda a 4 casas -> comparar com o mesmo arredondamento
    assert o["recall"][1] == pytest.approx(round(1 / 3, 4))     # so 'a' no top-1
    assert o["recall"][2] == pytest.approx(round(2 / 3, 4))     # 'a' e 'b' no top-2
    # MRR = (1 + 1/2 + 0)/3
    assert o["mrr"] == pytest.approx(round((1 + 0.5 + 0) / 3, 4))
    assert agg["misses"] == ["c"]


def test_aggregate_breakdown_por_kind():
    queries = [
        _q("d1", ["README.md"], kinds=["doc"]),
        _q("c1", ["x.py"], kinds=["code"]),
        _q("m1", ["y.py"], kinds=[]),   # mixed (sem kind fixado)
    ]
    ret = _fake_retrieve({
        "d1": [("README.md", None, "doc")],
        "c1": [("x.py", None, "code")],
        "m1": [("y.py", None, "config")],
    })
    rows = rc.evaluate(queries, ret, ks=[1])
    agg = rc.aggregate(rows, ks=[1])
    assert set(agg["by_kind"]) == {"doc", "code", "mixed"}
    assert agg["by_kind"]["doc"]["n"] == 1
    assert agg["by_kind"]["doc"]["recall"][1] == 1.0


# --------------------------------------------------------------------------
# load_dataset
# --------------------------------------------------------------------------

def test_load_dataset_roundtrip(tmp_path: Path):
    p = tmp_path / "ds.jsonl"
    p.write_text(
        "# comentario ignorado\n"
        "\n"
        + json.dumps({"id": "q1", "question": "oi", "expect_paths": ["a.py"],
                      "expect_symbols": ["s"], "expect_kinds": ["code"], "note": "n"}) + "\n",
        encoding="utf-8",
    )
    qs = rc.load_dataset(p)
    assert len(qs) == 1
    assert qs[0].id == "q1"
    assert qs[0].expect_symbols == ("s",)
    assert qs[0].matches("a.py", "s", "code")


def test_load_dataset_invalido_raisa(tmp_path: Path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"question": "sem id"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        rc.load_dataset(p)


def test_dataset_real_carrega_e_tem_alvos_validos():
    """O dataset curado do repo deve carregar e cada pergunta ter >=1 path esperado."""
    qs = rc.load_dataset()
    assert len(qs) >= 20
    for q in qs:
        assert q.expect_paths, f"{q.id} sem expect_paths"
        assert q.question.strip(), f"{q.id} pergunta vazia"


# --------------------------------------------------------------------------
# gate de regressão (S15) — puro, sem DB/rede
# --------------------------------------------------------------------------

def _agg_com_recall8(v):
    return {"overall": {"n": 30, "recall": {1: 0.4, 3: 0.6, 5: 0.7, 8: v, 10: 0.9},
                        "mrr": 0.5}, "by_kind": {}, "misses": []}


def test_gate_piso_eh_baseline_menos_margem():
    assert rc.gate_threshold() == round(rc.BASELINE_RECALL_AT_8 - rc.MARGEM_REGRESSAO, 4)
    # baseline 0,933 - margem 0,033 => piso ~0,90
    assert abs(rc.gate_threshold() - 0.90) < 1e-9


def test_gate_aprova_no_baseline():
    g = rc.check_gate(_agg_com_recall8(0.933))
    assert g["passed"] is True
    assert g["k"] == rc.GATE_K and g["medido"] == 0.933


def test_gate_aprova_exatamente_no_piso():
    g = rc.check_gate(_agg_com_recall8(0.90))
    assert g["passed"] is True  # >= piso


def test_gate_reprova_abaixo_do_piso():
    # regressão sutil (peso da fusão alterado) cai de 0,933 p/ 0,867 -> reprova
    g = rc.check_gate(_agg_com_recall8(0.867))
    assert g["passed"] is False
    assert g["piso"] == rc.gate_threshold()


def test_gate_falha_conservador_sem_metrica():
    # recall@8 ausente (k não avaliado / sem perguntas) NÃO é aprovado
    assert rc.check_gate({"overall": {"recall": {}}})["passed"] is False
    assert rc.check_gate({})["passed"] is False


def test_gate_override_de_threshold():
    g = rc.check_gate(_agg_com_recall8(0.95), threshold=0.97)
    assert g["passed"] is False and g["piso"] == 0.97


# --------------------------------------------------------------------------
# S23 · Eval v2 — recusa, cobertura multi-target e breakdown por fonte
# (só funcoes puras; nada toca DB/rede)
# --------------------------------------------------------------------------

def _neg(qid="n1"):
    return rc.Query(id=qid, question=f"fora do assunto {qid}", expect_paths=(),
                    expect_symbols=(), expect_kinds=(), should_refuse=True)


def _ext(qid="e1", paths=("README.md",)):
    return rc.Query(id=qid, question=f"externas {qid}", expect_paths=tuple(paths),
                    expect_symbols=(), expect_kinds=(), source="external")


def test_query_negativa_e_recusada_so_com_lista_vazia():
    ret = _fake_retrieve({"n1": []})           # busca cortou tudo => recusa correta
    rows = rc.evaluate([_neg("n1")], ret, ks=[1, 8])
    r = rows[0]
    assert r.is_negative and r.refused
    assert r.recall(8) == 1.0                  # recusar conta como acerto
    assert r.coverage(8) == 1.0                # nada a cobrir


def test_query_negativa_que_vaza_e_falha():
    # gate nao cortou: retornou chunks => vazamento, deve contar como ERRO
    ret = _fake_retrieve({"n1": [("README.md", None, "doc")]})
    rows = rc.evaluate([_neg("n1")], ret, ks=[1, 8])
    r = rows[0]
    assert r.is_negative and not r.refused
    assert r.recall(8) == 0.0


def test_cobertura_multialvo_no_topk():
    q = rc.Query(id="m1", question="multi", expect_paths=("a.py", "b.py"),
                 expect_symbols=(), expect_kinds=(), expect_targets=2)
    # so 'a' cai no top-2 => cobertura 1/2; ambos caem ate @3 => 2/2
    ret = _fake_retrieve({"m1": [("a.py", None, "code"), ("x.py", None, "code"),
                                 ("b.py", None, "code")]})
    rows = rc.evaluate([q], ret, ks=[2, 3])
    r = rows[0]
    assert r.targets == 2
    assert r.covered == 2                       # kmax=3 pega os dois
    assert r.coverage(3) == 1.0


def test_aggregate_reporta_by_source_e_recusa():
    queries = [_q("c1", ["a.py"]), _ext("e1", ["b.py"]), _neg("n1")]
    ret = _fake_retrieve({
        "c1": [("a.py", None, "code")],         # curada acertada
        "e1": [("zz.py", None, "code")],        # externa errada (miss)
        "n1": [],                               # negativa bem recusada
    })
    rows = rc.evaluate(queries, ret, ks=[1])
    agg = rc.aggregate(rows, ks=[1])
    assert set(agg["by_source"]) == {"curated", "external"}
    assert agg["by_source"]["external"]["recall"][1] == 0.0
    # a negativa e curated por default => recusa medida dentro do grupo curated
    assert agg["by_source"]["curated"]["refusal"] == 1.0
    assert agg["by_source"]["external"]["refusal"] is None   # sem negativas aqui
    assert agg["overall"]["refusal"] == 1.0
    assert "e1" in agg["misses"]


def test_load_dataset_v2_preserva_campos_extras(tmp_path: Path):
    p = tmp_path / "ds.jsonl"
    p.write_text(json.dumps({
        "id": "e9", "question": "oi", "expect_paths": ["a.py"],
        "source": "external", "should_refuse": False, "expect_targets": 3,
    }) + "\n" + json.dumps({
        "id": "n9", "question": "fora", "expect_paths": [], "should_refuse": True,
    }) + "\n", encoding="utf-8")
    qs = rc.load_dataset(p)
    by = {q.id: q for q in qs}
    assert by["e9"].source == "external"
    assert by["e9"].targets == 3
    assert by["n9"].is_negative()
    assert by["n9"].targets == 0 or by["n9"].expect_targets == 0


def test_dataset_v2_real_carrega_com_treseixos():
    """dataset-v2.jsonl deve ter externas, multi-target e negativas de verdade."""
    v2 = rc.EVAL_DIR / "dataset-v2.jsonl"
    if not v2.exists():
        pytest.skip("dataset-v2 ausente")
    qs = rc.load_dataset(v2)
    ext = [q for q in qs if q.source == "external"]
    multi = [q for q in qs if q.targets > 1]
    neg = [q for q in qs if q.is_negative()]
    assert len(ext) >= 15, "S23 exige >=15 perguntas externas"
    assert len(multi) >= 3, "S23 exige perguntas multi-target"
    assert len(neg) >= 5, "S23 exige casos negativos/recusa"
    # negativas NAO devem ter alvo esperado (senao a recusa e mal definida)
    for q in neg:
        assert not q.expect_paths, f"{q.id} negativa com expect_paths"
