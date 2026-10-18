# Stack LiteLLM + catálogo NovAI — configuração e inventário

- **Data:** 2026-10-15
- **Escopo:** S101 (aceite 3) — relatório de configuração da stack LiteLLM
  (rotas, `model_info`, custos, invariante 7, cache/Redis) + inventário do
  catálogo NovAI (121 ids, 11 labs, contagens por modalidade, endpoint por
  família, gaps medidos em S97/S99).
- **Fontes:** `litellm/config.yaml` (fonte de verdade das rotas), sonda read-only
  `GET https://aiapi-pro.com/v1/models` (S97/S99, `NOVAI_API_KEY` nunca impressa)
  e o dump `docs/novai-model-marketplace.html` (tabela oficial de preço/ctx).
- **Natureza:** diagnóstico local (gitignored). Não é governança.

---

## 1. Visão geral da stack

O LiteLLM é o **único ponto de entrada** dos modelos deste repo: o RAG (chat +
embeddings) e o agente (Roo Code / Copilot) falam só com o proxy em `:4000`,
autenticados pela `LITELLM_MASTER_KEY`. O proxy traduz para os provedores
upstream (Gemini, Qwen MaaS/Token Plan, DeepSeek, NovAI, Ollama local).

- **Config:** `litellm/config.yaml` (comentários = registro canônico de decisão).
- **Grupos hoje:** **25** `model_name` (17 → 25 na S95).
- **`litellm_settings`:** `drop_params: true`, `set_verbose: false`,
  `num_retries: 2`, `fallbacks: [rag-chat → qwen3:4b-instruct-2507]`.
- **Cache:** Redis, **só** `supported_call_types: ["aembedding"]`, `ttl: 86400`.

### 1.1 Invariante 7 (inegociável)

> **Rotas NovAI são chat-only.** Nenhum `novai-*` entra em `rag-chat`,
> `fallbacks` ou nos embeddings do RAG.

Motivo: o RAG precisa de um gerador de embeddings **único e estável** (espaços
vetoriais de modelos diferentes são incompatíveis — misturar corrompe o índice).
O chat do RAG é pinado no Gemini free tier com fallback local; rotas NovAI são
**opcionais** e servem uso pontual do agente / bench multi-modelo.

---

## 2. Rotas por família

### 2.1 Chat do RAG (primário + fallback)

| Grupo | Upstream | Papel |
| --- | --- | --- |
| `rag-chat` | `gemini/gemini-3.8-flash` | primário (pin fixo, não `-latest`) |
| `qwen3:4b-instruct-2507` | `ollama_chat/qwen3:4b-instruct-2507-q4_K_M` | fallback local (emergência, sem warmup) |

### 2.2 Agente — Qwen Token Plan (MaaS `sk-sp-`)

Convenção **S44**: id **base = thinking ON** (herda default upstream); sufixo
**`-fast` = thinking OFF** (`enable_thinking: false`).

| Grupo | Thinking | in $/M | out $/M | cache read | cache write |
| --- | --- | --- | --- | --- | --- |
| `qwen3.8-max` | ON | 2,00 | 6,00 | 0,17 | 2,50 |
| `qwen3.8-max-fast` | OFF | 2,00 | 6,00 | 0,17 | 2,50 |
| `qwen3.8-flash` | ON | 0,15 | 0,47 | 0,016 | 0,20 |
| `qwen3.8-flash-fast` | OFF | 0,15 | 0,47 | 0,016 | 0,20 |

Tarifas = marketplace PAYG Qwen (preço canônico de custo-equivalente, S30
resolvida). O `$` do SpendLogs = tokens reais × esta tarifa.

### 2.3 Agente — DeepSeek direto (S55)

Convenção **S55**: `thinking` vai **top-level** no `litellm_params` (não em
`extra_body`) — o shim `_thinking_mode_active()` do provedor só arma com
`optional_params["thinking"]["type"] == "enabled"`.

| Grupo | Thinking | in $/M | out $/M | cache read | ctx |
| --- | --- | --- | --- | --- | --- |
| `deepseek-flash` | ON | 0,15 | 0,60 | 0,003 | 1M |
| `deepseek-flash-fast` | OFF | 0,15 | 0,60 | 0,003 | 1M |
| `deepseek-v4-pro` | ON | 0,66 | 1,98 | 0,022 | 1M |
| `deepseek-v4-pro-fast` | OFF | 0,66 | 1,98 | 0,022 | 1M |

Tarifas = card oficial **off-peak**; **peak = 2×** (01:00–04:00 e 06:00–10:00
UTC, seg–sex) ⇒ SpendLogs **sub-notifica** em peak (nunca sobre-notifica).
DeepSeek não cobra surcharge de cache-write (`cache_creation == input`).

### 2.4 NovAI gateway (chat-only, rota opcional)

Gateway OpenAI-compatível (Hong Kong), base `https://aiapi-pro.com/v1`, chave
prefixo `nvai-` em `NOVAI_API_KEY`. Conta em **modo standard: 60 rpm, cota
unlimited** (S56). Convenção S44/S46 replicada: base = thinking ON, `-fast` =
`extra_body: {thinking: {type: disabled}}`.

| Grupo | Upstream | Thinking | in $/M | out $/M | ctx |
| --- | --- | --- | --- | --- | --- |
| `novai-glm-4.7-flash` | `glm-4.7-flash` | ON | 0 (free) | 0 (free) | 202K |
| `novai-glm-4.7-flash-fast` | `glm-4.7-flash` | OFF | 0 (free) | 0 (free) | 202K |
| `novai-doubao-seed-2.0-pro` | `doubao-seed-2.0-pro` | ON | 0,40 | 2,00 | 256K |
| `novai-doubao-seed-2.0-pro-fast` | `doubao-seed-2.0-pro` | OFF | 0,40 | 2,00 | 256K |
| `novai-deepseek-v4.1-flash` | `deepseek-v4.1-flash` | ON | 0,308 | 1,231 | 128K |
| `novai-deepseek-v4.1-flash-fast` | `deepseek-v4.1-flash` | OFF | 0,308 | 1,231 | 128K |
| `novai-deepseek-v4-pro` | `deepseek-v4-pro` | ON | 0,57 | 1,15 | 128K |
| `novai-deepseek-v4-pro-fast` | `deepseek-v4-pro` | OFF | 0,57 | 1,15 | 128K |
| `novai-deepseek-v4-flash` | `deepseek-v4-flash` | ON | 0,08 | 0,17 | 128K |
| `novai-deepseek-v4-flash-fast` | `deepseek-v4-flash` | OFF | 0,08 | 0,17 | 128K |
| `novai-deepseek-v4-flash-vision` | `deepseek-v4-flash-vision` | ON | 0,308 | 1,231 | 128K |
| `novai-deepseek-v4-flash-vision-fast` | `deepseek-v4-flash-vision` | OFF | 0,308 | 1,231 | 128K |

Custos travados na **S96** (fonte única: `docs/novai-model-marketplace.html`).
NovAI cobra só input/output (sem surcharge de cache exposto) ⇒ `cache_read`/
`cache_creation` ficam de fora de propósito.

### 2.5 Embeddings (perfis trocáveis, S32-c/I9)

**Sem fallback entre perfis** (invariante 7): cada grupo serve um **espaço
vetorial próprio** (tabela + dim no registry `ingest/profiles.py`).

| Grupo | Upstream | Dim | Papel |
| --- | --- | --- | --- |
| `rag-embeddings` | `gemini/gemini-embedding-2` | 3072 (MRL 768/1536/3072) | gerador canônico |
| `rag-embeddings-qwen37` | `openai/qwen3.7-text-embedding` (MaaS) | 1024 | melhor global medido (r@8 0,949) |
| `rag-embeddings-bgem3` | `openai/bge-m3:latest` (Ollama) | 1024 | local, $0/offline, forte pt-BR |

Trocar de perfil = sync dedicado (`rag-sync --profile X`) que re-embeda o índice
**inteiro** naquela tabela; o ponteiro `published_profile` por repo decide qual
espaço atende leitura (S32-b).

---

## 3. Catálogo NovAI (inventário)

Fonte: `GET https://aiapi-pro.com/v1/models` (S97/S99, HTTP 200, 8.705 bytes).

- **121 ids**, **11 labs** (`owned_by`): tencent 27, alibaba 23, minimax 16,
  zhipu 14, bytedance 12, novai 11, moonshot 6, deepseek 4, xiaomi 3, vidu 3,
  tripo 2.
- **Campo `type`** existe **só nos NÃO-chat** (60 itens); ausente = **chat**
  (61 itens). Convenção assimétrica confirmada pela API.

### 3.1 Contagens por modalidade

| Modalidade | Qtd | Endpoint do gateway |
| --- | --- | --- |
| chat | 61 | `/v1/chat/completions` |
| video | 20 | `/v1/video/generations` (**só 9 roteáveis**) |
| image | 14 | `/v1/images/generations` |
| audio | 13 | `/v1/audio/speech` (11) + `/v1/audio/transcriptions` (2) |
| threed | 7 | `/v1/three_d/generations` |
| embedding | 6 | `/v1/embeddings` |
| **Total** | **121** | — |

Bate **1:1** com as 6 abas do dump (`#category-{video,image,chat,embedding,audio,threed}`,
mesmos rótulos e contagens) ⇒ a categorização do dump é **confirmada pela API**.

### 3.2 Gaps e limites (fail-closed)

- **Vídeo: 20 no catálogo, só 9 no endpoint** — 11 slugs anunciados em
  `/v1/models` **não** são roteáveis. Gap registrado, não mascarado.
- **`type` = família de modalidade, não contrato de capacidade.** `vision` **não**
  é exposto (`deepseek-v4-flash-vision`, `glm-4.6v-flash`, `doubao-*-vision` caem
  no bucket `chat` sem campo distintivo). Também **não** há `dim`, `ctx`, `size`
  nem suporte a tool-calling por API.
- **Sem preço por token na API:** `pricing` existe em só **5** ids e é a string
  `"free"` (`glm-4.6v-flash`, `glm-4.7-flash`, `glm-4.1v-thinking-flash`,
  `cogview-3-flash`, `cogvideox-flash`) ⇒ preço só no dump.
- **Sem endpoint de detalhe:** `/v1/models/{id}`, `/v1/model/info`, `/v1/pricing`
  etc. → **404**. `?type=chat` é aceito e ignorado (devolve os 121).
- **Drift de ids:** o dump anuncia `doubao-seedream-4.0/4.5`; a API já serve
  `doubao-seedream-5.0/5.0-pro` ⇒ **a API é a fonte ATUAL de ids** (para `ctx`/
  preço continua valendo o dump).

### 3.3 Limite do próprio LiteLLM (insumo para S100)

`CallTypesLiteral` **não tem** `video` nem `3D` ⇒ essas duas famílias
provavelmente exigem **passthrough** (ou ficam de fora do proxy). Decidir por
**medição** antes de prometer (aceite 3 do S100).

---

## 4. Referências

- `litellm/config.yaml` — fonte de verdade das rotas (comentários = decisão).
- `docs/novai-model-marketplace.html` — tabela oficial de preço/ctx (dump local).
- `.planning/20-BACKLOG.md` — S95/S96 (rotas NovAI DeepSeek), S97/S99 (sondas do
  catálogo), S100 (lote completo), S101 (este diretório).
- `reports/README.md` — política de `reports/` (relatórios + logs).
