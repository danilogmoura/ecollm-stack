# ecollm-stack

Gateway local de LLMs com [LiteLLM](https://docs.litellm.ai/) na porta `4000`, servindo três papéis:

- **Agente de código** (Roo Code / GitHub Copilot BYOK / LM Studio) → Qwen Token Plan
- **Chat de RAG** (`rag-chat`) → Gemini com fallback local via Ollama
- **Embeddings** → **3 perfis trocáveis** (S32): Google `gemini-embedding-2` (3072d), Qwen MaaS `qwen3.7-text-embedding` (1024d) e `bge-m3` local/Ollama (1024d, $0). Cada perfil é um **espaço vetorial isolado** (tabela própria); trocar de perfil = re-embedar o índice inteiro naquela tabela. Default global `bgem3` (local/$0); o perfil **ativo** aqui é `qwen37` (via `RAG_PROFILE` no `.env`).

Além do gateway, a stack inclui um **pipeline RAG completo** sobre pgvector (ingest
incremental → chunker AST/markdown/config → embeddings → busca híbrida HNSW+tsvector
via RRF → CLI `rag`/`rag-sync` → servidor MCP `rag_search`). Ver [Pipeline RAG](#pipeline-rag-fases-05).

## Serviços

| Container | Imagem | Porta | Papel |
| --- | --- | --- | --- |
| `ai-litellm` | `ghcr.io/berriai/litellm:main-stable` | 4000 | gateway / roteamento / fallbacks / cache |
| `ai-ollama` | `ollama/ollama` | 11434 | modelo local de emergência (`qwen3:4b-instruct-2507-q4_K_M`) |
| `ai-litellm-db` | `postgres:15` | — | SpendLogs e chaves do LiteLLM |
| `ai-litellm-redis` | `redis:7-alpine` | — | cache de respostas (hoje: só embeddings) |
| `ai-rag-db` | `pgvector/pgvector:pg17` | `127.0.0.1:5433`→5432 | índice vetorial do RAG — **uma tabela por perfil** (`chunks`/gemini halfvec 3072, `chunks_qwen37`/`chunks_bgem3` halfvec 1024) + HNSW + tsvector GIN; bind loopback só |

> ⚠️ Não use a tag `:main` do LiteLLM — congelada em Dez/2023, ignora o config montado (detalhes em `litellm/config.yaml`).

## Modelos expostos (`/v1/models`)

**Chat / agente:**

| Grupo | Backend | Thinking | Uso |
| --- | --- | --- | --- |
| `rag-chat` | gemini-3.8-flash → fallback qwen3:4b local | — | chat do RAG |
| `qwen3.8-max` / `qwen3.8-flash` | Token Plan | ON | Architect / debug difícil |
| `qwen3.8-max-fast` / `qwen3.8-flash-fast` | Token Plan | OFF | loop de agente (Code/Ask/Copilot) |
| `deepseek-flash` / `deepseek-v4-pro` | DeepSeek V4.1-Flash / V4-Pro (rota opcional, fora do RAG) | ON | uso pontual / bench multi-modelo (ctx 1M; pro sem visão) |
| `deepseek-flash-fast` / `deepseek-v4-pro-fast` | DeepSeek (mesmos upstreams) | OFF | preferidas em loop de agente com tools |
| `novai-glm-4.7-flash` / `-fast` | NovAI (aiapi-pro.com, **free**) | ON / OFF | chat opcional (cota 10/dia·upstream, compartilhada) |
| `novai-doubao-seed-2.0-pro` / `-fast` | NovAI (ByteDance, **pago**) | ON / OFF | chat opcional (contexto 256K) |

**Embeddings (perfis trocáveis, um espaço vetorial cada):**

| Grupo | Backend | dims | Tabela |
| --- | --- | --- | --- |
| `rag-embeddings` | gemini/gemini-embedding-2 | 3072 | `chunks` |
| `rag-embeddings-qwen37` | openai/qwen3.7-text-embedding (MaaS) | 1024 | `chunks_qwen37` |
| `rag-embeddings-bgem3` | bge-m3 (Ollama local, $0) | 1024 | `chunks_bgem3` |

Os grupos `-fast` dos Qwen fixam `enable_thinking: false` **no proxy** — clientes nunca enviam o parâmetro. Nos grupos NovAI o thinking OFF usa `extra_body: {thinking: {type: disabled}}` (a flag `enable_thinking` **não** funciona no Doubao — gotcha medido). Nas rotas DeepSeek o `thinking` vai **top-level** em `litellm_params` (`thinking: {type: enabled|disabled}`), não em `extra_body`: só assim o LiteLLM arma o shim que devolve `reasoning_content` em multi-turno e evita HTTP 400 em loop de agente. Convenção em todo o repo: id **base** = thinking ON, sufixo **`-fast`** = thinking OFF — a **flag correta é por provider**. A justificativa completa (matriz medida de tokens/latência, armadilha de HTTP 400 com `tool_choice` + thinking ON) está comentada em `litellm/config.yaml`.

## Setup rápido

```bash
cp .env.example .env   # mínimo: GEMINI_API_KEY + QWEN_PLAN_API_KEY.
                       # p/ o perfil de embed ativo (qwen37) preencha também QWEN_MAAS_API_KEY
                       # (chave MaaS separada do Token Plan). Rotas opcionais: DEEPSEEK_API_KEY,
                       # NOVAI_API_KEY. O .env.example traz todas as chaves.
docker compose up -d
# LITELLM_MASTER_KEY fica no .env; leia de la em vez de colar a chave no comando
curl -s localhost:4000/v1/models -H "Authorization: Bearer $(grep LITELLM_MASTER_KEY .env | cut -d= -f2)" | jq -r '.data[].id'
```

Chave dos clientes = `LITELLM_MASTER_KEY` (uma chave por camada; chaves upstream só no `.env`).

## Pipeline RAG (FASES 0–5)

Índice vetorial do próprio repo sobre pgvector (`ai-rag-db`). Python 3.12 em `.venv/`
(criado com **uv**; não tem `pip` — instale com `VIRTUAL_ENV=.venv ~/.local/bin/uv pip install -r requirements.txt`).
O CLI é um módulo: invoque via `.venv/bin/python -m ingest.cli …`. Config de conexão vem do `.env` da raiz.

| Comando | O que faz |
| --- | --- |
| `rag-sync` / `python -m ingest.cli sync [--repo PATH] [--dry-run]` | ingest incremental (loader→chunker→embed→store). Idempotente: re-execução sem mudança = 0 embeddings. Gate gitleaks aborta se achar segredo no corpus. |
| `rag "pergunta"` / `… cli search "pergunta"` | busca híbrida (HNSW denso + tsvector/BM25 → fusão RRF), imprime top-k com fonte, score e ranks. Filtros `--kind code\|doc\|config`, `--path PREFIXO`, `-k N`. |
| `rag --ask "pergunta"` | busca + gera resposta citando `[n]` via **`qwen3.8-flash-fast`** (default real; override por env `RAG_CHAT_MODEL`). Fora do corpus → responde "NÃO SEI". |

```bash
# sincronizar o índice e consultar
.venv/bin/python -m ingest.cli sync
.venv/bin/python -m ingest.cli search "como funciona o gate de segredos"
.venv/bin/python -m ingest.cli search --ask "qual modelo e dims dos embeddings?"
```

**Servidor MCP `rag_search`** (`mcpsrv/rag_server.py`, stdio): expõe a mesma busca como
tool para agentes (Roo Code / Copilot). Contrato de retorno: JSON `{results:[{path,symbol,kind,score,source,content,<proveniência>}]}`.
As **6 chaves núcleo** vêm primeiro em ordem congelada (byte-prefixo estável p/ o prompt-cache); a **cauda de proveniência** da S48 acrescenta `vec_rank`, `lex_rank`, `cosine_distance` e `provenance` (`hybrid`/`dense_only`/`lexical_only`) — metadados que o cliente usa para calibrar o próprio corte "NÃO SEI", já que o gate de distância é desligado no MCP por design. **Tuning S37:** o cliente nunca precisa passar `k`; quando omite, a tool emite `DEFAULT_K=6` chunks mas busca internamente `SEARCH_DEPTH=8` (mantém o ranking canônico recall@8, só encolhe a cauda enviada). Ajustável por env `RAG_DEFAULT_K`/`RAG_SEARCH_DEPTH` sem tocar código; o schema MCP permanece `k:int=8` byte-idêntico.
Registro do lado do cliente em `mcpsrv/mcp.example.json`:

```jsonc
{ "mcpServers": { "rag-search": {
    "command": "/home/demo/ecollm-stack/.venv/bin/python",
    "args": ["/home/demo/ecollm-stack/mcpsrv/rag_server.py"],
    "cwd": "/home/demo/ecollm-stack",
    "env": { "PYTHONPATH": "/home/demo/ecollm-stack", "RAG_REPO": "ecollm-stack" }
} } }
```

**Baseline de avaliação** (`eval/`): `recall@k` sobre dois datasets. *Snapshot 2026-10-14 —
o dono canônico dos números é `10-STATE.md` §2; re-meça antes de citar.*

- **Dataset curado** (`dataset.jsonl`, 30 perguntas): **recall@8 = 1,000** (MRR 0,659).
- **Dataset-v2** (`dataset-v2.jsonl`, 65 perguntas, gate canônico exige `--gate-dist`) por perfil:
  **qwen37 r@8 = 0,949** · bgem3 0,897 · gemini 0,8205. Só `qwen37` atinge a barra ≥0,900.
- **Chunks no índice** (ecollm-stack): gemini 836 · qwen37 752 · bgem3 705.

### Testes e CI

Dependências travadas em `uv.lock` (fonte: `pyproject.toml`; `requirements.txt` é só
doc legível). Ambiente local:

```bash
VIRTUAL_ENV=.venv ~/.local/bin/uv sync --extra dev   # cria/.atualiza .venv a partir do lock
.venv/bin/python -m pytest                            # suíte unitária (sem rede/DB)
```

A pipeline **`.github/workflows/ci.yml`** roda essa suíte em todo push/PR no runner da
GitHub Actions (`uv sync --frozen` + `pytest`) — falha bloqueia merge com branch protection.
O **gate de recall** (`python -m eval.recall --gate`) **não** roda na CI: exige índice
pgvector vivo + chamada real de embedding no perfil ativo (hoje `qwen37` via chave MaaS;
`bgem3` local dispensa cota externa, mas ainda exige o serviço Ollama) — inviável/seguro no
runner efêmero. Ele continua validado localmente após qualquer mudança que afete ranking.

### Runbook — recuperação do índice

`init.sql` roda **só no primeiro bootstrap do volume**. Se o schema corromper ou mudar:

```bash
docker compose down rag-db
docker volume rm ecollm-stack_rag_db_data   # nome do volume conforme `docker volume ls`
docker compose up -d rag-db                  # re-executa init.sql (extensão + tabela + índices)
.venv/bin/python -m ingest.cli sync          # re-embeda o corpus do zero
```

Após qualquer edição em `rag-db/init.sql`, recrie o volume e confira `pg_indexes`
(HNSW `halfvec_cosine_ops` + GIN tsvector) — ver Gotchas abaixo (BUG-002).

## Decisões registradas

- **Embeddings**: **3 perfis trocáveis** (S32), cada um um espaço vetorial isolado — Google `gemini-embedding-2` (3072d), Qwen MaaS `qwen3.7-text-embedding` (1024d, melhor r@8 medido = 0,949), `bge-m3` local (1024d, $0/offline). **Nunca há fallback entre perfis** (misturar vetores de modelos diferentes corromperia o índice — invariante 7). O Token Plan **não** serve embeddings (404 no endpoint, comprovado) — o embedder Qwen usa a chave MaaS separada. Default global `bgem3` (local/$0, aceito operar 0,003 abaixo do gate); perfil ativo aqui é `qwen37` via `RAG_PROFILE`. Registry em `ingest/profiles.py`; trocar = `rag-sync --profile X` (re-embeda a tabela toda).
- **Cache**: dois mecanismos orthogonalmente diferentes, ambos ativos. (1) **Cache de RESPOSTA do LiteLLM** (Redis), escopo deliberado `aembedding` — `litellm/config.yaml` lista `supported_call_types: ["aembedding", "atranscription"]`, mas `atranscription` é **no-op hoje** (não há modelo de transcrição na stack), logo o efeito prático é só embeddings; é hash do request inteiro, logo inútil para o loop de agente (as mensagens mudam a cada iteração); semântico descartado (risco em tráfego agentic). (2) **Context/prompt caching de UPSTREAM no Token Plan Qwen — EXISTE e está ativo.** Ao contrário do que uma leitura antiga deste README afirmava, o Token Plan Individual **suporta** context caching no endpoint OpenAI-compatível (confirmado pelo suporte Alibaba, ticket `0065ETFBAP`, + doc oficial + medido empíricamente via nosso próprio proxy: `usage.prompt_tokens_details.cached_tokens`). Três modos nos modelos `qwen3.8-*`: **implícito** (automático, não desliga; hit ~20%), **explícito** (`cache_control:{type:"ephemeral"}`, criação 125% / hit menor, TTL 5 min, ≤4 markers, lookback ≤20 blocos) e **session** (só na Responses API). ⚠️ Exceção de preço: o hit de `qwen3.8-max`/`flash` **não** segue os 10%/20% padrão — conferir no marketplace antes de projetar economia. Este é o lever real para os ~105k prompt-tokens do agente. Detalhes e trabalho a planejar: `.planning/PLANO-RAG.md` §4b-5/§4b-6 e BUG-007.
- **Fallback RAG**: cadeia simples `rag-chat → qwen3:4b` mantida de propósito (multinível funciona no LiteLLM 1.102, avaliado e dispensado por ora).
- **Warmup Ollama**: removido — GPU livre em repouso; cold load ~41 s aceitável para papel de emergência.

## Gotchas

Armadilhas já encontradas ao montar o índice RAG (pgvector + Docker):

- **HNSW tem teto de dimensões.** Índices HNSW/IVFFlat sobre `vector` (float4) aceitam no máximo 2000 dimensões; embedders de 3072d (ex.: `gemini-embedding-2`) exigem armazenar como `halfvec(3072)` — fp16 indexável até 4000d, com erro de precisão (~1e-3) irrelevante para ranking. Truncar via MRL é alternativa, mas descarta informação.
- **Operator class errada = índice enfeite.** `USING hnsw (embedding vector_cosine_ops)` numa coluna `halfvec` cria o índice sem erro algum — e o planner nunca usa `<=>` contra ele: seq scan silencioso. A classe deve bater com o tipo exato da coluna (`halfvec_cosine_ops` p/ halfvec). Validar sempre com `EXPLAIN`, nunca confiar só no `\di`.
- **`init.sql` quebra em silêncio.** O entrypoint do Postgres roda os scripts de bootstrap statement a statement; um erro no meio aborta o resto sem sinal externo — o container declara "database system is ready" com schema incompleto. Após qualquer mudança em `rag-db/init.sql`, recriar o volume e conferir `pg_indexes` pós-boot.

## Roadmap

- [x] Gateway multi-provedor + grupos fast/thinking + cache de embeddings
- [x] **Ingest RAG** (FASES 0–5): serviço pgvector (`rag-db`), loader via `git ls-files`, chunker AST (tree-sitter) p/ código e por `##` p/ docs, busca híbrida (HNSW+tsvector via RRF), **3 perfis de embedding trocáveis** (S32), baseline curada recall@8=1,000 / dataset-v2 qwen37 0,949, CLI `rag`/`rag-sync` e servidor MCP `rag_search` (com proveniência da fusão, S48)
- [ ] **Headroom / context caching**: pré-processador de contexto (dedupe de chunks, resumo de histórico, trunc de tool-output) **+ cache de prefixo upstream**. Alvo: os ~105k prompt-tokens de ENTRADA por turno do agente Roo Code, medidos nos SpendLogs do LiteLLM (não a estimativa inicial de 16–54k). Ver `.planning/PLANO-RAG.md` §4b-6 e `PLANO-FASE6-CACHE.md`.
