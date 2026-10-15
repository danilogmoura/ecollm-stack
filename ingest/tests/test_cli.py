"""Testes da FASE 3 — CLI (cli.py).

Sem rede: o LLM é mockado (injetando ask_llm) e a busca também. Cobrimos a
camada que o CLI controla: formatação humana, montagem de contexto determinística
para o prompt (plano §4b-5), limiar "NÃO SEI" e roteamento dos subcomandos.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from ingest import cli, store
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


# Handle da implementação REAL do aviso fail-closed, capturado antes de qualquer
# patch. Os testes que exercitam o aviso chamam esta função diretamente; os demais
# (cmd_rag) usam a versão neutralizada pelo fixture autouse abaixo.
_real_warn = cli._warn_if_profile_unindexed


@pytest.fixture(autouse=True)
def _neutralize_profile_warn(monkeypatch):
    """Por default, cmd_rag não deve curto-circuitar por causa do aviso: estes
    testes focam busca/ask/gate, não o fail-closed. Stub retorna True (índice
    'pronto'). Os testes do próprio aviso sobrescrevem chamando _real_warn."""
    monkeypatch.setattr(cli, "_warn_if_profile_unindexed",
                        lambda *a, **k: True)


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
    """S21/S32: o CLI deve encaminhar o gate p/ search(). S32 mudou de um numero fixo
    (MIN_SCORE) para a sentinela PERFIL_GATE, que resolve o gate do perfil ativo em
    runtime (trocar RAG_PROFILE troca o gate sem editar codigo)."""
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
    assert seen.get("max_top1_dist") == cli.search.PERFIL_GATE
    # retro-compat: MIN_SCORE continua sendo o gate do perfil default (gemini)
    assert cli.MIN_SCORE == cli.search.MAX_TOP1_DIST == 0.34


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
# S36 · _warn_if_profile_unindexed — fail-closed de leitura no cmd_rag
# ---------------------------------------------------------------------------

class _WarnConn:
    """Conn fake p/ o aviso: controla se a tabela existe e quantos chunks tem."""

    def __init__(self, exists=True, chunks=0):
        self._exists = exists
        self._chunks = chunks
        self.closed = False

    def execute(self, sql, params=None):
        import types as _t
        if "to_regclass" in sql:
            return _t.SimpleNamespace(fetchone=lambda: (self._exists,))
        if "published_gen FROM rag_sync_state" in sql:
            return _t.SimpleNamespace(fetchone=lambda: (1,))  # gen publicada
        if "count(*)" in sql:
            return _t.SimpleNamespace(fetchone=lambda: (self._chunks,))
        return _t.SimpleNamespace(fetchone=lambda: None)

    def close(self):
        self.closed = True


def _stub_active_profile(monkeypatch, slug="qwen37"):
    prof = cli.profiles.resolve(slug)
    monkeypatch.setattr(cli.profiles, "active_profile",
                        lambda *a, **k: prof)
    return prof


def test_warn_sem_indice_retorna_false_e_aponta_sync(monkeypatch, capsys):
    """Perfil ativo sem tabela → False (cmd_rag aborta) + stderr orientando o sync."""
    conn = _WarnConn(exists=False)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    _stub_active_profile(monkeypatch, "qwen37")
    ready = _real_warn(Path("."), "r")
    err = capsys.readouterr().err
    assert ready is False, "sem índice → deve sinalizar NÃO-pronto p/ curto-circuitar"
    assert "qwen37" in err
    assert "ausente" in err
    assert "rag sync" in err and "--profile qwen37" in err
    assert conn.closed is True


def test_warn_tabela_vazia_retorna_false(monkeypatch, capsys):
    """Tabela existe mas 0 chunks publicados → tambem e 'sem indice pronto' (False)."""
    conn = _WarnConn(exists=True, chunks=0)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    _stub_active_profile(monkeypatch, "qwen37")
    ready = _real_warn(Path("."), "r")
    err = capsys.readouterr().err
    assert ready is False
    assert "vazia" in err
    assert "rag sync" in err and "--profile qwen37" in err


def test_warn_com_indice_pronto_retorna_true_silencioso(monkeypatch, capsys):
    """Tabela com chunks publicados → True + silencio (busca segue normal)."""
    conn = _WarnConn(exists=True, chunks=706)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    _stub_active_profile(monkeypatch, "qwen37")
    ready = _real_warn(Path("."), "r")
    assert ready is True
    assert capsys.readouterr().err == ""


def test_warn_db_inacessivel_retorna_true_sem_quebrar(monkeypatch, capsys):
    """Sem DB (connect levanta) → best-effort: True (deixa search tentar), nao lanca."""
    def _boom(*a, **k):
        raise RuntimeError("no db")
    monkeypatch.setattr(store, "connect", _boom)
    ready = _real_warn(Path("."), "r")  # nao deve lancar
    assert ready is True
    assert capsys.readouterr().err == ""


def test_cmd_rag_aborta_quando_perfil_sem_indice(monkeypatch, capsys):
    """Fail-closed no cmd_rag: aviso False → rc=3 e search() NUNCA é chamado
    (evita crash UndefinedTable). Sobrescreve o stub autouse com a função real."""
    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    conn = _WarnConn(exists=False)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    _stub_active_profile(monkeypatch, "qwen37")
    monkeypatch.setattr(cli, "_warn_if_profile_unindexed", _real_warn)
    called = {"search": False}

    def _never_search(*a, **k):
        called["search"] = True
        return []

    monkeypatch.setattr(cli.search, "search", _never_search)
    rc = cli.cmd_rag(_args("qualquer coisa"))
    assert rc == 3, "sem índice pronto → cmd_rag deve abortar com rc não-zero"
    assert called["search"] is False, "search não pode rodar sobre tabela inexistente"
    assert "rag sync" in capsys.readouterr().err


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


# ---------------------------------------------------------------------------
# S86 — ask_llm (HTTP) + cmd_profile (list/status/use/switch)
# ---------------------------------------------------------------------------

def test_ask_llm_monta_payload_e_extrai_resposta(monkeypatch):
    """ask_llm: monta o payload OpenAI-compat e extrai choices[0].message.content."""
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "  RESPOSTA  "}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(url=url, json=json, headers=headers)
        return _Resp()

    monkeypatch.setattr(cli.requests, "post", fake_post)
    out = cli.ask_llm("pergunta?", "contexto", cfg={"base_url": "http://x/v1",
                                                    "api_key": "k", "model": "m"})
    assert out == "RESPOSTA"                       # strip aplicado
    assert captured["url"] == "http://x/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["json"]["model"] == "m"
    assert captured["json"]["temperature"] == 0
    assert captured["json"]["messages"][0]["role"] == "system"


def test_ask_llm_sem_api_key_nao_manda_authorization(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(cli.requests, "post",
                        lambda url, json=None, headers=None, timeout=None:
                        captured.update(headers=headers) or _Resp())
    cli.ask_llm("q", "c", cfg={"base_url": "http://x/v1", "api_key": "", "model": "m"})
    assert "Authorization" not in captured["headers"]


def test_cmd_profile_list_imprime_perfis(monkeypatch, capsys):
    """cmd_profile list: imprime os perfis do registry, marca o ativo com '*'."""
    monkeypatch.setattr(cli.profiles, "active_profile", lambda *a, **k: cli.profiles.resolve("qwen37"))
    rc = cli.cmd_profile(types.SimpleNamespace(action="list", repo="."))
    assert rc == 0
    out = capsys.readouterr().out
    assert "qwen37" in out and "bgem3" in out
    assert "* qwen37" in out          # ativo marcado


def test_cmd_profile_status_imprime_estado(monkeypatch, capsys):
    """cmd_profile status: imprime o publicado + linhas por perfil."""
    conn = _WarnConn(exists=True, chunks=706)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(store, "get_published_profile", lambda c, r: "qwen37")
    monkeypatch.setattr(cli, "_profile_status_rows",
                        lambda c, r: [{"slug": "qwen37", "table": "chunks_qwen37",
                                       "dim": 1024, "model": "m", "exists": True,
                                       "chunks": 706, "published_gen": 14,
                                       "head_sha": "abc12345", "dirty": False}])
    monkeypatch.setattr(cli.profiles, "active_profile", lambda *a, **k: cli.profiles.resolve("qwen37"))
    rc = cli.cmd_profile(types.SimpleNamespace(action="status", repo="."))
    assert rc == 0
    out = capsys.readouterr().out
    assert "publicado=qwen37" in out
    assert "[PUB] qwen37" in out and "chunks=706" in out
    assert conn.closed is True


def test_cmd_profile_acao_desconhecida_retorna_2(monkeypatch, capsys):
    conn = _WarnConn()
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    rc = cli.cmd_profile(types.SimpleNamespace(action="xyz", repo="."))
    assert rc == 2
    assert "desconhecida" in capsys.readouterr().err


def test_cmd_profile_use_fail_closed_tabela_ausente(monkeypatch, capsys):
    """use: tabela ausente → rc=3 (fail-closed), nada publicado."""
    conn = _WarnConn(exists=False)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(cli.ingest_mod, "_git_state", lambda p: ("abc", False))
    rc = cli.cmd_profile(types.SimpleNamespace(action="use", repo=".", slug="qwen37"))
    assert rc == 3
    assert "não tem índice" in capsys.readouterr().err


def test_cmd_profile_use_fail_closed_indice_vazio(monkeypatch, capsys):
    """use: tabela existe mas 0 chunks → rc=3."""
    conn = _WarnConn(exists=True, chunks=0)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(cli.ingest_mod, "_git_state", lambda p: ("abc", False))
    rc = cli.cmd_profile(types.SimpleNamespace(action="use", repo=".", slug="qwen37"))
    assert rc == 3
    assert "vazio" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# S94: ramos de borda (cobertura de ramo)
# ---------------------------------------------------------------------------

def test_chat_cfg_le_env(monkeypatch):
    """S94: _chat_cfg monta o cfg do chat a partir do ambiente."""
    monkeypatch.setenv("LITELLM_BASE_URL", "http://proxy:4000/")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-x")
    monkeypatch.setenv("RAG_CHAT_MODEL", "meu-modelo")
    cfg = cli._chat_cfg()
    assert cfg["base_url"] == "http://proxy:4000"   # rstrip("/")
    assert cfg["api_key"] == "sk-x"
    assert cfg["model"] == "meu-modelo"


def test_chat_cfg_defaults(monkeypatch):
    """S94: _chat_cfg usa defaults quando o env não define."""
    monkeypatch.delenv("RAG_CHAT_MODEL", raising=False)
    cfg = cli._chat_cfg()
    assert cfg["model"] == cli.ASK_MODEL_DEFAULT


def test_profile_status_rows_lista_todos_os_perfis(monkeypatch):
    """S94: _profile_status_rows devolve uma linha por perfil do registry."""
    conn = _WarnConn(exists=True, chunks=5)
    rows = cli._profile_status_rows(conn, "r")
    assert len(rows) == len(cli.profiles.PROFILES)
    assert all("slug" in r and "exists" in r for r in rows)


def test_profile_status_rows_tabela_ausente(monkeypatch):
    """S94: _profile_status_rows com tabela ausente → exists=False, chunks=0."""
    conn = _WarnConn(exists=False)
    rows = cli._profile_status_rows(conn, "r")
    assert all(r["exists"] is False for r in rows)
    assert all(r["chunks"] == 0 for r in rows)


def test_cmd_profile_switch_sync_falha_nao_publica(monkeypatch, capsys):
    """S94: switch com sync falhando → retorna o código, nada publicado."""
    conn = _WarnConn(exists=True, chunks=5)
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(cli.ingest_mod, "_git_state", lambda p: ("abc", False))
    monkeypatch.setattr(cli, "cmd_sync", lambda args: 7)  # sync falha
    rc = cli.cmd_profile(types.SimpleNamespace(action="switch", repo=".",
                                               slug="qwen37", quiet=True,
                                               skip_gitleaks=False))
    assert rc == 7
    assert "falhou" in capsys.readouterr().err


def test_main_sem_func_imprime_help_retorna_1(monkeypatch, capsys):
    """S94: main sem subcomando → help + rc=1."""
    rc = cli.main([])
    assert rc == 1
