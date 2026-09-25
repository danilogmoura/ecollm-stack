-- ============================================================================
-- FASE 0 — Fundação do índice RAG (ver .planning/PLANO-RAG.md §3)
-- Executado UMA vez pelo docker-entrypoint-initdb.sh na primeira criação
-- do volume rag_db_data. Mudanças depois exigem migração manual (ALTER).
-- IMPORTANTE (BUG-002): o entrypoint roda psql SEM ON_ERROR_STOP por default;
-- ate a versao atual do script oficial ele para no primeiro erro, mas NAO ha
-- garantia. Validar schema pos-boot com \d chunks sempre que mexer aqui.
-- S11 (T-OPS-1): a validacao esta automatizada. Healthcheck no compose marca o
-- servico unhealthy se faltar tabela/indice obrigatorio; e o script completo
-- (meio ambiente / CI) roda:  python rag-db/verify_schema.py
-- init.sql so executa em VOLUME NOVO -- mudar este arquivo num volume existente
-- NAO re-aplica nada; faca ALTER manual OU docker compose down -v (apaga os
-- dados) e suba de novo. Nunca confie em "container up" = "schema pronto".
-- S18 (T-OPS-3): para EVOLUIR o schema depois do bootstrap, use a convencao de
-- migracoes versionadas em rag-db/migrations/ + python rag-db/run_migrations.py.
-- init.sql retrata o estado inicial (volume novo); as migracoes trazem o delta
-- (volume antigo). Os dois caminhos convergem p/ o mesmo schema (verify_schema.py).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Tabela única de chunks. Decisões travadas no plano:
--  - um só espaço vetorial (gemini-embedding-2, 3072d). Trocar embedder =
--    re-embedar TUDO em tabela nova, nunca misturar dims nesta.
--  - content_hash = sha256 do texto do chunk (com o task-prefix já aplicado?
--    NAO — hash do texto PURO; o prefixo é adicionado so na hora do embed,
--    assim mudar a string de task nao invalida o indice inteiro).
--  - file_hash = git blob sha do arquivo pai: sync incremental deleta chunks
--    cujo file_hash nao existe mais / diff por arquivo.
--  - kind: code|doc|config → filtro barato p/ busca e p/ relatorio recall/kind.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repo          text   NOT NULL,
    path          text   NOT NULL,
    lang          text,                      -- python|markdown|yaml|... (NULL ok)
    kind          text   NOT NULL CHECK (kind IN ('code','doc','config')),
    symbol        text,                      -- nome da funcao/classe/seccao (NULL ok)
    content       text   NOT NULL,           -- texto PURO do chunk (sem task-prefix)
    content_hash  char(64) NOT NULL,         -- sha256(content), hex minusculo
    -- halfvec(3072) e NAO vector(3072): o pgvector impoe teto de 2000 dimensoes
    -- ao indice HNSW em float4 (BUG-001). halfvec (2 bytes/dim) aceita ate 4000
    -- dimensoes indexadas, mantem a operadora <=> (cosine distance) e a
    -- precisao fp16 e irrelevante p/ ranking (erro ~1e-3 << ruido do embedder).
    -- Espelho da decisao MRL: truncar dims seria opcao, perder informacao nao.
    embedding     halfvec(3072) NOT NULL,
    file_hash     char(40) NOT NULL,         -- git blob sha do arquivo
    created_at    timestamptz NOT NULL DEFAULT now(),

    -- Idempotencia bruta: mesmo repo+path+conteudo jamais duplica.
    UNIQUE (repo, path, content_hash)
);

-- Coluna gerada p/ BM25-ish lexical. 'simple' de proposito: corpus tecnico em
-- ingles/simbolos (OLLAMA_KEEP_ALIVE, nomes de funcao); stemming pt-br/en
-- atrapalharia mais do que ajuda em identificadores. (Risco R3 do plano.)
ALTER TABLE chunks DROP COLUMN IF EXISTS tsv;
ALTER TABLE chunks ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;

-- ---------------------------------------------------------------------------
-- Índices
--  - HNSW (cosine) sobre halfvec: m/ef_construction defaults conservadores do
--    plano. Distancia <=> = cosine distance — usar SEMPRE esta operadora nas
--    queries p/ casar com o indice (operator class errada = seq scan silencioso).
--    halfvec e vector compartilham a familia de operadores <=>, entao as queries
--    da FASE 3 funcionam igual.
--  - GIN no tsv: caminho lexical da busca hibrida.
-- ---------------------------------------------------------------------------
-- BUG-002: halfvec exige halfvec_cosine_ops. Usar vector_cosine_ops numa coluna
-- halfvec NAO casa com a operadora <=> → o planner faz seq scan silencioso e o
-- indice vira enfeite. Ver tambem ON_ERROR_STOP no cabecalho do entrypoint.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin
    ON chunks USING gin (tsv);

-- Filtros comuns (por repo e por kind) — baratos, ajudam o planner.
CREATE INDEX IF NOT EXISTS chunks_repo_kind ON chunks (repo, kind);

-- ---------------------------------------------------------------------------
-- Estado de sync (S14 / T-OPS-2) — sinaliza indice desatualizado.
-- Uma linha por repo: guarda o HEAD (e se a arvore estava suja) no momento do
-- ultimo ingest bem-sucedido. rag/rag_search comparam o git atual contra este
-- registro e emitem aviso quando divergir. NAO faz parte do corpus; nao e
-- embedado nem indexado vetorialmente.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_sync_state (
    repo        text PRIMARY KEY,
    head_sha    text,                      -- git rev-parse HEAD no momento do sync
    dirty       boolean NOT NULL DEFAULT false,  -- arvore versionada suja no sync?
    synced_at   timestamptz NOT NULL DEFAULT now()
);
