-- ============================================================================
-- Migração 005 · perfis de embedding trocáveis — estado por perfil (S32-b / I10)
-- ----------------------------------------------------------------------------
-- Problema: até S32-a o índice tinha UM espaço vetorial (`chunks`, halfvec(3072),
-- gate/prefixo/dim hardcoded). S32 introduz um registry de PERFIS (gemini/qwen37/
-- bgem3), cada um com sua própria tabela derivada. O blue-green do S29 já era
-- keyed por `repo`; agora precisa ser keyed por `(repo, profile)` — cada perfil
-- publica sua própria geração independentemente, e o flip de "qual perfil está
-- ativo" é um ponteiro separado (published_profile), nunca uma mistura de espaços.
--
-- Design (SPEC-S32 §2.4):
--   * `rag_sync_state` ganha `profile text NOT NULL DEFAULT 'gemini'`; PK passa de
--     `(repo)` para `(repo, profile)`. A linha legada (sem profile) cai no default
--     `gemini` → continua legível pelo código novo sem re-boot (R7).
--   * `published_profile text` guarda o slug do perfil PUBLICADO (o que as buscas
--     usam por default quando RAG_PROFILE não está setado). Default `gemini` =
--     comportamento atual. Não há fallback entre perfis (invariante 7): trocar é
--     um ato explícito de publicação via `rag profile use/switch`.
--
-- Espelha rag-db/init.sql (lockstep, I11). Idempotente: IF NOT EXISTS / IF EXISTS;
-- a troca de PK é protegida por checagem de constraint existente. NUNCA editada
-- depois de aplicada (regra de ouro S18) — correção vira 006.
-- ============================================================================

-- 1) Coluna profile (default gemini preserva a linha legada do S29/S14).
ALTER TABLE rag_sync_state
    ADD COLUMN IF NOT EXISTS profile text NOT NULL DEFAULT 'gemini';

-- 2) Coluna published_profile (ponteiro do perfil ativo lido pelas buscas).
ALTER TABLE rag_sync_state
    ADD COLUMN IF NOT EXISTS published_profile text NOT NULL DEFAULT 'gemini';

-- 3) PK passa de (repo) para (repo, profile). Drop da PK auto-nomeada do Postgres
--    (rag_sync_state_pkey) + criação explícita. Só age se a PK ainda for a antiga
--    (single-column), tornando a migração idempotente num volume já migrado.
DO $$
DECLARE
    old_pk_is_single boolean;
BEGIN
    SELECT count(*) = 1 AND bool_or(a.attname = 'repo')
      INTO old_pk_is_single
      FROM pg_constraint c
      JOIN pg_attribute a ON a.attrelid = c.conrelid
                         AND a.attnum = ANY(c.conkey)
     WHERE c.conrelid = 'rag_sync_state'::regclass
       AND c.contype = 'p';
    IF old_pk_is_single THEN
        ALTER TABLE rag_sync_state DROP CONSTRAINT rag_sync_state_pkey;
        ALTER TABLE rag_sync_state
            ADD CONSTRAINT rag_sync_state_pkey PRIMARY KEY (repo, profile);
    END IF;
END $$;
