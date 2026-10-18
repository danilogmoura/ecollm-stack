# S122-R — Reteste Completo: Evidências e Vereditos

**Data:** 2026-10-18T06:45Z  
**Executor:** Agente automatizado (Copilot)  
**Ambiente:** RAG_PROFILE=qwen37, gateway `https://aiapi-pro.com`, proxy `localhost:4000`  
**Evidências brutas:** `reports/logs/retest-2026-10-18-v2/`

---

## Resumo Executivo

| Error ID | Descrição | Veredito Anterior | Veredito Reteste | Mudança? |
|----------|-----------|-------------------|------------------|----------|
| P-3 | Reasoning accounting (chars/tokens) | 🔴 FAIL | 🔴 **FAIL persistente** (3/3) | Não |
| P-7a | wan2.2-t2i-flash timeout | 🔴 FAIL | 🔴 **FAIL determinístico** (3/3 timeout 120s) | Não |
| P-5 | FastAPI error envelope | 🔴 FAIL | 🔴 **FAIL confirmado** (gateway diverged) | Não |
| S115 | Error sweep dual-target | ✅ PASS | ✅ **PASS** (440/440) | Não |
| P-6 | Tools stream assimetria | 🔴 FAIL | 🔴 **FAIL parcial** (3/5 modelos) | Parcial |
| P-7b | minimax-text-01 sem [DONE] | 🔴 FAIL | 🔴 **FAIL confirmado** (events=8, done=0) | Não |
| P-7d | Vídeo task FAILED | 🔴 FAIL | 🔴 **FAIL confirmado** (task FAILED em 1 poll) | Não |
| P-7e | 3D hy-3d-3.1 | 🟡 | ⚪ **402 quota esgotada** (não é bug) | N/A |
| E-429 | ZhiPu load (glm-4.6v-flash) | 🟡 | 🔴 **PERSISTENTE** (3/3 HTTP 429) | Piorou |
| E-429 | ZhiPu load (glm-4.7-flash) | 🟡 | 🟡 **Intermitente** (1/3 pass) | Igual |
| P-7c | mimo-v2.6-pro intermitente | 🟡 | ✅ **RESOLVIDO** (3/3 pass) | Melhorou! |

**Mudanças significativas:**
- 🟢 **P-7c RESOLVIDO** — mimo-v2.6-pro agora funciona consistentemente
- 🔴 **E-429 glm-4.6v-flash PIOROU** — de intermitente para persistente (3/3 fail)
- ⚪ **P-7e** não é bug — quota Tencent Hunyuan esgotada (402 billing)

---

## Onda 1 — Fails Ativos da Matriz

### P-3: Reasoning Accounting (3 modelos)

**Evidência:** `onda1-p3.txt`

| Modelo | reasoning_chars | reasoning_tokens | Veredito |
|--------|----------------|-----------------|----------|
| minimax-m2.7-fast | 102 | 28 | ❌ FAIL |
| minimax-m2.5-fast | 118 | 31 | ❌ FAIL |
| step-5-preview-fast | 133 | 0 | ❌ FAIL |

**Veredito:** 🔴 **FAIL persistente**. Todos os 3 modelos continuam reportando reasoning_chars > 0 mas tokens inconsistentes (step-5-preview-fast tem 133 chars mas 0 tokens).

### P-7a: wan2.2-t2i-flash Timeout

**Evidência:** `onda1-p7a.txt`

| Run | Timestamp | Resultado |
|-----|-----------|-----------|
| 1 | 06:20:44 | ❌ Read timed out (read timeout=120) |
| 2 | 06:22:55 | ❌ Read timed out (read timeout=120) |
| 3 | 06:25:06 | ❌ Read timed out (read timeout=120) |

**Veredito:** 🔴 **FAIL determinístico**. 3/3 timeout exato em 120s. Espaçamento entre runs (~131s) confirma que o gateway espera até o timeout antes de falhar. Não é intermitente — é bug estrutural no upstream de imagem.

---

## Onda 2 — Contrato Shape + Error Sweep

### P-5: FastAPI Error Envelope (S117)

**Evidência:** `onda2-contrato.txt` + `onda2-contrato.md`

| Endpoint | Alvo | Status | Evidência |
|----------|------|--------|-----------|
| error.openai | gateway | **diverged** | FastAPI `{detail}` (HTTP 400) |
| error.openai | proxy | pass | OpenAI `{error:{message}}` (HTTP 400) |

Todos os outros endpoints (chat.completion, chat.completion.chunk, embeddings, images.generation, models.list) = **pass** em ambos os alvos.

**Veredito:** 🔴 **FAIL confirmado**. Gateway retorna envelope FastAPI `{detail}` em vez de OpenAI `{error:{message}}`. Proxy corrige o envelope corretamente. Divergência documentada.

### S115: Error Sweep Dual-Target

**Evidência:** `onda2-error-sweep.txt`

```
# resumo por (alvo, teste)
  gateway  error_400  env:openai=1 pass=110
  gateway  error_404  env:fastapi=1 pass=110
  proxy    error_400  env:openai=1 pass=110
  proxy    error_404  env:openai=1 pass=110

# envelopes observados
  gateway  {'fastapi': 1, 'openai': 1}
  proxy    {'openai': 2}

# 440 checks · 440 pass · 0 fail
```

**Veredito:** ✅ **PASS**. 440/440 checks passaram. Envelopes consistentes dentro de cada alvo (gateway usa FastAPI para 404, OpenAI para 400; proxy normaliza tudo para OpenAI).

---

## Onda 3 — Tools Stream Assimetria + [DONE]

### P-6: Tools Stream Assimetria (5 modelos)

**Evidência:** `onda3-tools.txt`

| Modelo | Events | Tool Calls | Content Antes? | Veredito |
|--------|--------|------------|----------------|----------|
| glm-4.6v | 55 | 2 | Sim (linha 77 < 105) | ❌ P-6 FAIL |
| glm-5 | 18 | 2 | Não | ✅ P-6 PASS |
| minimax-m3 | 13 | 3 | Sim (linha 3 < 17) | ❌ P-6 FAIL |
| kimi-k2.8-preview | 53 | 7 | Sim (linha 71 < 89) | ❌ P-6 FAIL |
| hunyuan-t1-vision | 5 | 3 | Não | ✅ P-6 PASS |

**Veredito:** 🔴 **FAIL parcial**. 3/5 modelos falam antes de emitir tool_calls no stream. glm-5 e hunyuan-t1-vision são conformes. A assimetria é dependente do upstream, não do gateway.

### P-7b: minimax-text-01 sem [DONE]

**Evidência:** `onda3-tools.txt` (seção minimax-text-01)

```
events=8 done=0 tool_calls=2 content_before=1
❌ P-7b FAIL ([DONE] ausente, events=8)
```

**Veredito:** 🔴 **FAIL confirmado**. Stream encerra sem `data: [DONE]` após 8 eventos. Clientes SDK OpenAI que esperam `[DONE]` para fechar podem hang ou perder o último chunk.

---

## Onda 4 — Assíncronos: Vídeo + 3D

### P-7d: Vídeo minimax-video-v2.3-fast

**Evidência:** `onda4-video.txt`

```
checks=1 pass=0 fail=1 skip=0
  ❌ [video] minimax-video-v2.3-fast :: video_task — id=1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5 task falhou (status=FAILED) polls=1
```

**Veredito:** 🔴 **FAIL confirmado**. Task falha imediatamente (1 poll). Não é timeout — é rejeição upstream. Ticket necessário com task_id.

### P-7e: 3D hy-3d-3.1

**Evidência:** `onda4-3d.txt`

```
❌ [3d] hy-3d-3.1 :: video_task — POST HTTP 402: {"error":{"message":"[Tencent Hunyuan (混元)] The free trial quota for the service has been exhausted and postpaid billing...
```

**Veredito:** ⚪ **Não é bug**. HTTP 402 = quota gratuita esgotada, billing pós-pago não habilitado. Fora do escopo de erro de software.

### Passthrough Smoke

**Evidência:** `onda4-passthrough.txt`

```
checks=2 pass=2 fail=0 skip=0
  ✅ [video-passthrough] /novai/video :: status=queued
  ✅ [3d-passthrough] /novai/3d :: status=queued
```

**Veredito:** ✅ Rotas passthrough funcionam corretamente em ambos os alvos.

---

## Onda 5 — Intermitentes E-429 + P-7c

### E-429: glm-4.6v-flash (ZhiPu Load)

**Evidência:** `onda5-intermitentes.txt`

| Run | Resultado |
|-----|-----------|
| 1 | ❌ HTTP 429 |
| 2 | ❌ HTTP 429 |
| 3 | ❌ HTTP 429 |

**Veredito:** 🔴 **PERSISTENTE** (piorou). De intermitente passou a 3/3 fail. Recomendação: remover glm-4.6v-flash da rotação de tráfego no catálogo.

### E-429: glm-4.7-flash (ZhiPu Load)

**Evidência:** `onda5-intermitentes.txt`

| Run | Resultado |
|-----|-----------|
| 1 | ❌ HTTP 429 |
| 2 | ✅ HTTP 200 |
| 3 | ❌ HTTP 429 |

**Veredito:** 🟡 **Intermitente** (igual). 1/3 pass. Monitorar; retry cobre uso normal.

### P-7c: mimo-v2.6-pro

**Evidência:** `onda5-intermitentes.txt`

| Run | Events | [DONE] | Resultado |
|-----|--------|--------|-----------|
| 1 | 19 | ✅ | ✅ HTTP 200 |
| 2 | 15 | ✅ | ✅ HTTP 200 |
| 3 | 15 | ✅ | ✅ HTTP 200 |

**Veredito:** ✅ **RESOLVIDO**. 3/3 pass com [DONE] presente. Falha intermitente anterior não se reproduz.

---

## Ações Recomendadas

### Imediatas (backlog)

1. **E-429 glm-4.6v-flash → UPGRADE para 🔴 persistente.** Remover da rotação de tráfego no catálogo novai. Não é mais intermitente.
2. **P-7c mimo-v2.6-pro → MARCAR COMO RESOLVIDO.** Remover do backlog de erros ativos.
3. **P-7e hy-3d-3.1 → RECLASSIFICAR como ⚪ (quota/billing).** Não é bug de software. Adicionar nota no catálogo sobre quota Tencent Hunyuan.

### Tickets NovAI (manter)

4. **P-3 reasoning accounting** — 3 modelos afetados, persistente.
5. **P-7a wan2.2-t2i-flash** — timeout determinístico 120s, bug upstream.
6. **P-5 error envelope** — gateway FastAPI vs OpenAI shape (proxy mitiga).
7. **P-6 tools stream** — 3/5 modelos falam antes de tool_calls.
8. **P-7b minimax-text-01** — stream sem [DONE].
9. **P-7d vídeo** — task FAILED imediata, ticket com task_id `1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5`.

### Monitoramento

10. **E-429 glm-4.7-flash** — ainda intermitente (1/3), retry cobre.

---

## Arquivos de Evidência

| Arquivo | Conteúdo |
|---------|----------|
| `onda1-p3.txt` | P-3 reasoning accounting (3 modelos) |
| `onda1-p7a.txt` | P-7a wan2.2 timeout (3 runs) |
| `onda2-contrato.txt` | P-5 contrato shape dual-target |
| `onda2-contrato.md` | Tabela detalhada S117 |
| `onda2-error-sweep.txt` | S115 error sweep 440/440 |
| `onda3-tools.txt` | P-6 + P-7b tools stream + SSE cru |
| `onda4-video.txt` | P-7d vídeo task FAILED |
| `onda4-3d.txt` | P-7e 3D HTTP 402 |
| `onda4-passthrough.txt` | Passthrough smoke 2/2 pass |
| `onda5-intermitentes.txt` | E-429 + P-7c N=3 |

---

*Relatório gerado automaticamente. Evidências brutas preservadas em `reports/logs/retest-2026-10-18-v2/`.*
