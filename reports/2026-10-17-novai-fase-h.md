# Fase H — embeddings + pgvector isolado (S103 / T23)

- Data: **2026-10-17**
- Harness: `eval/novai_test.py` (`--family embedding --pgvector --target both --live`)
- Alvos: **gateway** `aiapi-pro.com/v1` + **proxy** LiteLLM `:4000/v1`
- Logs brutos: `reports/logs/2026-10-17-novai-embedding.jsonl` (60 linhas, redigido)
- Testes offline: **157 passed** em `eval/tests/test_novai_test.py`; suíte completa **753 passed**

## O que a Fase H cobre

| teste | chamada | aceite (matriz §10) |
| --- | --- | --- |
| `embed` (T6) | `POST /v1/embeddings` | `data[0].embedding` lista numérica + dim |
| `embed.pgvector` (T23) | embed → `CREATE TABLE` → `INSERT` → `SELECT ... ORDER BY embedding <=> $1 LIMIT 1` | **dim bate** + **busca por distância retorna o próprio vetor** |

A tabela de sonda é **`chunks_novai_<slug>`**, criada fora do registry
`ingest/profiles.py` e nunca lida por `ingest/search.py`. **Invariante 7
preservado: testar ≠ adotar.** Nenhum `novai-*` entrou em `rag-chat`,
`fallbacks` ou nos embeddings do RAG.

## Resultado (rodada final)

```
checks=24 pass=24 fail=0 skip=0
  ✅ novai-embed-qwen3.7-text-embedding        :: embed — dim=1024
  ✅ novai-embed-qwen3.7-text-embedding        :: embed.pgvector — dim=1024 :: distância=0 ≤ tol=0.001
  ✅ novai-embed-text-embedding-v4             :: embed — dim=1024
  ✅ novai-embed-text-embedding-v4             :: embed.pgvector — dim=1024 :: distância=0 ≤ tol=0.001
  ✅ novai-embed-kinfra-text-embedding-4b      :: embed — dim=2560
  ✅ novai-embed-kinfra-text-embedding-4b      :: embed.pgvector — dim=2560 :: distância=0 ≤ tol=0.001
  ✅ novai-embed-kinfra-vl-embedding-8b        :: embed — dim=4096
  ✅ novai-embed-kinfra-vl-embedding-8b        :: embed.pgvector — dim=4096 :: distância=0 ≤ tol=0.001
  ✅ novai-embed-kinfra-text-embedding-0.6b    :: embed — dim=1024
  ✅ novai-embed-kinfra-text-embedding-0.6b    :: embed.pgvector — dim=1024 :: distância=0 ≤ tol=0.001
  ✅ novai-embed-kinfra-vl-embedding-2b        :: embed — dim=2048
  ✅ novai-embed-kinfra-vl-embedding-2b        :: embed.pgvector — dim=2048 :: distância=0 ≤ tol=0.001
  (idem no proxy)

# divergência gateway × proxy
  same_pass     12 — ambos passam ⇒ comportamento do gateway NovAI
```

**Gateway e proxy se comportam de forma idêntica** nos 6 grupos: 12 `same_pass`,
zero divergência, nenhum bug do LiteLLM.

## Dimensões medidas (fonte: resposta do gateway)

| grupo | upstream | dim | norma L2 |
| --- | --- | --- | --- |
| `novai-embed-qwen3.7-text-embedding` | `qwen3.7-text-embedding` | 1024 | 1,0 |
| `novai-embed-text-embedding-v4` | `text-embedding-v4` | 1024 | 1,0 |
| `novai-embed-kinfra-text-embedding-4b` | `kinfra-text-embedding-4b` | 2560 | 1,0 |
| `novai-embed-kinfra-vl-embedding-8b` | `kinfra-vl-embedding-8b` | **4096** | 1,0 |
| `novai-embed-kinfra-text-embedding-0.6b` | `kinfra-text-embedding-0.6b` | 1024 | 1,0 |
| `novai-embed-kinfra-vl-embedding-2b` | `kinfra-vl-embedding-2b` | 2048 | 1,0 |

Todos os 6 devolvem vetores **normalizados** (norma 1,0) — a distância cosine é
equivalente ao produto interno, e o round-trip por `<=>` é comparável entre eles.

## Achados

### H1 — BUG NOSSO (classe H): modelos VL rejeitam `input` como lista de strings

Os dois grupos `*-vl-embedding-*` devolviam **HTTP 400** no smoke da Fase A
(`embed 4✅/2❌` no backlog). Causa medida no gateway direto:

| payload `input` | `kinfra-vl-embedding-8b` | `kinfra-vl-embedding-2b` |
| --- | --- | --- |
| `["texto de teste"]` | **400** `[Tencent (Kinfra)] The request parameter input is invalid or missing` | **400** (idem) |
| `[{"type":"text","text":"texto de teste"}]` | **200** | **200** |
| `[{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]` | **200** | **200** |

Não é bug do gateway nem do LiteLLM: os modelos VL do Tencent exigem o formato
**multimodal** de `input` (lista de objetos), não a lista de strings do formato
OpenAI clássico. O harness mandava sempre `[text]`.

**Corrigido**: `embedding_input(model, text)` (puro) escolhe o payload pelo
sufixo `-vl-embedding-` do nome do modelo. Efeito: família embedding
**4/6 → 6/6** no smoke, e os dois VL passaram a exercitar o round-trip pgvector.

### H2 — `halfvec` não comporta 4096 dims; fallback para `vector` sem HNSW

`kinfra-vl-embedding-8b` devolve **4096 dims**, acima do teto do `halfvec`
(4000). O primeiro run da Fase H falhou exatamente aí:

```
❌ novai-embed-kinfra-vl-embedding-8b :: embed.pgvector — pgvector: ValueError: dim inválida para halfvec: 4096
```

Medido no `ai-rag-db` (pgvector **0.8.6**):

| tipo | `INSERT`/`<=>` com 4096 dims | índice HNSW |
| --- | --- | --- |
| `halfvec(4096)` | **falha** (teto 4000) | — |
| `vector(4096)` | **OK** (distância 0,0) | **falha** — `column cannot have more than 2000 dimensions for hnsw index` |

**Corrigido**: `pgvector_column_type(dim)` escolhe `halfvec` até 4000 e `vector`
acima; o DDL só cria o índice HNSW quando a coluna é `halfvec`. A sonda T23 não
precisa de índice (tabela de 1 linha, `ORDER BY ... LIMIT 1` é seq scan exato).
O `notes` do check registra `tipo=halfvec|vector` para auditoria.

> **Nota para o RAG (não é ação desta fase):** se algum dia um perfil de
> produção usar um embedder de >4000 dims, ele **não** terá índice HNSW — só
> busca exata. Os perfis atuais (`gemini` 3072, `qwen37` 1024, `bgem3` 1024)
> estão todos dentro do teto do `halfvec`.

### H3 — custo real medido (informativo)

`usage.prompt_tokens` por chamada de 1 texto curto: 4 tok (v4, kinfra-text),
19 tok (qwen3.7), 23 tok (kinfra-vl). Com os preços do `config.yaml`
(7,69e-08 a 1,1e-07 por token), a rodada completa de 24 checks custou
**< $0,0001**. Custo não é trava (política do usuário) — é só registro.

## Isolamento verificado

```
tabelas de sonda criadas:
  chunks_novai_kinfra_text_embedding_0_6b
  chunks_novai_kinfra_text_embedding_4b
  chunks_novai_kinfra_vl_embedding_2b
  chunks_novai_kinfra_vl_embedding_8b
  chunks_novai_qwen3_7_text_embedding
  chunks_novai_text_embedding_v4

tabelas do RAG (intocadas):
  chunks        836
  chunks_qwen37 17937
  chunks_bgem3  705
```

Nenhuma tabela do RAG foi criada, alterada ou lida pela sonda. As tabelas
`chunks_novai_*` **não** estão no registry `ingest/profiles.py` e **não** são
alcançáveis por `ingest/search.py`.

## Logs e segredos

- `reports/logs/2026-10-17-novai-embedding.jsonl` — 60 linhas (24 checks × 2
  rodadas + 12 do smoke inicial), sucesso **e** falha.
- Aceite de redação: `grep -E '"(authorization|api_key|x-api-key)"' <jsonl>` =
  **0 hits** ✅.
- Nenhuma chave impressa em nenhum momento; o jsonl passa por `redact_obj`.

## Verificação final

| item | resultado |
| --- | --- |
| `RAG_PROFILE=qwen37 .venv/bin/python -m pytest` | **753 passed** |
| `eval.recall --gate` | **r@8 0,933 ≥ 0,900** (MRR 0,714) |
| jsonl sem segredo | **0 hits** |
| Invariante 7 | preservado (nenhum `novai-*` em rag-chat/fallbacks/embeddings) |
| Tabelas do RAG | intocadas |

## Artefatos

- `eval/novai_test.py` — `embedding_input`, `pgvector_table_for`,
  `pgvector_column_type`, `pgvector_ddl`, `verdict_pgvector_roundtrip`,
  `run_embedding_pgvector`, `_parse_pgvector_text`; flag `--pgvector`;
  `run_one(..., pgvector=, connect=)`.
- `eval/tests/test_novai_test.py` — +26 testes offline (veredito puro, DDL,
  fallback de tipo, runner com conexão fake, erro de banco ⇒ fail sem exceção).
- `reports/novai-test-matrix.csv` — linhas dos 6 grupos de embedding atualizadas.
