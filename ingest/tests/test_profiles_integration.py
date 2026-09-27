"""S32-b · Testes de INTEGRAÇÃO — tabelas por perfil + estado (SPEC §6 testes 8–13).

Cobrem o que os unitários (test_profiles.py, testes 1–7) NÃO podem: comportamento
real contra Postgres/pgvector. Skip-guard `_db_available()` idêntico ao S29
(test_sync_gen_integration.py) — sem infra, fazem skip e não quebram CI.

  8. ensure_profile_table é IDEMPOTENTE (2ª chamada = no-op) e cria os 7 objetos.
  9. Equivalência ESTRUTURAL chunks_qwen37 ≡ chunks via pg_attribute (R3): a DDL
     parametrizada não diverge da init.sql.
 10. EXPLAIN da busca densa numa tabela 1024-d mostra **Index Scan** no HNSW, não
     Seq Scan (R2 — o motivo de termos rejeitado a VIEW do §5).
 11. Sync completo de um perfil NÃO-default + flip + leitura pela tabela publicada.
 12. `rag profile use` fail-closed com head_sha divergente (R6): recusa publicar.
 13. verify_schema aprova o perfil publicado e REPROVA uma dim divergente.

Usam nomes de repo/tabela de TESTE isolados; nunca tocam o índice real do
ecollm-stack. Embeddings são stubados (sem cota/rede) exceto onde o teste exige
DDL/EXPLAIN reais (que não chamam o provedor).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

from ingest import profiles, store

_ROOT = Path(__file__).resolve().parents[2]

# verify_schema.py não é pacote instalável: carrega por caminho (mesmo padrão S29).
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
    r = tmp_path / "s32b_it_repo"
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


def _drop_profile_table(conn, table):
    """Remove uma tabela de perfil de TESTE + seu estado (limpa pós-teste).

    NUNCA chamar para 'chunks' (perfil default legado — pertence ao índice real).
    """
    assert table != "chunks", "não dropar a tabela default em teste"
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()


def _cleanup_state(conn, repo):
    conn.execute("DELETE FROM rag_sync_state WHERE repo = %s", (repo,))
    conn.commit()


# ---------------------------------------------------------------------------
# 8 · ensure_profile_table é idempotente e cria os 7 objetos
# ---------------------------------------------------------------------------

def test_ensure_profile_table_idempotente_cria_7_objetos(live_conn):
    prof = profiles.resolve("qwen37")          # chunks_qwen37, dim 1024
    _drop_profile_table(live_conn, prof.table)
    try:
        # 1ª chamada: cria tudo.
        tbl = store.ensure_profile_table(live_conn, profile=prof)
        live_conn.commit()
        assert tbl == prof.table

        objs = _count_objects(live_conn, prof.table)
        # índices criados pela DDL do perfil: UNIQUE(repo,path,content_hash,gen) +
        # HNSW(embedding) + GIN(tsv) + GIN parcial(tsv_pt) + (repo,kind) + (repo,gen)
        # = 6 índices; somado ao índice interno do PRIMARY KEY (id uuid) = 7 em
        # pg_index. O "7 objetos" da SPEC conta tabela + esses componentes.
        assert objs["indexes"] == 7, objs
        assert objs["exists"] is True

        # 2ª chamada: NO-OP — mesmo nº de objetos, sem erro, sem recriar.
        before = _index_names(live_conn, prof.table)
        store.ensure_profile_table(live_conn, profile=prof)
        live_conn.commit()
        after = _index_names(live_conn, prof.table)
        assert after == before, "2ª chamada deve ser no-op (idempotente)"
    finally:
        _drop_profile_table(live_conn, prof.table)


# ---------------------------------------------------------------------------
# 9 · equivalência estrutural chunks_qwen37 ≡ chunks via pg_attribute (R3)
# ---------------------------------------------------------------------------

def test_equivalencia_estrutural_com_chunks(live_conn):
    prof = profiles.resolve("qwen37")
    _drop_profile_table(live_conn, prof.table)
    try:
        store.ensure_profile_table(live_conn, profile=prof)
        live_conn.commit()
        cols_new = _column_signature(live_conn, prof.table)
        cols_ref = _column_signature(live_conn, "chunks")
        # MESMAS colunas/nomes/tipos-nulláveis, EXCETO a dimensão do embedding
        # (halfvec typmod), que é justamente o que difere por perfil (1024 vs 3072).
        assert set(cols_new) == set(cols_ref), (
            f"conjunto de colunas divergiu:\n  só em qwen37: {set(cols_new)-set(cols_ref)}"
            f"\n  só em chunks: {set(cols_ref)-set(cols_new)}")
        # para cada coluna comum, nullabilidade/idêntica; embedding difere só no typmod.
        for name in sorted(set(cols_new)):
            n, r = cols_new[name], cols_ref[name]
            if name == "embedding":
                assert "halfvec" in n["type"] and "halfvec" in r["type"]
                assert n["typmod"] != r["typmod"]   # 1024 vs 3072 — diferença esperada
            else:
                assert n["type"] == r["type"], f"{name}: tipo divergiu {n} vs {r}"
                assert n["attnotnull"] == r["attnotnull"], f"{name}: nullability divergiu"
    finally:
        _drop_profile_table(live_conn, prof.table)


# ---------------------------------------------------------------------------
# 10 · EXPLAIN da busca densa numa tabela 1024-d usa Index Scan no HNSW (R2)
# ---------------------------------------------------------------------------

def test_explain_usa_indice_hnsw_na_tabela_perfil(live_conn):
    prof = profiles.resolve("qwen37")
    _drop_profile_table(live_conn, prof.table)
    try:
        store.ensure_profile_table(live_conn, profile=prof)
        # semeia massa suficiente p/ o planejador preferir o HNSW ao invés de um
        # btree seletivo + Sort (vetores sintéticos de 1024 dim).
        _seed_profile_rows(live_conn, prof, repo="s32b_it_explain", gen=0, n=600)
        live_conn.commit()
        # ANALYZE atualiza as estatísticas p/ o planejador dimensionar o custo real.
        live_conn.execute(f"ANALYZE {prof.table}")
        live_conn.commit()
        plan = _explain_dense(live_conn, prof)
        joined = "\n".join(row[0] for row in plan)
        assert "Seq Scan" not in joined, f"planejador fez Seq Scan (R2 violado):\n{joined}"
        assert "Index Scan" in joined and "hnsw" in joined.lower(), (
            f"esperado Index Scan via HNSW:\n{joined}")
    finally:
        _drop_profile_table(live_conn, prof.table)


# ---------------------------------------------------------------------------
# 11 · sync completo de perfil não-default + flip + leitura pela tabela publicada
# ---------------------------------------------------------------------------

def test_sync_flip_leitura_perfil_nao_default(monkeypatch, test_repo, live_conn):
    from ingest import embed, ingest

    prof = profiles.resolve("bgem3")           # chunks_bgem3, dim 1024, prefix none
    repo = test_repo.resolve().name
    _drop_profile_table(live_conn, prof.table)
    _cleanup_state(live_conn, repo)
    monkeypatch.setattr(ingest, "gitleaks_gate",
                        lambda root, entries, *, skip=False: (True, "ok"))
    # stub de embed na dim DO PERFIL (não consome cota); valida escrita na tabela certa.
    monkeypatch.setattr(embed, "embed_documents",
                        lambda pairs, *, cfg=None, **k: [[0.1] * prof.dim for _ in pairs])
    try:
        rep = ingest.run_ingest(test_repo, verbose=False, profile=prof)
        assert rep.inserted > 0
        pub = store.get_published_gen(live_conn, repo, profile=prof)
        assert pub == 1
        # linhas foram PARA A TABELA DO PERFIL, não para chunks.
        got = live_conn.execute(
            f"SELECT count(*) FROM {prof.table} WHERE repo=%s AND gen=%s",
            (repo, pub)).fetchone()[0]
        assert got == rep.chunks_total
        # leitura pela tabela publicada: search() resolve o perfil e acerta chunks_bgem3.
        hits = _search_in_profile(live_conn, repo, prof)
        assert len(hits) >= 1
        # nada vazou para a tabela default deste repo.
        leaked = live_conn.execute(
            "SELECT count(*) FROM chunks WHERE repo=%s", (repo,)).fetchone()[0]
        assert leaked == 0
    finally:
        _drop_profile_table(live_conn, prof.table)
        _cleanup_state(live_conn, repo)


# ---------------------------------------------------------------------------
# 12 · `use` fail-closed com head_sha divergente (R6)
# ---------------------------------------------------------------------------

def test_use_recusa_publicar_com_head_divergente(monkeypatch, test_repo, live_conn):
    from ingest import cli, embed, ingest

    prof = profiles.resolve("qwen37")
    repo = test_repo.resolve().name
    _drop_profile_table(live_conn, prof.table)
    _cleanup_state(live_conn, repo)
    monkeypatch.setattr(ingest, "gitleaks_gate",
                        lambda root, entries, *, skip=False: (True, "ok"))
    monkeypatch.setattr(embed, "embed_documents",
                        lambda pairs, *, cfg=None, **k: [[0.1] * prof.dim for _ in pairs])
    try:
        # sync do perfil → publica índice na HEAD atual.
        ingest.run_ingest(test_repo, verbose=False, profile=prof)
        # marca o alvo como publicado ok primeiro (head coincide) — sanity.
        args = _profile_args(repo=str(test_repo), slug=prof.slug)
        rc_ok = cli._cmd_profile_set(live_conn, args, repo, test_repo, "use")
        assert rc_ok == 0

        # agora edita o repo (nova HEAD) SEM re-syncar o perfil → head diverge.
        (test_repo / "c.py").write_text("def g():\n    return 2\n")
        _git(test_repo, "add", ".")
        _git(test_repo, "commit", "-q", "-m", "diverge")
        # published_profile volta para gemini p/ garantir que 'use' tentaria mudar.
        store.set_published_profile(live_conn, repo, "gemini")
        live_conn.commit()

        rc = cli._cmd_profile_set(live_conn, args, repo, test_repo, "use")
        assert rc == 3, "use DEVE recusar (R6) quando head_sha do índice diverge"
        # publicação NÃO mudou (continua gemini), pois o flip foi barrado.
        assert store.get_published_profile(live_conn, repo) == "gemini"
    finally:
        _drop_profile_table(live_conn, prof.table)
        _cleanup_state(live_conn, repo)


# ---------------------------------------------------------------------------
# 13 · verify_schema aprova o perfil publicado e reprova dim divergente
# ---------------------------------------------------------------------------

def test_verify_schema_aprova_perfil_publicado_reprova_dim(live_conn):
    prof = profiles.resolve("qwen37")
    repo = "s32b_it_verify"
    _drop_profile_table(live_conn, prof.table)
    _cleanup_state(live_conn, repo)
    url = store.db_url_from_env()
    try:
        store.ensure_profile_table(live_conn, profile=prof)
        # publica o perfil (ponteiro por repo) apontando chunks_qwen37 como ativo.
        store.set_published_profile(live_conn, repo, prof.slug)
        live_conn.commit()

        # (a) com a tabela íntegra (dim 1024 = registry), check() passa.
        results = verify.check(url)
        failed = [m for ok, m in results if not ok]
        assert not failed, f"verify deveria aprovar perfil publicado íntegro: {failed}"
        names = " | ".join(m for _ok, m in results)
        assert prof.table in names, f"tabela publicada não validada: {names}"

        # (b) SABOTAGEM: recria a tabela homônima com dim ERRADA (512 ≠ 1024 do
        #     registry) e SEM os índices obrigatórios. verify deve REPROVAR
        #     (test 13 — dim divergente / estrutura incompleta = falha).
        live_conn.execute(f"DROP TABLE IF EXISTS {prof.table}")
        live_conn.execute(
            f"""
            CREATE TABLE {prof.table} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                repo text NOT NULL, path text NOT NULL, lang text,
                kind text NOT NULL, symbol text, content text NOT NULL,
                content_hash char(64) NOT NULL,
                embedding halfvec(512) NOT NULL,
                file_hash char(40) NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                gen bigint NOT NULL DEFAULT 0, meta jsonb,
                tsv tsvector, tsv_pt tsvector
            )
            """
        )
        live_conn.commit()
        results_bad = verify.check(url)
        bad_failed = [m for ok, m in results_bad if not ok]
        assert any(prof.table in m for m in bad_failed), (
            f"verify deveria reprovar dim/estrutura divergente; falhas={bad_failed}")
        # em particular a checagem de dimensão da tabela publicada deve falhar.
        assert any(("embedding" in m and "512" in m) for m in bad_failed), (
            f"esperado flag de dim 512 ≠ 1024; falhas={bad_failed}")
    finally:
        _drop_profile_table(live_conn, prof.table)
        _cleanup_state(live_conn, repo)


# ---------------------------------------------------------------------------
# helpers de baixo nível (SQL real do catalog / seed)
# ---------------------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**subprocess.os.environ,
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _profile_args(repo, slug):
    import argparse
    return argparse.Namespace(repo=repo, slug=slug, quiet=True, skip_gitleaks=True)


def _count_objects(conn, table):
    """(existe, nº de índices) de `table` no catalog."""
    exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (table,)).fetchone()[0]
    idx = conn.execute(
        "SELECT count(*) FROM pg_index i WHERE i.indrelid = %s::regclass",
        (table,)).fetchone()[0]
    return {"exists": bool(exists), "indexes": int(idx)}


def _index_names(conn, table):
    return frozenset(r[0] for r in conn.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_index i ON c.oid=i.indexrelid "
        "WHERE i.indrelid = %s::regclass", (table,)).fetchall())


def _column_signature(conn, table):
    """{coluna: {type, typmod, attnotnull}} — base da equivalência estrutural (R3)."""
    rows = conn.execute(
        """
        SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.atttypmod, a.attnotnull
        FROM pg_attribute a
        WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
        """,
        (table,),
    ).fetchall()
    return {r[0]: {"type": r[1], "typmod": r[2], "attnotnull": r[3]} for r in rows}


def _seed_profile_rows(conn, prof, repo, gen, n):
    """Insere n linhas sintéticas na tabela do perfil (vetor zero na dim do perfil)."""
    zero = "[" + ",".join(["0"] * prof.dim) + "]"
    for i in range(n):
        path = f"f{i}.py"
        conn.execute(
            f"INSERT INTO {prof.table} (repo, path, lang, kind, symbol, content, "
            "content_hash, file_hash, embedding, gen) VALUES "
            "(%s,%s,'py','code',NULL,%s,md5(%s),%s,%s::halfvec,%s) "
            "ON CONFLICT (repo,path,content_hash,gen) DO NOTHING",
            (repo, path, f"conteudo {path}", path, f"blob{i}", zero, gen),
        )
    conn.commit()


def _explain_dense(conn, prof):
    """EXPLAIN da query denso (operador <=> em ORDER BY) na tabela do perfil.

    O operador <=> SÓ aparece em ORDER BY/LIMIT (é a distância, não um filtro);
    colocá-lo em WHERE seria interpretado como booleano e daria DatatypeMismatch.
    Este é exatamente o shape de _VECTOR_SQL (search.py), que usa o HNSW.
    """
    qvec = "[" + ",".join(["0.1"] * prof.dim) + "]"
    sql = (
        f"EXPLAIN SELECT id FROM {prof.table} "
        "WHERE repo = %s "
        "ORDER BY embedding <=> %s::halfvec LIMIT 10"
    )
    return conn.execute(sql, ("s32b_it_explain", qvec)).fetchall()


def _search_in_profile(conn, repo, prof):
    """Chama search.search() fixando o perfil (lê da tabela publicada dele)."""
    from ingest import search
    return search.search("corpo", repo=repo, conn=conn,
                         qvec=[0.1] * prof.dim, profile=prof.slug, final_k=3)
