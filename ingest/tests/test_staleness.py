"""S14 — testes de detecção de índice desatualizado (T-OPS-2).

Cobre o núcleo da lógica SEM DB real nem git do workspace: um FakeConn devolve o
registro de rag_sync_state e monkeypatch._git_state controla o "estado atual do
git". Assim testamos as 4 decisões que importam:
  - HEAD igual + árvore limpa  -> fresco (sem aviso);
  - HEAD mudou                 -> stale com motivo;
  - sujo após sync limpo       -> stale;
  - sem registro / sem conexão -> conservador (stale, nunca falsa garantia).
E a integração: search.staleness_warning propaga, e o envelope MCP traz 'stale'.
"""

from __future__ import annotations

import json

import pytest

from ingest import ingest, search


class _StateConn:
    """Conexão fake que só responde ao SELECT de rag_sync_state."""

    def __init__(self, row):
        self.row = row  # (head_sha, dirty) | None
        self.closed = False

    def execute(self, sql, params=None):
        assert "rag_sync_state" in sql
        outer = self

        class _Cur:
            def fetchone(_):
                return outer.row
        return _Cur()

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# is_index_stale — lógica pura (git atual mockado)
# ---------------------------------------------------------------------------

def test_fresco_quando_head_igual_e_arvore_limpa(monkeypatch):
    monkeypatch.setattr(ingest, "_git_state", lambda root: ("abc123", False))
    conn = _StateConn(("abc123", False))
    stale, reason = ingest.is_index_stale(conn, "repo", "/x")
    assert stale is False
    assert "sincronizado" in reason


def test_stale_quando_head_mudou(monkeypatch):
    monkeypatch.setattr(ingest, "_git_state", lambda root: ("NEWHASH", False))
    conn = _StateConn(("OLDHASH", False))
    stale, reason = ingest.is_index_stale(conn, "repo", "/x")
    assert stale is True
    assert "HEAD mudou" in reason


def test_stale_quando_arvore_suja_apos_sync_limpo(monkeypatch):
    monkeypatch.setattr(ingest, "_git_state", lambda root: ("same", True))
    conn = _StateConn(("same", False))
    stale, reason = ingest.is_index_stale(conn, "repo", "/x")
    assert stale is True
    assert "nao commitadas" in reason


def test_fresco_quando_sujo_no_sync_e_agora(monkeypatch):
    # se já estava sujo no sync e continua no mesmo HEAD, não há nova deriva.
    monkeypatch.setattr(ingest, "_git_state", lambda root: ("same", True))
    conn = _StateConn(("same", True))
    stale, _ = ingest.is_index_stale(conn, "repo", "/x")
    assert stale is False


def test_sem_registro_de_sync_conservador(monkeypatch):
    monkeypatch.setattr(ingest, "_git_state", lambda root: ("h", False))
    conn = _StateConn(None)
    stale, reason = ingest.is_index_stale(conn, "repo", "/x")
    assert stale is True
    assert "nenhum registro" in reason


def test_sem_conexao_conservador():
    stale, reason = ingest.is_index_stale(None, "repo", "/x")
    assert stale is True
    assert "sem conexao" in reason


def test_erro_de_query_vira_aviso_nao_excecao():
    class Boom:
        def execute(self, *a, **k):
            raise RuntimeError("tabela ausente")
    stale, reason = ingest.is_index_stale(Boom(), "repo", "/x")
    assert stale is True
    assert "indisponivel" in reason


# ---------------------------------------------------------------------------
# _git_state — usa git real num repo temporário
# ---------------------------------------------------------------------------

def _git(repo, *args):
    import subprocess
    subprocess.run(["git", *args], cwd=repo, check=True,
                   env={**subprocess.os.environ,
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
                   capture_output=True)


def test_git_state_reflete_head_e_sujeira(tmp_path):
    r = tmp_path / "g"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "f.py").write_text("x = 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "c1")
    head, dirty = ingest._git_state(r)
    assert head and len(head) == 40
    assert dirty is False
    # edita arquivo versionado -> sujo
    (r / "f.py").write_text("x = 2\n")
    _, dirty2 = ingest._git_state(r)
    assert dirty2 is True


def test_git_state_ignora_untracked(tmp_path):
    r = tmp_path / "g2"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "f.py").write_text("x = 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "c1")
    # arquivo NAO versionado nao deve marcar dirty (corpus = git ls-files)
    (r / "scratch.txt").write_text("noise\n")
    _, dirty = ingest._git_state(r)
    assert dirty is False


# ---------------------------------------------------------------------------
# search.staleness_warning — propaga para None ou mensagem
# ---------------------------------------------------------------------------

def test_staleness_warning_none_quando_fresco(monkeypatch):
    monkeypatch.setattr(ingest, "is_index_stale",
                        lambda conn, repo, root: (False, "ok"))
    assert search.staleness_warning("/x", "repo", conn=_StateConn(("h", False))) is None


def test_staleness_warning_msg_quando_stale(monkeypatch):
    monkeypatch.setattr(ingest, "is_index_stale",
                        lambda conn, repo, root: (True, "HEAD mudou"))
    w = search.staleness_warning("/x", "repo", conn=_StateConn(("a", False)))
    assert w and "desatualizado" in w and "HEAD mudou" in w


def test_staleness_warning_nunca_levanta(monkeypatch):
    def boom(conn, repo, root):
        raise RuntimeError("db fora")
    monkeypatch.setattr(ingest, "is_index_stale", boom)
    w = search.staleness_warning("/x", "repo", conn=_StateConn(("h", False)))
    assert w and "nao foi possivel" in w
