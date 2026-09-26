-- ============================================================================
-- Migração 004 · coluna de geração p/ sync blue-green retomável (S29 / T-OPS-7)
-- ----------------------------------------------------------------------------
-- Problema: `run_ingest` roda o sync inteiro numa ÚNICA transação; um HTTP 429
-- do embedder no meio faz ROLLBACK completo e o índice volta ao estado anterior
-- — o progresso nunca acumula entre resets do teto diário. S29 troca por duas
-- versões coexistindo (velha servindo + nova sendo montada) com flip atômico.
--
-- Design (SPEC-S29 §3): cada sync opera sobre uma geração inteira nova
-- (`gen = published_gen + 1`). Leitores consultam SEMPRE `published_gen`.
-- Arquivos inalterados são COPIADOS (copy-forward, 0 cota), não re-embedados;
-- arquivos new/changed são embedados em transação própria POR ARQUIVO (retomável).
-- Quando a geração nova está completa, um único UPDATE publica (flip) e GC apaga
-- as gerações antigas.
--
-- A unicidade passa a incluir `gen`: o mesmo (repo,path,content_hash) pode
-- existir em duas gerações durante o sync. Isso RENOMEIA o índice de unicidade
-- (I9/R6): os três verificadores — verify_schema.py, healthcheck do compose e
-- init.sql — mudam em LOCKSTEP para o novo nome `chunks_repo_path_content_hash_gen_key`.
--
-- Retrocompatibilidade: linhas existentes ficam `gen=0`, `published_gen=0`; um
-- volume antigo permanece legível pelo código novo (que filtra gen=published_gen).
-- Idempotente: IF NOT EXISTS / IF EXISTS → no-op num volume que já a tenha.
-- ============================================================================

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS gen bigint NOT NULL DEFAULT 0;

-- Unicidade agora inclui gen (mesmo conteúdo pode viver em duas gerações).
-- DROP da constraint antiga (nome auto-gerado pelo Postgres) + criação da nova
-- com nome EXPLÍCITO, igual ao espelhado em init.sql e nos verificadores (I9).
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_repo_path_content_hash_key;
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_repo_path_content_hash_gen_key;
ALTER TABLE chunks ADD CONSTRAINT chunks_repo_path_content_hash_gen_key
    UNIQUE (repo, path, content_hash, gen);

-- Índice p/ o filtro de leitura (gen = published) e p/ o GC (gen < published).
CREATE INDEX IF NOT EXISTS chunks_repo_gen ON chunks (repo, gen);

-- rag_sync_state ganha o ponteiro de publicação (blue-green).
ALTER TABLE rag_sync_state ADD COLUMN IF NOT EXISTS published_gen   bigint NOT NULL DEFAULT 0;
ALTER TABLE rag_sync_state ADD COLUMN IF NOT EXISTS in_progress_gen bigint;
