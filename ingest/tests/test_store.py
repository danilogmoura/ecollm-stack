"""Testes da FASE 2 — store.py (sem DB: conexão fake).

Cobrem a lógica pura (build_rows, alinhamento chunk/vetor) e o SQL emitido por
upsert/delete via um cursor mock que registra as statements. A integração real
contra pgvector é validada à parte no run_ingest (FASE 2 checklist).
"""

from __future__ import annotations

import pytest

from ingest import store
from ingest.chunker import Chunk
from ingest.loader import content_sha256


class FakeCursor:
    def __init__(self, rowcount=1, rows=None):
        self._rowcount = rowcount
        self._rows = rows or []

    @property
    def rowcount(self):
        return self._rowcount

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)


class FakeConn:
    """Registra execute() e devolve rowcount configurável por chamada."""

    def __init__(self, results=None, rowcounts=None):
        self.calls: list[tuple[str, dict | tuple | None]] = []
        self._results = results or []
        self._rowcounts = rowcounts or []
        self._i = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        rc = self._rowcounts[self._i] if self._i < len(self._rowcounts) else 1
        rows = self._results[self._i] if self._i < len(self._results) else []
        self._i += 1
        return FakeCursor(rc, rows)


def _chunk(path="a.py", kind="code", lang="python", symbol="f", content="def f():\n    pass"):
    return Chunk(path=path, kind=kind, lang=lang, symbol=symbol, content=content)


def test_build_rows_alinha_e_hasha_texto_puro():
    chunks = [_chunk(content="alpha"), _chunk(content="beta")]
    vecs = [[0.1, 0.2], [0.3, 0.4]]
    rows = store.build_rows("repoX", "deadbeef" * 5, chunks, vecs)
    assert len(rows) == 2
    # content_hash = sha256 do texto PURO (sem task-prefix)
    assert rows[0].content_hash == content_sha256("alpha")
    assert rows[1].content_hash == content_sha256("beta")
    assert all(r.repo == "repoX" for r in rows)
    assert all(r.file_hash == "deadbeef" * 5 for r in rows)
    assert rows[0].embedding_text.startswith("[")


def test_build_rows_desalinhado_levanta():
    with pytest.raises(ValueError):
        store.build_rows("r", "h", [_chunk()], [])


def test_upsert_counta_inserted_vs_unchanged():
    rows = store.build_rows("r", "h", [_chunk(content="a"), _chunk(content="b")],
                            [[0.1], [0.2]])
    conn = FakeConn(rowcounts=[1, 0])  # primeiro insere, segundo conflita
    ins, unch = store.upsert_rows(conn, rows)
    assert (ins, unch) == (1, 1)
    # SQL de upsert com ON CONFLICT DO NOTHING presente
    assert "ON CONFLICT (repo, path, content_hash) DO NOTHING" in conn.calls[0][0]
    # cast ::halfvec aplicado ao embedding
    assert "::halfvec" in conn.calls[0][0]


def test_delete_stale_vazio_nao_executa():
    conn = FakeConn()
    assert store.delete_stale(conn, "r", []) == 0
    assert conn.calls == []


def test_delete_stale_usa_any_array():
    conn = FakeConn(rowcounts=[3])
    n = store.delete_stale(conn, "r", ["a.py", "b.md"])
    assert n == 3
    sql, params = conn.calls[0]
    assert "DELETE FROM chunks" in sql and "= ANY(" in sql
    assert params == ("r", ["a.py", "b.md"])


def test_delete_removed_sem_live_apaga_repo_todo():
    conn = FakeConn(rowcounts=[7])
    n = store.delete_removed(conn, "r", [])
    assert n == 7
    sql, params = conn.calls[0]
    assert "NOT (path = ANY(" not in sql  # caminho sem array
    assert params == ("r",)


def test_existing_file_hashes_dedup_por_path():
    conn = FakeConn(results=[[("a.py", "sha_a"), ("b.md", "sha_b")]])
    d = store.existing_file_hashes(conn, "r")
    assert d == {"a.py": "sha_a", "b.md": "sha_b"}
    sql = conn.calls[0][0]
    assert "DISTINCT ON (path)" in sql and "ORDER BY path" in sql


def test_count_chunks_retorna_escalar():
    conn = FakeConn(results=[[(42,)]])
    assert store.count_chunks(conn, "r") == 42
