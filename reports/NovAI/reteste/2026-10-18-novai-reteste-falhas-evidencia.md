# S120 — Reteste empírico de TODAS as falhas NovAI (evidência crua)

Data: **2026-10-18** (janela ~03:00–04:40 UTC). Alvo: gateway `https://aiapi-pro.com`
e proxy LiteLLM `http://localhost:4000`. Credenciais via `.env`.

Escopo: cada falha/pendência documentada em
`reports/2026-10-18-novai-consolidado-falhas-servidor.md` (P-1…P-7 + A6) foi
**re-executada ao vivo hoje**, com comprovante bruto salvo em
`reports/logs/retest-2026-10-18/` (um arquivo por classe, citado seção a seção).
Matriz antes/depois: `matrix-before.csv` (backup) vs `reports/novai-test-matrix.csv`
(157 linhas: 103 pass / 4 fail / 34 skip / 16 removed).

## Resumo dos vereditos

| # | Falha | Veredito do reteste | Evidência |
| --- | ------- | --------------------- | ----------- |
| P-1 | Catálogo anuncia modelos não-roteáveis | **CONFIRMADA** (persiste) | `envelope-erro.txt`, probes §1 |
| P-2 | Kimi/ZhiPu sem thinking-OFF | **CONFIRMADA** (Kimi mais rígida que ZhiPu) | probes §2 |
| P-3 | Contabilidade de reasoning (classe D) | **CONFIRMADA** (3/3 falham de novo, métricas mudam a cada run) | `2026-10-18-novai-proxy.jsonl` |
| P-4/A6 | Gateway ignora `thinking:disabled` | **REFINADA — não é falha do gateway**: era artefato de colocação do payload (`extra_body` literal na raiz). Gateway honra `thinking:{type:"disabled"}` quando chega na RAIZ. | `a6-thinking-forwarding.txt` |
| P-5 | Envelope de erro não-OpenAI no gateway | **CONFIRMADA** (FastAPI `{detail}`; GET `/v1/models/<x>` devolve HTML) | `envelope-erro.txt`, S117 |
| P-6 | tools+stream: modelo fala antes do tool_call | **CONFIRMADA** em glm-4.6v/glm-5/minimax-m3; kimi-k3 e deepseek-v4-flash limpos | `tools-stream-assimetria.txt` |
| P-7a | `wan2.2-t2i-flash` "transitório" | **NÃO é transitório — determinístico**: gateway corta conexão em ~60,5 s exatos (HTTP/2 e HTTP/1.1, PT e EN); controle `wan2.5-t2i-preview` = 200 em 14,8 s no mesmo endpoint | `wan22-transitorio.txt` |
| P-7b | `minimax-text-01` stream sem `[DONE]` | **CONFIRMADO** (0 ocorrências; último evento = chunk usage-only `choices:[]`) | `minimax-done.txt`, `minimax-stream-final.txt` |
| P-7c | `mimo-v2.6-pro` vision | **RECUPERADO** — 200 em 4,8–8,8 s; exige `max_tokens≥512` para emitir `content` (senão `finish=length` só com reasoning) | `mimo-vision.txt` |
| P-7d | `minimax-video-v2.3-fast` termina FAILED | **CONFIRMADO determinístico** — 2 tasks (prompt curto e rico PT-BR) ambas `failed/upstream_status=Fail` em <12 s, `video_url=null`, sem campo de motivo | `minimax-video*.txt/json` |
| P-7e | `hy-3d-3.1` nunca-terminal | **REFUTADO como falha do upstream**: as 2 tasks chegaram a `succeeded` (~10–13 min). O "nunca-terminal" era limite baixo de polling nosso + bug local: GET de poll **não passa pelo proxy** (`include_subpath:false` → `{"detail":"Not Found"}`) | `hy3d*.txt/json` |
| P-7f | `glm-4.6v-flash` 429 no scan de tools | **CONFIRMADO carga, não contrato**: hoje 429 `[ZhiPu] 该模型当前访问量过大` tanto com tools quanto sem (HTTP 429 em 1,3 s) | `glm46vflash-429.txt` |

---

## 1. P-1 — Catálogo ≠ roteável (CONFIRMADA)

`GET /v1/models` continua anunciando **121** ids, incluindo famílias mortas. Probes
chat hoje (gateway, `max_tokens=1`, controle `qwen3.8-max`):

```
qwen3-max          → 404 {"error":{"message":"[Alibaba Cloud] Model not exist."...}}
qwen3-coder-plus   → 404 [Alibaba Cloud] Model not exist.
qwen-vl-max        → 404 [Alibaba Cloud] Model not exist.
qwen-omni-turbo    → [Alibaba (通义千问)] Model not exist.
qwen3.8-max        → 200 "pong"   (controle: endpoint/payload corretos)
```

Reflete na matriz: grupos `novai-qwen3-*`/`novai-qwen-vl-*`/`novai-qwen-omni-*`
marcados `removed` (16 linhas, nota S114). **Veredito: persiste.** O catálogo do
gateway não é fonte de verdade para roteabilidade; a lista precisa de filtro ativo
por probe (como faz `eval/novai_inventory.py`).

## 2. P-2 — ZhiPu/Kimi sem thinking-OFF (CONFIRMADA, com nuance nova)

Probes diretos no gateway (POST `/v1/chat/completions`, variantes de campo):

- `glm-5.3` (ZhiPu):
  - `thinking:{type:"disabled"}` → **400** `"该模型始终思考，不支持关闭思考；请使用 low、high 或 max"`
  - `reasoning_effort:"low"` → **400** (mesma família de mensagem)
  - `thinking:{type:"enabled"}` → 200, reasoning preenchido (finish=length por budget)
  - ⇒ ZhiPu aceita enum mas **recusa desligar**; `low/high/max` são o mínimo.
- `kimi-k2.5` e `kimi-k2.8-preview` (Moonshot):
  - `disabled` → **400** `[Moonshot (Kimi)] ... rejected by an internal MaaS component`
  - `low` → **400** também! Kimi recusa até o esforço baixo — **mais rígida que ZhiPu**.

Consequência prática (já aplicada no harness): `thinking_off_supported()` marca
esses grupos e a matriz gera `skipped` (34 linhas) em vez de fail falso. Os skips
históricos de `kimi-*-fast`/`glm-*-fast` foram re-confirmados como comportamento
de upstream, não regressão nossa. **Veredito: persiste; Kimi ainda mais restritiva.**

## 3. P-3 — Contabilidade de reasoning, classe D (CONFIRMADA)

Re-run do harness exatamente nos 3 grupos que falham:

```
.venv/bin/python eval/novai_test.py --family chat --live --target proxy \
    --id novai-minimax-m2.7-fast novai-minimax-m2.5-fast novai-step-5-preview-fast
```

Log: `reports/logs/2026-10-18-novai-proxy.jsonl` (11 registros, 3 failures):

| grupo | baseline (matrix-before) | hoje |
| --- | --- | --- |
| novai-minimax-m2.7-fast | chars=79 tok=0 | **fail** chars=108 tok=28 |
| novai-minimax-m2.5-fast | chars=173 tok=48 | **fail** chars=134 tok=29 |
| novai-step-5-preview-fast | chars=123 tok=0 | **fail** chars=161 tok=0 |

Os números mudam a cada run (chars/tokens inconsistentes entre si e com o texto),
exatamente a assinatura da classe D: o gateway reporta `reasoning_tokens` que não
bater com o conteúdo de `reasoning_content`. **Veredito: persiste, não-determinístico
na magnitude, determinístico na inconsistência.**

## 4. P-4 / A6 — thinking OFF: REFINAMENTO IMPORTANTE (não é falha do gateway)

A narrativa histórica ("gateway ignora `thinking:{type:disabled}`") estava errada
na causa. Matriz de 4 casos (`a6-thinking-forwarding.txt`):

| alvo | modelo | payload | HTTP | completion | reasoning_tokens | rc_chars |
| --- | --- | --- | --- | --- | --- | --- |
| gateway | glm-5 | sem campo (baseline ON) | 200 | 114 | 112 | 376 |
| gateway | glm-5 | `thinking:{type:disabled}` **na raiz** | 200 | **1** | null | **0** |
| proxy | novai-glm-5-fast | `extra_body.thinking:disabled` (payload do harness) | 200 | **1** | null | 0 |
| gateway | glm-5 | `extra_body.thinking:disabled` **literal na raiz** | 200 | 149 | 147 | 520 |

Leitura: o gateway **honra** `thinking:disabled` quando o objeto chega no nível
raiz do JSON. Quando o cliente envia uma chave literal chamada `extra_body` (que é
convenção **do SDK Python da OpenAI**, desdobrado localmente antes do HTTP), o
gateway não a conhece e a ignora → thinking fica ON. Ou seja:

- Via proxy LiteLLM: funciona (LiteLLM desdobra `extra_body` corretamente) — rota
  `novai-glm-5-fast` OK.
- Via gateway direto com SDK: funciona (SDK desdobra localmente `extra_body`
  antes do HTTP).
- Via gateway direto com curl cru mandando `extra_body` como chave literal:
  **não** funciona — e era isso que o probe antigo media.

**Veredito: A6/P-4 encerrada como artefato de teste.** Corrigir a descrição no
consolidado: o gateway tem suporte simétrico a `thinking.disabled`; o cuidado é
enviar o campo na raiz, não embrulhado em `extra_body`.

## 5. P-5 — Envelope de erro não-OpenAI no gateway (CONFIRMADA)

`envelope-erro.txt` + re-run S117 (`contrato-shape.md`, 11 pass / 1 diverged):

- POST gateway com model inexistente → **HTTP 400 FastAPI**:
  `{"detail":"Model 'nao-existe-xyz' not supported. Available: glm-5, ..."}` —
  sem `error.message/type/param`, e vaza lista parcial de modelos.
- GET gateway `/v1/models/nao-existe-xyz` → **HTTP 404 página HTML** (SPA de marketing).
- Proxy (mesmos casos) → envelope OpenAI correto (`{"error":{"message":"/chat/completions: Invalid model name...","type":"invalid_request_error"}}`).

S117 shape contract completo hoje: `chat.completion`, `chat.completion.chunk`,
`embeddings`, `images.generation`, `models.list` conformes nos dois alvos
(gateway n=121, proxy n=152); única divergência = `error.openai @ gateway`
(estável vs baseline). **Veredito: persiste; único ponto de não-conformidade de
shape remanescente.**

## 6. P-6 — tools + stream: assimetria "fala antes do tool_call" (CONFIRMADA)

Probe stream com `tools=[noop]`, `tool_choice:auto`, gateway direto
(`tools-stream-assimetria.txt`):

| modelo | content antes do tool_call? | chunks com content | detalhe |
| --- | --- | --- | --- |
| glm-4.6v | **SIM** — `"\nI will call the noop tool as requested."` | 10 | finish=tool_calls |
| glm-5 | **SIM** — `"Vou chamar a ferramenta \`noop\` para você"` | 7 | |
| minimax-m3 | **SIM** — `"<think>The user is asking me to use the '` | 7 | raciocínio vazando em `delta.content` |
| kimi-k3 | não (só tool_calls, args fragmentados ok) | 0 | limpo |
| deepseek-v4-flash | não | 0 | limpo |

Consistente com o sweep S119 de ontem (112/212 irregulares no CSV
`2026-10-17-novai-tool-scan.csv`, classes `irregular_content_e_tool` / `fala_antes`).
O caso minimax-m3 é o pior: tags `<think>` chegam ao cliente dentro de `content`.
**Veredito: persiste no gateway; clientes precisam concatenar content+tool_calls
e sanitizar `<think>` nas famílias GLM-4.6v/GLM-5/MiniMax-M3.**

Spot-check adicional: `glm-4.6v-flash` (429 no scan de ontem) → hoje **429 de novo,
com e sem tools** (`glm46vflash-429.txt`): `[ZhiPu (智谱)] 该模型当前访问量过大，请您稍后再试`
em 1,3 s. É limitação de carga do provedor naquele id, não violação de contrato —
mas torna o modelo inutilizável em janelas de pico (registrado em P-7f).

## 7. P-7 — Estabilidade: cinco casos, quatro vereditos novos

### 7a. wan2.2-t2i-flash — NÃO é transitório (determinístico)

Baseline dizia "passou em 2026-10-17, tratado como transitório (classe G zerada)".
Errado. Hoje:

- 3× via proxy: `HTTP 000 em 150.0s` (read-timeout do LiteLLM esgotado; conexão
  cai sem resposta) — `wan22-transitorio.txt`.
- Gateway direto: **queda em 60,5–60,7 s exatos**, repetido em HTTP/2 e HTTP/1.1,
  prompt PT e EN ⇒ timeout fixo de ~60 s no lado do gateway/upstream Alibaba,
  não rede aleatória.
- Controle no MESMO endpoint (`/v1/images/generations`): `wan2.5-t2i-preview` →
  **200 em 14,8 s** com URL de PNG.
- Matriz de hoje: `novai-image-wan2.2-t2i-flash` = fail (único fail de image,
  família 11/12).

**Veredito: falha determinística de upstream para este id específico.** Remover ou
isolar `wan2.2-t2i-flash` do config; manter `wan2.5-t2i-preview`.

### 7b. minimax-text-01 — stream sem `[DONE]` (CONFIRMADO)

`minimax-done.txt`: ocorrências de `[DONE]`: **0**. `minimax-stream-final.txt`:
último evento é um chunk válido com `choices: []` e `usage`
(`total_tokens=560, completion_tokens=1`) — ou seja, o stream termina sem o
terminador SSE padrão OpenAI. Clientes que esperam `data: [DONE]` para fechar o
parser ficam pendurados. **Veredito: persiste (upstream MiniMax).**

### 7c. mimo-v2.6-pro vision — RECUPERADO, com restrição de budget

`mimo-vision.txt`: escada de `max_tokens` no mesmo pedido visual:

- 128 → 200, `finish=length`, `content=""`, só `reasoning_content` truncado;
- 256 → idem;
- **512 → 200 em 8,8 s, `finish=stop`, `content="Verde"`** ✔.

Ontem o grupo aparecia como instável; hoje funciona de forma confiável desde que
o orçamento comporte o raciocínio antes da resposta. **Veredito: recuperado;
documentar `max_tokens≥512` como requisito operacional do grupo.**

### 7d. minimax-video-v2.3-fast — FAILED determinístico (upstream)

Duas tasks assíncronas hoje (`minimax-video.txt`, `minimax-video-retry.txt`):
prompt curto PT e prompt rico PT-BR; submit OK (`status:queued`), poll 1 já
retorna:

```json
{"status":"failed","upstream_status":"Fail","video_url":null,...,"usage":{"total_tokens":0}}
```

(<12 s, sem qualquer campo explicando o motivo — `minimax-video-failed-full.json`.)
Nota de procedimento: o caminho correto é `POST /v1/video/generations`; usar
`/v1/videos/generations` dá 405 (achado deste reteste, corrigido no uso).
**Veredito: persiste como falha de upstream MiniMax vídeo; não-corrigível no nosso lado.**

### 7e. hy-3d-3.1 — "nunca-terminal" REFUTADO; bug de polling é NOSSO

`hy3d.txt`, `hy3d-task1-final.json`, `hy3d-final.json`, `hy3d-proxy.txt`:

- Submit via gateway direto e via proxy passthrough: OK (`queued`).
- Poll via **proxy** em qualquer caminho derivado (`/novai/3d/<id>`): sempre
  `{"detail":"Not Found"}` — porque a regra de passthrough tem
  `include_subpath: false`, então **GET de status não atravessa o proxy**. Isso
  gerou a falsa leitura de "task perdida".
- Poll via **gateway direto**: as duas tasks ficaram `processing/in_progress` por
  ~10–13 min e então viraram **`succeeded` / `upstream_status:completed`** com
  `model_url` (.glb assinado no Tencent COS):
  - task `1503253012881031168` → succeeded (confirmado por GET final);
  - task `1503253348777730048` → succeeded no poll 10 (~150–200 s após cruzar a
  janela do loop anterior).

**Veredito: hy-3d-3.1 funciona; SLA observado ≈ 10–13 min.** Ação nossa: ou
adicionar rota de GET no passthrough (subpath), ou documentar que polling 3D/vídeo
é sempre direto no gateway. Não é mais falha do gateway.

### 7f. glm-4.6v-flash — 429 de carga da ZhiPu (novo registro)

§6 acima: 429 imediato com e sem tools. Transitório por natureza (carga), mas
reincidente desde ontem; monitorar antes de rotacionar tráfego para esse id.

---

## 8. Estado consolidado pós-reteste

- Matriz (`reports/novai-test-matrix.csv`): 103 pass / **4 fail** / 34 skipped /
  16 removed. Os 3 fails históricos de chat (P-3) reproduziram; o 4º é wan2.2
  (P-7a, agora reconhecido como determinístico). Run completo da família chat com
  `--stream --thinking` não introduziu nenhum outro fail estrutural além dos já
  mapeados (os casos "so-on" de glm-4.6v-flash/glm-4.1v-thinking-flash caem nas
  classes P-2/P-3 já cobertas — skip por upstream, não bug novo).
- Embeddings: 4/4 pass. Image: 11/12 (único fail = wan2.2). Vision/TTS/ASR quick:
  pass. Passthrough submit (vídeo/3D): OK.
- S117 shape: 11/12, única divergência = error envelope do gateway (P-5).

## 9. Pendências que sobrevivem ao reteste (para o backlog)

1. **P-1**: manter filtro ativo de roteabilidade no catálogo (ids 404 "Model not
   exist" continuam anunciados).
2. **P-5**: pedir à NovAI envelope OpenAI-compliant em erros de POST e JSON (não
   HTML) em `GET /v1/models/<id>`.
3. **P-6**: mitigação client-side (concat content+tool_calls, strip `<think>`) ou
   reclamação formal sobre GLM-4.6v/GLM-5/MiniMax-M3.
4. **P-7a**: remover/isolar `wan2.2-t2i-flash` (determinístico, não transitório).
5. **P-7b**: reportar ausência de `[DONE]` no stream MiniMax-Text-01.
6. **P-7d**: `minimax-video-v2.3-fast` upstream Fail sistemático — abrir ticket com
   os dois task_ids deste laudo.
7. **Nosso bug (P-7e)**: habilitar polling assíncrono via proxy (rota GET de
   subpath no passthrough) ou documentar "poll sempre direto no gateway".
8. **Doc (P-4/A6)**: corrigir o consolidado — gateway honra `thinking:disabled`
   na raiz; `extra_body` é desdobramento do SDK, não parte do protocolo.

## Anexo — mapa de evidências

Diretório: `reports/logs/retest-2026-10-18/`

| arquivo | conteúdo |
| --- | --- |
| `matrix-before.csv` | snapshot da matriz antes dos re-runs de hoje |
| `a6-thinking-forwarding.txt` | matriz de 4 casos thinking raiz × extra_body × alvo |
| `envelope-erro.txt` | probes de erro POST/GET nos dois alvos (inclui HTML 404) |
| `contrato-shape.md` | re-run S117 (11 pass / 1 diverged) |
| `tools-stream-assimetria.txt` | 5 modelos, stream+tools, fala-antes? |
| `glm46vflash-429.txt` | 429 ZhiPu com e sem tools |
| `wan22-transitorio.txt` | 3× proxy + gateway direto (HTTP/2, HTTP/1.1, EN) + controle wan2.5 |
| `minimax-done.txt` / `minimax-stream-final.txt` | contagem [DONE]=0 + últimos eventos SSE |
| `mimo-vision.txt` | escada max_tokens 128/256/512 |
| `minimax-video.txt` / `minimax-video-retry.txt` / `minimax-video-failed-full.json` | 2 tasks failed + payload bruto |
| `hy3d.txt` / `hy3d-proxy.txt` / `hy3d-task1-final.json` / `hy3d-final.json` | polls das 2 tasks até succeeded + prova do 404 via proxy |
| `../2026-10-18-novai-proxy.jsonl` | re-run harness dos 3 grupos classe D |
| `../2026-10-18-novai-image.jsonl` | família image (11/12) |
| `../2026-10-18-novai-embedding.jsonl` | família embedding (4/4) |
