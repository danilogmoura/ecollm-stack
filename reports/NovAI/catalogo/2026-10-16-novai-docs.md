# NovAI — Documentação da API (scrape)

Fonte: `https://aiapi-pro.com/docs`
Título: NovAI API Documentation - OpenAI-Compatible China AI API
Seções: **66** · Tabelas: **18** · Blocos de código: **33**

## Índice

- [Overview](#overview)
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Available Models](#models)
  - Chat Models
  - Embedding Models
  - Quick Start Example
- [API Playground TRY FREE — NO SIGNUP](#playground)
- [Chat Completions](#chat-completions)
  - Request Body
  - Message Object
  - Example Request
  - Example Response
- [Responses API NEW — EXCLUSIVE](#responses-api)
  - Request Body
  - Example: Simple Request
  - Example: Conversation with Instructions
  - Example Response
  - Compatible Tools
- [Embeddings NEW](#embeddings)
  - Available models
  - Request Body
  - Example Request (text)
  - Example Request (multimodal)
  - Example Response
- [Image Generation NEW](#images-generations)
  - Available models
  - Request Body
  - Example Request (text-to-image)
  - Example Request (image editing)
  - Example Response
- [Audio NEW](#audio)
  - Speech & music models — POST /v1/audio/speech
  - Transcription models — POST /v1/audio/transcriptions
  - Speech request body
  - Example Request (TTS → audio URL)
  - Example Response (response_format=url)
  - Example Request (transcription)
  - Example Response (transcription)
- [Video Generation NEW](#video-generations)
  - Available models
  - Submit request body
  - Example Request (text-to-video)
  - Example Request (image-to-video)
  - Example Response (submit)
  - Poll the task
  - Example Response (poll, completed)
- [3D Generation NEW](#three-d-generations)
  - Available models
  - Submit request body
  - Example Request (text-to-3D)
  - Example Request (image-to-3D)
  - Example Response (submit)
  - Poll the task
  - Example Response (poll, completed)
- [Streaming](#streaming)
- [List Models](#list-models)
- [Error Codes](#errors)
- [Rate Limits](#rate-limits)
- [SDKs & Libraries](#sdks)
  - Python
  - Node.js
  - LangChain
  - Cursor IDE / Continue
- [Supported Email Providers](#email-providers)
  - Leave us a message

### Overview

NovAI is an AI API gateway based in Hong Kong, offering low-latency access to Chinese AI models through a unified, OpenAI-compatible interface.

> ⚠️ NovAI supports both the Chat Completions API ( /v1/chat/completions ) and the new Responses API ( /v1/responses ). We are the only platform offering Responses API access to Chinese AI models.

### Authentication

All API requests require an API key passed via the Authorization header: Authorization: Bearer nvai-your-api-key-here Get your API key by signing up at aiapi-pro.com . Registration requires only an email address.

```
Authorization: Bearer nvai-your-api-key-here
```

### Base URL

https://aiapi-pro.com/v1 Replace https://api.openai.com/v1 with the URL above in any existing OpenAI integration.

```
https://aiapi-pro.com/v1
```

### Available Models

> ⚠️ Free model available! Start building immediately with GLM-4.6V-Flash — no credit card required. Click model ID to copy.

#### Chat Models

| Model ID (click to copy) | Provider | Input | Output | Context | Notes |
|---|---|---|---|---|---|
| glm-4.6v-flash | Zhipu AI | Free | Free | 128K | Free multimodal FREE |
| glm-5 | Zhipu AI | $0.60/1M | $1.92/1M | 128K | Multimodal flagship |
| glm-5.1 | Zhipu AI | $1.05/1M | $3.96/1M | 128K | 8-hour autonomous coding |
| glm-5.2 | Zhipu AI | $1.19/1M | $3.74/1M | 1M | 1M context flagship NEW |
| glm-5.3 | Zhipu AI | $1.25/1M | $4.00/1M | 1M | Newest flagship, coding & agents NEW |
| glm-5v-turbo | Zhipu AI | $1.08/1M | $3.69/1M | 128K | Vision + coding multimodal NEW |
| minimax-text-01 | MiniMax | $0.14/1M | $1.10/1M | 1M | 1M context window |
| glm-4.6v | Zhipu AI | $0.30/1M | $0.90/1M | 128K | Multimodal vision |
| hy4-preview | Tencent | $0.834/1M | $2.501/1M | 1M | Next-gen flagship preview NEW |
| glm-5.3-flash | Zhipu AI | $0.08/1M | $0.28/1M | 1M | Budget flagship, coding & agents NEW |
| kimi-k2.8-preview | Moonshot | $0.93/1M | $3.89/1M | 256K | Next-gen agentic reasoning preview NEW |
| mimo-v2.5-pro | Xiaomi | $0.427/1M | $0.855/1M | 1M | Xiaomi flagship reasoning, 1M context NEW |
| hunyuan-t1-vision | Tencent | $0.55/1M | $1.64/1M | — | HY-Vision-1.5-Thinking, deep-reasoning vision NEW |
| hy-mt2-plus | Tencent | $0.072/1M | $0.287/1M | 8K | Machine translation, 30+ languages NEW |
| hy-mt2-lite | Tencent | $0.043/1M | $0.172/1M | 8K | Budget machine translation NEW |
| hy-vision-2.0-instruct | Tencent | $1.154/1M | $2.692/1M | — | Fast multimodal vision-language (OCR, VQA) NEW |
| hunyuan-turbos-vision-video | Tencent | $0.462/1M | $1.385/1M | — | Image & video frame understanding NEW |
| hy-role | Tencent | $0.369/1M | $1.477/1M | 32K | Role-play & character model NEW |
| deepseek-v4.1-flash | DeepSeek | $0.308/1M | $1.231/1M | 128K | Fast reasoning LLM for chat & agents NEW |
| deepseek-v4-flash-vision | DeepSeek | $0.308/1M | $1.231/1M | 128K | Fast vision-language (experimental) NEW |

#### Embedding Models

| Model ID (click to copy) | Provider | Input | Modality | Dims | Notes |
|---|---|---|---|---|---|
| kinfra-text-embedding-4b | Tencent | $0.0923/1M | Text | 2560 | High-quality text vectors for RAG & search NEW |
| kinfra-text-embedding-0.6b | Tencent | $0.0769/1M | Text | 1024 | Fast, compact text vectors NEW |
| kinfra-vl-embedding-8b | Tencent | $0.0923/1M | Multimodal | — | Text + image + video vectors NEW |
| kinfra-vl-embedding-2b | Tencent | $0.0769/1M | Multimodal | — | Fast multimodal vectors NEW |

#### Quick Start Example

```
curl https://aiapi-pro.com/v1/chat/completions \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-4.6v-flash",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### API Playground TRY FREE — NO SIGNUP

Test the API right here in your browser. Uses the free GLM-4.6V-Flash model — no API key required.

### Chat Completions

`POST /v1/chat/completions`

POST /v1/chat/completions Creates a model response for the given conversation.

#### Request Body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | Model ID to use (see table above) |
| messages | array | Required | List of messages in the conversation |
| temperature | float | Optional | Sampling temperature (0-2). Default: 1.0 |
| max_tokens | integer | Optional | Maximum tokens to generate |
| stream | boolean | Optional | Enable streaming responses. Default: false |
| top_p | float | Optional | Nucleus sampling parameter. Default: 1.0 |

#### Message Object

| Field | Type | Description |
|---|---|---|
| role | string | system , user , or assistant |
| content | string | The message content |

#### Example Request

```
curl https://aiapi-pro.com/v1/chat/completions \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

#### Example Response

```
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1709942400,
  "model": "glm-5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 9,
    "total_tokens": 29
  }
}
```

### Responses API NEW — EXCLUSIVE

`POST /v1/responses`

POST /v1/responses NovAI is the first and only API platform supporting OpenAI's new Responses API for Chinese AI models. This enables tools like Open Cowork, OpenAI Agents SDK, and any Responses API-based application to use GLM-5, MiniMax, and more China-exclusive models.

> ⚠️ Why this matters: Chinese AI providers (Zhipu, MiniMax) only support the legacy /v1/chat/completions endpoint. NovAI automatically translates Responses API format to Chat Completions format, making Chinese models accessible to all modern agent tools.

#### Request Body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | Model ID to use |
| input | string \| array | Required | Text prompt or message array |
| instructions | string | Optional | System instructions for the model |
| stream | boolean | Optional | Enable SSE streaming. Default: false |
| temperature | float | Optional | Sampling temperature (0-2). Default: 0.7 |
| max_output_tokens | integer | Optional | Maximum tokens to generate |
| tools | array | Optional | Function/tool definitions |
| tool_choice | string | Optional | auto , required , or none |

#### Example: Simple Request

```
curl https://aiapi-pro.com/v1/responses \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5",
    "input": "Explain quantum computing simply.",
    "stream": false
  }'
```

#### Example: Conversation with Instructions

```
curl https://aiapi-pro.com/v1/responses \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5",
    "instructions": "You are a senior code reviewer.",
    "input": [
      {"role": "user", "content": "Review: def add(a,b): return a+b"}
    ],
    "stream": true
  }'
```

#### Example Response

```
{
  "id": "resp_abc123...",
  "object": "response",
  "status": "completed",
  "model": "glm-5",
  "output": [
    {
      "type": "message",
      "role": "assistant",
      "content": [
        {"type": "output_text", "text": "Quantum computing uses..."}
      ]
    }
  ],
  "usage": {
    "input_tokens": 12,
    "output_tokens": 150,
    "total_tokens": 162
  }
}
```

#### Compatible Tools

The following tools work out of the box with NovAI's Responses API endpoint: Read the full guide: Responses API for Chinese Models →

### Embeddings NEW

`POST /v1/embeddings`

POST /v1/embeddings Creates a vector representation of the input, powered by Tencent Kinfra embedding models. Text models return 1024–2560 dimension vectors; multimodal (VL) models embed text, images and video in one shared space for cross-modal retrieval.

#### Available models

| Model | Modality | Dimensions | Price / 1M input tokens |
|---|---|---|---|
| kinfra-text-embedding-4b | Text | 2560 | $0.0923 |
| kinfra-text-embedding-0.6b | Text | 1024 | $0.0769 |
| kinfra-vl-embedding-8b | Multimodal (text + image + video) | — | $0.0923 |
| kinfra-vl-embedding-2b | Multimodal (text + image + video) | — | $0.0769 |

#### Request Body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | Embedding model ID (see table above) |
| input | string \| array | Required | Text models: a string or list of strings. Multimodal (VL) models: an object array such as [{"type":"text","text":"..."}] or [{"type":"image_url","image_url":"..."}] |

#### Example Request (text)

```
curl https://aiapi-pro.com/v1/embeddings \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kinfra-text-embedding-4b",
    "input": "The quick brown fox"
  }'
```

#### Example Request (multimodal)

```
curl https://aiapi-pro.com/v1/embeddings \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kinfra-vl-embedding-8b",
    "input": [{"type": "text", "text": "a cat sitting on a mat"}]
  }'
```

#### Example Response

{ "object": "list", "data": [ {"object": "embedding", "index": 0, "embedding": [0.0023, -0.0091, ...]} ], "model": "kinfra-text-embedding-4b", "usage": {"prompt_tokens": 5, "total_tokens": 5} } Billing: only input tokens are charged (at the per-1M rate above); the returned vectors are free.

```
{
  "object": "list",
  "data": [
    {"object": "embedding", "index": 0, "embedding": [0.0023, -0.0091, ...]}
  ],
  "model": "kinfra-text-embedding-4b",
  "usage": {"prompt_tokens": 5, "total_tokens": 5}
}
```

### Image Generation NEW

`POST /v1/images/generations`

POST /v1/images/generations Generates images from a text prompt, powered by Tencent Hunyuan, Vidu, ByteDance Seedream and WAND Vega image models via the TokenHub gateway. Returns an OpenAI-compatible {created, data:[{url}]} response. Even for models that are asynchronous upstream, NovAI polls to completion internally and returns the final image URL synchronously.

#### Available models

> ⚠️ TokenHub image models are billed by actual upstream token usage ( usage.total_tokens × token price), not a flat per-image fee. The per-image prices above are reference values at base resolution and scale with resolution and reference-image count. Legacy flat-price models ( doubao-seedream-4.5 , doubao-seedream-4.0 , cogview-3-flash ) keep their original pricing.

| Model | Vendor | Max size | Reference images | Reference price / image |
|---|---|---|---|---|
| hy-image-v3 | Tencent Hunyuan | ≤1024² | 0–3 | ~$0.031 |
| vidu-image-q2 | Vidu (Shengshu) | 1080p–4K | 0–7 | from ~$0.029 |
| seedream-image-v5.0-pro | ByteDance Seedream | 1K–2K | ≤10 | from ~$0.046 |
| seedream-image-v5.0-lite | ByteDance Seedream | 2K–4K | ≤14 | ~$0.034 |
| wand-vega-image-lite | Tencent WAND Vega | 1K–4K | 0–3 | from ~$0.025 |
| wand-vega-image-flash | Tencent WAND Vega | 1K–4K | 0–6 | from ~$0.069 |
| wand-vega-image-pro | Tencent WAND Vega | 1K–4K | 0–6 | from ~$0.146 |

#### Request Body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | Image model ID (see table above) |
| prompt | string | Required | Text description of the image to generate |
| n | integer | Optional | Number of images to generate (1–4, default 1) |
| size | string | Optional | Image size as WxH (e.g. 1024x1024 ). Mapped to each vendor's allowed sizes / aspect ratios. |
| images | string \| array | Optional | Reference image URL(s) for image-to-image editing (count limit varies by model) |

#### Example Request (text-to-image)

```
curl https://aiapi-pro.com/v1/images/generations \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hy-image-v3",
    "prompt": "a cute orange cat on a windowsill, soft sunlight",
    "size": "1024x1024",
    "n": 1
  }'
```

#### Example Request (image editing)

```
curl https://aiapi-pro.com/v1/images/generations \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "vidu-image-q2",
    "prompt": "change the background to a snowy mountain",
    "images": ["https://example.com/input.jpg"],
    "size": "1024x1024"
  }'
```

#### Example Response

{ "created": 1730000000, "data": [ {"url": "https://.../generated-image.png"} ], "usage": {"total_tokens": 20000} } Billing: the response usage.total_tokens reflects the real upstream token count; the charge is total_tokens / 1000 × token_price . For example, hy-image-v3 at 1024² returns ~20000 tokens ≈ $0.031. Async upstream models (Vidu, WAND Vega) are polled to completion (up to ~180s) before the URL is returned.

```
{
  "created": 1730000000,
  "data": [
    {"url": "https://.../generated-image.png"}
  ],
  "usage": {"total_tokens": 20000}
}
```

### Audio NEW

Two OpenAI-compatible audio endpoints powered by MiniMax and Tencent models via the TokenHub gateway: /v1/audio/speech (text → audio: TTS + music) and /v1/audio/transcriptions (audio → text: ASR). Both are synchronous.

#### Speech & music models — POST /v1/audio/speech

| Model | Vendor | Type | Reference cost |
|---|---|---|---|
| minimax-speech-2.8-hd | MiniMax | TTS (flagship) | ~$0.054 / 1K chars |
| minimax-speech-2.8-turbo | MiniMax | TTS (fast) | ~$0.031 / 1K chars |
| minimax-speech-2.6-hd | MiniMax | TTS | ~$0.054 / 1K chars |
| minimax-speech-2.6-turbo | MiniMax | TTS (fast) | ~$0.031 / 1K chars |
| minimax-speech-02-hd | MiniMax | TTS | ~$0.054 / 1K chars |
| minimax-speech-02-turbo | MiniMax | TTS (fast) | ~$0.031 / 1K chars |
| minimax-music-v3.0 | MiniMax | Music (lyrics→song) | ~$0.154 / song |
| minimax-music-v2.6 | MiniMax | Music (lyrics→song) | ~$0.154 / song |

#### Transcription models — POST /v1/audio/transcriptions

> ⚠️ All audio models are billed by actual upstream token usage at $1.54 / 1M tokens (10元/M upstream — the same rate as image and video). The per-unit prices above are references: TTS scales with text length (~20–35 tokens/char), music is ~100k tokens/song, ASR scales with audio duration.

| Model | Vendor | Features | Reference cost |
|---|---|---|---|
| hy-asr-3.0-preview | Tencent Hunyuan | Timestamps, SRT subtitles | ~$0.003 / min audio |
| wand-asr-v1 | Tencent WAND | Multilingual, language detection | ~$0.007 / min audio |

#### Speech request body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | Speech or music model ID (see tables above) |
| input | string | Required | Text to speak (TTS). For music models pass lyrics and prompt instead. |
| voice | string | Optional | Voice ID (TTS). Default male-qn-qingse . |
| response_format | string | Optional | mp3 (default, binary audio), wav / opus / aac / flac / pcm , or url (NovAI extension: JSON with an audio_url ). |
| speed / vol / pitch / emotion | number/string | Optional | Voice tweaks (TTS): speed 0.5–2, vol 0–10, pitch −12–12. |
| lyrics / prompt | string | Optional | Music models only: song lyrics and style prompt. |

#### Example Request (TTS → audio URL)

```
curl https://aiapi-pro.com/v1/audio/speech \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "minimax-speech-2.8-hd",
    "input": "Hello, welcome to NovAI.",
    "voice": "male-qn-qingse",
    "response_format": "url"
  }'
```

#### Example Response (response_format=url)

{ "id": "audgen-...", "model": "minimax-speech-2.8-hd", "status": "completed", "audio_url": "https://.../speech/....mp3", "usage": {"total_tokens": 1505, "characters": 43} } With the default response_format=mp3 the endpoint instead streams raw audio bytes ( Content-Type: audio/mpeg ), exactly like OpenAI’s native /v1/audio/speech — so the OpenAI SDK works unchanged.

```
{
  "id": "audgen-...",
  "model": "minimax-speech-2.8-hd",
  "status": "completed",
  "audio_url": "https://.../speech/....mp3",
  "usage": {"total_tokens": 1505, "characters": 43}
}
```

#### Example Request (transcription)

```
# JSON form: transcribe from a URL
curl https://aiapi-pro.com/v1/audio/transcriptions \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "wand-asr-v1", "file_url": "https://example.com/audio.mp3"}'

# OpenAI multipart form: upload a file
curl https://aiapi-pro.com/v1/audio/transcriptions \
  -H "Authorization: Bearer nvai-your-key" \
  -F model=hy-asr-3.0-preview \
  -F [email protected]
```

#### Example Response (transcription)

{ "text": "Hello, welcome to NovAI.", "language": "en", "duration_ms": 2426, "sentences": [{"begin_ms": 0, "end_ms": 2426, "text": "Hello, welcome to NovAI."}], "subtitle_url": "https://.../....srt", "usage": {"total_tokens": 121} } Billing: the charge is usage.total_tokens / 1000 × token_price (token_price = $0.0015385/1K). Transcription accepts either a multipart file upload (OpenAI-native) or a JSON file_url / base64 data field.

```
{
  "text": "Hello, welcome to NovAI.",
  "language": "en",
  "duration_ms": 2426,
  "sentences": [{"begin_ms": 0, "end_ms": 2426, "text": "Hello, welcome to NovAI."}],
  "subtitle_url": "https://.../....srt",
  "usage": {"total_tokens": 121}
}
```

### Video Generation NEW

`POST /v1/video/generations`

POST /v1/video/generations + GET /v1/video/generations/{id} Generates video from a text prompt (and optional source image), powered by MiniMax Hailuo and Tencent Hunyuan video models via the TokenHub gateway. Video generation is asynchronous : submit a task to get an id , then poll the GET endpoint until status is succeeded (the mp4 is in video_url ) or failed (auto-refunded).

#### Available models

> ⚠️ TokenHub video models are billed by actual upstream token usage at $1.54 / 1M tokens (10元/M upstream — the same rate as image and audio). The per-second values above are references. At submit an estimate ( tokens/s × duration ) is pre-deducted; when the task succeeds the charge is reconciled to the real tokenhub_usage.total_tokens (over-estimate refunded, under-estimate topped up). Per-second-billed models ( doubao-seedance-2.5 , doubao-seedance-2.0 , doubao-seedance-2.0-fast ) and the free cogvideox-flash are also served by this endpoint and keep their original pricing.

| Model | Vendor | Capabilities | Resolution | Reference tokens/s | Reference cost |
|---|---|---|---|---|---|
| minimax-video-h3 | MiniMax (海螺) | T2V | 768P/1080P | ~50,000 | ~$0.077/s · $0.385/5s |
| minimax-video-h3-max | MiniMax (海螺) | T2V (top quality) | 768P/1080P | ~50,000 | ~$0.077/s · $0.385/5s |
| minimax-video-v2.3 | MiniMax (海螺) | T2V | 768P/1080P | ~40,000 | ~$0.062/s · $0.308/5s |
| minimax-video-v2.3-fast | MiniMax (海螺) | I2V only | 768P/1080P | ~27,000 | ~$0.042/s · $0.208/5s |
| hy-video-v1.5 | Tencent Hunyuan | T2V + I2V | 720p/1080p | ~30,000 | ~$0.046/s · $0.231/5s |

#### Submit request body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | Video model ID (see table above) |
| prompt | string | Required | Text description of the video to generate |
| image | string | Optional | Source image URL for image-to-video. Required for minimax-video-v2.3-fast (I2V-only). |
| duration | number | Optional | Clip length in seconds (default 5) |
| resolution | string | Optional | 720p / 1080p (MiniMax maps these to 768P/1080P). Default 720p. |
| ratio | string | Optional | Aspect ratio, e.g. 16:9 (default), 9:16 , 1:1 |

#### Example Request (text-to-video)

```
curl https://aiapi-pro.com/v1/video/generations \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "minimax-video-h3",
    "prompt": "A red sports car driving along a coastal road at sunset, cinematic",
    "resolution": "720p",
    "duration": 5,
    "ratio": "16:9"
  }'
```

#### Example Request (image-to-video)

```
curl https://aiapi-pro.com/v1/video/generations \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hy-video-v1.5",
    "prompt": "Animate this scene with smooth cinematic motion",
    "image": "https://example.com/first-frame.jpg",
    "duration": 5
  }'
```

#### Example Response (submit)

```
{
  "id": "<task_id>",
  "status": "queued",
  "model": "minimax-video-h3",
  "resolution": "720p",
  "duration": 5
}
```

#### Poll the task

```
curl "https://aiapi-pro.com/v1/video/generations/<task_id>?model=minimax-video-h3" \
  -H "Authorization: Bearer nvai-your-key"
```

#### Example Response (poll, completed)

{ "id": "<task_id>", "status": "succeeded", "video_url": "https://.../output.mp4", "video_result": [{"url": "https://.../output.mp4"}], "duration": 5, "tokenhub_usage": {"total_tokens": 250000}, "novai_token_settlement": { "prepaid_usd": 0.384625, "actual_usd": 0.384625, "adjustment_usd": 0.0, "total_tokens": 250000 } } Billing: while status is queued / processing keep polling (generation typically takes 1–5 minutes). On succeeded the pre-deducted estimate is reconciled to the real token count and novai_token_settlement reports the adjustment. On failed / cancelled the pre-deducted amount is automatically refunded.

```
{
  "id": "<task_id>",
  "status": "succeeded",
  "video_url": "https://.../output.mp4",
  "video_result": [{"url": "https://.../output.mp4"}],
  "duration": 5,
  "tokenhub_usage": {"total_tokens": 250000},
  "novai_token_settlement": {
    "prepaid_usd": 0.384625, "actual_usd": 0.384625,
    "adjustment_usd": 0.0, "total_tokens": 250000
  }
}
```

### 3D Generation NEW

`POST /v1/three_d/generations`

POST /v1/three_d/generations + GET /v1/three_d/generations/{id} Generates a 3D model (mesh) from a text prompt and/or a source image, powered by Tencent Hunyuan 3D and Tripo (VAST) models via the TokenHub gateway. 3D generation is asynchronous : submit a task to get an id , then poll the GET endpoint until status is succeeded (downloadable model URLs are in outputs , primary in model_url ) or failed (auto-refunded).

#### Available models

> ⚠️ Unlike image/video/audio (which are billed by upstream token usage), TokenHub 3D models are billed upstream by credits and return no token usage on query. NovAI therefore charges a flat per-generation price (default tier): the full price is pre-deducted at submit and refunded in full if the job fails or is cancelled — you only pay for successful generations. Only the default generation mode is exposed (no PBR / high-poly / extra-format upcharges), so the flat price always matches the upstream cost.

| Model | Vendor | Input | Output formats | Price / generation |
|---|---|---|---|---|
| hy-3d-express | Tencent Hunyuan | Text / Image | obj (zip) | $0.277 |
| hy-3d-3.0 | Tencent Hunyuan | Text / Image | obj (zip) + glb | $0.369 |
| hy-3d-3.1 | Tencent Hunyuan | Text / Image | obj (zip) + glb | $0.369 |
| hy-3d-motion | Tencent Hunyuan | Text | fbx | $0.185 |
| hy-3d-polygen-image | Tencent Hunyuan | Image (required) | glb + obj + fbx | $0.554 |
| tripo-3d-3.1 | Tripo (VAST) | Text / Image | glb | $0.323 |
| tripo-3d-p1 | Tripo (VAST) | Text / Image | glb | $0.323 |

#### Submit request body

| Parameter | Type | Required | Description |
|---|---|---|---|
| model | string | Required | 3D model ID (see table above) |
| prompt | string | Conditional | Text description of the 3D asset. Required for text-to-3D; at least one of prompt / image must be provided. |
| image | string | Conditional | Source image URL for image-to-3D. Required for hy-3d-polygen-image . |

#### Example Request (text-to-3D)

```
curl https://aiapi-pro.com/v1/three_d/generations \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hy-3d-3.1",
    "prompt": "a cute cartoon dog"
  }'
```

#### Example Request (image-to-3D)

```
curl https://aiapi-pro.com/v1/three_d/generations \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tripo-3d-3.1",
    "image": "https://example.com/object.png"
  }'
```

#### Example Response (submit)

```
{
  "id": "<task_id>",
  "request_id": "3dgen-...",
  "status": "queued",
  "model": "hy-3d-3.1"
}
```

#### Poll the task

```
curl "https://aiapi-pro.com/v1/three_d/generations/<task_id>?model=hy-3d-3.1" \
  -H "Authorization: Bearer nvai-your-key"
```

#### Example Response (poll, completed)

{ "id": "<task_id>", "status": "succeeded", "upstream_status": "completed", "model_url": "https://.../model.glb", "outputs": [ {"type": "obj", "url": "https://.../model.obj.zip", "preview_image_url": "https://.../preview.png"}, {"type": "glb", "url": "https://.../model.glb", "preview_image_url": "https://.../preview.png"} ], "model": "hy-3d-3.1" } Billing: while status is queued / processing keep polling (generation typically takes 1–8 minutes). On succeeded the flat pre-deducted price is final (no token reconciliation). On failed / cancelled the pre-deducted amount is automatically refunded ( novai_refund is reported in the response). model_url is the primary downloadable asset (glb preferred); outputs lists every available format.

```
{
  "id": "<task_id>",
  "status": "succeeded",
  "upstream_status": "completed",
  "model_url": "https://.../model.glb",
  "outputs": [
    {"type": "obj", "url": "https://.../model.obj.zip", "preview_image_url": "https://.../preview.png"},
    {"type": "glb", "url": "https://.../model.glb", "preview_image_url": "https://.../preview.png"}
  ],
  "model": "hy-3d-3.1"
}
```

### Streaming

Set "stream": true to receive responses as Server-Sent Events (SSE): curl https://aiapi-pro.com/v1/chat/completions \ -H "Authorization: Bearer nvai-your-key" \ -H "Content-Type: application/json" \ -d '{ "model": "glm-5", "messages": [{"role": "user", "content": "Hello"}], "stream": true }' Each SSE event contains a JSON chunk with delta.content for the new token. The stream ends with [DONE] .

```
curl https://aiapi-pro.com/v1/chat/completions \
  -H "Authorization: Bearer nvai-your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-5",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

### List Models

`GET /v1/models`

GET /v1/models Returns a list of all available models.

```
curl https://aiapi-pro.com/v1/models \
  -H "Authorization: Bearer nvai-your-key"
```

### Error Codes

| HTTP Code | Meaning | Description |
|---|---|---|
| 400 | Bad Request | Invalid request body or missing required fields |
| 401 | Unauthorized | Invalid or missing API key |
| 402 | Insufficient Balance | Account balance too low (does not apply to free models) |
| 404 | Not Found | Invalid model ID |
| 429 | Rate Limited | Too many requests, please slow down |
| 500 | Server Error | Internal error, please retry |

### Rate Limits

Current rate limits per API key:

> ⚠️ Rate limits may be adjusted. If you need higher limits, contact us.

### SDKs & Libraries

NovAI works with any OpenAI-compatible SDK. Just set the base URL:

#### Python

```
pip install openai

from openai import OpenAI
client = OpenAI(api_key="nvai-...", base_url="https://aiapi-pro.com/v1")
```

#### Node.js

```
npm install openai

import OpenAI from 'openai';
const client = new OpenAI({ apiKey: 'nvai-...', baseURL: 'https://aiapi-pro.com/v1' });
```

#### LangChain

```
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="glm-5", openai_api_key="nvai-...", openai_api_base="https://aiapi-pro.com/v1")
```

#### Cursor IDE / Continue

Set base URL to https://aiapi-pro.com/v1 in your IDE settings. See our Cursor setup guide . More examples: GitHub Repository | Blog & Tutorials

### Supported Email Providers

Due to bot attacks targeting our free welcome credit, NovAI restricts new account registration to major email providers. This policy applies to new registrations only — all existing accounts are fully unaffected. If your email provider is not listed below, please contact [email protected] for manual approval. Note: Custom domain emails, dynamic DNS addresses, and temporary/disposable email services are not accepted. This restriction was introduced on June 24, 2026 to combat bot abuse. All 3,000+ users registered before this date are fully unaffected. Connect NovAI to your favorite tools in 60 seconds. Just change the Base URL and paste your API Key. Quick answers to common questions. Can't find yours? Contact support. © 2026 NovAI. AI API Gateway — Hong Kong. Home | Blog | Docs

| Provider | Accepted Domains | Notes |
|---|---|---|
| Google | gmail.com , googlemail.com | Recommended |
| Microsoft | outlook.com , hotmail.com , live.com , msn.com | Recommended |
| Yahoo | yahoo.com , yahoo.co.jp , yahoo.co.uk |  |
| Apple | icloud.com , me.com , mac.com |  |
| Proton | protonmail.com , proton.me | Privacy-focused |
| Tutanota | tutanota.com | Privacy-focused |
| Zoho | zoho.com | Business / developer |
| GMX | gmx.com , gmx.net | Europe popular |
| AOL | aol.com |  |
| Mail.com | mail.com |  |
| Yandex | yandex.com |  |
| Naver | naver.com | Korea |
| Daum / Kakao | daum.net | Korea |
| Web.de | web.de , t-online.de | Germany |
| Mail.ru | mail.ru | Russia |

#### Leave us a message

We'll reply to your email within a few hours.

