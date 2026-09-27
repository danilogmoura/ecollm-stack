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
from . import profiles as _profiles
from .embed import load_dotenv, vector_to_halfvec_text


DEFAULT_DB_URL = "postgresql://rag:rag_secret@localhost:5433/rag"


def db_url_from_env() -> str:
    load_dotenv()
    return os.environ.get("RAG_DB_URL", DEFAULT_DB_URL)


# ---------------------------------------------------------------------------
# S32-b (I3): nome de tabela POR PERFIL, sempre resolvido via registry.
# O identificador é interpolado em SQL (nomes de tabela não são parametrizáveis
# via %s), então a ÚNICA fonte é o registry e o slug é validado por regex ANTES
# (R1). Nunca chamar com input cru do usuário sem passar por profiles.resolve().
# ---------------------------------------------------------------------------

def table_for(profile=None) -> str:
    """Nome da tabela do perfil (slug, Profile, ou None→perfil ativo).

    Resolve via registry; um slug inválido/desconhecido levanta InvalidProfile
    antes de qualquer interpolação (R1 — defesa em profundidade contra injeção).
    `None` cai no perfil ativo (RAG_PROFILE > published > gemini), NUNCA em
    resolve(None) — resolve exige um slug explícito.
    """
    p = _profile_arg(profile)
    _profiles.validate_slug(p.slug)          # R1: revalida mesmo vindo do registry
    return p.table


def _profile_arg(profile=None) -> "_profiles.Profile":
    """Normaliza o parâmetro `profile` (slug | Profile | None→ativo) num Profile."""
    if isinstance(profile, _profiles.Profile):
        return profile
    if profile is None:
        return _profiles.active_profile()
    return _profiles.resolve(profile)


# DDL de uma tabela de perfil, clonando a FORMA de init.sql com dim parametrizado
# (SPEC-S32 §2.3). Os 7 objetos: tabela + UNIQUE(repo,path,content_hash,gen) +
# HNSW(halfvec_cosine_ops) + GIN(tsv) + GIN parcial(tsv_pt, kind='doc') +
# (repo,kind) + (repo,gen). {t} é o identificador validado; {dim} um int do registry.
_PROFILE_DDL_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {t} (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repo          text   NOT NULL,
    path          text   NOT NULL,
    lang          text,
    kind          text   NOT NULL CHECK (kind IN ('code','doc','config')),
    symbol        text,
    content       text   NOT NULL,
    content_hash  char(64) NOT NULL,
    embedding     halfvec({dim}) NOT NULL,
    file_hash     char(40) NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    gen           bigint NOT NULL DEFAULT 0,
    meta          jsonb,
    CONSTRAINT {t}_repo_path_content_hash_gen_key
        UNIQUE (repo, path, content_hash, gen)
);
ALTER TABLE {t} DROP COLUMN IF EXISTS tsv;
ALTER TABLE {t} ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
ALTER TABLE {t} DROP COLUMN IF EXISTS tsv_pt;
ALTER TABLE {t} ADD COLUMN tsv_pt tsvector
    GENERATED ALWAYS AS (
        CASE WHEN kind = 'doc' THEN to_tsvector('portuguese', content) END
    ) STORED;
CREATE INDEX IF NOT EXISTS {t}_embedding_hnsw
    ON {t} USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS {t}_tsv_gin ON {t} USING gin (tsv);
CREATE INDEX IF NOT EXISTS {t}_tsv_pt_gin ON {t} USING gin (tsv_pt) WHERE kind = 'doc';
CREATE INDEX IF NOT EXISTS {t}_repo_kind ON {t} (repo, kind);
CREATE INDEX IF NOT EXISTS {t}_repo_gen ON {t} (repo, gen);
"""


def profile_ddl(profile=None) -> str:
    """SQL de criação da tabela do perfil (dim/tabela do registry). Sem conectar.

    Exposto p/ teste unitário inspecionar o DDL (SPEC-S32 §6 teste 4): deve conter
    halfvec(<dim>) e halfvec_cosine_ops, e o identificador validado. Idempotente
    (IF NOT EXISTS / DROP COLUMN IF EXISTS) → pode rodar 2× sem efeito (teste 8).
    """
    p = _profile_arg(profile)
    _profiles.validate_slug(p.slug)                 # R1 antes de formatar
    if not isinstance(p.dim, int) or p.dim <= 0:    # dim só do registry, nunca input
        raise _profiles.InvalidProfile(f"dim inválida p/ perfil {p.slug!r}: {p.dim!r}")
    return _PROFILE_DDL_TEMPLATE.format(t=p.table, dim=p.dim)


def ensure_profile_table(conn, profile=None) -> str:
    """Cria a tabela do perfil se preciso (idempotente); retorna o nome da tabela.

    Perfis extras NÃO entram em init.sql/migração — são criados sob demanda
    (SPEC-S32 §2.3, desvio documentado da convenção S18). O perfil default
    (`gemini`→`chunks`) já existe via init.sql, então aqui é no-op (IF NOT EXISTS).

    Atalho anti-lock (S32-b): se a tabela JÁ existe (to_regclass não-nulo), NÃO
    re-executamos o DDL inteiro. Rodar `CREATE TABLE IF NOT EXISTS` + os
    `ALTER TABLE ... DROP/ADD COLUMN` a cada sync tomaria AccessExclusiveLock na
    tabela mesmo quando nada muda, serializando writers e bloqueando leitores.
    A checagem de existência é barata e idempotente; o caminho de criação mantém
    o DDL completo (7 objetos). SPEC §6 teste 8 valida que a 2ª chamada é no-op.
    """
    p = _profile_arg(profile)
    exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (p.table,)).fetchone()[0]
    if exists:
        return p.table
    conn.execute(profile_ddl(p))
    return p.table



@dataclass(frozen=True)
class Row:
    """Uma linha pronta p/ a tabela chunks (sem id/created_at/tsv — gerados).

    S29: `gen` é a geração blue-green a que a linha pertence. Default 0 = a
    geração publicada herdada de volumes antigos; um sync novo grava em
    gen=published_gen+1 e publica com flip atômico.
    """
    repo: str
    path: str
    lang: str | None
    kind: str
    symbol: str | None
    content: str
    content_hash: str      # sha256 do texto PURO (sem task-prefix)
    file_hash: str         # git blob sha do arquivo pai
    embedding_text: str    # literal "[f1,...]" p/ cast ::halfvec(3072)
    gen: int = 0           # S29: geração (blue-green); 0 = publicado legado


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
INSERT INTO {t} (repo, path, lang, kind, symbol, content, content_hash,
                 file_hash, embedding, gen)
VALUES (%(repo)s, %(path)s, %(lang)s, %(kind)s, %(symbol)s, %(content)s,
        %(content_hash)s, %(file_hash)s, %(embedding)s::halfvec, %(gen)s)
ON CONFLICT (repo, path, content_hash, gen) DO NOTHING
"""


def build_rows(repo: str, file_hash: str, chunks: Sequence[Chunk],
               vectors: Sequence[Sequence[float]], gen: int = 0) -> list[Row]:
    """Monta as linhas a partir dos chunks + vetores alinhados (mesma ordem).

    content_hash vem do chunk PURO (loader.content_sha256), nao do texto
    prefixado — assim mudar a string de task nao invalida o indice.
    S29: `gen` marca a geração blue-green das linhas (default 0 = legado).
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
            gen=gen,
        ))
    return rows


def existing_file_hashes(conn: psycopg.Connection, repo: str,
                         gen: int | None = None,
                         profile=None) -> dict[str, str]:
    """{path: file_hash} currently stored para este repo (base do sync).

    S29/I3: quando `gen` é dado, filtra por aquela geração (o plano deve comparar
    contra a geração PUBLICADA, senão re-embeda arquivos já copiados na nova).
    Sem `gen`, mantém o comportamento legado (todas as gerações, DISTINCT ON path).
    S32-b (I3): `profile` (slug|Profile|None→ativo) escolhe a TABELA; nunca input cru.
    """
    t = table_for(profile)
    if gen is None:
        cur = conn.execute(
            f"SELECT DISTINCT ON (path) path, file_hash FROM {t} WHERE repo = %s "
            "ORDER BY path, created_at DESC",
            (repo,),
        )
    else:
        cur = conn.execute(
            f"SELECT path, file_hash FROM {t} WHERE repo = %s AND gen = %s "
            "GROUP BY path, file_hash",
            (repo, gen),
        )
    return {r[0]: r[1] for r in cur.fetchall()}


def upsert_rows(conn: psycopg.Connection, rows: Iterable[Row],
                profile=None) -> tuple[int, int]:
    """Insere linhas novas; retorna (inserted, unchanged). unchanged = conflito."""
    sql = _UPSERT_SQL.format(t=table_for(profile))
    inserted = unchanged = 0
    for r in rows:
        cur = conn.execute(sql, {
            "repo": r.repo, "path": r.path, "lang": r.lang, "kind": r.kind,
            "symbol": r.symbol, "content": r.content, "content_hash": r.content_hash,
            "file_hash": r.file_hash, "embedding": r.embedding_text, "gen": r.gen,
        })
        if cur.rowcount and cur.rowcount > 0:
            inserted += 1
        else:
            unchanged += 1
    return inserted, unchanged


def delete_stale(conn: psycopg.Connection, repo: str,
                 paths_to_refresh: Iterable[str], profile=None) -> int:
    """Remove chunks de arquivos que vao ser re-embedados (blob mudou).

    Chamado ANTES do upsert para o mesmo path: garante que um arquivo editado
    nao acumule versoes antigas do mesmo conteudo com hash diferente.
    """
    paths = list(paths_to_refresh)
    if not paths:
        return 0
    cur = conn.execute(
        f"DELETE FROM {table_for(profile)} WHERE repo = %s AND path = ANY(%s)",
        (repo, paths),
    )
    return cur.rowcount or 0


def delete_removed(conn: psycopg.Connection, repo: str,
                   live_paths: Iterable[str], profile=None) -> int:
    """Remove chunks cujos paths SUMIRAM do corpus (arquivos apagados)."""
    t = table_for(profile)
    live = list(live_paths)
    if live:
        cur = conn.execute(
            f"DELETE FROM {t} WHERE repo = %s AND NOT (path = ANY(%s))",
            (repo, live),
        )
    else:
        cur = conn.execute(f"DELETE FROM {t} WHERE repo = %s", (repo,))
    return cur.rowcount or 0


def count_chunks(conn: psycopg.Connection, repo: str,
                 gen: int | None = None, profile=None) -> int:
    t = table_for(profile)
    if gen is None:
        return conn.execute(
            f"SELECT count(*) FROM {t} WHERE repo = %s", (repo,)).fetchone()[0]
    return conn.execute(
        f"SELECT count(*) FROM {t} WHERE repo = %s AND gen = %s",
        (repo, gen)).fetchone()[0]


# ---------------------------------------------------------------------------
# S29 · Sync incremental retomável com publicação atômica (blue-green por gen).
# Ver .planning/SPEC-S29-SYNC-RETOMAVEL.md §3–5. Cada execução monta uma geração
# nova (gen=published_gen+1): arquivos inalterados são COPIADOS (copy-forward, 0
# cota), new/changed são embedados por arquivo (retomável), e um único UPDATE
# publica (flip) seguido de GC da geração anterior. Leitores veem sempre published_gen.
# ---------------------------------------------------------------------------

_COPY_FORWARD_SQL = """
INSERT INTO {t} (repo, path, lang, kind, symbol, content, content_hash,
                 file_hash, embedding, meta, gen)
SELECT repo, path, lang, kind, symbol, content, content_hash,
       file_hash, embedding, meta, %(new_gen)s
FROM {t}
WHERE repo = %(repo)s AND gen = %(src_gen)s AND path = ANY(%(paths)s)
ON CONFLICT (repo, path, content_hash, gen) DO NOTHING
"""


def copy_forward_unchanged(conn: psycopg.Connection, repo: str, src_gen: int,
                           new_gen: int, unchanged_paths: Sequence[str],
                           profile=None) -> int:
    """Copia os chunks de `unchanged_paths` da geração publicada p/ a nova.

    Um só statement, ZERO chamadas ao embedder (cota intocada). Idempotente via
    ON CONFLICT DO NOTHING → pode rodar de novo num resume sem duplicar. Retorna
    o nº de linhas inseridas na nova geração. Paths vazios ⇒ no-op (0).
    S32-b (I3): cópia DENTRO da mesma tabela do perfil (espaços nunca se misturam).
    """
    paths = list(unchanged_paths)
    if not paths:
        return 0
    sql = _COPY_FORWARD_SQL.format(t=table_for(profile))
    cur = conn.execute(sql, {
        "repo": repo, "src_gen": src_gen, "new_gen": new_gen, "paths": paths,
    })
    return cur.rowcount or 0


def next_generation(conn: psycopg.Connection, repo: str,
                    profile=None) -> tuple[int, int]:
    """(published_gen, new_gen) do perfil. Cria a linha de estado se não existir.

    new_gen = published_gen + 1. Não grava in_progress_gen aqui — quem faz isso é
    begin_generation (depois de saber que não há sync concorrente, sob lock advisory).
    S32-b (I3): estado keyed por (repo, profile).
    """
    prof = _profile_arg(profile)
    row = conn.execute(
        "SELECT published_gen FROM rag_sync_state WHERE repo = %s AND profile = %s",
        (repo, prof.slug),
    ).fetchone()
    published = row[0] if row else 0
    return published, published + 1


def begin_generation(conn: psycopg.Connection, repo: str, new_gen: int,
                     profile=None) -> None:
    """Marca in_progress_gen=new_gen (o writer está montando esta geração).

    Upset idempotente do ponteiro; chamado dentro da transação do writer, após o
    lock advisory. head_sha/dirty ficam para o flip (record_sync_state no fim).
    """
    prof = _profile_arg(profile)
    conn.execute(
        """
        INSERT INTO rag_sync_state (repo, profile, published_gen, in_progress_gen)
        VALUES (%(repo)s, %(profile)s, 0, %(gen)s)
        ON CONFLICT (repo, profile) DO UPDATE SET in_progress_gen = EXCLUDED.in_progress_gen
        """,
        {"repo": repo, "profile": prof.slug, "gen": new_gen},
    )


def file_in_generation(conn: psycopg.Connection, repo: str, gen: int,
                       path: str, file_hash: str, profile=None) -> bool:
    """True se `path` já tem linhas em `gen` com este `file_hash` (resume: pular).

    Átomo de retomada = arquivo (§3.3): um arquivo está inteiro em new_gen ou
    ausente. Se já commitamos suas linhas nesta geração, pulamos o re-embed.
    """
    row = conn.execute(
        f"SELECT 1 FROM {table_for(profile)} WHERE repo = %s AND gen = %s AND path = %s "
        "AND file_hash = %s LIMIT 1",
        (repo, gen, path, file_hash),
    ).fetchone()
    return row is not None


def publish_generation(conn: psycopg.Connection, repo: str, new_gen: int,
                       profile=None) -> None:
    """FLIP atômico: published_gen ← new_gen, limpa in_progress_gen.

    Um único UPDATE → atomicidade por construção. Depois disto os leitores veem a
    geração nova inteira. §5.2: crash entre flip e GC deixa órfão inofensivo.
    """
    prof = _profile_arg(profile)
    conn.execute(
        "UPDATE rag_sync_state SET published_gen = %s, in_progress_gen = NULL "
        "WHERE repo = %s AND profile = %s",
        (new_gen, repo, prof.slug),
    )


def gc_old_generations(conn: psycopg.Connection, repo: str,
                       published_gen: int, profile=None) -> int:
    """Apaga gerações antigas (gen < published_gen). NUNCA usa <= in_progress_gen (R4).

    Chamado APÓS o flip commitar, em transação separada. Retorna nº de linhas removidas.
    """
    cur = conn.execute(
        f"DELETE FROM {table_for(profile)} WHERE repo = %s AND gen < %s",
        (repo, published_gen)
    )
    return cur.rowcount or 0


def get_published_gen(conn: psycopg.Connection, repo: str, profile=None) -> int:
    """Geração publicada atual do perfil (leitores filtram por ela). Default 0 (legado)."""
    prof = _profile_arg(profile)
    row = conn.execute(
        "SELECT published_gen FROM rag_sync_state WHERE repo = %s AND profile = %s",
        (repo, prof.slug),
    ).fetchone()
    return row[0] if row else 0


def set_in_progress_gen(conn: psycopg.Connection, repo: str, gen: int | None,
                        profile=None) -> None:
    """Grava (ou limpa, com gen=None) o ponteiro da geração em montagem.

    Chamado no início do sync (gen=nova) e no finally (None) para liberar o
    estado se a execução abortar no meio — a próxima retomada recomeça do zero
    nesta geração (copy-forward é idempotente; linhas órfãs são GC-adas depois).
    """
    prof = _profile_arg(profile)
    conn.execute(
        """
        INSERT INTO rag_sync_state (repo, profile, in_progress_gen)
        VALUES (%(repo)s, %(profile)s, %(gen)s)
        ON CONFLICT (repo, profile) DO UPDATE SET in_progress_gen = EXCLUDED.in_progress_gen
        """,
        {"repo": repo, "profile": prof.slug, "gen": gen},
    )


# ---------------------------------------------------------------------------
# Estado de sync (S14 / T-OPS-2) — uma linha por repo com o HEAD do ultimo ingest.
# ---------------------------------------------------------------------------

_SYNC_STATE_UPSERT = """
INSERT INTO rag_sync_state (repo, profile, head_sha, dirty, synced_at)
VALUES (%(repo)s, %(profile)s, %(head)s, %(dirty)s, now())
ON CONFLICT (repo, profile) DO UPDATE
   SET head_sha = EXCLUDED.head_sha,
       dirty    = EXCLUDED.dirty,
       synced_at = now()
"""


def record_sync_state(conn: psycopg.Connection, repo: str,
                      head_sha: str | None, dirty: bool, profile=None) -> None:
    """Grava/atualiza o estado do git no momento deste sync (chamado dentro da transacao).

    S32-b (I3): keyed por (repo, profile) — cada perfil registra seu próprio HEAD.
    """
    prof = _profile_arg(profile)
    conn.execute(_SYNC_STATE_UPSERT,
                 {"repo": repo, "profile": prof.slug, "head": head_sha, "dirty": dirty})


def get_sync_state(conn: psycopg.Connection, repo: str, profile=None):
    """(head_sha, dirty) do ultimo sync daquele perfil, ou None se nao houver registro."""
    prof = _profile_arg(profile)
    return conn.execute(
        "SELECT head_sha, dirty FROM rag_sync_state WHERE repo = %s AND profile = %s",
        (repo, prof.slug),
    ).fetchone()


# ---------------------------------------------------------------------------
# S32-b (I3/I6): ponteiro do perfil PUBLICADO (qual espaço as buscas usam).
# Uma linha por repo em rag_sync_state com published_profile; default 'gemini'.
# Trocar é um ato EXPLÍCITO de publicação (invariante 7 — sem fallback automático).
# ---------------------------------------------------------------------------

def get_published_profile(conn: psycopg.Connection, repo: str) -> str:
    """Slug do perfil publicado p/ este repo. Default 'gemini' (legado/sem linha).

    Lê a coluna published_profile; se não houver nenhuma linha (volume pré-S32 ou
    repo nunca sincronizado), devolve o default sem gravar — leitura nunca falha.
    """
    row = conn.execute(
        "SELECT published_profile FROM rag_sync_state WHERE repo = %s "
        "ORDER BY profile LIMIT 1",
        (repo,),
    ).fetchone()
    if row and row[0]:
        return row[0]
    return _profiles.DEFAULT_PROFILE


def set_published_profile(conn: psycopg.Connection, repo: str, slug: str) -> None:
    """Publica o perfil: grava published_profile=slug na linha (repo, slug).

    Chamado por `rag profile use/switch` APÓS os checks fail-closed (§2.4/R6).
    Usa ON CONFLICT na PK (repo, profile) para garantir que a linha do alvo exista;
    depois atualiza published_profile em TODAS as linhas do repo (o ponteiro é por
    repo, não por perfil — qualquer perfil lido aponta para o mesmo ativo).
    """
    prof = _profiles.resolve(slug)          # R1: só slugs do registry
    _profiles.validate_slug(prof.slug)
    conn.execute(
        """
        INSERT INTO rag_sync_state (repo, profile, published_profile)
        VALUES (%(repo)s, %(profile)s, %(profile)s)
        ON CONFLICT (repo, profile) DO NOTHING
        """,
        {"repo": repo, "profile": prof.slug},
    )
    conn.execute(
        "UPDATE rag_sync_state SET published_profile = %s WHERE repo = %s",
        (prof.slug, repo),
    )


def connect(url: str | None = None) -> psycopg.Connection:
    """Abre conexao (autocommit desligado — o chamador controla a transacao)."""
    return psycopg.connect(url or db_url_from_env())
