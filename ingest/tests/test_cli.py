"""Testes da FASE 3 — CLI (cli.py).

Sem rede: o LLM é mockado (injetando ask_llm) e a busca também. Cobrimos a
camada que o CLI controla: formatação humana, montagem de contexto determinística
para o prompt (plano §4b-5), limiar "NÃO SEI" e roteamento dos subcomandos.
"""

from __future__ import annotations

import types

from ingest import cli
from ingest.search import Hit


def _hit(i, path, score, symbol=None, kind="code", content="conteudo"):
    return Hit(id=f"id{i}", repo="r", path=path, lang="py", kind=kind,
               symbol=symbol, content=content, score=score,
               vec_rank=i, lex_rank=None)


# ---------------------------------------------------------------------------
# format_hits
# ---------------------------------------------------------------------------

def test_format_hits_vazio():
    assert cli.format_hits([]) == "(nenhum resultado)"


def test_format_hits_numerado_e_com_fonte():
    out = cli.format_hits([_hit(1, "a.py", 0.03, symbol="f"), _hit(2, "b.md", 0.02, kind="doc")])
    lines = out.splitlines()
    assert lines[0].startswith("[1] a.py::f [code]")
    assert "score=0.0300" in lines[0]
    assert "[2] b.md [doc]" in out


def test_format_hits_trunca_snippet():
    long = _hit(1, "a.py", 0.03, content="x" * 500)
    out = cli.format_hits([long], show_content=100)
    snippet_line = out.splitlines()[1]
    assert len(snippet_line.strip()) <= 101  # 100 chars + ellipsis
    assert snippet_line.rstrip().endswith("…")


def test_format_hits_sem_snippet():
    out = cli.format_hits([_hit(1, "a.py", 0.03)], show_content=0)
    # sem corpo: só a linha de cabeçalho por hit
    assert len(out.splitlines()) == 1


# ---------------------------------------------------------------------------
# build_context — ordem determinística, numeração [n]
# ---------------------------------------------------------------------------

def test_build_context_numeracao_e_ordem():
    hits = [_hit(1, "a.py", 0.03, content="ALFA"), _hit(2, "b.py", 0.02, content="BETA")]
    ctx = cli.build_context(hits)
    assert "[1] FONTE: a.py [code]" in ctx
    assert "[2] FONTE: b.py [code]" in ctx
    assert ctx.index("ALFA") < ctx.index("BETA")
    assert "---" in ctx  # separador entre blocos


def test_build_context_estavel_entre_chamadas():
    hits = [_hit(1, "a.py", 0.03), _hit(2, "b.py", 0.02)]
    assert cli.build_context(hits) == cli.build_context(hits)


# ---------------------------------------------------------------------------
# cmd_rag — NÃO SEI quando nada relevante; citação quando há resposta
# ---------------------------------------------------------------------------

def _args(query, ask=False, k=8, kind=None, path=None, repo="."):
    return types.SimpleNamespace(
        query=query, ask=ask, k=k, kind=kind, path=path, repo=repo, no_snippet=True
    )


def test_cmd_rag_busca_sua_imprime_hits(monkeypatch, capsys):
    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    monkeypatch.setattr(cli.search, "search", lambda *a, **k: [_hit(1, "a.py", 0.03)])
    rc = cli.cmd_rag(_args("pergunta"))
    assert rc == 0
    assert "[1] a.py [code]" in capsys.readouterr().out


def test_cmd_rag_ask_nao_sei_quando_busca_filtra_tudo(monkeypatch, capsys):
    """S21: o gate por distancia vive DENTRO de search(); quando nada e relevante a
    busca devolve lista vazia e o CLI imprime 'NAO SEI' sem chamar o LLM."""
    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    monkeypatch.setattr(cli.embed, "embed_texts", lambda *a, **k: [[0.0]])
    monkeypatch.setattr(cli.embed, "config_from_env", lambda: {})
    monkeypatch.setattr(cli.search, "search", lambda *a, **k: [])
    called = {"llm": False}

    def _boom(*a, **k):
        called["llm"] = True
        return "nao deveria chamar"

    monkeypatch.setattr(cli, "ask_llm", _boom)
    rc = cli.cmd_rag(_args("besteira", ask=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "NÃO SEI" in out
    assert called["llm"] is False  # nada relevante => nem chama o LLM


def test_cmd_rag_ask_passa_o_limiar_de_distancia_pra_busca(monkeypatch, capsys):
    """S21: o CLI deve encaminhar max_top1_dist=MIN_SCORE (limiar medido) p/ search()."""
    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    monkeypatch.setattr(cli.embed, "embed_texts", lambda *a, **k: [[0.0]])
    monkeypatch.setattr(cli.embed, "config_from_env", lambda: {})
    seen = {}

    def _capture(*a, **k):
        seen.update(k)
        return [_hit(1, "a.py", score=0.03, content="X")]

    monkeypatch.setattr(cli.search, "search", _capture)
    monkeypatch.setattr(cli, "ask_llm", lambda q, ctx, cfg=None: "RESPOSTA")
    cli.cmd_rag(_args("algo", ask=True))
    assert seen.get("max_top1_dist") == cli.MIN_SCORE
    assert cli.MIN_SCORE == cli.search.MAX_TOP1_DIST  # limiar agora e por distancia


def test_cmd_rag_ask_chama_llm_e_mostra_resposta(monkeypatch, capsys):
    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    monkeypatch.setattr(cli.embed, "embed_texts", lambda *a, **k: [[0.0]])
    monkeypatch.setattr(cli.embed, "config_from_env", lambda: {})
    monkeypatch.setattr(cli.search, "search",
                        lambda *a, **k: [_hit(1, "a.py", score=0.03, content="X")])
    monkeypatch.setattr(cli, "ask_llm", lambda q, ctx, cfg=None: f"RESPOSTA[{ctx[:3]}]")
    cli.cmd_rag(_args("algo", ask=True))
    out = capsys.readouterr().out
    assert "RESPOSTA" in out


# ---------------------------------------------------------------------------
# roteamento main()
# ---------------------------------------------------------------------------

def test_main_insere_search_para_query_bareta(monkeypatch):
    seen = {}

    def fake_func(args):
        seen["query"] = args.query
        return 0

    monkeypatch.setattr(cli, "cmd_rag", fake_func)
    rc = cli.main(["oi tudo bem"])
    assert rc == 0
    assert seen["query"] == "oi tudo bem"
