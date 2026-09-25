# ecollm-stack

Gateway local de LLMs com [LiteLLM](https://docs.litellm.ai/) na porta `4000`, servindo três papéis:

- **Agente de código** (Roo Code / GitHub Copilot BYOK / LM Studio) → Qwen Token Plan
- **Chat de RAG** (alias pronto; pipeline de ingestão ainda em construção) → Gemini free tier com fallback local via Ollama
- **Embeddings** → exclusivamente Google (`gemini-embedding-2`, 3072 dims)

## Serviços

| Container | Imagem | Porta | Papel |
| --- | --- | --- | --- |
| `ai-litellm` | `ghcr.io/berriai/litellm:main-stable` | 4000 | gateway / roteamento / fallbacks / cache |
| `ai-ollama` | `ollama/ollama` | 11434 | modelo local de emergência (`qwen3:4b-instruct-2507-q4_K_M`) |
| `ai-litellm-db` | `postgres:15` | — | SpendLogs e chaves do LiteLLM |
| `ai-litellm-redis` | `redis:7-alpine` | — | cache de respostas (hoje: só embeddings) |

> ⚠️ Não use a tag `:main` do LiteLLM — congelada em Dez/2023, ignora o config montado (detalhes em `litellm/config.yaml`).

## Modelos expostos (`/v1/models`)

| Grupo | Backend | Thinking | Uso |
| --- | --- | --- | --- |
| `rag-chat` | gemini-3.8-flash → fallback qwen3:4b local | — | chat do RAG |
| `rag-embeddings` | gemini-embedding-2 | — | único gerador de vetores da stack |
| `qwen3.8-max` / `qwen3.8-flash` | Token Plan | ON | Architect / debug difícil |
| `qwen3.8-max-fast` / `qwen3.8-flash-fast` | Token Plan | OFF | loop de agente (Code/Ask/Copilot) |

Os grupos `-fast` fixam `enable_thinking: false` **no proxy** — clientes nunca enviam o parâmetro. A justificativa completa (matriz medida de tokens/latência, armadilha de HTTP 400 com `tool_choice` + thinking ON) está comentada em `litellm/config.yaml`.

## Setup rápido

```bash
cp .env.example .env   # preencha GEMINI_API_KEY e QWEN_PLAN_API_KEY
docker compose up -d
# LITELLM_MASTER_KEY fica no .env; leia de la em vez de colar a chave no comando
curl -s localhost:4000/v1/models -H "Authorization: Bearer $(grep LITELLM_MASTER_KEY .env | cut -d= -f2)" | jq -r '.data[].id'
```

Chave dos clientes = `LITELLM_MASTER_KEY` (uma chave por camada; chaves upstream só no `.env`).

## Decisões registradas

- **Embeddings**: só Google. O Token Plan não tem embedder (404 no upstream, comprovado). Upgrade path pago documentado: `voyage-code-3` (~$0,18 o ingest inteiro) — decidir com baseline recall@k, não no escuro. Trocar embedder = re-embedar o índice todo.
- **Cache**: exato (Redis), escopo `aembedding` apenas. Tráfego de agente fica fora porque o cache é hash do request inteiro e as mensagens mudam a cada iteração. Semântico descartado (risco em tráfego agentic). Prompt-caching de upstream não existe no plano Qwen.
- **Fallback RAG**: cadeia simples `rag-chat → qwen3:4b` mantida de propósito (multinível funciona no LiteLLM 1.102, avaliado e dispensado por ora).
- **Warmup Ollama**: removido — GPU livre em repouso; cold load ~41 s aceitável para papel de emergência.

## Gotchas

Armadilhas já encontradas ao montar o índice RAG (pgvector + Docker):

- **HNSW tem teto de dimensões.** Índices HNSW/IVFFlat sobre `vector` (float4) aceitam no máximo 2000 dimensões; embedders de 3072d (ex.: `gemini-embedding-2`) exigem armazenar como `halfvec(3072)` — fp16 indexável até 4000d, com erro de precisão (~1e-3) irrelevante para ranking. Truncar via MRL é alternativa, mas descarta informação.
- **Operator class errada = índice enfeite.** `USING hnsw (embedding vector_cosine_ops)` numa coluna `halfvec` cria o índice sem erro algum — e o planner nunca usa `<=>` contra ele: seq scan silencioso. A classe deve bater com o tipo exato da coluna (`halfvec_cosine_ops` p/ halfvec). Validar sempre com `EXPLAIN`, nunca confiar só no `\di`.
- **`init.sql` quebra em silêncio.** O entrypoint do Postgres roda os scripts de bootstrap statement a statement; um erro no meio aborta o resto sem sinal externo — o container declara "database system is ready" com schema incompleto. Após qualquer mudança em `rag-db/init.sql`, recriar o volume e conferir `pg_indexes` pós-boot.

## Roadmap

- [x] Gateway multi-provedor + grupos fast/thinking + cache de embeddings
- [ ] **Ingest RAG**: serviço pgvector (`rag-db`), loader via `git ls-files`, chunker AST (tree-sitter) p/ código e por `##` p/ docs, busca híbrida, baseline recall@k
- [ ] **Headroom**: pré-processador de contexto (dedupe de chunks, resumo de histórico, trunc de tool-output) — ataca os ~16–54k tokens de entrada por chamada de agente
