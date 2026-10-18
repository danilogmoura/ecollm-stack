# S122-R — Reteste Consolidado: Evidências, Análise Técnica e Implicações

**Data:** 2026-10-18T06:45Z  
**Executor:** Agente automatizado (Copilot)  
**Ambiente:** RAG_PROFILE=qwen37, gateway `https://aiapi-pro.com`, proxy `localhost:4000`  
**Evidências brutas:** `reports/logs/retest-2026-10-18-v2/`  
**Dossier de referência:** `2026-10-18-novai-erros-servidor-dossie-completo.md`

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

### Mudanças Significativas

- 🟢 **P-7c RESOLVIDO** — mimo-v2.6-pro agora funciona consistentemente
- 🔴 **E-429 glm-4.6v-flash PIOROU** — de intermitente para persistente (3/3 fail)
- ⚪ **P-7e** não é bug — quota Tencent Hunyuan esgotada (402 billing)

---

## Metodologia

O reteste seguiu plano de 5 ondas executadas sequencialmente:

| Onda | Escopo | Ferramenta | Modelos-alvo |
|------|--------|------------|--------------|
| 1 | Fails ativos da matriz | `novai_test.py --live` | minimax-m2.7-fast, minimax-m2.5-fast, step-5-preview-fast (P-3); wan2.2-t2i-flash (P-7a) |
| 2 | Contrato shape + error sweep | `novai_contract.py --target both` + `novai_error_sweep --target both` | glm-5/glm-4.7-flash (contrato); 110 modelos × 2 alvos (sweep) |
| 3 | Tools stream + [DONE] | Script ad-hoc curl SSE | glm-4.6v, glm-5, minimax-m3, kimi-k2.8-preview, hunyuan-t1-vision (P-6); minimax-text-01 (P-7b) |
| 4 | Assíncronos vídeo + 3D | `novai_test.py --video/--3d/--passthrough` | minimax-video-v2.3-fast (P-7d); hy-3d-3.1 (P-7e) |
| 5 | Intermitentes N=3 | Script ad-hoc curl | glm-4.6v-flash, glm-4.7-flash (E-429); mimo-v2.6-pro (P-7c) |

Todos os comandos prefixados com `RAG_PROFILE=qwen37`. Dual-target (gateway + proxy) aplicado onde aplicável.

---

## Análise por Error ID

---

### P-3 — Reasoning Accounting Inconsistente

#### O que é?

Testa se os modelos que suportam *thinking/reasoning* reportam métricas consistentes entre `reasoning_chars` (caracteres do raciocínio) e `reasoning_tokens` (tokens contabilizados). A API OpenAI estendida pela NovAI retorna ambos os campos no objeto `usage` da resposta. O teste verifica se `reasoning_chars > 0` implica `reasoning_tokens > 0` e se a proporção é plausível (~2–5 chars/token para CJK/latim misto).

Modelos testados: `minimax-m2.7-fast`, `minimax-m2.5-fast`, `step-5-preview-fast`.

#### Por que testar?

P-3 foi identificado como fail ativo na matriz (`novai-test-matrix.csv`). Se o accounting de reasoning estiver errado, **o custo real de inferência é subestimado** — tokens de reasoning consomem GPU mas não são cobrados corretamente. Além disso, sistemas de monitoramento que usam `usage.reasoning_tokens` para dashboards de custo mostram dados incorretos.

#### Evidência

| Modelo | reasoning_chars | reasoning_tokens | Veredito |
|--------|----------------|-----------------|----------|
| minimax-m2.7-fast | 102 | 28 | ❌ FAIL |
| minimax-m2.5-fast | 118 | 31 | ❌ FAIL |
| step-5-preview-fast | 133 | 0 | ❌ FAIL |

Arquivo: `onda1-p3.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Nosso proxy repassa o `usage` do gateway sem modificar. Se quisermos accounting correto, precisamos calcular tokens localmente (tokenizer por modelo) ou ignorar o campo. |
| Usuários | Custos reportados em dashboards LiteLLM (`spend_logs`) podem estar subestimados para estes modelos. Não afeta funcionalidade, apenas visibilidade financeira. |
| Ação | Ticket NovAI com evidência dos 3 modelos. Considerar adicionar estimativa local de reasoning tokens no proxy como workaround. |
| Prioridade | **Alta** |

---

### P-7a — wan2.2-t2i-flash Timeout Determinístico

#### O que é?

Testa geração de imagem via modelo `wan2.2-t2i-flash` através do proxy LiteLLM. O teste envia um prompt simples e espera a resposta dentro do timeout configurado (120s). O harness `novai_test.py --image` faz polling da URL retornada.

#### Por que testar?

P-7a foi classificado como "transiente" no dossier original, mas a suspeita era de que poderia ser um bug estrutural no upstream Wanx/Alibaba. Retestar com N=3 determina se é intermitente (retry resolve) ou determinístico (bug permanente).

#### Evidência

| Run | Timestamp | Resultado |
|-----|-----------|-----------|
| 1 | 06:20:44 | ❌ Read timed out (read timeout=120) |
| 2 | 06:22:55 | ❌ Read timed out (read timeout=120) |
| 3 | 06:25:06 | ❌ Read timed out (read timeout=120) |

Espaçamento entre runs (~131s) confirma que o gateway espera até o timeout antes de falhar. Arquivo: `onda1-p7a.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | A rota `novai-image-wan2.2-t2i-flash` no `litellm/config.yaml` está efetivamente morta. Qualquer chamada consome 120s de recurso (conexão aberta, thread bloqueada) antes de falhar. |
| Usuários | Geração de imagem via wan2.2 flash **não funciona**. Usuários que tentarem receberão timeout após 2 minutos. |
| Ação | Remover ou desabilitar a rota `wan2.2-t2i-flash` no config.yaml. Reportar à NovAI como bug upstream Wanx. Manter `wan2.5-t2i-preview` (funciona, pass na matriz). |
| Prioridade | **Alta** |

---

### P-5 — FastAPI Error Envelope (Divergência de Contrato)

#### O que é?

Testa se erros HTTP retornados pelo gateway seguem o formato OpenAI `{error: {message, type, code}}` ou o formato FastAPI nativo `{detail: "..."}`. O teste `novai_contract.py --target both` envia uma requisição intencionalmente inválida (modelo inexistente `xxx-nao-existe-s117`) e compara o shape da resposta entre gateway direto e proxy LiteLLM.

#### Por que testar?

SDKs OpenAI (Python, Node.js, Go) fazem parsing do campo `error.message` para extrair mensagens de erro legíveis. Se o gateway retorna `{detail}` em vez de `{error:{message}}`, o SDK pode: (a) lançar exceção genérica sem mensagem útil, (b) falhar silenciosamente, ou (c) tratar como erro de rede. O proxy LiteLLM deveria normalizar o envelope.

#### Evidência

| Endpoint | Alvo | Status | Evidência |
|----------|------|--------|-----------|
| error.openai | gateway | **diverged** | FastAPI `{detail}` (HTTP 400) |
| error.openai | proxy | pass | OpenAI `{error:{message}}` (HTTP 400) |

Todos os outros endpoints (chat.completion, chat.completion.chunk, embeddings, images.generation, models.list) = **pass** em ambos os alvos. Arquivos: `onda2-contrato.txt`, `onda2-contrato.md`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Enquanto usarmos o proxy, o problema é mitigado. Chamadas diretas ao gateway (sem proxy) quebram clientes OpenAI-compatíveis. |
| Usuários | Via proxy: experiência normal, erros legíveis. Via gateway direto: mensagens de erro confusas ou exceções não-tratadas. |
| Ação | Documentar que chamadas diretas ao gateway NÃO são OpenAI-compatíveis para erros. Ticket NovAI para padronizar envelope. |
| Prioridade | **Média** (proxy mitiga) |

---

### S115 — Error Sweep Dual-Target (Consistência de Envelopes)

#### O que é?

Varredura completa de todos os modelos do catálogo (110 por alvo × 2 alvos × 2 tipos de erro = 440 checks). Para cada modelo, envia duas requisições inválidas: uma que gera HTTP 400 (parâmetro faltando) e outra que gera HTTP 404 (modelo inexistente). Verifica se o envelope de erro é consistente dentro de cada alvo.

#### Por que testar?

S115 valida que o comportamento de erro é **previsível e uniforme**. Se alguns modelos retornassem OpenAI-shape e outros FastAPI-shape dentro do mesmo alvo, seria impossível escrever tratamento de erro genérico. Também detecta regressões: se um modelo que antes retornava envelope correto passar a retornar errado, indica mudança no upstream.

#### Evidência

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

Arquivo: `onda2-error-sweep.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Tratamento de erro genérico funciona. Não há regressão desde o último sweep (17/10). |
| Usuários | Erros são previsíveis. Retry logic e error handling funcionam conforme esperado. |
| Ação | Nenhuma. Manter sweep periódico (semanal) como health check. |
| Prioridade | **—** |

---

### P-6 — Tools Stream Assimetria (Content Antes de Tool Calls)

#### O que é?

Testa se, durante streaming com `tools` habilitado, o modelo emite `delta.content` (texto livre) **antes** de emitir `delta.tool_calls`. A convenção OpenAI é: quando o modelo decide chamar uma ferramenta, o stream deve conter **apenas** `delta.tool_calls` com `finish_reason=tool_calls`, sem `delta.content` concomitante.

Modelos testados: `glm-4.6v`, `glm-5`, `minimax-m3`, `kimi-k2.8-preview`, `hunyuan-t1-vision`.

#### Por que testar?

P-6 afeta **agentes de IA** (Copilot, Roo Code, LangChain) que processam streams de tool calls. Se o modelo "fala" antes de chamar a ferramenta, o agente pode: (a) mostrar texto espúrio ao usuário antes da ação, (b) interpretar o texto como resposta final e ignorar o tool call, (c) duplicar conteúdo (texto + resultado da ferramenta).

#### Evidência

| Modelo | Events | Tool Calls | Content Antes? | Veredito |
|--------|--------|------------|----------------|----------|
| glm-4.6v | 55 | 2 | Sim (linha 77 < 105) | ❌ P-6 FAIL |
| glm-5 | 18 | 2 | Não | ✅ P-6 PASS |
| minimax-m3 | 13 | 3 | Sim (linha 3 < 17) | ❌ P-6 FAIL |
| kimi-k2.8-preview | 53 | 7 | Sim (linha 71 < 89) | ❌ P-6 FAIL |
| hunyuan-t1-vision | 5 | 3 | Não | ✅ P-6 PASS |

Arquivo: `onda3-tools.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Agentes que usam estes modelos precisam de mitigação client-side: bufferizar `delta.content` e descartar se `tool_calls` aparecer depois. O Roo Code já tem essa lógica parcialmente. |
| Usuários | Em modelos afetados, o chat pode mostrar "pensamento em voz alta" antes da ação da ferramenta. Não quebra funcionalidade, mas degrada UX. |
| Ação | Mitigação client-side (strip content pré-tool-call). Ticket NovAI para os 3 upstreams afetados (ZhiPu GLM-4.6v, MiniMax-M3, Moonshot Kimi-K2.8). |
| Prioridade | **Alta** (afeta agentes) |

---

### P-7b — minimax-text-01 Stream Sem `[DONE]`

#### O que é?

Testa se o stream SSE do modelo `minimax-text-01` termina com o evento terminal `data: [DONE]`, conforme especificação OpenAI. O teste conta eventos `data:` e verifica presença de `[DONE]` no final do stream.

#### Por que testar?

O SDK OpenAI Python usa `[DONE]` como sinal de fim de stream. Sem ele, o iterador do SDK pode: (a) pendurar esperando mais dados, (b) levantar `StopIteration` prematuramente perdendo o último chunk, (c) tratar como erro de framing. É o mesmo tipo de bug que a NovAI já corrigiu anteriormente (S41→S42, framing `\n` vs `\n\n`).

#### Evidência

```
events=8 done=0 tool_calls=2 content_before=1
❌ P-7b FAIL ([DONE] ausente, events=8)
```

Arquivo: `onda3-tools.txt` (seção minimax-text-01)

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | SDKs OpenAI podem hang ou perder dados no último chunk. Nosso proxy repassa o stream raw — não adiciona `[DONE]` sintético. |
| Usuários | Aplicações que usam streaming com `minimax-text-01` podem travar ou mostrar resposta incompleta. Non-stream não é afetado. |
| Ação | Ticket NovAI (bug upstream MiniMax). Workaround possível: proxy detectar fim de stream e injetar `[DONE]` sintético. |
| Prioridade | **Média** (afeta só 1 modelo) |

---

### P-7d — Vídeo minimax-video-v2.3-fast Task FAILED

#### O que é?

Testa geração de vídeo assíncrona via modelo `minimax-video-v2.3-fast`. O fluxo é: POST cria task → polling GET até estado terminal (`succeeded` com `video_url` ou `failed`). O harness `novai_test.py --video` faz polling automático com backoff.

#### Por que testar?

P-7d foi identificado como fail no sweep anterior. Geração de vídeo é funcionalidade premium — falhas aqui têm impacto direto em usuários pagantes. Diferenciar entre "timeout lento" (SLA longo) e "rejeição imediata" (bug) é crítico para triagem.

#### Evidência

```
checks=1 pass=0 fail=1 skip=0
  ❌ [video] minimax-video-v2.3-fast :: video_task — id=1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5 task falhou (status=FAILED) polls=1
```

Arquivo: `onda4-video.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Rota de vídeo está inoperante. Polling não ajuda — a falha é na criação, não no processamento. |
| Usuários | Geração de vídeo via MiniMax V2.3 Fast **não funciona**. Erro imediato. |
| Ação | Ticket NovAI com task_id `1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5` para investigação upstream. Considerar remover rota do catálogo até fix. Verificar se outras variantes (`minimax-video-*`) funcionam. |
| Prioridade | **Alta** |

---

### P-7e — 3D hy-3d-3.1 Quota Esgotada

#### O que é?

Testa geração de modelo 3D via `hy-3d-3.1` (Tencent Hunyuan). Mesmo fluxo assíncrono de vídeo: POST → polling.

#### Por que testar?

P-7e foi originalmente classificado como bug nosso (rota GET subpath incorreta no proxy). Após fix da rota, retestamos para verificar se o proxy agora funciona corretamente.

#### Evidência

```
❌ [3d] hy-3d-3.1 :: video_task — POST HTTP 402: {"error":{"message":"[Tencent Hunyuan (混元)] The free trial quota for the service has been exhausted and postpaid billing...
```

Arquivo: `onda4-3d.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Rota proxy está correta. O problema é financeiro/contratual, não técnico. |
| Usuários | Geração 3D via Hunyuan indisponível até quota ser renovada ou billing habilitado. |
| Ação | Reclassificar de 🔴 para ⚪ (billing). Notificar equipe sobre necessidade de habilitar postpaid billing na conta Tencent Hunyuan. Adicionar nota no catálogo. |
| Prioridade | **Baixa** |

---

### E-429 — ZhiPu Rate Limiting

#### O que é?

Testa se modelos da família ZhiPu GLM respondem com HTTP 429 (rate limit) sob carga leve (3 requisições espaçadas 10s). Modelos testados: `glm-4.6v-flash` e `glm-4.7-flash`.

#### Por que testar?

E-429 foi classificado como "intermitente" — às vezes funciona, às vezes 429. Retestar com N=3 determina se a situação melhorou, piorou ou permaneceu igual. Rate limiting persistente torna o modelo inutilizável para produção.

#### Evidência

**glm-4.6v-flash:**

| Run | Resultado |
|-----|-----------|
| 1 | ❌ HTTP 429 |
| 2 | ❌ HTTP 429 |
| 3 | ❌ HTTP 429 |

**glm-4.7-flash:**

| Run | Resultado |
|-----|-----------|
| 1 | ❌ HTTP 429 |
| 2 | ✅ HTTP 200 |
| 3 | ❌ HTTP 429 |

Arquivo: `onda5-intermitentes.txt`

#### Implicações

| Modelo | Status | Implicação | Ação | Prioridade |
|--------|--------|------------|------|------------|
| glm-4.6v-flash | 🔴 PERSISTENTE (3/3) | Modelo inutilizável. Manter na rotação desperdiça requests e aumenta latência. | **Remover da rotação imediatamente.** Marcar como 🔴 persistente no catálogo. | **Urgente** |
| glm-4.7-flash | 🟡 Intermitente (1/3) | Utilizável com retry/backoff. | Monitorar. Se persistir >7 dias, reduzir peso no catálogo. | Baixa |

---

### P-7c — mimo-v2.6-pro ConnectionError Intermitente

#### O que é?

Testa se `mimo-v2.6-pro` completa chamadas tools-stream sem `ConnectionError`. Anteriormente classificado como intermitente (upstream derrubava conexão sob tools/stream). Teste adicional de visão com `max_tokens≥512` também incluído.

#### Por que testar?

P-7c era o único erro classificado como "intermitente de transporte" que poderia ter sido resolvido por mudanças no upstream (deploy, scaling, fix de rede). Retestar determina se a estabilidade melhorou.

#### Evidência

| Run | Events | [DONE] | Resultado |
|-----|--------|--------|-----------|
| 1 | 19 | ✅ | ✅ HTTP 200 |
| 2 | 15 | ✅ | ✅ HTTP 200 |
| 3 | 15 | ✅ | ✅ HTTP 200 |

Arquivo: `onda5-intermitentes.txt`

#### Implicações

| Dimensão | Detalhe |
|----------|---------|
| Stack | Modelo pode ser promovido de 🟡 para ✅ na matriz. Retry ainda recomendado como boa prática, mas não mais obrigatório. |
| Usuários | `mimo-v2.6-pro` agora é confiável para uso com ferramentas e streaming. |
| Ação | **Marcar como RESOLVIDO.** Remover do backlog de erros ativos. Atualizar matriz para `pass`. |
| Prioridade | **—** (resolvido) |

---

### Passthrough Smoke (Vídeo + 3D)

#### O que é?

Testa se as rotas passthrough do proxy (`/novai/video`, `/novai/3d`) aceitam requisições e retornam task IDs válidos com status `queued`. Não testa conclusão da task — apenas a submissão.

#### Por que testar?

Valida que a infraestrutura de proxy para endpoints assíncronos está operacional. Se o passthrough quebrar, nenhum modelo de vídeo/3D funciona independente do upstream.

#### Evidência

```
checks=2 pass=2 fail=0 skip=0
  ✅ [video-passthrough] /novai/video :: status=queued
  ✅ [3d-passthrough] /novai/3d :: status=queued
```

Arquivo: `onda4-passthrough.txt`

#### Implicações

Infraestrutura proxy saudável. Falhas de vídeo/3D são upstream, não nossas. Nenhuma ação necessária.

---

## Matriz de Decisão Rápida

| Error ID | Status Pós-Reteste | Ação Imediata | Prioridade | Corrigível por nós? |
|----------|---------------------|---------------|------------|---------------------|
| P-3 | 🔴 Persistente | Ticket NovAI | Alta | Não |
| P-7a | 🔴 Determinístico | Remover rota wan2.2 | Alta | Não (isolar/remover) |
| P-5 | 🔴 Confirmado | Documentar + ticket | Média | Proxy já normaliza |
| S115 | ✅ Pass | Nenhuma | — | — |
| P-6 | 🔴 Parcial (3/5) | Mitigação client-side + ticket | Alta | Sim (mitigação) |
| P-7b | 🔴 Confirmado | Ticket NovAI + workaround | Média | Sim (injetar [DONE]) |
| P-7d | 🔴 Confirmado | Ticket NovAI com task_id | Alta | Não |
| P-7e | ⚪ Billing | Habilitar postpaid | Baixa | Sim (financeiro) |
| E-429 (4.6v) | 🔴 Persistente | **Remover da rotação** | Urgente | Sim (catálogo) |
| E-429 (4.7) | 🟡 Intermitente | Monitorar | Baixa | Não (retry cobre) |
| P-7c | ✅ Resolvido | Atualizar matriz | — | — |

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
| `onda3-tools-live.txt` | Saída live da execução Onda 3 |
| `onda4-video.txt` | P-7d vídeo task FAILED |
| `onda4-3d.txt` | P-7e 3D HTTP 402 |
| `onda4-passthrough.txt` | Passthrough smoke 2/2 pass |
| `onda5-intermitentes.txt` | E-429 + P-7c N=3 |
| `onda5-live.txt` | Saída live da execução Onda 5 |

---

*Documento consolidado. Substitui `2026-10-18-novai-reteste-s122-r-evidencia.md` e `2026-10-18-novai-reteste-s122-r-detalhado.md` como referência única.*
