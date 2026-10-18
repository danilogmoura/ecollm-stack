# S122-R — Reteste Detalhado: Descrição, Motivação e Implicações

**Data:** 2026-10-18  
**Referência:** `2026-10-18-novai-reteste-s122-r-evidencia.md` (vereditos)  
**Dossier:** `2026-10-18-novai-erros-servidor-dossie-completo.md` (contexto técnico)

---

## Como ler este documento

Cada seção responde a três perguntas:

1. **O que é?** — descrição técnica do teste e do erro subjacente
2. **Por que testar?** — motivação para incluir este teste no reteste S122-R
3. **O que implica?** — consequências práticas do resultado para o stack, catálogo e usuários

---

## P-3 — Reasoning Accounting Inconsistente

### O que é?

Testa se os modelos que suportam *thinking/reasoning* reportam métricas consistentes entre `reasoning_chars` (caracteres do raciocínio) e `reasoning_tokens` (tokens contabilizados). A API OpenAI estendida pela NovAI retorna ambos os campos no objeto `usage` da resposta. O teste verifica se `reasoning_chars > 0` implica `reasoning_tokens > 0` e se a proporção é plausível (~2–5 chars/token para CJK/latim misto).

Modelos testados: `minimax-m2.7-fast`, `minimax-m2.5-fast`, `step-5-preview-fast`.

### Por que testar?

P-3 foi identificado como fail ativo na matriz (`novai-test-matrix.csv`). Se o accounting de reasoning estiver errado, **o custo real de inferência é subestimado** — tokens de reasoning consomem GPU mas não são cobrados corretamente. Além disso, sistemas de monitoramento que usam `usage.reasoning_tokens` para dashboards de custo mostram dados incorretos.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| 🔴 FAIL persistente (3/3) | Os 3 modelos continuam reportando reasoning inconsistente. `step-5-preview-fast` é o pior: 133 chars mas **0 tokens** — accounting completamente quebrado. |
| Para o stack | Nosso proxy repassa o `usage` do gateway sem modificar. Se quisermos accounting correto, precisamos calcular tokens localmente (tokenizer por modelo) ou ignorar o campo. |
| Para usuários | Custos reportados em dashboards LiteLLM (`spend_logs`) podem estar subestimados para estes modelos. Não afeta funcionalidade, apenas visibilidade financeira. |
| Ação | Ticket NovAI com evidência dos 3 modelos. Considerar adicionar estimativa local de reasoning tokens no proxy como workaround. |

---

## P-7a — wan2.2-t2i-flash Timeout Determinístico

### O que é?

Testa geração de imagem via modelo `wan2.2-t2i-flash` através do proxy LiteLLM. O teste envia um prompt simples e espera a resposta dentro do timeout configurado (120s). O harness `novai_test.py --image` faz polling da URL retornada.

### Por que testar?

P-7a foi classificado como "transiente" no dossier original, mas a suspeita era de que poderia ser um bug estrutural no upstream Wanx/Alibaba. Retestar com N=3 determina se é intermitente (retry resolve) ou determinístico (bug permanente).

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| 🔴 FAIL determinístico (3/3 timeout 120s) | Não é transiente. O gateway aceita a requisição, encaminha ao upstream, e **nunca recebe resposta** — timeout exato em 120s em todas as tentativas. Espaçamento de ~131s entre runs confirma que o gateway espera até o limite antes de falhar. |
| Para o stack | A rota `novai-image-wan2.2-t2i-flash` no `litellm/config.yaml` está efetivamente morta. Qualquer chamada consome 120s de recurso (conexão aberta, thread bloqueada) antes de falhar. |
| Para usuários | Geração de imagem via wan2.2 flash **não funciona**. Usuários que tentarem receberão timeout após 2 minutos. |
| Ação | Remover ou desabilitar a rota `wan2.2-t2i-flash` no config.yaml. Reportar à NovAI como bug upstream Wanx. Manter `wan2.5-t2i-preview` (funciona, pass na matriz). |

---

## P-5 — FastAPI Error Envelope (Divergência de Contrato)

### O que é?

Testa se erros HTTP retornados pelo gateway seguem o formato OpenAI `{error: {message, type, code}}` ou o formato FastAPI nativo `{detail: "..."}`. O teste `novai_contract.py --target both` envia uma requisição intencionalmente inválida (modelo inexistente `xxx-nao-existe-s117`) e compara o shape da resposta entre gateway direto e proxy LiteLLM.

### Por que testar?

SDKs OpenAI (Python, Node.js, Go) fazem parsing do campo `error.message` para extrair mensagens de erro legíveis. Se o gateway retorna `{detail}` em vez de `{error:{message}}`, o SDK pode: (a) lançar exceção genérica sem mensagem útil, (b) falhar silenciosamente, ou (c) tratar como erro de rede. O proxy LiteLLM deveria normalizar o envelope.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| 🔴 Gateway diverged, Proxy pass | O gateway retorna FastAPI `{detail}` para erros 400/404. O proxy LiteLLM **corrige automaticamente** para o shape OpenAI `{error:{message}}`. |
| Para o stack | Enquanto usarmos o proxy, o problema é mitigado. Chamadas diretas ao gateway (sem proxy) quebram clientes OpenAI-compatíveis. |
| Para usuários | Via proxy: experiência normal, erros legíveis. Via gateway direto: mensagens de erro confusas ou exceções não-tratadas. |
| Ação | Documentar que chamadas diretas ao gateway NÃO são OpenAI-compatíveis para erros. Ticket NovAI para padronizar envelope. Prioridade média (proxy mitiga). |

---

## S115 — Error Sweep Dual-Target (Consistência de Envelopes)

### O que é?

Varredura completa de todos os modelos do catálogo (110 por alvo × 2 alvos × 2 tipos de erro = 440 checks). Para cada modelo, envia duas requisições inválidas: uma que gera HTTP 400 (parâmetro faltando) e outra que gera HTTP 404 (modelo inexistente). Verifica se o envelope de erro é consistente dentro de cada alvo.

### Por que testar?

S115 valida que o comportamento de erro é **previsível e uniforme**. Se alguns modelos retornassem OpenAI-shape e outros FastAPI-shape dentro do mesmo alvo, seria impossível escrever tratamento de erro genérico. Também detecta regressões: se um modelo que antes retornava envelope correto passar a retornar errado, indica mudança no upstream.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| ✅ 440/440 pass | Comportamento de erro é 100% consistente. Gateway sempre usa FastAPI para 404 e OpenAI para 400. Proxy sempre normaliza para OpenAI. |
| Para o stack | Tratamento de erro genérico funciona. Não há regressão desde o último sweep (17/10). |
| Para usuários | Erros são previsíveis. Retry logic e error handling funcionam conforme esperado. |
| Ação | Nenhuma. Manter sweep periódico (semanal) como health check. |

---

## P-6 — Tools Stream Assimetria (Content Antes de Tool Calls)

### O que é?

Testa se, durante streaming com `tools` habilitado, o modelo emite `delta.content` (texto livre) **antes** de emitir `delta.tool_calls`. A convenção OpenAI é: quando o modelo decide chamar uma ferramenta, o stream deve conter **apenas** `delta.tool_calls` com `finish_reason=tool_calls`, sem `delta.content` concomitante.

Modelos testados: `glm-4.6v`, `glm-5`, `minimax-m3`, `kimi-k2.8-preview`, `hunyuan-t1-vision`.

### Por que testar?

P-6 afeta **agentes de IA** (Copilot, Roo Code, LangChain) que processam streams de tool calls. Se o modelo "fala" antes de chamar a ferramenta, o agente pode: (a) mostrar texto espúrio ao usuário antes da ação, (b) interpretar o texto como resposta final e ignorar o tool call, (c) duplicar conteúdo (texto + resultado da ferramenta).

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| 🔴 FAIL parcial (3/5) | `glm-4.6v`, `minimax-m3`, `kimi-k2.8-preview` falam antes de tool_calls. `glm-5` e `hunyuan-t1-vision` são conformes. |
| Para o stack | Agentes que usam estes modelos precisam de mitigação client-side: bufferizar `delta.content` e descartar se `tool_calls` aparecer depois. O Roo Code já tem essa lógica parcialmente. |
| Para usuários | Em modelos afetados, o chat pode mostrar "pensamento em voz alta" antes da ação da ferramenta. Não quebra funcionalidade, mas degrada UX. |
| Ação | Mitigação client-side (strip content pré-tool-call). Ticket NovAI para os 3 upstreams afetados (ZhiPu GLM-4.6v, MiniMax-M3, Moonshot Kimi-K2.8). Prioridade alta (afeta agentes). |

---

## P-7b — minimax-text-01 Stream Sem `[DONE]`

### O que é?

Testa se o stream SSE do modelo `minimax-text-01` termina com o evento terminal `data: [DONE]`, conforme especificação OpenAI. O teste conta eventos `data:` e verifica presença de `[DONE]` no final do stream.

### Por que testar?

O SDK OpenAI Python usa `[DONE]` como sinal de fim de stream. Sem ele, o iterador do SDK pode: (a) pendurar esperando mais dados, (b) levantar `StopIteration` prematuramente perdendo o último chunk, (c) tratar como erro de framing. É o mesmo tipo de bug que a NovAI já corrigiu anteriormente (S41→S42, framing `\n` vs `\n\n`).

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| 🔴 FAIL confirmado (events=8, done=0) | Stream encerra abruptamente sem `[DONE]`. Non-stream funciona normalmente. |
| Para o stack | SDKs OpenAI podem hang ou perder dados no último chunk. Nosso proxy repassa o stream raw — não adiciona `[DONE]` sintético. |
| Para usuários | Aplicações que usam streaming com `minimax-text-01` podem travar ou mostrar resposta incompleta. Non-stream não é afetado. |
| Ação | Ticket NovAI (bug upstream MiniMax). Workaround possível: proxy detectar fim de stream e injetar `[DONE]` sintético. Prioridade média (afeta só 1 modelo). |

---

## P-7d — Vídeo minimax-video-v2.3-fast Task FAILED

### O que é?

Testa geração de vídeo assíncrona via modelo `minimax-video-v2.3-fast`. O fluxo é: POST cria task → polling GET até estado terminal (`succeeded` com `video_url` ou `failed`). O harness `novai_test.py --video` faz polling automático com backoff.

### Por que testar?

P-7d foi identificado como fail no sweep anterior. Geração de vídeo é funcionalidade premium — falhas aqui têm impacto direto em usuários pagantes. Diferenciar entre "timeout lento" (SLA longo) e "rejeição imediata" (bug) é crítico para triagem.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| 🔴 FAIL (task FAILED em 1 poll) | Task falha **imediatamente** — não é timeout nem SLA longo. O upstream MiniMax rejeita a requisição na criação. Task ID: `1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5`. |
| Para o stack | Rota de vídeo está inoperante. Polling não ajuda — a falha é na criação, não no processamento. |
| Para usuários | Geração de vídeo via MiniMax V2.3 Fast **não funciona**. Erro imediato. |
| Ação | Ticket NovAI com task_id para investigação upstream. Considerar remover rota do catálogo até fix. Verificar se outras variantes (`minimax-video-*`) funcionam. |

---

## P-7e — 3D hy-3d-3.1 Quota Esgotada

### O que é?

Testa geração de modelo 3D via `hy-3d-3.1` (Tencent Hunyuan). Mesmo fluxo assíncrono de vídeo: POST → polling.

### Por que testar?

P-7e foi originalmente classificado como bug nosso (rota GET subpath incorreta no proxy). Após fix da rota, retestamos para verificar se o proxy agora funciona corretamente.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| ⚪ HTTP 402 (quota esgotada) | **Não é bug de software.** A Tencent Hunyuan esgotou a quota gratuita e billing pós-pago não está habilitado na conta NovAI. O proxy funciona corretamente — repassa o 402 do upstream. |
| Para o stack | Rota proxy está correta. O problema é financeiro/contratual, não técnico. |
| Para usuários | Geração 3D via Hunyuan indisponível até quota ser renovada ou billing habilitado. |
| Ação | Reclassificar de 🔴 para ⚪ (billing). Notificar equipe sobre necessidade de habilitar postpaid billing na conta Tencent Hunyuan. Adicionar nota no catálogo. |

---

## E-429 — ZhiPu Rate Limiting (glm-4.6v-flash / glm-4.7-flash)

### O que é?

Testa se modelos da família ZhiPu GLM respondem com HTTP 429 (rate limit) sob carga leve (3 requisições espaçadas 10s). Modelos testados: `glm-4.6v-flash` e `glm-4.7-flash`.

### Por que testar?

E-429 foi classificado como "intermitente" — às vezes funciona, às vezes 429. Retestar com N=3 determina se a situação melhorou, piorou ou permaneceu igual. Rate limiting persistente torna o modelo inutilizável para produção.

### O que implica?

### glm-4.6v-flash

| Resultado | Implicação |
|-----------|------------|
| 🔴 PERSISTENTE (3/3 HTTP 429) | **Piorou.** De intermitente passou a 100% fail. O upstream ZhiPu pode ter reduzido quota ou o modelo está sob carga crônica. |
| Para o stack | Modelo inutilizável. Manter na rotação de tráfego desperdiça requests e aumenta latência percebida. |
| Ação | **Remover da rotação imediatamente.** Marcar como 🔴 persistente no catálogo. Não rotear tráfego para este ID. |

### glm-4.7-flash

| Resultado | Implicação |
|-----------|------------|
| 🟡 Intermitente (1/3 pass) | Igual ao reteste anterior. Funciona ocasionalmente. |
| Para o stack | Utilizável com retry/backoff. Não remover da rotação, mas considerar peso menor no load balancing. |
| Ação | Monitorar. Se persistir por >7 dias, considerar reduzir peso no catálogo. |

---

## P-7c — mimo-v2.6-pro ConnectionError Intermitente

### O que é?

Testa se `mimo-v2.6-pro` completa chamadas tools-stream sem `ConnectionError`. Anteriormente classificado como intermitente (upstream derrubava conexão sob tools/stream). Teste adicional de visão com `max_tokens≥512` também incluído.

### Por que testar?

P-7c era o único erro classificado como "intermitente de transporte" que poderia ter sido resolvido por mudanças no upstream (deploy, scaling, fix de rede). Retestar determina se a estabilidade melhorou.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| ✅ RESOLVIDO (3/3 pass) | O upstream MiMo estabilizou. Tools-stream funciona consistentemente com `[DONE]` presente. |
| Para o stack | Modelo pode ser promovido de 🟡 para ✅ na matriz. Retry ainda recomendado como boa prática, mas não mais obrigatório. |
| Para usuários | `mimo-v2.6-pro` agora é confiável para uso com ferramentas e streaming. |
| Ação | **Marcar como RESOLVIDO.** Remover do backlog de erros ativos. Atualizar matriz para `pass`. |

---

## Passthrough Smoke (Vídeo + 3D)

### O que é?

Testa se as rotas passthrough do proxy (`/novai/video`, `/novai/3d`) aceitam requisições e retornam task IDs válidos com status `queued`. Não testa conclusão da task — apenas a submissão.

### Por que testar?

Valida que a infraestrutura de proxy para endpoints assíncronos está operacional. Se o passthrough quebrar, nenhum modelo de vídeo/3D funciona independente do upstream.

### O que implica?

| Resultado | Implicação |
|-----------|------------|
| ✅ 2/2 pass | Rotas funcionam. Tasks enfileiradas com sucesso em ambos os endpoints. |
| Para o stack | Infraestrutura proxy saudável. Falhas de vídeo/3D são upstream, não nossas. |
| Ação | Nenhuma. Health check básico funcionando. |

---

## Matriz de Decisão Rápida

| Error ID | Status Pós-Reteste | Ação Imediata | Prioridade |
|----------|---------------------|---------------|------------|
| P-3 | 🔴 Persistente | Ticket NovAI | Alta |
| P-7a | 🔴 Determinístico | Remover rota wan2.2 | Alta |
| P-5 | 🔴 Confirmado | Documentar + ticket | Média (proxy mitiga) |
| S115 | ✅ Pass | Nenhuma | — |
| P-6 | 🔴 Parcial (3/5) | Mitigação client-side + ticket | Alta |
| P-7b | 🔴 Confirmado | Ticket NovAI + workaround | Média |
| P-7d | 🔴 Confirmado | Ticket NovAI com task_id | Alta |
| P-7e | ⚪ Billing | Habilitar postpaid | Baixa |
| E-429 (4.6v) | 🔴 Persistente | **Remover da rotação** | Urgente |
| E-429 (4.7) | 🟡 Intermitente | Monitorar | Baixa |
| P-7c | ✅ Resolvido | Atualizar matriz | — |

---

*Documento complementar ao relatório de evidências. Para dados brutos, ver `reports/logs/retest-2026-10-18-v2/`.*
