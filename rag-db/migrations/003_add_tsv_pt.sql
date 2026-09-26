-- ============================================================================
-- Migração 003 · tsvector em português p/ chunks de documentação (S20/T-RET-2)
-- ----------------------------------------------------------------------------
-- O `tsv` atual usa config 'simple' (sem stemming): ideal p/ código/identifi-
-- cadores (OLLAMA_KEEP_ALIVE, nomes de função), mas ruím p/ prosa em pt-BR —
-- não lematiza ("índice"/"indices", "acontece"/"acontecendo" não casam).
--
-- S20 adiciona uma SEGUNDA coluna gerada `tsv_pt` com config 'portuguese'
-- (stemming Snowball + stopwords pt), preenchida SOMENTE para kind='doc'
-- (prosa); code/config ficam NULL e são cobertos pelo `tsv` simple de sempre.
-- O índice GIN é PARCIAL (WHERE kind='doc'): pequeno, e o planner só o usa
-- quando o predicado confirma kind='doc'.
--
-- A busca lexical passa a consultar as DUAS colunas p/ docs e fundir as listas
-- (ver ingest/search.py). Aceite = A/B na eval: adota-se só se melhorar sem
-- regressão; senão reverter é DROP COLUMN tsv_pt + DROP INDEX (migração N+1).
--
-- Idempotente: IF NOT EXISTS → no-op num volume que já a tenha.
-- ============================================================================

ALTER TABLE chunks DROP COLUMN IF EXISTS tsv_pt;
ALTER TABLE chunks ADD COLUMN tsv_pt tsvector
    GENERATED ALWAYS AS (
        CASE WHEN kind = 'doc'
             THEN to_tsvector('portuguese', content)
        END
    ) STORED;

CREATE INDEX IF NOT EXISTS chunks_tsv_pt_gin
    ON chunks USING gin (tsv_pt)
    WHERE kind = 'doc';
