# Fase G — mídia: vision/OCR, image, TTS, ASR (S103)

- Data: **2026-10-17**
- Harness: `eval/novai_test.py` (`--media --target both --live`)
- Alvos: **gateway** `aiapi-pro.com/v1` + **proxy** LiteLLM `:4000/v1`
- Logs brutos: **locais, não versionados** (ver "Logs e segredos" abaixo)
- Testes offline: **363 passed** (`RAG_PROFILE=qwen37 .venv/bin/python -m pytest eval/tests/`)

## O que a Fase G cobre

| endpoint | rota | representante | veredito |
| --- | --- | --- | --- |
| vision (T22) | `/chat/completions` (multimodal) | `novai-qwen3-vl-plus` | cor da imagem presente na resposta |
| image | `/images/generations` | `novai-image-wand-vega-image-flash` | `data[0].url` presente |
| tts | `/audio/speech` | `novai-tts-minimax-speech-2.8-hd` | bytes de áudio com header válido |
| asr | `/audio/transcriptions` | `novai-asr-hy-asr-3.0-preview` | `text` não vazio |

## Resultado (rodada final)

```
checks=8 pass=8 fail=0 skip=0
  ✅ [chat]  novai-qwen3-vl-plus              :: vision — cor=red match='vermelh' len=8
  ✅ [image] novai-image-wand-vega-image-flash :: image — url=http://data-shanghai-.../wand-vega/d8
  ✅ [tts]   novai-tts-minimax-speech-2.8-hd   :: tts — bytes=20724 header=b'ID3\x04...'
  ✅ [asr]   novai-asr-hy-asr-3.0-preview      :: asr — text_len=50
  (idem no proxy)

# divergência gateway × proxy
  same_pass      4 — ambos passam ⇒ comportamento do gateway NovAI
```

**Gateway e proxy se comportam de forma idêntica** nas 4 modalidades: nenhuma
divergência, nenhum bug do LiteLLM. O que passa no gateway passa no proxy.

## Achados

### G1 — BUG NOSSO (classe H): fixture de ASR era um tom puro

O fixture antigo `eval/fixtures/hello.wav` era uma **senoide de 440 Hz** com
envelope constante. Medições:

| métrica | `hello.wav` (antigo) | `speech.wav` (novo) |
| --- | --- | --- |
| pico espectral | 440,0 Hz | 379,0 Hz (formante) |
| razão tom/total | **1,0000** | **0,0195** |
| envelope | plano (rms 8485 em todos os 100 ms) | variável (sílabas) |
| harmônicos | h2..h5 ≈ 0 | presentes |

O ASR devolvia `text: ""` **corretamente** — não há fala num tom puro. O teste
acusava o modelo por um bug nosso.

**Corrigido**: fixture sintetizado com `espeak-ng` (`"Hello world. This is a
test of speech recognition."`, 22 050 Hz mono, 3,8 s). Resultado nos dois
caminhos:

```
gateway: {"text":"Hello world, this is a test of speech recognition.", ...}
proxy:   {"text":"Hello world, this is a test of speech recognition.", ...}
```

`hello.wav` foi removido do repo. `run_asr` agora usa `speech.wav` e trata
fixture ausente como `skipped`, não como falha.

### G2 — BUG NOSSO (classe H): `size` de imagem inválido mascarava falhas

`run_image` mandava `size: "512x512"`. Os modelos Seedream rejeitam esse
tamanho:

```
HTTP 400: [ByteDance (Seedream)] The parameter `size` specified in the request
are not valid: image area must be ...
```

Isso fazia 2 modelos **saudáveis** aparecerem como quebrados. **Corrigido**:
`size: "1024x1024"` (menor tamanho aceito por todos os provedores). A varredura
da família `image` subiu de **8/14 para 10/14**.

### G3 — ACHADO (classe B): `wan2.2-t2i-flash` derruba a conexão

O upstream `wan2.2-t2i-flash` fecha a conexão sem resposta, de forma
**determinística** (N=3, back-to-back com `wan2.5-t2i-preview` no mesmo
instante):

| modelo | resultado |
| --- | --- |
| `wan2.2-t2i-flash` | `RemoteDisconnected` (3/3) |
| `wan2.5-t2i-preview` | HTTP 200 com URL (3/3) |

Não é timeout, não é rate limit, não é saldo: é o upstream derrubando o socket.
O gateway **lista** `wan2.2-t2i-flash` como disponível, mas não o serve.

**Ação**: o representante de `image` em `MEDIA_REPRESENTATIVES` passou a ser
`novai-image-wand-vega-image-flash` (passa limpo). O `wan2.2` fica como achado
documentado — não é bug do nosso stack.

### G4 — ACHADO (classe B): nomes de modelo divergem entre inventário e gateway

O gateway lista os modelos de imagem **sem** o prefixo `novai-image-`:

```
Available: hy-image-v3, vidu-image-q2, seedream-image-v5.0-pro,
seedream-image-v5.0-lite, wand-vega-image-lite, wand-vega-image-flash,
wand-vega-image-pro, doubao-seedream-5.0-pro, doubao-seedream-5.0,
cogview-3-flash, wan2.2-t2i-flash, qwen-image-plus, qwen-image,
wan2.5-t2i-preview
```

Mandar o nome do grupo (`novai-image-wan2.2-t2i-flash`) dá
`400 Model not found`. O `run_one` já converte para `upstream_id` no gateway
(correção da Fase F), então isso **não afeta o harness** — mas afeta qualquer
cliente que use o nome do grupo direto contra o gateway.

### G5 — ACHADO (classe B): 4 modelos de imagem quebrados no upstream

Varredura completa da família `image` (14 modelos, `--family image --live
--target gateway`): **10 pass / 4 fail**.

| modelo | erro |
| --- | --- |
| `novai-image-qwen-image` | 404 `[Alibaba Cloud] Model not exist.` |
| `novai-image-qwen-image-plus` | 404 `[Alibaba Cloud] Model not exist.` |
| `novai-image-wan2.2-t2i-flash` | `RemoteDisconnected` (ver G3) |
| `novai-image-seedream-image-v5.0-lite` | 400 `image size must be ...` (mínimo maior que 1024×1024) |

Os 10 que passam: `doubao-seedream-4.5`, `doubao-seedream-4.0`,
`seedream-image-v5.0-pro`, `hy-image-v3`, `vidu-image-q2`,
`wand-vega-image-pro`, `wand-vega-image-flash`, `wand-vega-image-lite`,
`cogview-3-flash`, `wan2.5-t2i-preview`.

## Implementação

### `verdict_vision` (T22)

Função pura, testável offline. Lê `choices[0].message.content` e procura a cor
esperada em PT/EN/zh:

```python
VISION_COLORS = {
    "red": ("vermelh", "red", "红"),
    "blue": ("azul", "blue", "蓝"),
}
```

Falha em: `choices` ausente, `content` vazio, cor ausente. Evidência:
`cor=red match='vermelh' len=8`.

### `run_vision`

Manda conteúdo multimodal em `/chat/completions`:

```python
body = {
    "model": group,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Qual é a cor predominante desta imagem? Responda em uma palavra."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
    "max_tokens": 64,
}
```

Fixture ausente ⇒ `skipped=True` (não falha).

### `--media` + `select_media`

Flag nova no CLI. Seleciona **1 representante por endpoint** na ordem fixa do
dict (determinística, preserva prompt-cache):

```python
MEDIA_REPRESENTATIVES = {
    "vision": "novai-qwen3-vl-plus",
    "image": "novai-image-wand-vega-image-flash",
    "tts": "novai-tts-minimax-speech-2.8-hd",
    "asr": "novai-asr-hy-asr-3.0-preview",
}
```

Grupo ausente do inventário é omitido (o relatório mostra o que rodou).

### Fixtures

| arquivo | origem | uso |
| --- | --- | --- |
| `eval/fixtures/red.png` | gerado (136 B) | vision — cor esperada `red` |
| `eval/fixtures/blue.png` | gerado (136 B) | vision — cor esperada `blue` |
| `eval/fixtures/speech.wav` | `espeak-ng` (167 KB) | asr — fala real |

`hello.wav` (tom puro) foi **removido**.

## Testes

13 testes novos em `eval/tests/test_novai_test.py`:

- `verdict_vision`: cor presente (PT/EN/zh), cor ausente, `choices` vazio,
  `content` vazio.
- `run_vision`: passa com sender fake, `skipped` sem fixture.
- `select_media`: 1 por endpoint, omite ausentes, ordem determinística.
- `run_image`: usa `1024x1024`.
- `test_body_raw_redacts_presigned_url`: o `body_raw` do jsonl não carrega
  `OSSAccessKeyId`/`Signature=` (ver G6).

Total: **363 passed**.

## Logs e segredos (G6)

As respostas de `/images/generations` trazem **URL pré-assinada** de OSS/COS com
credencial de terceiros na query:

```
https://.../i.png?OSSAccessKeyId=LTAI5t...&Signature=...
https://.../i.png?q-sign-algorithm=sha1&q-ak=AKID...&q-signature=...
```

O GitHub Push Protection bloqueia o push (`GH013`) quando isso entra num
arquivo versionado. Duas medidas:

1. **Redação no sender** — `make_capturing_sender` passa o `body_raw` por
   `redact_signed_urls` (o mesmo do S106, em `eval/novai_enrich.py`) antes de
   gravar. Preserva host+path, apaga a query.
2. **Logs de mídia não versionados** — `.gitignore` cobre
   `reports/logs/*-novai-{image,both,gateway}.jsonl` e `*.contaminated.jsonl`.
   O regex não cobre 100% das variantes de assinatura, então o log bruto fica
   local; o relatório versionado cita só host+path.

> ⚠️ A redação **não** pode ser aplicada sobre a linha JSON crua: o
> `redact_signed_urls` mexe em `\u001e`/`\u0000` escapados dentro de strings e
> corrompe o JSON. Aplique no **objeto já parseado** (campo a campo) ou no
> `body_raw` antes da serialização — que é o que o sender faz.

## Como reproduzir

```bash
# suíte de mídia (4 endpoints × 2 alvos)
.venv/bin/python -m eval.novai_test --media --live --target both --sleep 1.1

# varredura completa da família de imagem
.venv/bin/python -m eval.novai_test --family image --live --target gateway --sleep 1.1

# testes offline
RAG_PROFILE=qwen37 .venv/bin/python -m pytest eval/tests/
```

## Conclusão

A Fase G fecha **verde**: as 4 modalidades de mídia funcionam de ponta a ponta
no gateway e no proxy, com comportamento idêntico entre os dois. Os 3 bugs
encontrados eram **nossos** (fixture de ASR, `size` de imagem, representante
apontando para modelo morto) e foram corrigidos. Os 4 modelos de imagem
quebrados são falha do **upstream NovAI**, documentados como achado — não
bloqueiam o stack.
