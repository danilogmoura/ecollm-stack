# Dossiê completo — TODOS os erros do lado do servidor (NovAI) + Planejamento do reteste

**Data:** 2026-10-18 (S122)
**Escopo:** TODAS as famílias de teste da trilha NovAI — chat, chat-fast,
embedding, image, TTS, ASR, vídeo/3D (passthrough), tools (S119), contrato de
shape (S117), sweep de contrato de erro (S115) e inventário/roteabilidade.
**Método de atribuição:** dual-target (gateway direto `aiapi-pro.com` vs proxy
LiteLLM `:4000`). Divergência proxy≠gateway ⇒ bug NOSSO; falha igual nos dois ⇒
**erro do servidor** (gateway NovAI ou upstream). Este dossiê cataloga somente a
segunda categoria (bugs nossos aparecem na §4 só para completeness de estado).
**Fontes primárias:** `reports/novai-test-matrix.csv` (157 linhas),
`reports/2026-10-17-novai-tool-scan.csv` (212 linhas), relatórios de fase F–L,
`2026-10-17-novai-contrato-api.md`, `2026-10-17-novai-s115-sweep-contrato-erro.md`,
`2026-10-18-novai-consolidado-falhas-servidor.md`,
`2026-10-18-novai-reteste-falhas-evidencia.md` (vereditos S120 já incorporados).

> **Relação com os relatórios anteriores:** o `consolidado` (01:39 UTC) e o
> `reteste-evidencia` (04:40 UTC) de 2026-10-18 cobrem partes deste escopo. Este
> documento é a **síntese única e exaustiva** pedida pelo usuário: um catálogo por
> família com evidência e veredito, mais um **plano de reteste prospectivo**
> (§6) — os anteriores documentam o reteste *passado* (S120), este planeja o
> *próximo*.

---

## 0. Sumário executivo

| Fonte de teste | Cobertura | Erros de servidor encontrados |
| --- | --- | --- |
| Matriz funcional (`novai-test-matrix.csv`) | 157 linhas (103 pass / 4 fail / 34 skip / 16 removed) | **4 fails ativos** + 16 ids mortos (removed) + 9 rotas sem thinking-OFF (skip forçado) |
| Tool-scan S119/S120 (212 modelos × non-stream/stream) | 212 linhas, 112 irregulares | **~19 chat-like com erro HTTP**, 15 ignoram tools, 22+ falam junto no stream, 1 stream sem `[DONE]` |
| Contrato de shape S117 (12 checks dual-target) | 11 pass / 1 diverged | **1 divergência**: envelope de erro FastAPI `{detail}` no gateway |
| Sweep de erro S115 (440 checks) | 440/440 pass (com normalizador) | **0 fails** — mas confirmou envelope inconsistente (2 shapes: OpenAI vs `{detail}`) |
| Vídeo/3D assíncrono (Fase J + S120) | 2 famílias | **`minimax-video-v2.3-fast` FAILED sistemático**; `hy-3d-3.1` inocentado (bug de polling era nosso) |
| Embedding/TTS/ASR | 6+9+2 linhas | **0 fails ativos** (todos transitórios fechados ou bugs nossos de fixture corrigidos) |

**Total de erros de servidor distintos catalogados: 12** (P-1 … P-7f + classe D

+ tools-stream + sem-tool-call), dos quais **0 são corrigíveis localmente** —
todos exigem ação da NovAI/upstream ou mitigação client-side nossa.

Estado pós-reteste S120 (janela 03:00–04:40 UTC de 2026-10-18): matriz
**103 pass / 4 fail / 34 skip / 16 removed**; os 4 fails são
`minimax-m2.7-fast`, `minimax-m2.5-fast`, `step-5-preview-fast` (contabilidade de
reasoning, P-3) e `wan2.2-t2i-flash` (timeout determinístico ~60,5 s, P-7a).

---

## 1. Catálogo de erros por família de teste

Legenda de status: 🔴 ativo (reproduz) · 🟡 intermitente · ⚪ permanente/aceito ·
✅ corrigido/refutado (não é mais erro de servidor).

### 1.1 Família `chat` / `chat-fast` (matriz)

#### P-3 🔴 — Contabilidade de reasoning quebrada + thinking-OFF ignorado (3 fails ATIVOS da matriz)

+ **Grupos:** `novai-minimax-m2.7-fast`, `novai-minimax-m2.5-fast`, `novai-step-5-preview-fast`.
+ **Sintoma:** rota `-fast` (thinking OFF por convenção S44) retorna HTTP 200 com
  `reasoning_content` preenchido — o upstream **ignora o pedido de desligar** — e
  `usage.reasoning_tokens` zerado ou subcontabilizado.
+ **Evidência (reteste S120, `reports/logs/2026-10-18-novai-proxy.jsonl`):**

  | grupo | baseline 17/10 | reteste 18/10 |
  | --- | --- | --- |
  | `minimax-m2.7-fast` | chars=79 tok=0 | **fail** chars=108 tok=28 |
  | `minimax-m2.5-fast` | chars=90 tok=23 | **fail** chars=134 tok=29 |
  | `step-5-preview-fast` | chars=123 tok=0 | **fail** chars=161 tok=0 |
  As métricas mudam a cada run (não-determinismo do upstream), mas o fail é
  determinístico: 3/3 reproduzem em todas as corridas desde a Fase L.

- **Veredito S120:** CONFIRMADA. Erro duplo de contrato (comportamento +
  contabilidade) do gateway/upstream MiniMax e Step.
+ **Ação:** nenhuma local possível (já skipamos o veredito de thinking onde não
  há suporte; estes 3 **declaram** suporte e mentem). Candidato a ticket NovAI.

#### P-2 ⚪ — Kimi/ZhiPu: não existe mecanismo de thinking-OFF (9 rotas `-fast` em skip forçado + 2 extras)

+ **Grupos afetados (skip na matriz, 34 no total — 16 por esta causa + 17 não-reasoning + 1 glm-4.7):**
  `novai-kimi-k3-fast`, `k2.8-preview-fast`, `k2.7-code-fast`,
  `k2.7-code-highspeed-fast`, `k2.6-fast`, `k2.5-fast` (Moonshot) e
  `novai-glm-5.3-fast`, `glm-5.3-flash-fast`, `glm-5.3-flashx-fast`,
  `glm-5.2-fast`, `glm-5.1-fast`, `glm-5-fast`, `glm-5v-turbo-fast`,
  `glm-5-turbo-fast`, `glm-4.6v-fast`, `glm-4.6v-flash-fast`,
  `glm-4.1v-thinking-flash-fast`, `glm-4.7-flash-fast` (ZhiPu).
+ **Sintoma:** `thinking:{type:"disabled"}` → HTTP 400. Kimi: `"The request is
  invalid"` para qualquer valor ≠ `enabled`. ZhiPu glm-5.3*: `"该模型始终思考，
  不支持关闭思考；请使用 low、high 或 max"` — e `low` **não desliga** (medido e
  rejeitado na Fase L §3c: `glm-5.2-fast` com `low` → reasoning_tokens=112).
+ **Veredito S120:** CONFIRMADA; Kimi mais rígida que ZhiPu. `reasoning_effort:"low"`
  também é recusado pelo Kimi.
+ **Estado:** aceito como limitação permanente; harness faz `skip` (L3). A
  convenção "`-fast` = thinking OFF" não é universal — documentado.

#### P-4/A6 ✅ (REFINADO) — "Gateway ignora `extra_body.thinking`" era artefato de teste

+ **Histórico:** Fase F registrou A6: gateway aceitava `thinking:{type:disabled}`
  e silenciava (não repassava). O consolidado de 18/10 ainda listava como P-4.
+ **Veredito S120 (matriz 4 casos em `retest-2026-10-18/a6-thinking-forwarding.txt`):**
  `thinking:{type:"disabled"}` **na RAIZ do payload funciona** e desliga o
  reasoning. O que o gateway ignora é a chave literal `extra_body` — que é
  **desdobramento do SDK OpenAI**, não parte do protocolo. Curl cru enviando
  `{"extra_body":{...}}` aninhado = payload errado, leitura falsa.
+ **Estado:** NÃO é bug do gateway. Pendência apenas **documental**: corrigir a
  §2.4 do consolidado (feita neste dossiê). Harness já envia na raiz.

#### P-1 ⚪ — Catálogo anuncia 16 ids não-roteáveis (`404 "Model not exist"`)

+ **Sintoma:** `GET /v1/models` do gateway lista ids que o upstream (Alibaba
  Cloud) não serve: qualquer POST → `404 "Model not exist"`.
+ **Ids (removidos do nosso `config.yaml` no S114, 168→152 entradas):**
  `qwen3.6-max-preview`, `qwen3-max`, `qwen3-coder-plus`, `qwen-vl-max`,
  `qwen3-vl-flash`, `qwen-omni-turbo` (×2 rotas ON/OFF cada = 12 grupos chat) +
  `qwen-image`, `qwen-image-plus` (image) + `qwen-tts-latest`, `qwen-tts` (tts).
+ **Evidência:** Fase L classe A; S114 (relatório
  `2026-10-17-novai-s114-remocao-grupos-mortos.md`); reteste S120
  (`envelope-erro.txt`: probes continuam 404).
+ **Veredito S120:** CONFIRMADA (persiste). Nosso proxy já não os anuncia; o
  gateway sim.
+ **Ação:** manter filtro de roteabilidade ativo no nosso catálogo; ticket NovAI
  (remover/reativar ids). Reaparecem no tool-scan como parte dos "63 erro".

#### E-429 🟡 — 429 de carga ZhiPu (`该模型当前访问量过大`)

+ **Grupos:** `novai-glm-4.7-flash` (Fase L, classe E), `novai-glm-4.6v-flash`
  (reteste S120 §6: 429 imediato com e sem tools — `glm46vflash-429.txt`).
+ **Sintoma:** HTTP 429 com mensagem de carga do upstream, às vezes com
  `Retry-After`. Transitório por natureza, mas **reincidente** desde 17/10.
+ **Estado:** harness tem retry com backoff (L5) e honra `Retry-After`. Monitorar
  antes de rotacionar tráfego para esses ids. Não é defeito — é capacidade.

### 1.2 Família `image`

#### P-7a 🔴 — `wan2.2-t2i-flash`: timeout DETERMINÍSTICO ~60,5 s (fail ativo da matriz)

+ **Sintoma:** geração de imagem nunca completa; conexão cai por volta de 60,5 s
  consistentemente. Via proxy manifesta como `Read timed out (120s)` no harness
  (o gateway corta antes, em ~60 s, e o proxy fica pendurado).
+ **Evidência S120 (`wan22-transitorio.txt`):** 3× proxy + gateway direto
  (HTTP/2, HTTP/1.1, prompt EN) — **todas** cortam em ~60,5 s. Controle `wan2.5`
  no mesmo minuto: OK. A classificação anterior "transitório/RemoteDisconnected"
  foi **corrigida**: é determinístico.
+ **Veredito:** corte fixo de timeout no gateway para este modelo (ou upstream
  Wan quebrado). Não-corrigível localmente.
+ **Ação:** remover/isolar `wan2.2-t2i-flash` do catálogo ativo (candidato a
  remoção como no S114) + ticket NovAI. Único fail da família image (11/12 pass).

#### F-param ✅ — `size`/`voice` inválidos por modelo (era bug NOSSO de harness)

+ `seedream-image-v5.0-lite` rejeita o `size` default; `qwen3-tts-flash` rejeita
  a voz default. Corrigido com overrides por modelo (L4: `IMAGE_SIZE_OVERRIDES`,
  `TTS_VOICE_OVERRIDES`). Não é erro de servidor — registrado aqui para
  completeness (classe F da Fase L).

### 1.3 Famílias `embedding`, `tts`, `asr`

+ **Embedding: 0 erros de servidor.** 6/6 pass (Fase H: 24/24 checks verdes,
  gateway == proxy, round-trip pgvector distância 0,0). Re-run 18/10: 4/4 pass
  (`2026-10-18-novai-embedding.jsonl`). Achados H1/H2 eram bugs NOSSOS
  (input multimodal, halfvec 4000 dims) — corrigidos.
+ **TTS: 0 fails ativos.** 9 pass; os 3 fails da Fase L eram classe A (ids
  mortos, P-1) e classe F (voz, nosso) — resolvidos.
+ **ASR: 0 fails ativos.** `wand-asr-v1` teve fail transitório (200 com
  `text:""`) na Fase L; **passou no re-teste de 17/10** (matriz: pass, nota
  S115). O outro caso (`text:""` com tom puro) era fixture NOSSO (G1) — corrigido
  com fixture de fala real.

### 1.4 Famílias `video` / `3d` (passthrough assíncrono)

#### P-7d 🔴 — `minimax-video-v2.3-fast`: task FAILED sistemática em <12 s

+ **Sintoma:** `POST /v1/video/generations` aceita (`status:queued`), mas o
  poll 1 já retorna `{"status":"failed","upstream_status":"Fail","video_url":null,
  "usage":{"total_tokens":0}}` — sem nenhum campo explicando o motivo.
+ **Evidência S120:** 2 tasks independentes (prompt curto PT + prompt rico
  PT-BR), ambas failed (`minimax-video.txt`, `minimax-video-retry.txt`, payload
  bruto em `minimax-video-failed-full.json`). Já vinha da Fase J (achado J4).
+ **Nota de procedimento (achado do reteste):** caminho correto é
  `POST /v1/video/generations`; `/v1/videos/generations` → 405.
+ **Veredito:** upstream MiniMax vídeo quebrado para este id. Não-corrigível.
+ **Ação:** abrir ticket NovAI com os 2 task_ids do laudo.
+ **Contraste:** `minimax-video-h3` SUCCEEDED com artefato (Fase J) — a família
  funciona; o id `-v2.3-fast` não.

#### hy-3d-3.1 ✅ REFUTADO — "task nunca-terminal" era bug NOSSO de polling

+ **Leitura anterior (Fase J/L):** tasks 3D ficavam `processing` para sempre.
+ **Veredito S120 (`hy3d.txt`, `hy3d-task1-final.json`, `hy3d-final.json`,
  `hy3d-proxy.txt`):** as tasks **completam** em ~10–13 min (`succeeded`,
  `model_url` .glb assinado no Tencent COS). O falso positivo era nosso: a regra
  de passthrough tem `include_subpath:false`, então `GET /novai/3d/<id>` via
  proxy → `{"detail":"Not Found"}` — o poll nunca atravessava.
+ **Ação NOSSA (não é erro de servidor):** habilitar rota GET de subpath no
  passthrough **ou** documentar "polling de vídeo/3D é sempre direto no gateway".
  SLA observado: ≈10–13 min.

#### J3 🟡 — `cogvideox-flash` instável (Fase J)

+ Task de vídeo com falhas intermitentes no upstream (registrado na Fase J).
  Fora da matriz ativa (passthrough é genérico). Monitorar se entrar em uso.

### 1.5 Contrato de shape (S117) e de erro (S115)

#### P-5 🔴 — Envelope de erro inconsistente no gateway (única divergência S117)

+ **Sintoma:** erros próprios do gateway (rota/validação FastAPI) voltam como
  `{"detail": "..."}` em vez do envelope OpenAI `{"error":{...}}`; e
  `GET /v1/models/<id>` inexistente devolve **HTML** (não JSON).
+ **Evidência:** S117 live 11/12 (1 diverged: `error.openai` no gateway,
  `contrato-api.md` linha 31); reteste S120 `envelope-erro.txt` (probes POST/GET
  nos 2 alvos, inclui o HTML 404). O sweep S115 (440/440) só passa porque o
  normalizador aceita os **2 shapes** — sem ele, 110/110 `error_404` do gateway
  reprovariam. Erros originados no upstream são repassados em formato OpenAI;
  os gerados no gateway não.
+ **Impacto real:** clientes OpenAI-compat (SDK, Roo, Copilot) que fazem
  `err["error"]["message"]` quebram com KeyError nos erros do gateway.
+ **Ação:** pedir à NovAI envelope OpenAI-compliant em erros próprios + JSON em
  `GET /v1/models/<id>`. Nosso proxy já normaliza (LiteLLM traduz para o
  envelope OpenAI) — clientes do proxy não sofrem.

#### S115 error sweep ✅ — 440/440 pass

+ Nenhum erro de servidor novo no sweep de contrato de erro (4 famílias × 5
  cenários × 2 alvos, com normalizador). Confirma P-5 como única divergência de
  envelope. `reports/logs/2026-10-17-novai-error-sweep.jsonl` (440 registros).

### 1.6 Tools / function-calling (S119/S120 — 212 modelos)

Distribuição medida (CSV `2026-10-17-novai-tool-scan.csv`, 212 linhas):
non-stream: 103 conforme / 63 erro / 31 content+tool / 15 sem tool_call.
Stream: 108 só-tools / 63 erro / 20 fala-antes / 15 sem tool_call / 6 fala-depois.
**112 linhas irregulares.** Decomposição por causa:

#### T-1 ⚪ — 44 dos 63 "erro" são ruído esperado (modelos não-chat)

+ O inventário do gateway lista mídia (vídeo/3D/música/imagem/tradução/role) que
  não fala `/v1/chat/completions`: `doubao-seedance/seedream`, `kling-video-*`,
  `vidu-*`, `pixverse-*`, `tripo-*`, `hy-3d-*`, `hy-video-*`, `minimax-video-*`,
  `minimax-music-*`, `hunyuan-role`, `hy-role`, `hy-mt2-lite`, `qwen-mt-plus`,
  `qwen-omni-turbo`, `qwen-vl-ocr`-family etc. Erro é o comportamento correto.
  **Não é defeito** — é o inventário misto do gateway (ver P-1).

#### T-2 🔴 — ~19 chat-like com erro HTTP no tool-scan (maioria = P-1 + E-429 + P-7)

+ **Gateway:** `qwen-vl-max`, `qwen3-coder-plus`, `qwen3-max`, `qwen3-vl-flash`,
  `qwen3.6-max-preview` (= P-1, ids mortos, 404) · `glm-4.6v-flash`,
  `glm-4.7-flash` (= E-429, carga ZhiPu) · `mimo-v2.6-pro` (= P-7b,
  ConnectionError de transporte).
+ **Proxy:** os mesmos `novai-qwen*` (espelho de P-1 antes do S114 — o sweep
  rodou com a matriz antiga) + `novai-glm-4.7-flash-fast` (non-stream erro,
  stream OK = E-429 intermitente).
+ **Nenhum erro NOVO** — todos decompõem em P-1/E-429/P-7 já catalogados.

#### P-6 🔴 — Stream fala junto com tool_calls (divergência OpenAI em escala)

+ **Sintoma:** no stream com tools, o gateway emite `delta.content` (texto
  "pensando em voz alta"/resposta parcial) **antes** (20 casos) ou **depois**
  (6 casos) dos `delta.tool_calls`, com `finish_reason=tool_calls`. A convenção
  OpenAI é: stream de tool call não carrega `content`.
+ **Modelos (gateway, confirmação S120 `tools-stream-assimetria.txt`):**
  fala-antes: `glm-4.6v`, `glm-5`, `glm-5.2`, `glm-5v-turbo`, `minimax-m3`,
  `kimi-k2.8-preview` (+ variantes `-fast`/proxy: `glm-4.6v-flash`,
  `glm-5.1`, `glm-5.2-fast`, `kimi-k3`, `minimax-m3-fast` …).
  fala-depois: `hunyuan-t1-vision`, `hunyuan-turbos-vision-video` (×2 alvos).
  Non-stream com `content` + `tool_calls` na mesma resposta: 31 linhas
  (mesmas famílias + `hy4-preview`, `step-5-preview`, `kimi-k3`,
  `deepseek-v4-pro-fast`, `minimax-m2.7`).
+ **Impacto:** clientes que concatenam `delta.content` mostram "fala" espúria
  antes da ferramenta (Roo/Copilot: texto + tool call duplicados).
+ **Ação:** mitigação client-side (concatenar content+tool_calls, strip
  `<think>`) ou reclamação formal à NovAI (GLM-4.6v/GLM-5/MiniMax-M3 são os
  piores). Args sempre parseáveis (0 inválidos) — a divergência é de sequência,
  não de shape.

#### T-3 ⚪ — 15 modelos IGNORAM a ferramenta (sem tool_call, respondem em texto)

+ `glm-4.1v-thinking-flash` (×3 rotas: emite `<think>`/`<answer>` em texto,
  finish `length`/`stop`), `hy-mt2-plus`/`hy-mt2-pro` (×4, um emite
  `<tool_call>` **como texto**), `hy-vision-2.0-instruct` (×3, recusa: "não
  tenho acesso à ferramenta"), `qwen3.5-ocr` (×3, devolve JSON em code-block).
+ **Leitura:** são modelos de visão/tradução/OCR que não implementam
  function-calling de verdade — o gateway aceita o payload `tools` e o upstream
  responde em texto. Limítrofe entre "não-suporta" (P-1 de capacidades) e
  divergência de contrato. **Ação:** marcar no catálogo como sem-tools; não
  rotear agentes para eles.

#### P-7b 🔴 — `minimax-text-01`: stream sem `[DONE]`

+ **Sintoma:** SSE encerra sem o evento terminal `data: [DONE]` (events=8,
  done=False). Non-stream conforme.
+ **Evidência S120:** `minimax-done.txt` (contagem [DONE]=0) +
  `minimax-stream-final.txt` (últimos eventos). Reproduziu nas 2 corridas do
  sweep (17/10) e no reteste (18/10).
+ **Impacto:** clientes que esperam `[DONE]` para fechar (SDK OpenAI faz) podem
  pendurar ou tratar como erro de framing. Parente do bug de framing `\n` vs
  `\n\n` que a NovAI já corrigiu (S41→S42, relatório
  `2026-10-14-novai-sse-streaming.md`).
+ **Ação:** reportar à NovAI (P-7b do consolidado).

#### P-7c 🟡 — `mimo-v2.6-pro`: ConnectionError intermitente + visão recuperada

+ **Tools:** `transport: ConnectionError` no sweep (17/10 e 18/10 no gateway).
+ **Visão (S120 `mimo-vision.txt`):** o fail de visão da Fase L foi
  **RECUPERADO** — precisa `max_tokens≥512` (escada 128/256/512 medida); com
  128 o upstream trunca e cai. Era leitura falsa de "modelo quebrado".
+ **Estado:** transporte continua instável (upstream derruba conexão sob
  tools/stream). Monitorar; retry cobre uso normal.

### 1.7 Inventário / roteabilidade

Coberto por P-1 (16 ids mortos) e T-1 (inventário mistura modalidades). O
`/v1/models` do gateway não é fonte confiável de roteabilidade — nosso proxy
filtra (S114) e o harness probeia (S97/S99).

---

## 2. Tabela mestra de erros de servidor (índice rápido)

| ID | Família | Severidade | Status | Corrigível por nós? | Evidência canônica |
| --- | --- | --- | --- | --- | --- |
| P-1 | chat/image/tts (inventário) | média | ⚪ permanente | filtro já ativo (S114) | `envelope-erro.txt`; relatório S114 |
| P-2 | chat-fast (Kimi/ZhiPu) | baixa | ⚪ aceita | skip no harness (L3) | probes §2 S120; Fase L classe B |
| P-3 | chat-fast (MiniMax/Step) | **alta** | 🔴 ativo (3 fails) | não | `2026-10-18-novai-proxy.jsonl` |
| P-4/A6 | chat (thinking fwd) | — | ✅ refutado | doc corrigida | `a6-thinking-forwarding.txt` |
| P-5 | contrato de erro | média | 🔴 ativo | proxy já normaliza | `contrato-shape.md`, `envelope-erro.txt` |
| P-6 | tools stream | **alta** | 🔴 ativo (22+ modelos) | mitigação client-side possível | `tools-stream-assimetria.txt`, CSV S119 |
| P-7a | image (`wan2.2-t2i-flash`) | **alta** | 🔴 ativo (1 fail) | isolar/remover rota | `wan22-transitorio.txt` |
| P-7b | chat stream (`minimax-text-01`) | média | 🔴 ativo | não | `minimax-done.txt` |
| P-7c | chat (`mimo-v2.6-pro`) | baixa | 🟡 intermitente | retry | CSV S119; `mimo-vision.txt` |
| P-7d | vídeo (`minimax-video-v2.3-fast`) | média | 🔴 ativo | não | `minimax-video-failed-full.json` |
| P-7e | 3D (`hy-3d-3.1`) | — | ✅ refutado (bug nosso) | **sim** (rota GET subpath) | `hy3d*.json/txt` |
| P-7f/E-429 | chat (ZhiPu flash) | baixa | 🟡 carga | retry/backoff (L5) | `glm46vflash-429.txt` |
| T-3 | tools (15 modelos) | baixa | ⚪ capacidade | marcar sem-tools no catálogo | CSV S119 linhas `sem_tool_call` |

Fails ATIVOS na matriz hoje: **4** = P-3 (×3) + P-7a (×1).

---

## 3. Erros que pareciam de servidor e NÃO eram (lições para o reteste)

Para não repetir falsos positivos no próximo ciclo:

1. **A6/P-4** — `extra_body` literal no curl cru ≠ protocolo; SDK desdobra na
   raiz. Sempre testar o payload **como o cliente real envia**.
2. **hy-3d-3.1** — poll via proxy com `include_subpath:false` → 404 nosso lido
   como "task perdida". Sempre confirmar falha assíncrona **direto no gateway**.
3. **mimo-v2.6-pro visão** — `max_tokens=128` truncava; "modelo quebrado" era
   parâmetro nosso. Escalonar parâmetros antes de condenar.
4. **wan2.2-t2i-flash** — classificado "transitório" sem medir repetição; 3+
   execuções mostraram corte determinístico de ~60,5 s. Transitório exige
   prova de intermitência (N≥3 com resultados mistos).
5. **ASR `text:""`** — fixture de tom puro não é fala; 200 com texto vazio era
   entrada inválida nossa.
6. **Classe C (17 "rota ON não emite reasoning")** — expectativa do harness, não
   defeito: modelo não-reasoning não tem par de thinking. Veredito correto: skip.

---

## 4. Falhas NOSSAS (não-servidor) — estado, para completeness

| Item | Estado |
| --- | --- |
| S112 cooldown 429 (`router_settings`) | ✅ corrigido |
| S113 `DEEPSEEK_API_KEY` 401 | ⏸️ decisão do usuário (fora do escopo NovAI) |
| Roo Code 401 (placeholder key) | ✅ corrigido (virtual key `roo-code-s115`) |
| Cache de modelos do Roo (168→152) | ⬜ refresh manual (P-9) |
| Polling 3D/vídeo via proxy (P-7e) | ⬜ abrir rota GET subpath no passthrough **ou** documentar poll direto |
| Logs do proxy perdidos em restart | ℹ️ P-12 opcional |
| Harness (H1/H2, G1/G2, I1/I2, J1/J2, K1, L2–L6, S115-fix, S117-fix) | ✅ todos corrigidos |

---

## 5. Critérios de atribuição usados (regra do jogo)

Um erro entra neste dossiê como "do lado do servidor" somente se:

1. **Reproduz nos dois alvos** (gateway direto E proxy) com o mesmo código/mensagem,
   **OU** reproduz só no gateway (proxy apenas repassa) — divergência proxy≠gateway
   com proxy pior = bug nosso, vai para §4;
2. **Não é explicado por parâmetro/fixture/harness nosso** (§3 — sempre escalonar
   `max_tokens`, `size`, `voice`, caminho de rota, e confirmar polling direto antes
   de condenar);
3. **Tem evidência crua** versionada em `reports/logs/` (jsonl/txt/json do probe),
   com URLs pré-assinadas redigidas (política GH013).

Classes de falha (convenção da trilha): A rota 404 · B contrato · C infra-pausa ·
D balance-pausa · E 429 (honrar `Retry-After`) · F timeout · G regressão de bug
conhecido · H NOSSO bug (fail-closed, corrigir) · I flaky (re-run N=3).

---

## 6. PLANEJAMENTO DO RETESTE (S122-R)

Objetivo: re-verificar todos os erros 🔴/🟡 do catálogo, detectar correções da
NovAI (o gateway já corrigiu o framing SSE uma vez — S41→S42), e fechar S115
quando os critérios forem atingidos.

### 6.0 Princípios

+ **Ordem:** barato/determinístico primeiro (ondas 1–2), caro/assíncrono depois
  (ondas 4–5). Cada onda só roda com a anterior verde ou com falha registrada.
+ **Dual-target sempre:** todo reteste de erro confirmado roda gateway + proxy
  (atribuição §5). Exceção: itens com veredito de proxy já conhecido.
+ **N=3 para intermitentes** (🟡): 3 execuções espaçadas ≥60 s; veredito
  "corrigido" exige 3/3 pass; "persiste" com 3/3 fail; misto = continua 🟡.
+ **Evidência:** gravar tudo em `reports/logs/retest-<DATA>/` (novo diretório por
  rodada), redigir URLs assinadas ANTES do `git add` (regex GH013 em bytes:
  `(q-ak=AKID[A-Za-z0-9]+|AKID[A-Za-z0-9]{20,})`).
+ **Custo:** cota NovAI unlimited (standard 60 rpm) → custo $0; orçamento de
  tempo ~2 h para as 5 ondas (tool-scan completo é a maior, ~50 min).
+ **Não repetir o que já respondeu:** se um item foi re-verificado há <24 h com
  evidência (S120), só re-rodar se houver **fato novo** (mudança anunciada da
  NovAI, novo fail, ou prazo da onda).

### Onda 1 — Fails ativos da matriz (P-3 ×3 + P-7a) · ~15 min · PRIORIDADE MÁXIMA

```bash
# P-3: os 3 grupos de contabilidade de reasoning (re-run cirúrgico por --id)
for g in novai-minimax-m2.7-fast novai-minimax-m2.5-fast novai-step-5-preview-fast; do
  RAG_PROFILE=qwen37 .venv/bin/python -m eval.novai_test --id "$g" --live --sleep 1.1
done
# P-7a: wan2.2-t2i-flash — 3× com timestamp (prova de determinismo/correção)
for i in 1 2 3; do
  RAG_PROFILE=qwen37 .venv/bin/python -m eval.novai_test --id novai-image-wan2.2-t2i-flash --live
  sleep 60
done
```

+ **Aceite P-3:** fail reproduz (chars>0 e tok≠chars) → mantém 🔴 e entra no
  ticket NovAI; OU reasoning_tokens coerente com reasoning_content em 3/3 →
  ✅ corrigido, matriz atualiza para pass.
+ **Aceite P-7a:** imagem retorna <60 s → ✅ corrigido; corte em ~60,5 s de novo
  → executar remoção/isolamento da rota (decisão pendente do consolidado §9.4) e
  marcar ⚪ permanente.
+ **Saída:** `reports/logs/retest-<DATA>/onda1-matrix.{jsonl,txt}` + atualização
  da `novai-test-matrix.csv` se houver mudança de status.

### Onda 2 — Contrato: shape + erro + thinking forwarding · ~10 min

```bash
.venv/bin/python -m eval.novai_contract --target both --live \
  --out reports/logs/retest-<DATA>/onda2-contrato.md
.venv/bin/python -m eval.novai_error_sweep --target both --sleep 0.3   # sempre live (sem flag --live)
```

+ **P-5:** aceite = 12/12 pass sem normalizador (gateway adotou envelope OpenAI)
  → ✅; senão mantém 🔴 (nosso proxy continua normalizando — impacto só em
  cliente direto do gateway).
+ **P-4/A6:** 1 probe de sanidade (thinking raiz em 1 modelo Kimi + 1 ZhiPu) só
  se o P-2 mudar; senão não re-rodar (refutado com evidência em 18/10).
+ **Saída:** `onda2-contrato.md` (tabela 12 checks) + jsonl do sweep.

### Onda 3 — Tools: assimetria de stream + `[DONE]` · ~20 min (cirúrgico, NÃO o sweep inteiro)

```bash
# O tool_scan NÃO tem flag de seleção por modelo (só --limit N primeiros).
# Cirúrgico = script ad-hoc (openai SDK / curl) nos 6 modelos-alvo:
#   glm-4.6v, glm-5, minimax-m3, kimi-k2.8-preview, hunyuan-t1-vision (P-6)
#   minimax-text-01 (P-7b: contar 'data: [DONE]' no SSE)
# gravando SSE cru em reports/logs/retest-<DATA>/onda3-tools.txt
# Re-sweep COMPLETO (só se houver fato novo — ver abaixo):
.venv/bin/python -m eval.novai_tool_scan --live --dump-responses --sleep 1.5
```

+ **P-6:** aceite = stream sem `delta.content` quando há `tool_calls` → ✅
  (remover mitigação client-side do backlog se implementada); senão mantém 🔴 e
  sobe prioridade da mitigação nossa.
+ **P-7b:** aceite = `data: [DONE]` presente no fim do stream do
  `minimax-text-01` em 3/3 → ✅; senão mantém 🔴 (ticket).
+ **Re-sweep completo (212 modelos, ~50 min):** SÓ se as ondas 1–3 detectarem
  mudança estrutural no gateway (ex.: P-5 corrigido ⇒ indício de release novo) —
  aí rodar `--live --dump-responses` inteiro e diffar o CSV contra 17/10.
+ **Saída:** `onda3-tools.txt` + jsonl por alvo.

### Onda 4 — Assíncronos: vídeo + 3D · ~30 min (maioria é espera de SLA)

```bash
# P-7d: task de vídeo com polling até estado terminal (harness Fase J):
.venv/bin/python -m eval.novai_test --video minimax-video-v2.3-fast --live
# P-7e (nosso): após o fix da rota GET subpath no passthrough:
.venv/bin/python -m eval.novai_test --3d hy-3d-3.1 --live
.venv/bin/python -m eval.novai_test --passthrough both --live   # smoke + registro na matriz
# Se o fix não tiver sido feito: poll manual DIRETO no gateway (curl), como no S120.
```

+ **P-7d:** aceite = task `succeeded` com `video_url` → ✅; `failed` em <12 s de
  novo → ⚪ permanente + ticket com task_id.
+ **P-7e:** pré-requisito = nossa rota de polling via proxy (item §4). Aceite =
  poll via proxy reflete o status do gateway (queued→processing→succeeded, SLA
  ~10–13 min). Sem o fix: NÃO re-rodar (veredito já é conhecido — 404 nosso).
+ **Saída:** `onda4-async/` com task_ids + payloads brutos (redigidos).

### Onda 5 — Intermitentes de carga/transporte (E-429, P-7c) · ~10 min, N=3

```bash
# glm-4.6v-flash + glm-4.7-flash: 3 chamadas espaçadas 60 s (com e sem tools)
# mimo-v2.6-pro: 3 chamadas tools-stream + 1 visão com max_tokens=512
```

+ **Aceite:** 3/3 sem 429/ConnectionError → 🟡→✅ (monitorar mesmo assim);
  qualquer fail → mantém 🟡. Se glm-4.6v-flash continuar 429 por >7 dias
  seguidos, propor no catálogo: não rotacionar tráfego para o id.

### 6.6 Regra de fechamento (herda S115)

O ciclo de reteste fecha quando:

1. fails ativos da matriz ≤ 2 **ou** reclassificados como permanentes (⚪) com
   ticket/decisão registrada;
2. cada 🔴 do catálogo tem veredito da rodada (corrigido / persiste / permanente);
3. evidência crua versionada em `reports/logs/retest-<DATA>/` (0 credenciais,
   validado com o regex GH013);
4. matriz `novai-test-matrix.csv` + consolidado atualizados no mesmo commit;
5. closeout padrão (RESULTADO no bloco S122 do backlog, INDEX, diário, commit+push FF).

### 6.7 Gatilhos para re-rodar fora de ciclo

+ Anúncio/mudança da NovAI (como o fix de framing S41→S42) → ondas 2+3.
+ Fail novo em uso real (Roo/Copilot/ingest) → onda cirúrgica do item.
+ Prazo: re-ciclo completo a cada 7 dias enquanto houver 🔴 (próximo sugerido:
  2026-10-25).

---

## 7. Mapa de evidências (arquivos canônicos)

| Erro | Evidência |
| --- | --- |
| P-1 | `retest-2026-10-18/envelope-erro.txt`; `2026-10-17-novai-s114-remocao-grupos-mortos.md` |
| P-2 | `retest-2026-10-18/` probes §2; `2026-10-17-novai-fase-l.md` §2 classe B/§3c |
| P-3 | `logs/2026-10-18-novai-proxy.jsonl`; `retest-2026-10-18/matrix-before.csv` |
| P-4/A6 | `retest-2026-10-18/a6-thinking-forwarding.txt` |
| P-5 | `retest-2026-10-18/contrato-shape.md`, `envelope-erro.txt`; `2026-10-17-novai-contrato-api.md` |
| P-6 | `retest-2026-10-18/tools-stream-assimetria.txt`; `2026-10-17-novai-tool-scan.{md,csv}` |
| P-7a | `retest-2026-10-18/wan22-transitorio.txt`; `logs/2026-10-18-novai-image.jsonl` |
| P-7b | `retest-2026-10-18/minimax-done.txt`, `minimax-stream-final.txt` |
| P-7c | `2026-10-17-novai-tool-scan.csv` (linha mimo); `retest-2026-10-18/mimo-vision.txt` |
| P-7d | `retest-2026-10-18/minimax-video{,-retry}.txt`, `minimax-video-failed-full.json` |
| P-7e | `retest-2026-10-18/hy3d{,-proxy,-final,-task1-final}.{txt,json}` |
| P-7f | `retest-2026-10-18/glm46vflash-429.txt` |
| T-1/T-2/T-3 | `2026-10-17-novai-tool-scan.{md,csv}` + dumps `logs/tool-scan-2026-10-17-{gateway,proxy}.jsonl` |
| S115 sweep | `logs/2026-10-17-novai-error-sweep.jsonl` (440 reg); `2026-10-17-novai-s115-sweep-contrato-erro.md` |
| Matriz | `novai-test-matrix.csv` (157 linhas) |
