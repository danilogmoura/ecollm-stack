"""Testes da FASE 2 — ingest.py (orquestrador), com git real + embed/store fake.

Nao tocam LiteLLM nem pgvector: gitleaks/embed sao stubados e o "DB" e um dict
em memoria que imita existing_file_hashes/upsert/delete. O objetivo e validar a
MAQUINA de sync incremental (new/changed/unchanged/removido) e o --dry-run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ingest import embed, ingest, store


def _git(repo: Path, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   env={**subprocess.os.environ,
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
                   capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "myrepo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "hello.py").write_text("def greet():\n    return 'hi'\n")
    (r / "notes.md").write_text("# Title\n\n## Section A\n\nbody one two three\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "init")
    return r


class _NullConn:
    """Conexão fake só com close() — o orquestrador usa `with conn:` e close()."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


class FakeDB:
    """Imita as partes de store que o orquestrador usa, em memoria."""
    def __init__(self):
        self.rows: dict[tuple[str, str], store.Row] = {}  # (path, content_hash)
        self.file_hashes: dict[str, str] = {}             # path -> file_hash
        self.embedded: list[tuple[str, str]] = []         # (text, kind) chamados

    def existing(self, repo):
        return dict(self.file_hashes)

    def delete_stale(self, repo, paths):
        n = 0
        for p in paths:
            for key in [k for k in self.rows if k[0] == p]:
                del self.rows[key]
                n += 1
            self.file_hashes.pop(p, None)
        return n

    def delete_removed(self, repo, live):
        live = set(live)
        n = 0
        for key in [k for k in self.rows if k[0] not in live]:
            del self.rows[key]
            n += 1
        for p in [p for p in self.file_hashes if p not in live]:
            self.file_hashes.pop(p)
        return n

    def upsert(self, rows):
        ins = unch = 0
        for r in rows:
            key = (r.path, r.content_hash)
            if key in self.rows:
                unch += 1
            else:
                self.rows[key] = r
                ins += 1
            self.file_hashes[r.path] = r.file_hash
        return ins, unch

    def count(self, repo):
        return len(self.rows)


@pytest.fixture
def patched(monkeypatch):
    """Stub gitleaks + embed + camada de store no orquestrador."""
    db = FakeDB()

    monkeypatch.setattr(ingest, "gitleaks_gate", lambda root, entries: (True, "ok"))

    def fake_embed_documents(pairs, *, cfg=None, **kw):
        db.embedded.extend(pairs)
        return [[0.5, 0.5] for _ in pairs]

    monkeypatch.setattr(embed, "embed_documents", fake_embed_documents)

    monkeypatch.setattr(store, "connect", lambda url=None: _NullConn())
    monkeypatch.setattr(store, "existing_file_hashes", lambda conn, repo: db.existing(repo))
    monkeypatch.setattr(store, "delete_stale", lambda conn, repo, paths: db.delete_stale(repo, paths))
    monkeypatch.setattr(store, "delete_removed", lambda conn, repo, live: db.delete_removed(repo, live))
    monkeypatch.setattr(store, "upsert_rows", lambda conn, rows: db.upsert(rows))
    monkeypatch.setattr(store, "count_chunks", lambda conn, repo: db.count(repo))
    return db


def test_primeira_execucao_inserta_tudo(repo, patched):
    rep = ingest.run_ingest(repo, verbose=False)
    assert rep.inserted > 0
    assert rep.deleted == 0
    assert rep.chunks_total == rep.inserted
    # conteudo embedado NAO contem task-prefix (prefixo so na chamada de embed,
    # mas embed_documents recebe texto puro + kind; aqui validamos que nao vazou)
    assert all(not t.startswith(embed.TASK_PREFIX_DOC) for t, _ in patched.embedded)


def test_reexecucao_sem_mudanca_zero_embeddings(repo, patched):
    ingest.run_ingest(repo, verbose=False)
    patched.embedded.clear()
    rep2 = ingest.run_ingest(repo, verbose=False)
    assert patched.embedded == []          # nada re-embedado (blob igual)
    assert rep2.inserted == 0
    assert rep2.unchanged > 0


def test_arquivo_editado_reembeda_so_ele(repo, patched):
    ingest.run_ingest(repo, verbose=False)
    patched.embedded.clear()
    (repo / "hello.py").write_text("def greet():\n    return 'hello world'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "edit")
    rep = ingest.run_ingest(repo, verbose=False)
    # só hello.py foi re-embedado
    paths_embedded = {c for c in patched.embedded}
    assert rep.changed_files == ["hello.py"]
    assert rep.deleted >= 1  # chunk antigo de hello.py removido
    assert rep.inserted >= 1


def test_arquivo_apagado_remove_chunks(repo, patched):
    ingest.run_ingest(repo, verbose=False)
    total_before = patched.count("myrepo")
    (repo / "notes.md").unlink()
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "rm")
    rep = ingest.run_ingest(repo, verbose=False)
    assert "notes.md" in rep.removed_files
    assert rep.deleted >= 1
    assert patched.count("myrepo") < total_before


def test_dry_run_nao_escreve_nem_embeda(repo, patched):
    rep = ingest.run_ingest(repo, dry_run=True, verbose=False)
    assert patched.embedded == []
    assert patched.count("myrepo") == 0
    assert rep.inserted == 0


def test_gate_falha_aborta(repo, monkeypatch):
    monkeypatch.setattr(ingest, "gitleaks_gate", lambda root, entries: (False, "segredo!"))
    monkeypatch.setattr(store, "connect", lambda url=None: pytest.fail("não deveria conectar"))
    with pytest.raises(SystemExit) as exc:
        ingest.run_ingest(repo, verbose=False)
    assert exc.value.code == 2
