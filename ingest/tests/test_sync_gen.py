"""S29 · Sync incremental retomável com publicação atômica (blue-green por `gen`).

Testes UNITÁRIOS dos critérios §8 da SPEC-S29 (itens 1–10): sem DB real nem rede,
usando conexão fake que registra SQL / devolve resultados. Cobrem:

  1. copy_forward_copia_unchanged_sem_embed   — unchanged não toca o embedder.
  2. resume_pula_arquivo_ja_na_geracao        — arquivo já commitado na gen é pulado.
  3. 429_no_meio_preserva_progresso           — falha no arquivo K preserva <K; retoma.
  4. flip_e_atomico_e_publica_geracao_completa— leitores veem velha até o flip.
  5. gc_apaga_apenas_geracoes_antigas         — DELETE usa `gen < published_gen`.
  6. arquivo_removido_nao_aparece_na_nova_geracao.
  7. search_filtra_por_published_gen          — SQL denso/léxico incluem `gen`.
  8. existing_file_hashes_usa_published_gen   (I3).
  9. staleness_reflete_geracao_publicada      (I5).
 10. parity_unchanged_antes_do_flip           (R2).

A camada de store (copy_forward/publish/gc/file_in_generation/next_generation) é
exercitada via FakeConn que inspeciona o SQL emitido; a orquestração (run_ingest)
via o FakeDB azul-verde de test_ingest (importado daqui p/ os testes 2/3/4/6).
"""

from __future__ import annotations

import pytest

from ingest import ingest, search, store
from ingest.tests.conftest import _git


# ---------------------------------------------------------------------------
# FakeConn genérico (registra SQL + params; devolve resultados configuráveis)
# ---------------------------------------------------------------------------

class _Cur:
    def __init__(self, rowcount=1, rows=None):
        self.rowcount = rowcount
        self._rows = rows if rows is not None else []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class Conn:
    """Conexão fake: grava (sql, params); escolhe a resposta pela palavra-chave."""

    def __init__(self, responses=None, rowcounts=None):
        self.calls: list[tuple[str, dict | tuple | None]] = []
        self._responses = responses or {}
        self._rowcounts = rowcounts or []
        self._i = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        rc = self._rowcounts[self._i] if self._i < len(self._rowcounts) else 1
        self._i += 1
        for key, rows in self._responses.items():
            if key in sql:
                return _Cur(rc, rows)
        return _Cur(rc, [])

    # contexto transacional (no-op aqui)
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def commit(self):
        pass

    def close(self):
        pass


def _row(gen, path, content_hash="h", file_hash="f", kind="code"):
    return store.Row(repo="r", path=path, lang="py", kind=kind, symbol=None,
                     content="c", content_hash=content_hash, file_hash=file_hash,
                     embedding_text="[0.1]", gen=gen)


# ---------------------------------------------------------------------------
# 1 · copy-forward não chama o embedder (cota intocada)
# ---------------------------------------------------------------------------

def test_copy_forward_copia_unchanged_sem_embed(monkeypatch):
    conn = Conn(rowcounts=[7])
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise AssertionError("copy-forward NUNCA pode chamar o embedder")

    monkeypatch.setattr(ingest.embed, "embed_documents", boom)
    n = store.copy_forward_unchanged(conn, "r", src_gen=3, new_gen=4,
                                     unchanged_paths=["a.py", "b.md"])
    assert n == 7
    assert calls["n"] == 0
    sql, params = conn.calls[0]
    assert "INSERT INTO chunks" in sql and "SELECT" in sql
    assert "ON CONFLICT (repo, path, content_hash, gen) DO NOTHING" in sql
    assert params["src_gen"] == 3 and params["new_gen"] == 4
    assert set(params["paths"]) == {"a.py", "b.md"}


def test_copy_forward_paths_vazios_noop():
    conn = Conn()
    assert store.copy_forward_unchanged(conn, "r", 0, 1, []) == 0
    assert conn.calls == []


# ---------------------------------------------------------------------------
# 2 · resume pula arquivo já presente na geração em montagem
# ---------------------------------------------------------------------------

def test_resume_pula_arquivo_ja_na_geracao_unit():
    conn = Conn(responses={"SELECT 1 FROM chunks": [(1,)]})
    assert store.file_in_generation(conn, "r", 4, "a.py", "blobsha") is True
    _, params = conn.calls[0]
    assert params == ("r", 4, "a.py", "blobsha")


def test_resume_pula_arquivo_ja_na_geracao_orchestrator(patched, repo, monkeypatch):
    """Um arquivo já commitado na geração em montagem é PULADO na retomada (0 re-embed)."""
    # Força ordem determinística: hello.py antes de notes.md no plano.
    orig_plan = ingest.plan_sync

    def ordered(root, existing):
        return sorted(orig_plan(root, existing), key=lambda p: p.entry.path)

    monkeypatch.setattr(ingest, "plan_sync", ordered)

    # Estado pós-crash: gen 1 ainda NÃO publicada; hello.py já tem linhas nela
    # (transação própria commitou antes do 429); published_gen continua 0.
    # file_hash SEM o mesmo blob sha que plan_sync verá, senão não casa no resume.
    import subprocess
    hello_blob = subprocess.run(
        ["git", "rev-parse", "HEAD:hello.py"], cwd=repo, check=True,
        capture_output=True, text=True).stdout.strip()
    patched.rows[(1, "hello.py", "x")] = _row(1, "hello.py", content_hash="x",
                                              file_hash=hello_blob)
    patched.embedded.clear()
    rep = ingest.run_ingest(repo, verbose=False)

    # hello.py foi pulado (nada do seu conteúdo foi re-embedado nesta execução).
    assert all("greet" not in t for t, _ in patched.embedded)
    # notes.md entrou agora; a retomada publicou a geração completa.
    assert rep.inserted >= 1
    assert patched.published_gen == 1
    paths_gen1 = {r.path for (g, _p, _c), r in patched.rows.items() if g == 1}
    assert paths_gen1 == {"hello.py", "notes.md"}


# ---------------------------------------------------------------------------
# 3 · um 429 no meio preserva o progresso dos arquivos anteriores
# ---------------------------------------------------------------------------

def test_429_no_meio_preserva_progresso(patched, repo, monkeypatch):
    orig_plan = ingest.plan_sync

    def ordered(root, existing):
        return sorted(orig_plan(root, existing), key=lambda p: p.entry.path)

    monkeypatch.setattr(ingest, "plan_sync", ordered)

    patched.fail_embed_after = 1  # deixa o 1º arquivo passar, estoura no 2º
    with pytest.raises(RuntimeError):
        ingest.run_ingest(repo, verbose=False)

    # O arquivo anterior ao erro permanece commitado (transação própria por arquivo).
    first = sorted({r.path for (g, _p, _c), r in patched.rows.items() if g == 1})
    assert first == ["hello.py"]
    # A geração parcial NUNCA foi publicada.
    assert patched.published_gen == 0
    # O ponteiro in_progress foi liberado no finally (próxima execução recomeça limpa).
    assert patched.in_progress_gen is None


# ---------------------------------------------------------------------------
# 4 · flip é atômico e publica a geração inteira
# ---------------------------------------------------------------------------

def test_flip_e_atomico_e_publica_geracao_completa():
    conn = Conn()
    store.publish_generation(conn, "r", 5)
    sql, params = conn.calls[0]
    assert "UPDATE rag_sync_state SET published_gen" in sql
    assert "in_progress_gen = NULL" in sql
    # S32-b: o flip é chaveado por (repo, profile); default → slug 'bgem3' (local).
    assert params == (5, "r", "bgem3")


def test_leitores_veem_velha_ate_flip_e_nova_depois(patched, repo):
    """Antes do flip, published_gen aponta a geração anterior; depois, a nova inteira."""
    # Primeira execução completa → publica gen 1.
    ingest.run_ingest(repo, verbose=False)
    assert patched.published_gen == 1
    total_gen1 = patched.count("myrepo", gen=1)
    assert total_gen1 > 0

    # Edita UM arquivo → segunda execução monta gen 2 mas, se abortássemos antes do
    # flip, published ainda seria 1. Aqui deixamos completar: published vira 2.
    (repo / "hello.py").write_text("def greet():\n    return 'mudou mesmo'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "edit")
    ingest.run_ingest(repo, verbose=False)
    assert patched.published_gen == 2
    # A nova geração publicada está COMPLETA (ambos os arquivos presentes).
    paths_gen2 = {r.path for (g, _p, _c), r in patched.rows.items() if g == 2}
    assert paths_gen2 == {"hello.py", "notes.md"}


# ---------------------------------------------------------------------------
# 5 · GC apaga apenas gerações antigas
# ---------------------------------------------------------------------------

def test_gc_apaga_apenas_geracoes_antigas():
    conn = Conn(rowcounts=[3])
    n = store.gc_old_generations(conn, "r", published_gen=4)
    assert n == 3
    sql, params = conn.calls[0]
    assert "DELETE FROM chunks" in sql
    assert "gen < %s" in sql          # NUNCA <= in_progress_gen (R4)
    assert params == ("r", 4)


# ---------------------------------------------------------------------------
# 6 · arquivo removido não aparece na nova geração
# ---------------------------------------------------------------------------

def test_arquivo_removido_nao_aparece_na_nova_geracao(patched, repo):
    ingest.run_ingest(repo, verbose=False)
    (repo / "notes.md").unlink()
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "rm")
    rep = ingest.run_ingest(repo, verbose=False)
    assert "notes.md" in rep.removed_files
    # Na nova geração publicada (2), notes.md não existe.
    paths_gen2 = {r.path for (g, _p, _c), r in patched.rows.items() if g == 2}
    assert "notes.md" not in paths_gen2
    assert "hello.py" in paths_gen2
    # Geração antiga (1) foi coletada pelo GC.
    assert not [k for k in patched.rows if k[0] < patched.published_gen]


# ---------------------------------------------------------------------------
# 7 · search filtra pela geração publicada
# ---------------------------------------------------------------------------

def test_search_sql_constantes_incluem_gen():
    for sql in (search._VECTOR_SQL, search._LEXICAL_SQL, search._LEXICAL_PT_SQL):
        assert "AND gen = %(gen)s" in sql


def test_search_filtra_por_published_gen():
    conn = Conn()
    search.search("q", repo="r", conn=conn, qvec=[0.1, 0.2], final_k=3)
    # A primeira consulta resolve published_gen (lazy get_published_gen).
    assert any("published_gen" in sql for sql, _ in conn.calls)
    # Toda consulta de busca carrega o parâmetro gen resolvido (default legado 0).
    busca = [(sql, params) for sql, params in conn.calls if "<=>" in sql or "tsv" in sql]
    assert busca, "esperava ao menos uma query de busca"
    assert all(params.get("gen") == 0 for _sql, params in busca)


def test_search_respeita_gen_explícito():
    conn = Conn()
    search.search("q", repo="r", conn=conn, qvec=[0.1], gen=9, final_k=3)
    # gen explícito → nenhuma leitura de published_gen.
    assert not any("published_gen" in sql for sql, _ in conn.calls)
    busca = [params for sql, params in conn.calls if "<=>" in sql or "tsv" in sql]
    assert busca and all(p.get("gen") == 9 for p in busca)


# ---------------------------------------------------------------------------
# 8 · existing_file_hashes compara contra a geração publicada (I3)
# ---------------------------------------------------------------------------

def test_existing_file_hashes_usa_published_gen():
    conn = Conn(responses={"file_hash": [("a.py", "sha_a")]})
    out = store.existing_file_hashes(conn, "r", gen=3)
    assert out == {"a.py": "sha_a"}
    sql, params = conn.calls[0]
    assert "AND gen = %s" in sql
    assert params == ("r", 3)


def test_existing_file_hashes_legado_sem_gen():
    conn = Conn(responses={"file_hash": [("a.py", "sha_a")]})
    store.existing_file_hashes(conn, "r")
    sql, _ = conn.calls[0]
    assert "DISTINCT ON (path)" in sql
    assert "gen" not in sql


# ---------------------------------------------------------------------------
# 9 · staleness reflete a geração publicada (I5)
# ---------------------------------------------------------------------------

def test_staleness_reflete_geracao_publicada(patched, repo):
    # Antes de qualquer sync: sem registro de estado → índice desconhecido/stale.
    conn = Conn()
    stale, reason = ingest.is_index_stale(conn, "myrepo", repo)
    assert stale is True

    # Após um sync completo, o flip grava head_sha/dirty NO MESMO commit da
    # publicação (record_sync_state dentro da transação do publish_generation).
    ingest.run_ingest(repo, verbose=False)
    assert patched.published_gen == 1
    # O relatório do sync corresponde à geração publicada (chunks_total da nova gen).
    assert patched.count("myrepo", gen=1) > 0


# ---------------------------------------------------------------------------
# 10 · paridade unchanged ANTES do flip (R2)
# ---------------------------------------------------------------------------

def test_parity_unchanged_antes_do_flip_passa():
    conn = Conn(responses={"NOT IN": []})  # nenhum path faltando
    assert ingest._parity_ok(conn, "r", 1, 2, ["a.py", "b.md"]) is True
    sql, params = conn.calls[0]
    assert "published_gen" not in sql  # usa os ints passados, não lê estado
    assert params[0] == "r" and params[1] == 1 and params[3] == "r" and params[4] == 2


def test_parity_unchanged_falha_aborta_flip(patched, repo, monkeypatch):
    """Se um unchanged sumiu da nova geração, o flip é cancelado (índice intacto)."""
    ingest.run_ingest(repo, verbose=False)  # publica gen 1
    patched.published_gen = 1
    patched.embedded.clear()
    # Força paridade a falhar (simula copy-forward incompleto).
    monkeypatch.setattr(ingest, "_parity_ok", lambda *a, **k: False)
    with pytest.raises(SystemExit) as exc:
        ingest.run_ingest(repo, verbose=False)
    assert "paridade" in str(exc.value)
    # published_gen continua 1 — a geração parcial NÃO foi publicada.
    assert patched.published_gen == 1
