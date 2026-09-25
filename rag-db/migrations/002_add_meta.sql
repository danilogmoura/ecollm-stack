-- ============================================================================
-- Migração 002 · coluna de metadados JSONB em chunks (S18 — migração de teste)
-- ----------------------------------------------------------------------------
-- Primeira migração REAL da convenção (S18/T-OPS-3). Adiciona `meta jsonb`
-- p/ guardar metadados futuros do chunk sem nova ALTER por campo (ex.: âncora
-- de heading da S19, flags de avaliação, proveniência). Nullable + default NULL
-- → não reescreve linhas existentes nem invalida o índice HNSW/tsv.
--
-- Idempotente: IF NOT EXISTS permite re-aplicar num volume que já a tenha.
-- ============================================================================

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS meta jsonb;
