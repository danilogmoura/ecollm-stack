-- ============================================================================
-- Migração 001 · baseline — FASE 0 + S11 + S14 (idempotente)
-- ----------------------------------------------------------------------------
-- Convenção de migrações (S18 / T-OPS-3): ver rag-db/migrations/README.md.
--
-- Esta NÃO é uma mudança: é o ESTADO INICIAL do schema, expresso de forma
-- IDEMPOTENTE para que `run_migrations.py` possa aplicá-la com segurança tanto
-- num volume NOVO (init.sql já criou tudo → aqui vira no-op) quanto num volume
-- ANTIGO criado antes de alguma tabela existir (aqui cria o que falta).
--
-- Por isso cada objeto usa IF NOT EXISTS / DROP COLUMN IF EXISTS ... ADD, e o
-- conteúdo espelha exatamente rag-db/init.sql. Se init.sql mudar, a mudança vai
-- para uma migração NOVA (NNN_*.sql), NUNCA se edita 001 retroativamente.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repo          text   NOT NULL,
    path          text   NOT NULL,
    lang          text,
    kind          text   NOT NULL CHECK (kind IN ('code','doc','config')),
    symbol        text,
    content       text   NOT NULL,
    content_hash  char(64) NOT NULL,
    -- halfvec(3072), NÃO vector(3072): teto HNSW de 2000 dim (BUG-001).
    embedding     halfvec(3072) NOT NULL,
    file_hash     char(40) NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repo, path, content_hash)
);

-- Coluna gerada p/ BM25-ish lexical ('simple' de propósito — corpus técnico).
ALTER TABLE chunks DROP COLUMN IF EXISTS tsv;
ALTER TABLE chunks ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;

-- BUG-002: operator class halfvec_cosine_ops (vector_* = seq scan silencioso).
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin
    ON chunks USING gin (tsv);

CREATE INDEX IF NOT EXISTS chunks_repo_kind ON chunks (repo, kind);

-- Estado de sync (S14 / T-OPS-2).
CREATE TABLE IF NOT EXISTS rag_sync_state (
    repo        text PRIMARY KEY,
    head_sha    text,
    dirty       boolean NOT NULL DEFAULT false,
    synced_at   timestamptz NOT NULL DEFAULT now()
);
