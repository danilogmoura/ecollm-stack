"""S31-a · Cobertura da camada VIVA de eval/recall.py — SEM rede/DB/cota.

As métricas puras já têm testes (test_recall.py). O que ficava descoberto era a
camada que liga o harness ao mundo real: `make_live_retriever` (traduz o resultado
de `ingest.search.search` em tuplas e encaminha os knobs de tuning), `render_report`
(markdown do relatório) e `main` (CLI: argv → evaluate → arquivo + exit codes do gate).

Tudo aqui é determinístico: a busca real é substituída por um stub injetado via
monkeypatch, e as dependências de rede do `main` (load_dataset/make_live_retriever)
são trocadas por fake. Nenhum teste toca LiteLLM nem Postgres.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval import recall as rc
from ingest import search as search_mod
from ingest.search import Hit


def _hit(path: str, symbol: str | None, kind: str) -> Hit:
    return Hit(id="x", repo="r", path=path, lang=None, kind=kind, symbol=symbol,
               content="c", score=0.05, vec_rank=1, lex_rank=1, dist=0.2)


# ---------------------------------------------------------------------------
# make_live_retriever
# ---------------------------------------------------------------------------

def test_make_live_retriever_traduz_hits_para_tuplas(monkeypatch):
    chamado: dict = {}

    def fake_search(question, *, repo, final_k, **kw):
        chamado.update(question=question, repo=repo, final_k=final_k, kw=kw)
        return [_hit("ingest/store.py", "iter_files", "code"),
                _hit("README.md", None, "doc")]

    monkeypatch.setattr(search_mod, "search", fake_search)
    retrieve = rc.make_live_retriever("meu-repo", final_k=8)
    q = rc.Query(id="q1", question="onde esta iter_files", expect_paths=("ingest/store.py",),
                 expect_symbols=(), expect_kinds=())
    out = retrieve(q)
    # contrato da saida: lista de (path, symbol|None, kind)
    assert out == [("ingest/store.py", "iter_files", "code"), ("README.md", None, "doc")]
    assert chamado["question"] == "onde esta iter_files"
    assert chamado["repo"] == "meu-repo"
    assert chamado["final_k"] == 8
    # sem knobs => nada extra encaminhado (default do modulo)
    assert chamado["kw"] == {}


def test_make_live_retriever_encaminha_knobs_e_omite_none(monkeypatch):
    capturado: dict = {}

    def fake_search(question, *, repo, final_k, **kw):
        capturado.update(kw=kw, final_k=final_k)
        return []

    monkeypatch.setattr(search_mod, "search", fake_search)
    retrieve = rc.make_live_retriever(
        "r", final_k=10, lexical_pt_weight=0.0, ef_search=64,
        rrf_k=80, vector_topk=120, max_top1_dist=0.34)
    q = rc.Query(id="q", question="x", expect_paths=(), expect_symbols=(), expect_kinds=())
    retrieve(q)
    assert capturado["kw"] == {"lexical_pt_weight": 0.0, "ef_search": 64,
                               "rrf_k": 80, "vector_topk": 120, "max_top1_dist": 0.34}
    assert capturado["final_k"] == 10

    # so alguns knobs => os demais NAO aparecem (deixam o default do modulo)
    retrieve2 = rc.make_live_retriever("r", final_k=5, rrf_k=42)
    retrieve2(q)
    assert capturado["kw"] == {"rrf_k": 42}


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------

def _perquery(qid, rank, *, kind_group="code", source="curated", is_negative=False,
              refused=False, targets=1, covered=0, rr=None):
    return rc.PerQuery(id=qid, question=f"pergunta {qid}", kind_group=kind_group,
                       rank=rank, ks=(1, 3, 5, 8), source=source,
                       is_negative=is_negative, refused=refused, targets=targets,
                       covered=covered)


def _agg_simple():
    overall = {"recall": {1: 0.5, 3: 0.75, 5: 0.9, 8: 1.0}, "mrr": 0.62,
               "coverage": {8: 1.0}, "refusal": None}
    by_kind = {"code": {"n": 2, "recall": {1: 0.5, 3: 0.75, 5: 0.9, 8: 1.0},
                        "mrr": 0.62, "coverage": {8: 1.0}, "refusal": None}}
    return {"overall": overall, "by_kind": by_kind, "by_source": {}, "misses": []}


def test_render_report_contem_secoes_e_veredito(tmp_path):
    rows = [_perquery("q1", 1, targets=1, covered=1), _perquery("q2", 3, targets=1, covered=1)]
    md = rc.render_report(rows, _agg_simple(), ks=(1, 3, 5, 8),
                          dataset_path=tmp_path / "dataset.jsonl", repo="ecollm",
                          embedder="gemini-embedding-2")
    assert "# Relatório de avaliação RAG" in md
    assert "## Métricas globais" in md
    assert "## Por tipo de alvo (kind)" in md
    assert "## Acertos por pergunta" in md
    # recall@8 = 1.0 >= 0.7 => ACEITO
    assert "✅ ACEITO" in md
    assert "`ecollm`" in md
    assert "| @8 | 1.000 |" in md
    assert "q1" in md and "q2" in md


def test_render_report_veredito_negativo_com_misses():
    overall = {"recall": {1: 0.0, 3: 0.0, 5: 0.1, 8: 0.5}, "mrr": 0.1,
               "coverage": {8: 0.5}, "refusal": None}
    agg = {"overall": overall, "by_kind": {}, "by_source": {}, "misses": ["q9"]}
    rows = [_perquery("q9", None, targets=1, covered=0)]
    md = rc.render_report(rows, agg, ks=(1, 3, 5, 8),
                          dataset_path=Path("dataset.jsonl"), repo="r", embedder="e")
    assert "ABAIXO DO CORTE" in md
    assert "### Perguntas sem acerto no top-8" in md
    assert "`q9`" in md


def test_render_report_inclui_bloco_por_fonte_quando_presente():
    agg = _agg_simple()
    agg["by_source"] = {
        "curated": {"n": 2, "recall": {8: 1.0}, "mrr": 0.6, "coverage": {8: 1.0}, "refusal": None},
        "external": {"n": 1, "recall": {8: 0.6}, "mrr": 0.4, "coverage": {8: 0.6}, "refusal": 0.75},
    }
    rows = [_perquery("q1", 1, source="curated", targets=1, covered=1),
            _perquery("e1", 2, source="external", targets=1, covered=1)]
    md = rc.render_report(rows, agg, ks=(1, 3, 5, 8),
                          dataset_path=Path("d.jsonl"), repo="r", embedder="e")
    assert "## Por fonte da pergunta (overfitting)" in md
    assert "external" in md


def test_render_report_linha_negativa_recusada_e_vazou():
    overall = {"recall": {8: 1.0}, "mrr": 1.0, "coverage": {8: 1.0}, "refusal": 0.5}
    agg = {"overall": overall, "by_kind": {}, "by_source": {}, "misses": []}
    neg_refusada = _perquery("n1", None, is_negative=True, refused=True)
    neg_vazou = _perquery("n2", 4, is_negative=True, refused=False)
    md = rc.render_report([neg_refusada, neg_vazou], agg, ks=(1, 3, 5, 8),
                          dataset_path=Path("d.jsonl"), repo="r", embedder="e")
    assert "recusada" in md   # negativa cortada pelo gate
    assert "VAZOU" in md      # negativa que retornou resultados (falha de recusa)
    assert "🚫" in md


# ---------------------------------------------------------------------------
# main (CLI) — argv mockado, dependências de rede substituídas
# ---------------------------------------------------------------------------

def _wire_main_stubs(monkeypatch, tmp_path, ranks_by_id):
    """Faz main() rodar sem rede: dataset fake + retriever que respeita ranks."""
    queries = [rc.Query(id=qid, question=f"p {qid}", expect_paths=(f"{qid}.py",),
                        expect_symbols=(), expect_kinds=())
               for qid in ranks_by_id]

    def fake_load(path):
        return queries

    def fake_retriever(repo, final_k, **kw):
        def _r(q):
            rank = ranks_by_id.get(q.id)
            if rank is None:
                return []
            hits = [(None, None, None)] * (rank - 1)
            hits.append((q.expect_paths[0], None, "code"))
            return hits
        return _r

    monkeypatch.setattr(rc, "load_dataset", fake_load)
    monkeypatch.setattr(rc, "make_live_retriever", fake_retriever)
    out = tmp_path / "relatorio.md"
    return out


def test_main_escreve_relatorio_e_retorna_zero(monkeypatch, tmp_path, capsys):
    out = _wire_main_stubs(monkeypatch, tmp_path, {"q1": 1, "q2": 2})
    rc.main(["--dataset", str(tmp_path / "d.jsonl"), "--out", str(out)])
    assert out.exists()
    conteudo = out.read_text(encoding="utf-8")
    assert "# Relatório de avaliação RAG" in conteudo
    printed = capsys.readouterr().out
    assert "[eval]" in printed and "relatório ->" in printed


def test_main_json_imprime_payload(monkeypatch, tmp_path, capsys):
    out = _wire_main_stubs(monkeypatch, tmp_path, {"q1": 1})
    rc.main(["--dataset", str(tmp_path / "d.jsonl"), "--out", str(out), "--json"])
    printed = capsys.readouterr().out
    assert '"overall"' in printed  # JSON dumpado
    assert out.exists()


def test_main_gate_passa_retorna_zero(monkeypatch, tmp_path):
    out = _wire_main_stubs(monkeypatch, tmp_path, {"q1": 1, "q2": 1})
    rc._GATE_BASELINE_RECALL_AT_8 = 1.0  # não depende do estado global real
    code = rc.main(["--dataset", str(tmp_path / "d.jsonl"), "--out", str(out),
                    "--gate", "--min-recall", "0.5"])
    assert code == 0


def test_main_gate_repruva_retorna_um(monkeypatch, tmp_path, capsys):
    # todas erram => recall@8 = 0 < piso => exit 1
    out = _wire_main_stubs(monkeypatch, tmp_path, {"q1": None})
    code = rc.main(["--dataset", str(tmp_path / "d.jsonl"), "--out", str(out),
                    "--gate", "--min-recall", "0.9"])
    assert code == 1
    assert "REPROVADO" in capsys.readouterr().err


def test_main_gate_forca_k8_mesmo_sem_listar(monkeypatch, tmp_path):
    # --k 1,3 nao inclui @8; modo gate deve acrescenta-lo para vigiar
    out = _wire_main_stubs(monkeypatch, tmp_path, {"q1": 1})
    code = rc.main(["--dataset", str(tmp_path / "d.jsonl"), "--out", str(out),
                    "--k", "1,3", "--gate", "--min-recall", "0.1"])
    assert code == 0
    md = out.read_text(encoding="utf-8")
    assert "| @8 |" in md  # @8 foi avaliado apesar de --k=1,3
