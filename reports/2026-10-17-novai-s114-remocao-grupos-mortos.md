# S114 — Remoção dos 16 grupos mortos do catálogo NovAI

**Data:** 2026-10-17
**Escopo:** executar a opção (a) da decisão deixada aberta em L1 (§3g da Fase L):
remover do `litellm/config.yaml` os 16 grupos cujo `upstream_id` o provider
**nunca serve** (404 permanente), e reconciliar o resto do stack com a nova
contagem.
**Custo:** zero (cota NovAI unlimited, modo standard 60 rpm).

---

## 1. Motivação

A Fase L (§3g) mediu que os 16 grupos de classe A devolvem
`404 [Alibaba Cloud] Model not exist` **mesmo chamados direto no gateway, sem o
proxy**, enquanto o controle positivo (`qwen3.8-max`, `qwen3-coder-flash`,
`qwen-plus`) responde 200 no mesmo instante. Conclusão: o `config.yaml` estava
correto — o gateway anuncia em `/v1/models` ids que o provider não roteia.

Um `model_name` que sempre devolve 404 é pior que ausência: o cliente descobre o
problema em runtime. Decisão: **remover**.

---

## 2. O que foi removido

### Chat (12 grupos = 6 upstreams × ON/OFF)

| Upstream | Grupos |
| --- | --- |
| `qwen3.6-max-preview` | `novai-qwen3.6-max-preview`, `-fast` |
| `qwen3-max` | `novai-qwen3-max`, `-fast` |
| `qwen3-coder-plus` | `novai-qwen3-coder-plus`, `-fast` |
| `qwen-vl-max` | `novai-qwen-vl-max`, `-fast` |
| `qwen3-vl-flash` | `novai-qwen3-vl-flash`, `-fast` |
| `qwen-omni-turbo` | `novai-qwen-omni-turbo`, `-fast` |

### Image (2)

`novai-image-qwen-image`, `novai-image-qwen-image-plus`

### TTS (2)

`novai-tts-qwen-tts-latest`, `novai-tts-qwen-tts`

**Total: 16 grupos.** Cada bloco removido deixou um comentário `S114` no
`config.yaml` no ponto onde estava, para preservar a rastreabilidade da decisão.

---

## 3. Arquivos alterados

| Arquivo | Mudança |
| --- | --- |
| `litellm/config.yaml` | 16 entradas removidas (168 → **152** entradas em `model_list`); cabeçalhos `IMAGE (14 upstreams)` → `(12)` e `TTS / MUSIC (11 upstreams)` → `(9)`; 4 blocos de comentário `S114` |
| `eval/cache_report.py` | 6 chaves órfãs removidas de `PRICE_PER_MTOKEN` (os 6 upstreams de chat) |
| `README.md` | contagens corrigidas: **55 upstreams de chat × ON/OFF = 110 grupos**, **139 ids NovAI**, tabela por modalidade (chat 55, image 12, tts 9, embed 6, asr 2) |
| `eval/tests/test_novai_inventory.py` | `test_real_config_counts_locked` travado em 139/55/55/6/12/9/2 (antes 155/61/61/6/14/11/2) |
| `reports/novai-test-matrix.csv` | 16 linhas marcadas `removed` com nota S114 (evidência 404 preservada) |

### Aritmética do catálogo

```
chat   55 upstreams × 2 (ON/OFF) = 110
embed   6
image  12
tts     9
asr     2
------------------------------------
NovAI ids                        139
+ grupos locais (ollama/rag)      13
------------------------------------
total no proxy                   152
```

---

## 4. Validação

| Verificação | Resultado |
| --- | --- |
| `yaml.safe_load(config.yaml)` | OK |
| `grep` dos 16 ids no config | só linhas de comentário |
| pares ON/OFF de chat | `base 55 / chat 110`, `base sem par: []`, `fast sem base: []` |
| `pytest -q` | **833 passed in 11.67s** |
| Invariante 7 | `rag-chat: ['rag-chat']`, `fallbacks: [{'rag-chat': ['qwen3:4b-instruct-2507']}]` — nenhum `novai-*` |
| Proxy recriado | `docker compose up -d --force-recreate litellm` |
| `GET /v1/models` | **total ids: 152**, `mortos ainda listados: []` |

---

## 5. Sweep de chat pós-remoção

```bash
RAG_PROFILE=qwen37 .venv/bin/python -m eval.novai_test --family chat --live --sleep 1.1
```

Cobertura: **110/110 grupos de chat**, todos presentes na matriz.

### Matriz final (157 linhas)

| Status | Linhas |
| --- | --- |
| pass | **101** |
| skipped | **26** |
| removed | **16** |
| fail | **14** |
| **total** | **157** |

### Os 14 fails restantes — todos de upstream, nenhum nosso

| Classe | Grupos | Causa |
| --- | --- | --- |
| B — Kimi/ZhiPu sem modo off (9) | `novai-kimi-k2.8-preview-fast`, `-k2.7-code-fast`, `-k2.7-code-highspeed-fast`, `-k2.6-fast`, `-k2.5-fast`, `novai-glm-5.3-fast`, `novai-glm-5.3-flash-fast`, `novai-glm-5-turbo-fast`, `novai-glm-5.3-flashx-fast` | `HTTP 400` — upstream rejeita `thinking:{type:disabled}`; não existe modo off |
| D — contabilidade de reasoning (3) | `novai-minimax-m2.7-fast`, `novai-minimax-m2.5-fast`, `novai-step-5-preview-fast` | `reasoning_chars>0` mas `reasoning_tokens=0` (ou parcial) |
| G — rede / resposta vazia (2) | `novai-image-wan2.2-t2i-flash`, `novai-asr-wand-asr-v1` | `RemoteDisconnected` / `text: ''` |

**Nenhum fail é defeito do harness ou do nosso stack.**

### Os 26 skips

17 de chat (modelos não-reasoning cuja rota ON não emite reasoning — falso
positivo do harness, corrigido em L2) + 9 de chat-fast (Kimi/ZhiPu sem modo off,
corrigido em L3).

---

## 6. Observações

- **`eval/novai_test.py` não foi alterado.** `TTS_VOICE_OVERRIDES` ainda cita
  `novai-tts-qwen-tts` / `-latest`, mas é só lookup de dict — inofensivo.
- **`eval/tests/test_novai_test.py` não foi alterado.** O teste de
  `image_size_for("novai-image-qwen-image")` usa string literal, independente do
  config.
- **`reports/logs/2026-10-17-novai-chat.jsonl`** acumula execuções antigas (408
  linhas para 110 grupos); a análise por grupo usa a **última** ocorrência.
- **Gap do gateway permanece:** `/v1/models` do NovAI continua anunciando os 16
  ids. Nós paramos de anunciá-los no proxy; o gateway não.

---

## 7. Conclusão

O catálogo do proxy agora só anuncia rotas que respondem. A matriz reflete a
realidade: 101 pass, 26 skip justificado, 16 removed, 14 fail de upstream. O
único item acionável por nós (L1) está fechado.
