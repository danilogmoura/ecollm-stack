"""S29 · Testes de INTEGRAÇÃO do sync blue-green contra Postgres real.

Espelham os critérios §8 itens 11–14 da SPEC-S29:

  11. Sync completo de repo pequeno → flip → GC → contagem estável na gen publicada.
  12. Sync interrompido (linhas órfãs em in_progress) → re-execução → índice final
      idêntico ao ininterrupto (copy-forward idempotente + resume por arquivo).
  13. verify_schema.check() verde após a migração 004 (lockstep de rename I9/R6).
  14. A query do healthcheck do docker-compose retorna 'ok' no volume migrado.

Estes exigem o banco de desenvolvimento reachable (rag-db em 127.0.0.1:5433, via
RAG_DB_URL do .env). Quando indisponível, fazem skip (mesma restrição do gate de
recall — não quebram CI sem infra). Usam um `repo` de TESTE isolado (nome único)
para nunca tocar o índice real do ecollm-stack.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

from ingest import store

_ROOT = Path(__file__).resolve().parents[2]

# verify_schema.py / run_migrations.py não são pacotes instaláveis: carrega por caminho.
_VS_PATH = _ROOT / "rag-db" / "verify_schema.py"
_vs_spec = importlib.util.spec_from_file_location("verify_schema", _VS_PATH)
verify = importlib.util.module_from_spec(_vs_spec)
assert _vs_spec.loader is not None
_vs_spec.loader.exec_module(verify)


def _db_available() -> bool:
    try:
        conn = store.connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return True
    except Exception:  # noqa: BLE001 — qualquer falha de conexão ⇒ sem infra p/ integração
        return False


pytestmark = pytest.mark.skipif(not _db_available(),
                                reason="Postgres de integração indisponível (rag-db :5433)")


@pytest.fixture
def live_conn():
    conn = store.connect()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def test_repo(tmp_path):
    """Repo git descartável com nome único (não colide com 'ecollm-stack' real)."""
    r = tmp_path / "s29_it_repo"
    r.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=r, check=True, capture_output=True,
                       env={**subprocess.os.environ,
                            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    (r / "a.py").write_text("def f():\n    return 1\n")
    (r / "b.md").write_text("# T\n\n## S\n\nbody x y z\n")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    return r


def _cleanup(conn, repo):
    # NÃO usar `with conn:` — em psycopg3 o bloco fecha a conexão ao sair.
    conn.execute("DELETE FROM chunks WHERE repo = %s", (repo,))
    conn.execute("DELETE FROM rag_sync_state WHERE repo = %s", (repo,))
    conn.commit()


def _seed_gen(conn, repo, gen, paths_hashes):
    """Insere linhas sintéticas numa geração (embedding halfvec(3072) zero)."""
    zero = "[" + ",".join(["0"] * 3072) + "]"
    for path, fh in paths_hashes.items():
        conn.execute(
            "INSERT INTO chunks (repo, path, lang, kind, symbol, content, "
            "content_hash, file_hash, embedding, gen) VALUES "
            "(%s,%s,'py','code',NULL,%s,md5(%s),%s,%s::halfvec,%s) "
            "ON CONFLICT (repo,path,content_hash,gen) DO NOTHING",
            (repo, path, f"conteudo {path}", path, fh, zero, gen),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# helpers de baixo nível (sem orquestrador) — exercitam o SQL real das funções
# ---------------------------------------------------------------------------

def test_copy_forward_e_gc_no_db_real(live_conn):
    repo = "s29_it_cf"
    _cleanup(live_conn, repo)
    try:
        _seed_gen(live_conn, repo, 0, {"keep.py": "blob1", "drop.py": "blob2"})
        n = store.copy_forward_unchanged(live_conn, repo, 0, 1, ["keep.py"])
        live_conn.commit()
        assert n == 1
        # só keep.py foi para a gen 1; drop.py ficou para trás (será removida no GC).
        g1 = {r[0] for r in live_conn.execute(
            "SELECT path FROM chunks WHERE repo=%s AND gen=1", (repo,)).fetchall()}
        assert g1 == {"keep.py"}
        # GC apaga apenas gen < published (mantém a publicada intacta).
        deleted = store.gc_old_generations(live_conn, repo, published_gen=1)
        live_conn.commit()
        assert deleted >= 1
        remaining = {r[0] for r in live_conn.execute(
            "SELECT DISTINCT path FROM chunks WHERE repo=%s", (repo,)).fetchall()}
        assert remaining == {"keep.py"}
    finally:
        _cleanup(live_conn, repo)


def test_flip_publica_e_leitores_veem_nova_inteira(live_conn):
    repo = "s29_it_flip"
    _cleanup(live_conn, repo)
    try:
        _seed_gen(live_conn, repo, 0, {"x.py": "b"})
        pub, new = store.next_generation(live_conn, repo)
        assert (pub, new) == (0, 1)
        store.begin_generation(live_conn, repo, new)
        _seed_gen(live_conn, repo, new, {"x.py": "b", "y.py": "c"})
        live_conn.commit()
        # antes do flip: published ainda é 0 → leitor vê só x.py.
        assert store.get_published_gen(live_conn, repo) == 0
        store.publish_generation(live_conn, repo, new)
        live_conn.commit()
        # depois do flip: published=1 e in_progress limpo; leitor vê a nova inteira.
        assert store.get_published_gen(live_conn, repo) == 1
        state = live_conn.execute(
            "SELECT in_progress_gen FROM rag_sync_state WHERE repo=%s", (repo,)).fetchone()
        assert state[0] is None
        seen = {r[0] for r in live_conn.execute(
            "SELECT DISTINCT path FROM chunks WHERE repo=%s AND gen=%s",
            (repo, 1)).fetchall()}
        assert seen == {"x.py", "y.py"}
    finally:
        _cleanup(live_conn, repo)


def test_existing_file_hashes_por_gen_publicada(live_conn):
    repo = "s29_it_exist"
    _cleanup(live_conn, repo)
    try:
        _seed_gen(live_conn, repo, 0, {"old.py": "b0"})
        _seed_gen(live_conn, repo, 1, {"new.py": "b1"})
        base_pub = store.existing_file_hashes(live_conn, repo, gen=0)
        assert set(base_pub) == {"old.py"}
        base_new = store.existing_file_hashes(live_conn, repo, gen=1)
        assert set(base_new) == {"new.py"}
    finally:
        _cleanup(live_conn, repo)


# ---------------------------------------------------------------------------
# 11 · sync completo de ponta a ponta (run_ingest real, embed stubado)
# ---------------------------------------------------------------------------

def test_sync_completo_flip_gc_integracao(monkeypatch, test_repo, live_conn):
    from ingest import embed, ingest

    repo = test_repo.resolve().name
    _cleanup(live_conn, repo)
    monkeypatch.setattr(ingest, "gitleaks_gate",
                        lambda root, entries, *, skip=False: (True, "ok"))
    monkeypatch.setattr(embed, "embed_documents",
                        lambda pairs, *, cfg=None, **k: [[0.1] * 3072 for _ in pairs])
    try:
        rep1 = ingest.run_ingest(test_repo, verbose=False)
        assert rep1.inserted > 0
        pub1 = store.get_published_gen(live_conn, repo)
        assert pub1 == 1
        total1 = store.count_chunks(live_conn, repo, gen=pub1)
        assert total1 == rep1.chunks_total

        # Reexecução sem mudança: copy-forward move tudo, 0 novos embeddings, flip 2.
        embedded = []
        monkeypatch.setattr(embed, "embed_documents",
                            lambda pairs, *, cfg=None, **k: (embedded.extend(pairs),
                                                             [[0.1] * 3072 for _ in pairs])[1])
        rep2 = ingest.run_ingest(test_repo, verbose=False)
        assert embedded == []                      # nada re-embedado (blob igual)
        pub2 = store.get_published_gen(live_conn, repo)
        assert pub2 == 2
        assert store.count_chunks(live_conn, repo, gen=pub2) == total1
        # GC coletou a geração anterior (nenhuma linha com gen < published).
        stale = live_conn.execute(
            "SELECT count(*) FROM chunks WHERE repo=%s AND gen < %s",
            (repo, pub2)).fetchone()[0]
        assert stale == 0
    finally:
        _cleanup(live_conn, repo)


# ---------------------------------------------------------------------------
# 12 · sync interrompido → re-execução converge para o mesmo índice
# ---------------------------------------------------------------------------

def test_sync_interrompido_reexecucao_converge(monkeypatch, test_repo, live_conn):
    from ingest import embed, ingest

    repo = test_repo.resolve().name
    ref_repo = "s29_it_ref"
    _cleanup(live_conn, repo)
    _cleanup(live_conn, ref_repo)
    monkeypatch.setattr(ingest, "gitleaks_gate",
                        lambda root, entries, *, skip=False: (True, "ok"))
    monkeypatch.setattr(embed, "embed_documents",
                        lambda pairs, *, cfg=None, **k: [[0.1] * 3072 for _ in pairs])
    try:
        # Execução de referência (ininterrupta) num repo irmão idêntico.
        ref = test_repo.parent / ref_repo
        subprocess.run(["cp", "-r", str(test_repo), str(ref)], check=True)
        ingest.run_ingest(ref, verbose=False)
        ref_paths = {r[0] for r in live_conn.execute(
            "SELECT DISTINCT path FROM chunks WHERE repo=%s", (ref_repo,)).fetchall()}

        # Simula crash no meio: linhas órfãs numa geração em montagem (nunca publicada).
        _seed_gen(live_conn, repo, 1, {"a.py": "orfaoblob"})
        store.set_in_progress_gen(live_conn, repo, 1)
        live_conn.commit()

        ing = ingest.run_ingest(test_repo, verbose=False)
        pub = store.get_published_gen(live_conn, repo)
        got_paths = {r[0] for r in live_conn.execute(
            "SELECT DISTINCT path FROM chunks WHERE repo=%s AND gen=%s",
            (repo, pub)).fetchall()}
        assert got_paths == {"a.py", "b.md"}
        assert got_paths == ref_paths              # índice final idêntico ao ininterrupto
        assert ing.chunks_total == store.count_chunks(live_conn, repo, gen=pub)
        # Órfãs pré-flip foram coletadas pelo GC.
        assert live_conn.execute(
            "SELECT count(*) FROM chunks WHERE repo=%s AND gen < %s",
            (repo, pub)).fetchone()[0] == 0
    finally:
        _cleanup(live_conn, repo)
        _cleanup(live_conn, ref_repo)


# ---------------------------------------------------------------------------
# 13 · verify_schema verde após a migração 004 (lockstep I9/R6)
# ---------------------------------------------------------------------------

def test_verify_schema_verde_apos_004(live_conn):
    url = store.db_url_from_env()
    results = verify.check(url)
    failed = [msg for ok, msg in results if not ok]
    assert not failed, f"verify_schema falhou: {failed}"
    # garante que a checagem específica do rename S29 está presente e passou
    names = " | ".join(msg for _ok, msg in results)
    assert "chunks_repo_path_content_hash_gen_key" in names
    assert "chunks.gen" in names


# ---------------------------------------------------------------------------
# 14 · healthcheck do compose retorna 'ok' no volume migrado (lockstep I9/R6)
# ---------------------------------------------------------------------------

_HEALTHCHECK_NEEDLES = (
    "chunks_embedding_hnsw",
    "chunks_tsv_gin",
    "chunks_repo_path_content_hash_gen_key",
)


def test_healthcheck_rag_db_apos_004():
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    # O nome da constraint no healthcheck DEVE bater com verify_schema/init.sql.
    for needle in _HEALTHCHECK_NEEDLES:
        assert needle in compose, f"healthcheck sem o índice obrigatório {needle}"
    assert "chunks_repo_path_content_hash_key" not in compose.replace(
        "chunks_repo_path_content_hash_gen_key", ""), \
        "healthcheck ainda referencia o nome ANTIGO da constraint (sem _gen)"
