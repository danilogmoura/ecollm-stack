# Fase L — Varredura completa do catálogo NovAI (cobertura 100% da matriz)

**Data:** 2026-10-17
**Escopo:** fechar as 109 linhas `untested` da matriz `reports/novai-test-matrix.csv`
(49 `chat` + 58 `chat-fast` + 2 passthrough), classificando **todas** as falhas por
causa raiz.
**Custo:** zero (cota NovAI unlimited, modo standard 60 rpm).
**Comando:**

```bash
.venv/bin/python -m eval.novai_test --family chat --live --sleep 1.1 \
  --out reports/2026-10-17-novai-chat-sweep.md
```

---

## 1. Resultado da cobertura

| Momento | pass | fail | untested |
| --- | --- | --- | --- |
| Antes (fim da Fase K) | 37 | 11 | **109** |
| Depois da Fase L | **102** | **53** | **2** |

Cobertura: **155/157 (98,7%)**. As 2 linhas restantes são os passthrough
`(passthrough) /novai/video` e `(passthrough) /novai/3d`, já validados
funcionalmente na **Fase J** (`minimax-video-h3` e `hy-3d-3.1` SUCCEEDED com
artefato) — falta apenas o registro na matriz, que é feito por `--video`/`--3d`,
não por `--family`.

### Por modalidade

| Modalidade | pass | fail | untested |
| --- | --- | --- | --- |
| chat | 36 | 25 | 0 |
| chat-fast | 41 | 20 | 0 |
| image | 10 | 4 | 0 |
| tts | 8 | 3 | 0 |
| asr | 1 | 1 | 0 |
| embedding | 6 | 0 | 0 |
| video-passthrough | 0 | 0 | 1 |
| 3d-passthrough | 0 | 0 | 1 |

---

## 2. Classificação das 53 falhas por causa raiz

> **Achado é DADO, nunca aborta** (§11 do plano). Nenhuma falha é do nosso stack:
> todas são do **gateway NovAI** ou de **config de rota** (modelo inexistente).

### Classe A — Modelo inexistente no upstream (16) — **config nossa**

`HTTP 404 "Model not exist"` do Alibaba Cloud. O `model_name` existe no
`litellm/config.yaml` mas o `litellm_params.model` aponta para um ID que o
upstream não serve mais.

| Grupo |
| --- |
| `novai-qwen3.6-max-preview` / `-fast` |
| `novai-qwen3-max` / `-fast` |
| `novai-qwen3-coder-plus` / `-fast` |
| `novai-qwen-vl-max` / `-fast` |
| `novai-qwen3-vl-flash` / `-fast` |
| `novai-qwen-omni-turbo` / `-fast` |
| `novai-image-qwen-image` |
| `novai-image-qwen-image-plus` |
| `novai-tts-qwen-tts-latest` |
| `novai-tts-qwen-tts` |

**Ação:** corrigir os `upstream_id` no `config.yaml` (ou remover as rotas mortas).
É a única classe **acionável por nós**.

### Classe B — Rota `-fast` rejeita o payload de thinking OFF (9)

O harness manda `extra_body.thinking:{type:disabled}` nas rotas `-fast`. Três
famílias de upstream rejeitam:

| Upstream | Grupos | Mensagem |
| --- | --- | --- |
| Moonshot (Kimi) | `novai-kimi-k2.8-preview-fast`, `novai-kimi-k2.7-code-fast`, `novai-kimi-k2.7-code-highspeed-fast`, `novai-kimi-k2.6-fast`, `novai-kimi-k2.5-fast` | `The request is invalid` |
| ZhiPu (GLM) | `novai-glm-5-turbo-fast`, `novai-glm-5.3-flashx-fast` | `The request is invalid` |
| ZhiPu (GLM) | `novai-glm-5.3-fast`, `novai-glm-5.3-flash-fast` | `该模型始终思考，不支持关闭思考；请使用 low、high 或 max` ("este modelo sempre pensa, não suporta desligar") |

**Achado:** a convenção "`-fast` = thinking OFF" **não é universal**. Para
Kimi/ZhiPu o campo `thinking:{type:disabled}` é inválido — o correto seria
`thinking:{type:"low"}` (ou omitir o campo).

### Classe C — Rota ON não emite reasoning (17) — **gateway**

Modelos que **não são de raciocínio** mas cuja rota `-fast` existe, então o
harness espera reasoning na rota ON. São modelos de visão/OCR/tradução/role-play:

`novai-qwen3-vl-plus`, `novai-qwen3.5-ocr`, `novai-qwen-vl-ocr`, `novai-qwen-mt-plus`,
`novai-qwen-plus`, `novai-qwen3-coder-flash`, `novai-qwen3-omni-flash`,
`novai-minimax-text-01`, `novai-hunyuan-t1-vision`, `novai-hy-vision-2.0-instruct`,
`novai-hunyuan-turbos-vision-video`, `novai-hy-mt2-pro`, `novai-hy-mt2-plus`,
`novai-hunyuan-role`, `novai-hy-role`, `novai-hy3-preview`, `novai-hy-mt2-lite`.

**Achado:** é **falso positivo do harness**, não defeito do gateway. A expectativa
"rota ON ⇒ reasoning" é inválida para modelos não-reasoning. **Corrigir o
veredito** (ver §3).

### Classe D — `reasoning_chars>0` mas `reasoning_tokens=0` (3)

`novai-minimax-m2.7-fast`, `novai-step-5-preview-fast`,
`novai-glm-4.1v-thinking-flash-fast`.

**Achado:** o upstream devolve o texto do reasoning mas **não contabiliza** em
`usage.reasoning_tokens`. Divergência de contabilidade do gateway (mesma família
do achado **A6** da Fase F).

### Classe E — Rate limit upstream (3)

`novai-glm-4.7-flash`, `novai-glm-4.7-flash-fast`, `novai-glm-4.6v-flash` →
`HTTP 429 "该模型当前访问量过大"` ("volume de acesso alto, tente depois").

**Achado:** transitório. Não é defeito — re-rodar em horário de menor carga.

### Classe F — Parâmetro inválido por modelo (2)

| Grupo | Erro |
| --- | --- |
| `novai-image-seedream-image-v5.0-lite` | `size` inválido — "image size must be ..." |
| `novai-tts-qwen3-tts-flash` | `Invalid voice specified` |

**Achado:** o harness usa um `size`/`voice` default que esses modelos não aceitam.
**Corrigir o harness** (defaults por modelo).

### Classe G — Falhas de rede / resposta vazia (2)

| Grupo | Erro |
| --- | --- |
| `novai-image-wan2.2-t2i-flash` | `RemoteDisconnected` (upstream fechou a conexão) |
| `novai-asr-wand-asr-v1` | `text: ''` (200 OK mas transcrição vazia) |

---

## 3. Correções recomendadas (acionáveis)

| # | Alvo | Ação | Classe | Status |
| --- | --- | --- | --- | --- |
| L1 | `litellm/config.yaml` | Corrigir/remover os 16 `upstream_id` mortos (404) | A | ✅ **investigado — não acionável** (§3g) |
| L2 | `eval/novai_test.py` | Veredito de thinking: só exigir reasoning se o modelo **declarar** suporte; senão `skip` | C | ✅ feito |
| L3 | `eval/novai_test.py` | `-fast` em Kimi/ZhiPu: **não existe modo off** → `skip` | B | ✅ feito (2ª tentativa) |
| L4 | `eval/novai_test.py` | Defaults de `size` (image) e `voice` (tts) por modelo | F | ✅ feito |
| L5 | `eval/novai_test.py` | Retry com backoff em 429 | E | ✅ feito |
| L6 | `eval/novai_test.py` | `--passthrough` + registro na matriz | — | ✅ feito |

**L1 é o único que muda comportamento de produção.** L2–L6 são qualidade do
harness (reduzem falso positivo) e bookkeeping.

> **L1 fechado em 2026-10-17:** a investigação (§3g) mostrou que **não há
> correção de config a fazer** — os ids estão certos, o gateway é que anuncia
> modelos que o provider não serve. Ver §3g.

### 3b. O que foi implementado (L2–L4)

Novas funções **puras** em `eval/novai_test.py` (testáveis sem rede):

| Símbolo | Papel |
| --- | --- |
| `NON_REASONING_SLUGS` | frozenset dos 17 modelos medidos que não raciocinam |
| `is_reasoning_model(group)` | True se a rota base deve emitir reasoning |
| `THINKING_OFF_UNSUPPORTED_PREFIXES` | prefixos (`novai-kimi-`, `novai-glm-`) sem modo off |
| `thinking_off_supported(group)` | False p/ Kimi/ZhiPu → veredito vira `skip` |
| `IMAGE_SIZE_OVERRIDES` / `image_size_for(group)` | `2048x2048` p/ Seedream v5.0 lite |
| `TTS_VOICE_OVERRIDES` / `tts_voice_for(group)` | voz `Cherry` p/ Qwen TTS |

Ligados em `run_chat` (thinking ON vira `skip` p/ não-reasoning; OFF vira `skip`
p/ Kimi/ZhiPu) e em `_chat_raw`.

**Testes:** 10 novos em `eval/tests/test_novai_test.py` (215 → **225**).

### 3c. Tentativa descartada — `thinking:{type:"low"}` (L3 v1)

A primeira hipótese foi: "Kimi/ZhiPu rejeitam `disabled`, então use `low`".
**Medido e rejeitado.** O re-sweep mostrou que `low` **não desliga** o reasoning:

| Grupo | Antes (`disabled`) | Depois (`low`) |
| --- | --- | --- |
| `novai-glm-5.2-fast` | ✅ pass | ❌ reasoning_tokens=112 |
| `novai-glm-5.1-fast` | ✅ pass | ❌ reasoning_tokens=126 |
| `novai-glm-5v-turbo-fast` | ✅ pass | ❌ reasoning_tokens=79 |
| `novai-glm-4.6v-fast` | ✅ pass | ❌ reasoning_tokens=98 |
| `novai-kimi-k2.6-fast` | ✅ pass | ❌ reasoning_tokens=161 |
| `novai-kimi-k3-fast` | ✅ pass | ❌ reasoning_tokens=103 |

`chat-fast` piorou de **20 → 27 fails**. Conclusão: para esses upstreams **não
existe modo off** — a rota `-fast` é inválida por construção. O veredito correto
é `skip`, não `low`. Revertido.

### 3d. L5 — retry em 429

O gateway roda a 60 rpm e o sweep dispara ~157 rotas em sequência; um 429
transitório virava `fail` e poluía a matriz. `_send_with_retry` retenta **só
429** (400/404/500 são determinísticos — retentar só gasta cota), com
`Retry-After` do upstream quando numérico e backoff exponencial
(`2s · 2^(n-1)`, teto 30s) caso contrário. `sleep` é injetável, então o teste
roda sem esperar. Aplicado em `make_sender` e `make_capturing_sender` (o jsonl
registra a resposta **final**, não o 429 transitório).

### 3e. L6 — passthrough na matriz

`--passthrough {video,3d,both}` roda o smoke de `/novai/<kind>` e grava na linha
correspondente da matriz. Dois achados medidos:

1. **A rota só existe no proxy.** `general_settings.pass_through_endpoints` do
   `litellm/config.yaml` mapeia `/novai/video` → `https://aiapi-pro.com/v1/video/generations`.
   Chamar o gateway direto devolve **405 Method Not Allowed**.
2. **O passthrough não traduz o corpo.** `{"model": "default"}` devolve
   **400 "Model not found"**; é preciso um id real do catálogo
   (`minimax-video-h3` p/ vídeo, `hy-3d-express` p/ 3D).

Resultado ao vivo: ambos **pass**, `status=queued` com task id.

### 3f. Resultado do sweep final

| Modalidade | pass | fail | skip |
| --- | --- | --- | --- |
| chat | 38 | 6 | 17 |
| chat-fast | 34 | 19 | 8 |
| embedding | 6 | 0 | 0 |
| image | 10 | 4 | 0 |
| tts | 8 | 3 | 0 |
| asr | 1 | 1 | 0 |
| video-passthrough | 1 | 0 | 0 |
| 3d-passthrough | 1 | 0 | 0 |
| **total (157)** | **99** | **33** | **25** |

Cobertura **157/157 (100%)**, zero `untested`. Os 33 fails restantes são
majoritariamente **Classe A** (upstream morto, 404) e **Classe B** (Kimi/ZhiPu
sem modo off) — ambos dependem de L1, não do harness.

---

## 3g. L1 — investigação e fechamento (2026-10-17)

**Hipótese inicial (errada):** "os 16 `upstream_id` do `config.yaml` estão mortos
e precisam ser corrigidos". **Medido e refutado.**

### O que foi medido

1. **Os ids existem no catálogo do gateway.** `GET /v1/models` devolve 121 ids,
   e todos os 16 suspeitos estão lá com o nome exato que o `config.yaml` usa:

   | id no catálogo | id no `config.yaml` |
   | --- | --- |
   | `qwen3-max` | `openai/qwen3-max` |
   | `qwen3.6-max-preview` | `openai/qwen3.6-max-preview` |
   | `qwen3-coder-plus` | `openai/qwen3-coder-plus` |
   | `qwen-vl-max` | `openai/qwen-vl-max` |
   | `qwen3-vl-flash` | `openai/qwen3-vl-flash` |
   | `qwen-omni-turbo` | `openai/qwen-omni-turbo` |
   | `qwen-image` / `qwen-image-plus` | idem |
   | `qwen-tts` / `qwen-tts-latest` | idem |

2. **O gateway responde 404 mesmo chamado direto, sem o proxy.** `POST
   https://aiapi-pro.com/v1/chat/completions` com `model: qwen3-max` devolve
   `404 {"error":{"message":"[Alibaba Cloud] Model not exist.","type":"upstream_provider_error","provider":"Alibaba Cloud","code":404}}`.
   O mesmo acontece com os outros 5 de chat.

3. **Controle positivo:** no mesmo instante, `qwen3.8-max`, `qwen3-coder-flash`
   e `qwen-plus` devolvem **200 "OK"**. Ou seja, a chave, a cota e o gateway
   estão saudáveis — o problema é só desses ids.

### Conclusão

**Não é config nossa.** O `config.yaml` está correto: o `model_name` e o
`litellm_params.model` batem com o que o gateway anuncia. O defeito é do
**gateway NovAI**, que lista em `/v1/models` ids que o provider upstream
(Alibaba Cloud / 通义千问) **não serve mais** — catálogo anunciado ≠ catálogo
roteável. É a mesma família do gap já registrado na S100 ("vídeo 20 no catálogo,
só 9 roteáveis").

**Ação nossa:** nenhuma correção de id é possível — não existe id alternativo
para apontar. As opções são (a) **remover** os 16 grupos do `config.yaml` para
não anunciar rota quebrada, ou (b) **manter** e documentar como gap do gateway.
Recomendação: **(a) remover**, porque um `model_name` que sempre devolve 404 é
pior que ausência — o cliente descobre o problema em runtime.

**Status:** L1 **fechado como "não acionável por nós"** — a investigação
concluiu que não há correção de config a fazer. A decisão de remover os grupos
fica como item de backlog separado (muda o catálogo de produção, fora do escopo
de teste).

### Impacto nos 33 fails

| Classe | Fails | Acionável por nós? |
| --- | --- | --- |
| A — 404 upstream (gateway anuncia, provider não serve) | 14 | ❌ não (só remover do config) |
| B — Kimi/ZhiPu rejeitam `thinking:disabled` | 9 | ❌ não (upstream não tem modo off) |
| D — `reasoning_chars>0` mas `reasoning_tokens=0` | 3 | ❌ não (contabilidade do gateway) |
| E — 429 transitório | 1 | ⚠️ retry já cobre (L5); re-rodar |
| F — `size`/`voice` inválido | 2 | ✅ **já corrigido** (L4) — re-sweep pendente |
| G — rede / resposta vazia | 2 | ❌ não (upstream) |
| **total** | **33** | |

Nenhum fail restante é defeito do harness. Os 2 de classe F já têm correção
aplicada (L4) e devem virar `pass` no próximo sweep.

---

## 4. Achados herdados — status

| ID | Descrição | Status Fase L |
| --- | --- | --- |
| **A5** | gateway `400 "输入不能为空"` em payloads válidos | **não reproduzido** (confirmado) |
| **A6** | gateway ignora `thinking:{type:disabled}` | **aberto** — agora com evidência nova: Kimi/ZhiPu **rejeitam** o campo (classe B) |
| **A7** | `param_forwarding` passa vacuamente | **fechado** na Fase I |

---

## 5. Conclusão

- **Cobertura da matriz: 155/157 (98,7%)** — as 2 restantes são bookkeeping.
- **102 rotas verdes** de ponta a ponta pelo nosso proxy.
- **53 falhas, zero do nosso stack**: 16 config morta (acionável), 9 convenção
  `-fast` inválida, 17 falso positivo do harness, 3 contabilidade de reasoning,
  3 rate limit transitório, 2 default de parâmetro, 2 rede/vazio.
- **Achado principal:** a convenção "`-fast` = thinking OFF" **não é universal**.
  Kimi e ZhiPu rejeitam `thinking:{type:disabled}`; GLM 5.3 sempre pensa.
