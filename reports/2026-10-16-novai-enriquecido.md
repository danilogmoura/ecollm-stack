# NovAI — Catálogo enriquecido (todas as fontes cruzadas)

Fonte: `eval.novai_enrich` — cruza 5 fontes por modelo:

1. **`GET /models` do gateway direto** (`https://aiapi-pro.com`) — metadados reais: `owned_by` (provedor), `pricing`, `type`. O proxy LiteLLM mascara tudo como `owned_by: openai`, por isso usamos o upstream.
2. **Listas autoritativas por modalidade** — cada endpoint revela, no erro 400 (`Available: ...`), a lista de modelos daquela modalidade.
3. **JSON-LD schema.org** das páginas `/models/<slug>.html` — `brand`, `price`, `priceCurrency`, `availability`, `priceValidUntil`, `description`.
4. **Modelos fantasma** — páginas/listas que existem mas não aparecem no `/models`.
5. **Comandos da tag code** — exemplos cURL/Python/Node extraídos de cada página.

## Cobertura

| Fonte | Modelos com dado |
|---|---|
| Total de modelos | 124 |
| `owned_by` (gateway `/models`) | 121 |
| `type` (gateway `/models`) | 60 |
| Modalidade (via erro 400) | 57 |
| Página HTML baixada | 124 |
| JSON-LD com preço | 123 |
| Comandos de código extraídos | 246 |

## Provedores (`owned_by`)

| Provedor | Modelos |
|---|---|
| tencent | 27 |
| alibaba | 23 |
| minimax | 16 |
| zhipu | 14 |
| bytedance | 12 |
| novai | 11 |
| moonshot | 6 |
| deepseek | 4 |
| — | 3 |
| xiaomi | 3 |
| vidu | 3 |
| tripo | 2 |

## Tipos (`type` do gateway)

| Tipo | Modelos |
|---|---|
| — | 64 |
| video | 20 |
| image | 14 |
| audio | 13 |
| threed | 7 |
| embedding | 6 |

## Modalidades (via lista `Available:` do erro 400)

| Modalidade | Modelos |
|---|---|
| chat | 21 |
| image | 14 |
| audio | 11 |
| video | 9 |
| embedding | 6 |

## Modelos fantasma (fora do `/models`)

| ID | Modalidade | Tem página |
|---|---|---|
| `doubao-seedream-4.0` | — | sim |
| `doubao-seedream-4.5` | — | sim |
| `moonshot-v1-128k` | chat | sim |

## Tabela completa por modelo

| ID | Provedor | Tipo | Modalidade | Marca | Preço | Moeda | Disponível | Válido até | Comandos |
|---|---|---|---|---|---|---|---|---|---|
| `cogvideox-flash` | zhipu | video | video | Zhipu AI | 0 | USD | InStock | 2026-12-31 | 2 |
| `cogview-3-flash` | zhipu | image | image | Zhipu AI | 0 | USD | InStock | 2026-12-31 | 2 |
| `deepseek-v4-flash` | deepseek | — | chat | DeepSeek | 0.21 | USD | InStock | 2026-12-31 | 2 |
| `deepseek-v4-flash-vision` | deepseek | — | — | DeepSeek | 0.308 | USD | InStock | 2026-12-31 | 2 |
| `deepseek-v4-pro` | deepseek | — | chat | DeepSeek | 0.63 | USD | InStock | 2026-12-31 | 6 |
| `deepseek-v4.1-flash` | deepseek | — | — | DeepSeek | 0.308 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seed-2.0-code` | bytedance | — | chat | ByteDance | 0.45 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seed-2.0-lite` | bytedance | — | chat | ByteDance | 0.075 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seed-2.0-pro` | bytedance | — | chat | ByteDance | 0.40 | USD | InStock | 2026-12-31 | 6 |
| `doubao-seed-2.1-pro` | bytedance | — | — | ByteDance (Volcengine) | 0.4 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seed-2.1-turbo` | bytedance | — | — | ByteDance (Volcengine) | 0.15 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seedance-2.0` | bytedance | video | chat, video | ByteDance | 0.067 | USD | InStock | 2026-12-31 | 3 |
| `doubao-seedance-2.0-fast` | bytedance | video | chat, video | ByteDance | 0.054 | USD | InStock | 2026-12-31 | 1 |
| `doubao-seedance-2.5` | bytedance | video | video | ByteDance | 0.14 | USD | InStock | 2026-12-31 | 3 |
| `doubao-seedream-4.0` | — | — | — | ByteDance | 0.027 | USD | InStock | 2026-12-31 | 1 |
| `doubao-seedream-4.5` | — | — | — | ByteDance | 0.034 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seedream-5.0` | bytedance | image | chat, image | ByteDance | 0.027 | USD | InStock | 2026-12-31 | 2 |
| `doubao-seedream-5.0-pro` | bytedance | image | chat, image | ByteDance | 0.034 | USD | InStock | 2026-12-31 | 2 |
| `glm-4.1v-thinking-flash` | zhipu | — | — | Zhipu AI | 0 | USD | InStock | 2026-12-31 | 2 |
| `glm-4.6v` | zhipu | — | chat | Zhipu AI (智谱) | 0.10 | USD | InStock | 2026-12-31 | 2 |
| `glm-4.6v-flash` | zhipu | — | chat | Zhipu AI | 0 | USD | InStock | 2026-12-31 | 0 |
| `glm-4.7-flash` | zhipu | — | — | Zhipu AI | 0 | USD | InStock | 2026-12-31 | 2 |
| `glm-5` | zhipu | — | chat | Zhipu AI | 0.67 | USD | InStock | 2026-12-31 | 2 |
| `glm-5-turbo` | zhipu | — | — | Zhipu AI | 1.08 | USD | InStock | 2026-12-31 | 2 |
| `glm-5.1` | zhipu | — | chat | Zhipu AI | 1.01 | USD | InStock | 2026-12-31 | 2 |
| `glm-5.2` | zhipu | — | chat | Zhipu AI | 1.34 | USD | InStock | 2026-12-31 | 2 |
| `glm-5.3` | zhipu | — | — | Zhipu AI | 1.25 | USD | InStock | 2026-12-31 | 2 |
| `glm-5.3-flash` | zhipu | — | — | Zhipu AI | 0.08 | USD | InStock | 2026-12-31 | 2 |
| `glm-5.3-flashx` | zhipu | — | — | NovAI | 0.12 | USD | — | — | 2 |
| `glm-5v-turbo` | zhipu | — | chat | Zhipu AI (智谱) | 1.08 | USD | InStock | 2026-12-31 | 2 |
| `hunyuan-role` | tencent | — | — | Tencent Hunyuan | 0.47 | USD | InStock | 2026-12-31 | 2 |
| `hunyuan-t1-vision` | tencent | — | — | Tencent | 0.55 | USD | InStock | 2026-12-31 | 2 |
| `hunyuan-turbos-vision-video` | tencent | — | — | Tencent | 0.462 | USD | InStock | 2026-12-31 | 2 |
| `hy-3d-3.0` | tencent | threed | — | Tencent | 0.369 | USD | InStock | 2026-12-31 | 2 |
| `hy-3d-3.1` | tencent | threed | — | Tencent | 0.369 | USD | InStock | 2026-12-31 | 2 |
| `hy-3d-express` | tencent | threed | — | Tencent | 0.277 | USD | InStock | 2026-12-31 | 2 |
| `hy-3d-motion` | tencent | threed | — | Tencent | 0.185 | USD | InStock | 2026-12-31 | 2 |
| `hy-3d-polygen-image` | tencent | threed | — | Tencent | 0.554 | USD | InStock | 2026-12-31 | 2 |
| `hy-asr-3.0-preview` | tencent | audio | — | Tencent (Hunyuan) | 1.54 | USD | InStock | 2026-12-31 | 3 |
| `hy-image-v3` | tencent | image | image | Tencent (Hunyuan) | 0.031 | USD | InStock | 2026-12-31 | 2 |
| `hy-mt2-lite` | tencent | — | — | Tencent | 0.043 | USD | InStock | 2026-12-31 | 2 |
| `hy-mt2-plus` | tencent | — | — | Tencent | 0.072 | USD | InStock | 2026-12-31 | 2 |
| `hy-mt2-pro` | tencent | — | — | Tencent Hunyuan | 0.29 | USD | InStock | 2026-12-31 | 2 |
| `hy-role` | tencent | — | — | Tencent | 0.369 | USD | InStock | 2026-12-31 | 2 |
| `hy-video-v1.5` | tencent | video | video | Tencent | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `hy-vision-2.0-instruct` | tencent | — | — | Tencent | 1.154 | USD | InStock | 2026-12-31 | 2 |
| `hy3` | tencent | — | — | Tencent Hunyuan | 0.18 | USD | InStock | 2026-12-31 | 2 |
| `hy3-preview` | tencent | — | — | Tencent Hunyuan | 0.13 | USD | InStock | 2026-12-31 | 2 |
| `hy4-preview` | tencent | — | — | Tencent | 0.834 | USD | InStock | 2026-12-31 | 2 |
| `kimi-k2.5` | moonshot | — | — | Moonshot AI | 0.64 | USD | InStock | 2026-12-31 | 2 |
| `kimi-k2.6` | moonshot | — | — | Moonshot AI | 1.04 | USD | InStock | 2026-12-31 | 2 |
| `kimi-k2.7-code` | moonshot | — | — | Moonshot AI | 1.04 | USD | InStock | 2026-12-31 | 2 |
| `kimi-k2.7-code-highspeed` | moonshot | — | — | Moonshot AI | 2.07 | USD | InStock | 2026-12-31 | 2 |
| `kimi-k2.8-preview` | moonshot | — | — | Moonshot | 0.93 | USD | InStock | 2026-12-31 | 2 |
| `kimi-k3` | moonshot | — | — | Moonshot AI | 2.90 | USD | InStock | 2026-12-31 | 2 |
| `kinfra-text-embedding-0.6b` | tencent | embedding | embedding | Tencent (Kinfra) | 0.0769 | USD | InStock | 2026-12-31 | 2 |
| `kinfra-text-embedding-4b` | tencent | embedding | embedding | Tencent (Kinfra) | 0.0923 | USD | InStock | 2026-12-31 | 2 |
| `kinfra-vl-embedding-2b` | tencent | embedding | embedding | Tencent (Kinfra) | 0.0769 | USD | InStock | 2026-12-31 | 2 |
| `kinfra-vl-embedding-8b` | tencent | embedding | embedding | Tencent (Kinfra) | 0.0923 | USD | InStock | 2026-12-31 | 2 |
| `kling-video-o1` | novai | video | — | Kuaishou Kling | 1.54 | USD | InStock | — | 2 |
| `kling-video-v2.5-turbo` | novai | video | — | Kuaishou Kling | 1.54 | USD | InStock | — | 2 |
| `kling-video-v2.6` | novai | video | — | Kuaishou Kling | 1.54 | USD | InStock | — | 2 |
| `kling-video-v3` | novai | video | — | Kuaishou Kling | 1.54 | USD | InStock | — | 2 |
| `kling-video-v3-omni` | novai | video | — | Kuaishou Kling | 1.54 | USD | InStock | — | 2 |
| `kling-video-v3-turbo` | novai | video | — | Kuaishou Kling | 1.54 | USD | InStock | — | 2 |
| `mimo-v2.5-pro` | xiaomi | — | — | Xiaomi | 0.427 | USD | InStock | 2026-12-31 | 2 |
| `mimo-v2.6-flash` | xiaomi | — | — | NovAI | 0.10 | USD | — | — | 2 |
| `mimo-v2.6-pro` | xiaomi | — | — | NovAI | 0.43 | USD | — | — | 2 |
| `minimax-m2.5` | minimax | — | — | MiniMax | 0.28 | USD | InStock | 2026-12-31 | 2 |
| `minimax-m2.7` | minimax | — | — | MiniMax | 0.30 | USD | InStock | 2026-12-31 | 2 |
| `minimax-m3` | minimax | — | — | MiniMax | 0.35 | USD | InStock | 2026-12-31 | 2 |
| `minimax-music-v2.6` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 1 |
| `minimax-music-v3.0` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 1 |
| `minimax-speech-02-hd` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-speech-02-turbo` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-speech-2.6-hd` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-speech-2.6-turbo` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-speech-2.8-hd` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-speech-2.8-turbo` | minimax | audio | audio | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-text-01` | minimax | — | chat | MiniMax | 0.20 | USD | InStock | 2026-12-31 | 2 |
| `minimax-video-h3` | minimax | video | video | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-video-h3-max` | minimax | video | video | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-video-v2.3` | minimax | video | video | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `minimax-video-v2.3-fast` | minimax | video | video | MiniMax | 1.54 | USD | InStock | 2026-12-31 | 2 |
| `moonshot-v1-128k` | — | — | chat | — | — | — | — | — | 0 |
| `pixverse-video-c1` | novai | video | — | PixVerse | 1.54 | USD | InStock | — | 2 |
| `pixverse-video-v5.6` | novai | video | — | PixVerse | 1.54 | USD | InStock | — | 2 |
| `pixverse-video-v6.0` | novai | video | — | PixVerse | 1.54 | USD | InStock | — | 2 |
| `qwen-image` | alibaba | image | image | Alibaba Cloud | 0.0385 | USD | InStock | 2026-12-31 | 2 |
| `qwen-image-plus` | alibaba | image | image | Alibaba Cloud | 0.0308 | USD | InStock | 2026-12-31 | 2 |
| `qwen-mt-plus` | alibaba | — | — | Alibaba Cloud | 0.25 | USD | InStock | 2026-12-31 | 2 |
| `qwen-omni-turbo` | novai | — | — | NovAI | 0.30 | USD | — | — | 2 |
| `qwen-plus` | alibaba | — | chat | Alibaba Cloud | 0.26 | USD | InStock | 2026-12-31 | 2 |
| `qwen-tts` | alibaba | audio | audio | Alibaba Cloud | 0.013 | USD | InStock | 2026-12-31 | 2 |
| `qwen-tts-latest` | alibaba | audio | audio | Alibaba Cloud | 0.013 | USD | InStock | 2026-12-31 | 2 |
| `qwen-vl-max` | alibaba | — | — | Alibaba Cloud | 0.8 | USD | InStock | 2026-12-31 | 2 |
| `qwen-vl-ocr` | alibaba | — | — | Alibaba Cloud | 0.7 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-coder-flash` | alibaba | — | — | Alibaba Cloud | 0.15 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-coder-plus` | alibaba | — | — | Alibaba Cloud | 0.65 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-max` | alibaba | — | chat | Alibaba Cloud | 0.33 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-omni-flash` | alibaba | — | — | Alibaba Cloud | 0.15 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-tts-flash` | alibaba | audio | audio | Alibaba Cloud | 0.0145 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-vl-flash` | alibaba | — | — | Alibaba Cloud | 0.08 | USD | InStock | 2026-12-31 | 2 |
| `qwen3-vl-plus` | alibaba | — | — | Alibaba Cloud | 0.21 | USD | InStock | 2026-12-31 | 2 |
| `qwen3.5-ocr` | alibaba | — | — | Alibaba Cloud | 0.7 | USD | InStock | 2026-12-31 | 2 |
| `qwen3.6-max-preview` | alibaba | — | chat | Alibaba | 1.03 | USD | InStock | 2026-12-31 | 0 |
| `qwen3.7-max` | alibaba | — | chat | Alibaba | 1.16 | USD | InStock | 2026-12-31 | 0 |
| `qwen3.7-text-embedding` | alibaba | embedding | embedding | Alibaba Cloud | 0.11 | USD | InStock | 2026-12-31 | 2 |
| `qwen3.8-max` | alibaba | — | — | Alibaba | 1.84 | USD | InStock | 2026-12-31 | 0 |
| `seedream-image-v5.0-lite` | bytedance | image | image | ByteDance (Seedream) | 0.034 | USD | InStock | 2026-12-31 | 2 |
| `seedream-image-v5.0-pro` | bytedance | image | image | ByteDance (Seedream) | 0.046 | USD | InStock | 2026-12-31 | 2 |
| `step-5-preview` | novai | — | — | NovAI | 0.40 | USD | — | — | 2 |
| `text-embedding-v4` | alibaba | embedding | embedding | Alibaba Cloud | 0.08 | USD | InStock | 2026-12-31 | 2 |
| `tripo-3d-3.1` | tripo | threed | — | Tripo | 0.323 | USD | InStock | 2026-12-31 | 2 |
| `tripo-3d-p1` | tripo | threed | — | Tripo | 0.323 | USD | InStock | 2026-12-31 | 2 |
| `vidu-image-q2` | vidu | image | image | Vidu (Shengshu) | 0.029 | USD | InStock | 2026-12-31 | 2 |
| `vidu-video-q3` | vidu | video | — | Vidu Shengshu | 1.54 | USD | InStock | — | 2 |
| `vidu-video-q3-pro` | vidu | video | — | Vidu Shengshu | 1.54 | USD | InStock | — | 2 |
| `wan2.2-t2i-flash` | alibaba | image | image | Alibaba Cloud | 0.0215 | USD | InStock | 2026-12-31 | 2 |
| `wan2.5-t2i-preview` | alibaba | image | image | Alibaba Cloud | 0.0308 | USD | InStock | 2026-12-31 | 2 |
| `wand-asr-v1` | tencent | audio | — | Tencent (WAND) | 1.54 | USD | InStock | 2026-12-31 | 3 |
| `wand-vega-image-flash` | tencent | image | image | Tencent (WAND Vega) | 0.069 | USD | InStock | 2026-12-31 | 2 |
| `wand-vega-image-lite` | tencent | image | image | Tencent (WAND Vega) | 0.025 | USD | InStock | 2026-12-31 | 2 |
| `wand-vega-image-pro` | tencent | image | image | Tencent (WAND Vega) | 0.146 | USD | InStock | 2026-12-31 | 2 |

## Comandos de código por linguagem

| Tipo | Total |
|---|---|
| curl | 152 |
| python | 93 |
| other | 1 |

## Testes de execução dos comandos (`--test-code`)

- Modelos com testes: **119**
- Comandos executados: **246** (ok: 95, falha: 151)

| Motivo | Total |
|---|---|
| só cURL é executado (segurança) | 94 |
| sem motivo | 36 |
| timeout | 20 |
| 'utf-8' codec can't decode byte 0xbf in position 4: invalid start byte | 1 |

> Nota: apenas comandos `curl` são executados (segurança); exemplos Python/Node são extraídos mas não rodados. `ok` reflete apenas o exit code do `curl` — erros de upstream (ex.: 429) ainda retornam `ok: true` com o erro no `stdout`.
