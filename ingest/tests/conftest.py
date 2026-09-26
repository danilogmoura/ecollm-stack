import sys
from pathlib import Path

import pytest

# ingest/tests/conftest.py -> raiz do repo (ingest/ precisa estar importavel)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest import embed, ingest, store  # noqa: E402


def _git(repo: Path, *args):
    import subprocess
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
    """Conexão fake só com close()/commit() — o orquestrador S29 faz commits por
    etapa (copy-forward, embed/arquivo, flip, GC) e grava estado de sync.

    Também aceita .execute() no-op (S14 record_sync_state + lock advisory S29).
    """

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):  # S14 record_sync_state / S29 lock — nada a gravar no fake
        return self

    def commit(self):  # S29: commits por etapa são no-op no fake
        pass

    def close(self):
        pass


class FakeDB:
    """Imita as partes de store que o orquestrador S29 usa, em memoria.

    Chaves agora incluem a geração: (gen, path, content_hash). O estado guarda os
    ponteiros published_gen/in_progress_gen e um flag `fail_embed_after` p/ simular
    um 429 no meio (retomada). copy_forward é idempotente (ON CONFLICT DO NOTHING).
    """
    def __init__(self):
        self.rows: dict[tuple[int, str, str], store.Row] = {}  # (gen,path,content_hash)
        self.file_hashes: dict[str, str] = {}             # path -> file_hash (publicada)
        self.embedded: list[tuple[str, str]] = []         # (text, kind) chamados
        self.published_gen = 0
        self.in_progress_gen = None
        self.fail_embed_after = None                      # nº de embeds antes de estourar
        self._embed_calls = 0

    def existing(self, repo, gen=None):
        # plano compara contra a geração publicada (I3); sem gen, usa map legado.
        return dict(self.file_hashes)

    def next_generation(self, repo):
        return self.published_gen, self.published_gen + 1

    def begin_generation(self, repo, gen):
        self.in_progress_gen = gen

    def set_in_progress_gen(self, repo, gen):
        self.in_progress_gen = gen

    def copy_forward(self, repo, src_gen, new_gen, paths):
        n = 0
        for (g, path, ch), row in list(self.rows.items()):
            if g == src_gen and path in set(paths):
                key = (new_gen, path, ch)
                if key not in self.rows:
                    self.rows[key] = row
                    n += 1
        return n

    def file_in_gen(self, repo, gen, path, file_hash):
        return any(g == gen and r.path == path and r.file_hash == file_hash
                   for (g, _p, _c), r in self.rows.items())

    def upsert(self, rows):
        ins = unch = 0
        for r in rows:
            self._embed_calls += 0  # noop; contagem de embed é feita no fake_embed
            key = (r.gen, r.path, r.content_hash)
            if key in self.rows:
                unch += 1
            else:
                self.rows[key] = r
                ins += 1
            self.file_hashes[r.path] = r.file_hash
        return ins, unch

    def publish(self, repo, gen):
        self.published_gen = gen
        self.in_progress_gen = None
        # file_hashes passa a refletir só a geração publicada (base do próximo plano).
        self.file_hashes = {r.path: r.file_hash
                            for (g, _p, _c), r in self.rows.items() if g == gen}

    def gc(self, repo, published_gen):
        n = 0
        for key in [k for k in self.rows if k[0] < published_gen]:
            del self.rows[key]
            n += 1
        return n

    def parity(self, repo, published_gen, new_gen, unchanged_paths):
        have = {r.path for (g, _p, _c), r in self.rows.items()
                if g == published_gen and r.path in set(unchanged_paths)}
        in_new = {r.path for (g, _p, _c), r in self.rows.items() if g == new_gen}
        return have <= in_new

    def count(self, repo, gen=None):
        if gen is None:
            return len(self.rows)
        return sum(1 for (g, _p, _c) in self.rows if g == gen)


@pytest.fixture
def patched(monkeypatch):
    """Stub gitleaks + embed + camada de store (blue-green S29) no orquestrador."""
    db = FakeDB()

    monkeypatch.setattr(ingest, "gitleaks_gate", lambda root, entries, *, skip=False: (True, "ok"))

    def fake_embed_documents(pairs, *, cfg=None, **kw):
        db.embedded.extend(pairs)
        if db.fail_embed_after is not None and len(db.embedded) > db.fail_embed_after:
            raise RuntimeError("HTTP 429 simulado (teto diário)")
        return [[0.5, 0.5] for _ in pairs]

    monkeypatch.setattr(embed, "embed_documents", fake_embed_documents)

    monkeypatch.setattr(store, "connect", lambda url=None: _NullConn())
    monkeypatch.setattr(store, "existing_file_hashes", lambda conn, repo, gen=None: db.existing(repo))
    monkeypatch.setattr(store, "next_generation", lambda conn, repo: db.next_generation(repo))
    monkeypatch.setattr(store, "begin_generation", lambda conn, repo, gen: db.begin_generation(repo, gen))
    monkeypatch.setattr(store, "set_in_progress_gen", lambda conn, repo, gen: db.set_in_progress_gen(repo, gen))
    monkeypatch.setattr(store, "copy_forward_unchanged",
                        lambda conn, repo, src, new, paths: db.copy_forward(repo, src, new, paths))
    monkeypatch.setattr(store, "file_in_generation",
                        lambda conn, repo, gen, path, fh: db.file_in_gen(repo, gen, path, fh))
    monkeypatch.setattr(store, "upsert_rows", lambda conn, rows: db.upsert(rows))
    monkeypatch.setattr(store, "publish_generation", lambda conn, repo, gen: db.publish(repo, gen))
    monkeypatch.setattr(store, "gc_old_generations", lambda conn, repo, pub: db.gc(repo, pub))
    monkeypatch.setattr(store, "count_chunks", lambda conn, repo, gen=None: db.count(repo, gen))
    # helper de paridade do orquestrador usa conn.execute direto; redireciona p/ o fake.
    monkeypatch.setattr(ingest, "_parity_ok",
                        lambda conn, repo, pub, new, paths: db.parity(repo, pub, new, paths))
    # lock advisory é no-op no fake.
    monkeypatch.setattr(ingest, "_acquire_sync_lock", lambda conn, repo: None)
    monkeypatch.setattr(ingest, "_release_sync_lock", lambda conn, repo: None)
    return db
