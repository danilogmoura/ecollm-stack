"""Store da FASE 2 — persiste chunks+vetores no pgvector (rag-db).

Regras travadas no plano (.planning/PLANO-RAG.md §3 FASE 2, §4b-3):
  - Upsert IDEMPOTENTE: ON CONFLICT (repo, path, content_hash) DO NOTHING.
    Re-execucao sem mudanca = 0 inserts novos (o hash do conteudo puro decide).
  - Sync incremental SIMPLES por arquivo (NAO Merkle tree — decisao de escopo
    para reduzir manutencao): compara o git blob sha (`file_hash`) por path;
    arquivo cujo blob mudou ou sumiu tem seus chunks antigos removidos e os
    novos re-embedados (o embedador + cache Redis cuidam do resto).
  - Contadores minimos p/ relatorio: inserted / unchanged / deleted.
  - Coluna embedding = halfvec(3072); inserimos como texto "[...]"::halfvec.
    NUNCA usar operator class vector_* numa coluna halfvec (BUG-002).

psycopg3 (binary). URL lida de RAG_DB_URL no ambiente (.env no repo root).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import psycopg

from .chunker import Chunk
from .embed import load_dotenv, vector_to_halfvec_text


DEFAULT_DB_URL = "postgresql://rag:rag_secret@localhost:5433/rag"


def db_url_from_env() -> str:
    load_dotenv()
    return os.environ.get("RAG_DB_URL", DEFAULT_DB_URL)


@dataclass(frozen=True)
class Row:
    """Uma linha pronta p/ a tabela chunks (sem id/created_at/tsv — gerados)."""
    repo: str
    path: str
    lang: str | None
    kind: str
    symbol: str | None
    content: str
    content_hash: str      # sha256 do texto PURO (sem task-prefix)
    file_hash: str         # git blob sha do arquivo pai
    embedding_text: str    # literal "[f1,...]" p/ cast ::halfvec(3072)


@dataclass
class SyncReport:
    repo: str
    files_seen: int = 0
    chunks_total: int = 0
    inserted: int = 0
    unchanged: int = 0
    deleted: int = 0
    changed_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[store:{self.repo}] arquivos={self.files_seen} chunks={self.chunks_total} "
            f"inseridos={self.inserted} inalterados={self.unchanged} removidos={self.deleted}"
        )


_UPSERT_SQL = """
INSERT INTO chunks (repo, path, lang, kind, symbol, content, content_hash,
                    file_hash, embedding)
VALUES (%(repo)s, %(path)s, %(lang)s, %(kind)s, %(symbol)s, %(content)s,
        %(content_hash)s, %(file_hash)s, %(embedding)s::halfvec)
ON CONFLICT (repo, path, content_hash) DO NOTHING
"""


def build_rows(repo: str, file_hash: str, chunks: Sequence[Chunk],
               vectors: Sequence[Sequence[float]]) -> list[Row]:
    """Monta as linhas a partir dos chunks + vetores alinhados (mesma ordem).

    content_hash vem do chunk PURO (loader.content_sha256), nao do texto
    prefixado — assim mudar a string de task nao invalida o indice.
    """
    from .loader import content_sha256  # import local p/ evitar ciclo no topo

    if len(chunks) != len(vectors):
        raise ValueError(f"chunks({len(chunks)}) != vectors({len(vectors)})")
    rows: list[Row] = []
    for c, vec in zip(chunks, vectors):
        rows.append(Row(
            repo=repo, path=c.path, lang=c.lang, kind=c.kind, symbol=c.symbol,
            content=c.content, content_hash=content_sha256(c.content),
            file_hash=file_hash, embedding_text=vector_to_halfvec_text(vec),
        ))
    return rows


def existing_file_hashes(conn: psycopg.Connection, repo: str) -> dict[str, str]:
    """{path: file_hash} currently stored para este repo (base do sync)."""
    cur = conn.execute(
        "SELECT DISTINCT ON (path) path, file_hash FROM chunks WHERE repo = %s "
        "ORDER BY path, created_at DESC",
        (repo,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def upsert_rows(conn: psycopg.Connection, rows: Iterable[Row]) -> tuple[int, int]:
    """Insere linhas novas; retorna (inserted, unchanged). unchanged = conflito."""
    inserted = unchanged = 0
    for r in rows:
        cur = conn.execute(_UPSERT_SQL, {
            "repo": r.repo, "path": r.path, "lang": r.lang, "kind": r.kind,
            "symbol": r.symbol, "content": r.content, "content_hash": r.content_hash,
            "file_hash": r.file_hash, "embedding": r.embedding_text,
        })
        if cur.rowcount and cur.rowcount > 0:
            inserted += 1
        else:
            unchanged += 1
    return inserted, unchanged


def delete_stale(conn: psycopg.Connection, repo: str,
                 paths_to_refresh: Iterable[str]) -> int:
    """Remove chunks de arquivos que vao ser re-embedados (blob mudou).

    Chamado ANTES do upsert para o mesmo path: garante que um arquivo editado
    nao acumule versoes antigas do mesmo conteudo com hash diferente.
    """
    paths = list(paths_to_refresh)
    if not paths:
        return 0
    cur = conn.execute(
        "DELETE FROM chunks WHERE repo = %s AND path = ANY(%s)",
        (repo, paths),
    )
    return cur.rowcount or 0


def delete_removed(conn: psycopg.Connection, repo: str,
                   live_paths: Iterable[str]) -> int:
    """Remove chunks cujos paths SUMIRAM do corpus (arquivos apagados)."""
    live = list(live_paths)
    if live:
        cur = conn.execute(
            "DELETE FROM chunks WHERE repo = %s AND NOT (path = ANY(%s))",
            (repo, live),
        )
    else:
        cur = conn.execute("DELETE FROM chunks WHERE repo = %s", (repo,))
    return cur.rowcount or 0


def count_chunks(conn: psycopg.Connection, repo: str) -> int:
    return conn.execute("SELECT count(*) FROM chunks WHERE repo = %s", (repo,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Estado de sync (S14 / T-OPS-2) — uma linha por repo com o HEAD do ultimo ingest.
# ---------------------------------------------------------------------------

_SYNC_STATE_UPSERT = """
INSERT INTO rag_sync_state (repo, head_sha, dirty, synced_at)
VALUES (%(repo)s, %(head)s, %(dirty)s, now())
ON CONFLICT (repo) DO UPDATE
   SET head_sha = EXCLUDED.head_sha,
       dirty    = EXCLUDED.dirty,
       synced_at = now()
"""


def record_sync_state(conn: psycopg.Connection, repo: str,
                      head_sha: str | None, dirty: bool) -> None:
    """Grava/atualiza o estado do git no momento deste sync (chamado dentro da transacao)."""
    conn.execute(_SYNC_STATE_UPSERT,
                 {"repo": repo, "head": head_sha, "dirty": dirty})


def get_sync_state(conn: psycopg.Connection, repo: str):
    """(head_sha, dirty) do ultimo sync, ou None se nao houver registro."""
    return conn.execute(
        "SELECT head_sha, dirty FROM rag_sync_state WHERE repo = %s", (repo,)
    ).fetchone()


def connect(url: str | None = None) -> psycopg.Connection:
    """Abre conexao (autocommit desligado — o chamador controla a transacao)."""
    return psycopg.connect(url or db_url_from_env())
