# NovAI — Metadados por modelo (via API)

Fonte: `GET /v1/models` (via proxy LiteLLM) + sondas de capacidade por modelo.
Modelos: **94**

Cada modelo traz: metadados do `/v1/models` (`owned_by`, `pricing`, `type`), o grupo/modalidade do inventário local, e o resultado das sondas de capacidade (chat, thinking, tools, embedding, image, tts, asr).

## Resumo por modalidade

| Modalidade | Modelos |
|---|---|
| asr | 2 |
| chat | 61 |
| embedding | 6 |
| image | 14 |
| tts | 11 |

## Sucesso das sondas

| Sonda | ok | total |
|---|---|---|
| asr | 0 | 2 |
| chat | 45 | 61 |
| embedding | 4 | 6 |
| image | 10 | 14 |
| thinking | 38 | 61 |
| tools | 44 | 61 |
| tts | 8 | 11 |

## Detalhe por modelo

### `cogview-3-flash`

- grupo: `novai-image-cogview-3-flash` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://maas-watermark-prod-new.cn-wlcb.ufileos.com/2… |

### `deepseek-v4-flash`

- grupo: `novai-deepseek-v4-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=66 reasoning_tokens=19 |
| tools | ✅ tool=noop args_json_ok |

### `deepseek-v4-flash-vision`

- grupo: `novai-deepseek-v4-flash-vision` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=53 reasoning_tokens=17 |
| tools | ✅ tool=noop args_json_ok |

### `deepseek-v4-pro`

- owned_by: `openai` · grupo: `novai-deepseek-v4-pro` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=66 reasoning_tokens=20 |
| tools | ✅ tool=noop args_json_ok |

### `deepseek-v4.1-flash`

- grupo: `novai-deepseek-v4.1-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=53 reasoning_tokens=17 |
| tools | ✅ tool=noop args_json_ok |

### `doubao-seed-2.0-code`

- grupo: `novai-doubao-seed-2.0-code` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=119 reasoning_tokens=63 |
| tools | ✅ tool=noop args_json_ok |

### `doubao-seed-2.0-lite`

- grupo: `novai-doubao-seed-2.0-lite` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=107 reasoning_tokens=71 |
| tools | ✅ tool=noop args_json_ok |

### `doubao-seed-2.0-pro`

- grupo: `novai-doubao-seed-2.0-pro` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=162 reasoning_tokens=80 |
| tools | ✅ tool=noop args_json_ok |

### `doubao-seed-2.1-pro`

- grupo: `novai-doubao-seed-2.1-pro` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=91 reasoning_tokens=69 |
| tools | ✅ tool=noop args_json_ok |

### `doubao-seed-2.1-turbo`

- grupo: `novai-doubao-seed-2.1-turbo` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=58 reasoning_tokens=48 |
| tools | ✅ tool=noop args_json_ok |

### `doubao-seedream-4.0`

- grupo: `novai-image-doubao-seedream-4.0` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/… |

### `doubao-seedream-4.5`

- grupo: `novai-image-doubao-seedream-4.5` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/… |

### `glm-4.1v-thinking-flash`

- grupo: `novai-glm-4.1v-thinking-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=19 |
| thinking | ✅ reasoning_chars=363 reasoning_tokens=0 |
| tools | ❌ finish=length n_tool_calls=0 |

### `glm-4.6v`

- grupo: `novai-glm-4.6v` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=216 reasoning_tokens=87 |
| tools | ✅ tool=noop args_json_ok |

### `glm-4.6v-flash`

- grupo: `novai-glm-4.6v-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 429: {"error":{"message":"litellm.RateLimitError: Ra… |
| thinking | ❌ HTTP 429: {"error":{"message":"litellm.RateLimitError: Ra… |
| tools | ✅ tool=noop args_json_ok |

### `glm-4.7-flash`

- grupo: `novai-glm-4.7-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 429: {"error":{"message":"litellm.RateLimitError: Ra… |
| thinking | ✅ reasoning_chars=887 reasoning_tokens=331 |
| tools | ❌ HTTP 429: {"error":{"message":"litellm.RateLimitError: Ra… |

### `glm-5`

- grupo: `novai-glm-5` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=416 reasoning_tokens=169 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5-turbo`

- grupo: `novai-glm-5-turbo` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=length len(content)=2 |
| thinking | ✅ reasoning_chars=43 reasoning_tokens=26 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5.1`

- grupo: `novai-glm-5.1` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=331 reasoning_tokens=132 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5.2`

- grupo: `novai-glm-5.2` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=356 reasoning_tokens=138 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5.3`

- grupo: `novai-glm-5.3` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=119 reasoning_tokens=45 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5.3-flash`

- grupo: `novai-glm-5.3-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=139 reasoning_tokens=59 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5.3-flashx`

- grupo: `novai-glm-5.3-flashx` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=65 reasoning_tokens=36 |
| tools | ✅ tool=noop args_json_ok |

### `glm-5v-turbo`

- grupo: `novai-glm-5v-turbo` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=416 reasoning_tokens=151 |
| tools | ✅ tool=noop args_json_ok |

### `hunyuan-role`

- grupo: `novai-hunyuan-role` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `hunyuan-t1-vision`

- grupo: `novai-hunyuan-t1-vision` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ✅ tool=noop args_json_ok |

### `hunyuan-turbos-vision-video`

- grupo: `novai-hunyuan-turbos-vision-video` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ✅ tool=noop args_json_ok |

### `hy-asr-3.0-preview`

- grupo: `novai-asr-hy-asr-3.0-preview` · modalidade: `asr`

| Sonda | Resultado |
|---|---|
| asr | ❌ requer arquivo de áudio (não sondado) |

### `hy-image-v3`

- grupo: `novai-image-hy-image-v3` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://aigc-output-image-1326893053.cos.ap-guangzhou… |

### `hy-mt2-lite`

- grupo: `novai-hy-mt2-lite` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `hy-mt2-plus`

- grupo: `novai-hy-mt2-plus` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `hy-mt2-pro`

- grupo: `novai-hy-mt2-pro` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ finish=stop n_tool_calls=0 |

### `hy-role`

- grupo: `novai-hy-role` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `hy-vision-2.0-instruct`

- grupo: `novai-hy-vision-2.0-instruct` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ finish=length n_tool_calls=0 |

### `hy3`

- grupo: `novai-hy3` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=220 reasoning_tokens=106 |
| tools | ✅ tool=noop args_json_ok |

### `hy3-preview`

- grupo: `novai-hy3-preview` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=150 reasoning_tokens=49 |
| tools | ✅ tool=noop args_json_ok |

### `hy4-preview`

- grupo: `novai-hy4-preview` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=221 reasoning_tokens=80 |
| tools | ✅ tool=noop args_json_ok |

### `kimi-k2.5`

- grupo: `novai-kimi-k2.5` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=403 reasoning_tokens=160 |
| tools | ✅ tool=noop args_json_ok |

### `kimi-k2.6`

- grupo: `novai-kimi-k2.6` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=459 reasoning_tokens=155 |
| tools | ✅ tool=noop args_json_ok |

### `kimi-k2.7-code`

- grupo: `novai-kimi-k2.7-code` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=66 reasoning_tokens=21 |
| tools | ✅ tool=noop args_json_ok |

### `kimi-k2.7-code-highspeed`

- grupo: `novai-kimi-k2.7-code-highspeed` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=188 reasoning_tokens=61 |
| tools | ✅ tool=noop args_json_ok |

### `kimi-k2.8-preview`

- grupo: `novai-kimi-k2.8-preview` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=189 reasoning_tokens=65 |
| tools | ✅ tool=noop args_json_ok |

### `kimi-k3`

- grupo: `novai-kimi-k3` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ content vazio (finish=length) |
| thinking | ✅ reasoning_chars=37 reasoning_tokens=25 |
| tools | ✅ tool=noop args_json_ok |

### `kinfra-text-embedding-0.6b`

- grupo: `novai-embed-kinfra-text-embedding-0.6b` · modalidade: `embedding`

| Sonda | Resultado |
|---|---|
| embedding | ✅ dim=1024 |

### `kinfra-text-embedding-4b`

- grupo: `novai-embed-kinfra-text-embedding-4b` · modalidade: `embedding`

| Sonda | Resultado |
|---|---|
| embedding | ✅ dim=2560 |

### `kinfra-vl-embedding-2b`

- grupo: `novai-embed-kinfra-vl-embedding-2b` · modalidade: `embedding`

| Sonda | Resultado |
|---|---|
| embedding | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `kinfra-vl-embedding-8b`

- grupo: `novai-embed-kinfra-vl-embedding-8b` · modalidade: `embedding`

| Sonda | Resultado |
|---|---|
| embedding | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `mimo-v2.5-pro`

- grupo: `novai-mimo-v2.5-pro` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=76 reasoning_tokens=48 |
| tools | ✅ tool=noop args_json_ok |

### `mimo-v2.6-flash`

- grupo: `novai-mimo-v2.6-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=3 reasoning_tokens=4 |
| tools | ✅ tool=noop args_json_ok |

### `mimo-v2.6-pro`

- grupo: `novai-mimo-v2.6-pro` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=43 reasoning_tokens=36 |
| tools | ✅ tool=noop args_json_ok |

### `minimax-m2.5`

- grupo: `novai-minimax-m2.5` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=168 reasoning_tokens=65 |
| tools | ✅ tool=noop args_json_ok |

### `minimax-m2.7`

- grupo: `novai-minimax-m2.7` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=310 reasoning_tokens=99 |
| tools | ✅ tool=noop args_json_ok |

### `minimax-m3`

- grupo: `novai-minimax-m3` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |
| tools | ✅ tool=noop args_json_ok |

### `minimax-music-v2.6`

- grupo: `novai-tts-minimax-music-v2.6` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=86821 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-music-v3.0`

- grupo: `novai-tts-minimax-music-v3.0` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=101554 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-speech-02-hd`

- grupo: `novai-tts-minimax-speech-02-hd` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=16116 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-speech-02-turbo`

- grupo: `novai-tts-minimax-speech-02-turbo` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=16116 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-speech-2.6-hd`

- grupo: `novai-tts-minimax-speech-2.6-hd` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=16116 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-speech-2.6-turbo`

- grupo: `novai-tts-minimax-speech-2.6-turbo` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=15540 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-speech-2.8-hd`

- grupo: `novai-tts-minimax-speech-2.8-hd` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=16116 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-speech-2.8-turbo`

- grupo: `novai-tts-minimax-speech-2.8-turbo` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ✅ bytes=15540 header=b'ID3\x04\x00\x00\x00\x00\x08jTX' |

### `minimax-text-01`

- grupo: `novai-minimax-text-01` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ✅ tool=noop args_json_ok |

### `qwen-image`

- grupo: `novai-image-qwen-image` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |

### `qwen-image-plus`

- grupo: `novai-image-qwen-image-plus` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |

### `qwen-mt-plus`

- grupo: `novai-qwen-mt-plus` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `qwen-omni-turbo`

- grupo: `novai-qwen-omni-turbo` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |
| thinking | ❌ HTTP 429: {"error":{"message":"No deployments available f… |
| tools | ❌ HTTP 429: {"error":{"message":"No deployments available f… |

### `qwen-plus`

- grupo: `novai-qwen-plus` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ✅ tool=noop args_json_ok |

### `qwen-tts`

- grupo: `novai-tts-qwen-tts` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |

### `qwen-tts-latest`

- grupo: `novai-tts-qwen-tts-latest` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |

### `qwen-vl-max`

- grupo: `novai-qwen-vl-max` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |
| thinking | ❌ HTTP 429: {"error":{"message":"No deployments available f… |
| tools | ❌ HTTP 429: {"error":{"message":"No deployments available f… |

### `qwen-vl-ocr`

- grupo: `novai-qwen-vl-ocr` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ❌ finish=stop n_tool_calls=0 |

### `qwen3-coder-flash`

- grupo: `novai-qwen3-coder-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ✅ tool=noop args_json_ok |

### `qwen3-coder-plus`

- grupo: `novai-qwen3-coder-plus` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |
| thinking | ❌ HTTP 429: {"error":{"message":"No deployments available f… |
| tools | ❌ HTTP 429: {"error":{"message":"No deployments available f… |

### `qwen3-max`

- grupo: `novai-qwen3-max` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |
| thinking | ❌ HTTP 429: {"error":{"message":"No deployments available f… |
| tools | ❌ HTTP 429: {"error":{"message":"No deployments available f… |

### `qwen3-omni-flash`

- grupo: `novai-qwen3-omni-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ sem reasoning (esperado ON) |
| tools | ✅ tool=noop args_json_ok |

### `qwen3-tts-flash`

- grupo: `novai-tts-qwen3-tts-flash` · modalidade: `tts`

| Sonda | Resultado |
|---|---|
| tts | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |

### `qwen3-vl-flash`

- grupo: `novai-qwen3-vl-flash` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |
| thinking | ❌ HTTP 429: {"error":{"message":"No deployments available f… |
| tools | ❌ HTTP 429: {"error":{"message":"No deployments available f… |

### `qwen3-vl-plus`

- grupo: `novai-qwen3-vl-plus` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=1312 reasoning_tokens=501 |
| tools | ✅ tool=noop args_json_ok |

### `qwen3.5-ocr`

- grupo: `novai-qwen3.5-ocr` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ❌ HTTP 400: {"error":{"message":"litellm.BadRequestError: O… |
| tools | ❌ finish=stop n_tool_calls=0 |

### `qwen3.6-max-preview`

- grupo: `novai-qwen3.6-max-preview` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ❌ HTTP 404: {"error":{"message":"litellm.NotFoundError: Not… |
| thinking | ❌ HTTP 429: {"error":{"message":"No deployments available f… |
| tools | ❌ HTTP 429: {"error":{"message":"No deployments available f… |

### `qwen3.7-max`

- grupo: `novai-qwen3.7-max` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=817 reasoning_tokens=290 |
| tools | ✅ tool=noop args_json_ok |

### `qwen3.7-text-embedding`

- grupo: `novai-embed-qwen3.7-text-embedding` · modalidade: `embedding`

| Sonda | Resultado |
|---|---|
| embedding | ✅ dim=1024 |

### `qwen3.8-max`

- owned_by: `openai` · grupo: `novai-qwen3.8-max` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=171 reasoning_tokens=73 |
| tools | ✅ tool=noop args_json_ok |

### `seedream-image-v5.0-lite`

- grupo: `novai-image-seedream-image-v5.0-lite` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://aigc-output-image-1326893053.cos.ap-guangzhou… |

### `seedream-image-v5.0-pro`

- grupo: `novai-image-seedream-image-v5.0-pro` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://aigc-output-image-1326893053.cos.ap-guangzhou… |

### `step-5-preview`

- grupo: `novai-step-5-preview` · modalidade: `chat`

| Sonda | Resultado |
|---|---|
| chat | ✅ finish=stop len(content)=2 |
| thinking | ✅ reasoning_chars=247 reasoning_tokens=0 |
| tools | ✅ tool=noop args_json_ok |

### `text-embedding-v4`

- grupo: `novai-embed-text-embedding-v4` · modalidade: `embedding`

| Sonda | Resultado |
|---|---|
| embedding | ✅ dim=1024 |

### `vidu-image-q2`

- grupo: `novai-image-vidu-image-q2` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=https://aigc-output-image-1326893053.cos.ap-guangzhou… |

### `wan2.2-t2i-flash`

- grupo: `novai-image-wan2.2-t2i-flash` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ❌ erro rede: HTTPConnectionPool(host='localhost', port=4000… |

### `wan2.5-t2i-preview`

- grupo: `novai-image-wan2.5-t2i-preview` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ❌ erro rede: HTTPConnectionPool(host='localhost', port=4000… |

### `wand-asr-v1`

- grupo: `novai-asr-wand-asr-v1` · modalidade: `asr`

| Sonda | Resultado |
|---|---|
| asr | ❌ requer arquivo de áudio (não sondado) |

### `wand-vega-image-flash`

- grupo: `novai-image-wand-vega-image-flash` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=http://data-shanghai-1378942524.cos.ap-shanghai.myqcl… |

### `wand-vega-image-lite`

- grupo: `novai-image-wand-vega-image-lite` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=http://data-shanghai-1378942524.cos.ap-shanghai.myqcl… |

### `wand-vega-image-pro`

- grupo: `novai-image-wand-vega-image-pro` · modalidade: `image`

| Sonda | Resultado |
|---|---|
| image | ✅ url=http://data-shanghai-1378942524.cos.ap-shanghai.myqcl… |

