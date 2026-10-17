# Relatório de avaliação RAG — baseline recall@k

- Data: **2026-10-17**
- Repo indexado: `ecollm-stack`
- Embedder: `qwen37:rag-embeddings-qwen37`
- Dataset: `eval/dataset.jsonl` (30 perguntas)
- Busca: híbrida (HNSW cosine + tsvector BM25 → RRF k=60), final_k=10
- Critério de corte (plano §FASE 4): recall@8 ≥ 0.7 → **✅ ACEITO**

## Métricas globais

| k | recall@k |
| --- | --- |
| @1 | 0.567 |
| @3 | 0.833 |
| @5 | 0.900 |
| @8 | 0.933 |
| @10 | 0.933 |
| MRR | 0.714 |

## Por tipo de alvo (kind)

| kind | n | r@1 | r@3 | r@5 | r@8 | r@10 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| code | 15 | 0.60 | 0.93 | 0.93 | 1.00 | 1.00 | 0.76 |
| config | 6 | 0.67 | 0.83 | 0.83 | 0.83 | 0.83 | 0.75 |
| doc | 7 | 0.43 | 0.71 | 0.86 | 0.86 | 0.86 | 0.60 |
| mixed | 2 | 0.50 | 0.50 | 1.00 | 1.00 | 1.00 | 0.62 |

## Por fonte da pergunta (overfitting)

`external` = perguntas de fonte independente do autor do código;
recall externo mais baixo que o curado indica sobre-ajuste ao crivo local.

| fonte | n | r@1 | r@3 | r@5 | r@8 | r@10 | MRR | cobertura@10 | recusa |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| curated | 30 | 0.57 | 0.83 | 0.90 | 0.93 | 0.93 | 0.71 | 0.92 | — |

## Acertos por pergunta

| id | rank | RR | grupo | fonte | alvos | cobertos | pergunta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| q02 | 1 | 1.00 | doc | curated | 1 | 1/1 | Por que o HNSW recusa vector(3072) e qual foi a solução? |
| q05 | 1 | 1.00 | mixed | curated | 2 | 2/2 | Em que porta o LiteLLM escuta e qual container serve o gateway? |
| q06 | 1 | 1.00 | config | curated | 2 | 1/2 | Qual é o modelo de fallback local quando o chat do RAG falha? |
| q07 | 1 | 1.00 | config | curated | 1 | 1/1 | Por que existem versões -fast dos modelos Qwen com thinking OFF? |
| q08 | 1 | 1.00 | config | curated | 1 | 1/1 | Qual armadilha de HTTP 400 existe ao combinar tool_choice com thinking ON? |
| q10 | 1 | 1.00 | doc | curated | 1 | 1/1 | Como fazer o setup rápido da stack a partir do .env.example? |
| q13 | 1 | 1.00 | code | curated | 1 | 1/1 | De que forma chunk_doc divide um markdown por headings? |
| q16 | 1 | 1.00 | code | curated | 1 | 1/1 | Como é calculado o content_sha256 de um chunk? |
| q18 | 1 | 1.00 | code | curated | 1 | 1/1 | Como o _split_lines_window corta linhas longas numa janela? |
| q19 | 1 | 1.00 | code | curated | 1 | 1/1 | Um teste que verifica se uma função curta vira exatamente um chunk |
| q20 | 1 | 1.00 | code | curated | 1 | 1/1 | Teste que garante que código nunca ultrapassa o teto de tokens |
| q21 | 1 | 1.00 | code | curated | 1 | 1/1 | Teste que confere detecção de arquivo binário por byte nulo |
| q22 | 1 | 1.00 | code | curated | 1 | 1/1 | Teste de idempotência: mesma lista no mesmo commit não duplica |
| q23 | 1 | 1.00 | config | curated | 1 | 1/1 | Quais volumes persistentes o docker-compose declara? |
| q26 | 1 | 1.00 | doc | curated | 1 | 1/1 | Qual é o roadmap atual do projeto segundo o README? |
| q27 | 1 | 1.00 | code | curated | 2 | 2/2 | Como funciona o sync incremental por arquivo em vez de Merkle tree? |
| q28 | 1 | 1.00 | code | curated | 1 | 1/1 | De que jeito a busca híbrida combina resultado vetorial e léxico? |
| q01 | 2 | 0.50 | doc | curated | 1 | 1/1 | Qual modelo gera os embeddings da stack e com quantas dimensões? |
| q03 | 2 | 0.50 | doc | curated | 1 | 1/1 | O que acontece se eu usar a operator class errada num índice halfvec? |
| q11 | 2 | 0.50 | code | curated | 1 | 1/1 | Qual variável controla quanto tempo o Ollama mantém o modelo carregado na GPU? |
| q12 | 2 | 0.50 | code | curated | 1 | 1/1 | Como a função chunk_code separa funções e classes em chunks? |
| q14 | 2 | 0.50 | code | curated | 1 | 1/1 | O que faz a função chunk_config ao fatiar YAML? |
| q17 | 2 | 0.50 | code | curated | 1 | 1/1 | Como load_corpus percorre os arquivos do repositório? |
| q25 | 2 | 0.50 | config | curated | 1 | 1/1 | O que a seção litellm_settings habilita no proxy? |
| q29 | 3 | 0.33 | code | curated | 1 | 1/1 | Como o CLI decide responder NÃO SEI para pergunta fora do corpus? |
| q30 | 4 | 0.25 | mixed | curated | 2 | 2/2 | Qual serviço expõe SpendLogs e chaves do LiteLLM? |
| q09 | 5 | 0.20 | doc | curated | 1 | 1/1 | Que chave de API é usada para os clientes acessarem o proxy? |
| q15 | 8 | 0.12 | code | curated | 1 | 1/1 | Como o loader classifica um arquivo como code, doc ou config? |
| q04 | - | 0.00 | doc | curated | 1 | 0/1 | Como o init.sql do Postgres pode falhar em silencio? |
| q24 | - | 0.00 | config | curated | 1 | 0/1 | Como está configurada a lista de modelos no LiteLLM (model_list)? |

### Perguntas sem acerto no top-10

- `q04` — Como o init.sql do Postgres pode falhar em silencio?
- `q24` — Como está configurada a lista de modelos no LiteLLM (model_list)?

