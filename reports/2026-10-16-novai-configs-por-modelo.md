# NovAI — Configurações por modelo (scrape das páginas "Try")

Fonte: `https://aiapi-pro.com/models/<slug>.html` (links "Try" do `docs/novai-model-marketplace.html`).
Modelos: **121/121** baixados com sucesso.

Cada página de modelo expõe, quando disponível:

- **Preço** (input/output por 1M tokens) — formato `price-cell` (chat) ou `spec-item` "Token Price" (vídeo/imagem/3D).
- **Specs técnicas** — tabela `Technical specifications` (chat) ou card `Specifications & Pricing` (vídeo/imagem/3D).
- **Exemplos de código** — blocos `<pre><code>` (chat) ou `<div class="code-block">` (vídeo/imagem/3D), com o `model` ID e os parâmetros de uso sugeridos pela NovAI.
- **Casos de uso** — seção `Best use cases`.

> Observação: as páginas **não** trazem um bloco formal de "configuração sugerida" (temperature/top_p/etc.). Os parâmetros aparecem apenas dentro dos exemplos de código, quando a NovAI os inclui.

## Cobertura da extração

| Campo | Modelos com dado |
|---|---|
| Preço (input) | 74 |
| Preço (output) | 57 |
| Descrição/subtítulo | 113 |
| Vendor | 33 |
| Specs técnicas | 30 |
| Casos de uso | 83 |
| Blocos de código | 121 |
| Parâmetros em exemplos | 61 |

## Modelos por família

### glm (12)

- **`glm-4.1v-thinking-flash`** — in FREE / out FREE
  - A free vision-language model that thinks before it answers: visual chain-of-thought reasoning over images, documents, charts, and screenshots, with a 128K context window.
  - Parâmetros (exemplos): image_url={"url": "https://example.com/invoice.png
  - Casos de uso: Screenshot-to-code: turn UI mockups into HTML/CSS/React, Document intelligence: invoices, contracts, forms, Chart question-answering and data extraction, Automated UI testing and visual QA, Educational tools that explain diagrams step by step
- **`glm-4.6v`**
- **`glm-4.6v-flash`** — in $0.00 / out $0.00
- **`glm-4.7-flash`** — in FREE / out FREE
  - A 30B-class model balancing performance and efficiency, further optimized for agentic coding: stronger coding capability and long-horizon task planning. Free forever on NovAI - no per-token cost, no platform fee.
  - Casos de uso: High-volume chatbots and assistants at zero marginal cost, Coding agents and CLI tools on a budget, Classification, routing, and extraction pipelines, Free-tier products that need a reliable workhorse model, Long-context document Q&A
- **`glm-5`** — in $0.60 / out $3.02
  - Zhipu's next-generation multimodal flagship model. Balanced performance across reasoning, code, and vision.
  - Casos de uso: Multimodal chatbots, Document understanding with images, Bilingual content generation, Function-calling agents
- **`glm-5-turbo`** — in $1.08 / out $3.69
  - Zhipu GLM-5-Turbo is a latency-optimized GLM-5 variant tuned for high-throughput production traffic while keeping GLM-5 quality.
  - Casos de uso: Real-time chat products, High-QPS API backends, Agentic tool calling, Content pipelines
- **`glm-5.1`** — in $1.01 / out $4.03
  - Zhipu's newest flagship (April 2026). Dramatically enhanced coding. Autonomously plans, executes, and iterates for up to 8 hours in a single task, delivering engineering-grade results.
  - Casos de uso: Autonomous software engineering agents (full-feature delivery), Multi-file refactoring and repo-level migrations, Long-running research agents with plan-execute-revise loops, CI-integrated code review and auto-fix agents, Complex enterprise workflow automation
- **`glm-5.2`** — in $1.19 / out $3.74
  - Zhipu's newest flagship (2026). Dramatically enhanced coding. Autonomously plans, executes, and iterates for up to 8 hours in a single task, delivering engineering-grade results.
  - Casos de uso: Autonomous software engineering agents (full-feature delivery), Multi-file refactoring and repo-level migrations, Long-running research agents with plan-execute-revise loops, CI-integrated code review and auto-fix agents, Complex enterprise workflow automation
- **`glm-5.3`** — in $1.25 / out $4.00
  - Zhipu's newest flagship (2026). Dramatically enhanced coding. Autonomously plans, executes, and iterates for up to 8 hours in a single task, delivering engineering-grade results.
  - Casos de uso: Autonomous software engineering agents (full-feature delivery), Multi-file refactoring and repo-level migrations, Long-running research agents with plan-execute-revise loops, CI-integrated code review and auto-fix agents, Complex enterprise workflow automation
- **`glm-5.3-flash`** — in $0.08 / out $0.28
  - Zhipu's GLM-5.3-Flash pairs flagship-class coding and agentic ability with a 1M-token context at one of the lowest prices on the market — $0.08 per 1M input tokens, direct from Zhipu, zero platform fee.
  - Casos de uso: High-volume coding assistants, Long-context RAG over large document sets, Budget agentic pipelines, Bulk summarization and extraction, Cost-sensitive production chat
- **`glm-5.3-flashx`** — in $0.12 / out $0.40
  - Fast variant of GLM-5.3 with reduced latency and cost. Strong reasoning and coding at a fraction of flagship price.
  - Casos de uso: High-volume chat and Q&A, Low-latency code assistance, Batch processing pipelines, Cost-sensitive production deployments, Real-time conversational agents
- **`glm-5v-turbo`**

### qwen (12)

- **`qwen3-coder-flash`** — in $0.15 / out $0.75
  - A fast, cost-efficient coding model with 256K context - built for high-volume developer tooling and autocomplete.
  - Casos de uso: High-volume code autocomplete, Budget coding agents, Inline suggestions in IDEs, Batch code transformations, Cost-sensitive dev tooling
- **`qwen3-coder-plus`** — in $0.65 / out $3.25
  - Alibaba's flagship agentic coding model with 256K context, repo-level reasoning and OpenAI-compatible tool calling.
  - Casos de uso: Coding agents and CLI assistants, Pull-request review and refactoring, Repo-level code Q&A, Automated test generation, Long-context technical reasoning
- **`qwen3-max`** — in $0.57 / out $1.32
  - Alibaba Cloud's 2026 flagship. 397B-parameter MoE with 22B active. Top-tier agentic reasoning, multilingual, and long-context performance.
  - Casos de uso: Multilingual agent workflows, Enterprise RAG with long documents, Structured data extraction, Research-grade reasoning
- **`qwen3-omni-flash`** — in $0.15 / out $0.6
  - An omni-modal model that accepts text, image, audio and video input through a single OpenAI-compatible API.
  - Parâmetros (exemplos): image_url={"url":"https://example.com/photo.jpg
  - Casos de uso: Multimodal chat assistants, Audio + image understanding, Video content analysis, Voice-enabled visual apps, Cross-modal retrieval
- **`qwen3-tts-flash`**
  - A fast, low-latency text-to-speech model built for realtime voice and streaming applications.
  - Parâmetros (exemplos): voice=Cherry
  - Casos de uso: Realtime voice agents, Live streaming narration, Conversational AI, Voice bots, Interactive voice response
- **`qwen3-vl-flash`** — in $0.08 / out $0.24
  - A fast, low-cost vision-language model for high-volume image understanding and OCR pipelines.
  - Parâmetros (exemplos): image_url={"url":"https://example.com/photo.jpg
  - Casos de uso: High-volume image tagging, Budget OCR pipelines, Image content moderation, Batch visual extraction, Cost-sensitive multimodal apps
- **`qwen3-vl-plus`** — in $0.21 / out $0.63
  - A balanced vision-language model that understands images, charts and documents alongside text, with 256K context.
  - Parâmetros (exemplos): image_url={"url":"https://example.com/photo.jpg
  - Casos de uso: Image captioning and description, Document and screenshot understanding, Chart / diagram analysis, Visual Q&A assistants, Multimodal content moderation
- **`qwen3.5-ocr`** — in $0.7 / out $0.7
  - Alibaba's latest OCR model with structured extraction for tables, handwriting and multilingual documents.
  - Parâmetros (exemplos): image_url={"url":"https://example.com/photo.jpg
  - Casos de uso: Table and form extraction, Handwritten note digitization, Multilingual document OCR, Structured data pipelines, Archive digitization
- **`qwen3.6-max-preview`** — in $1.03 / out $6.16
- **`qwen3.7-max`** — in $1.16 / out $3.48
- **`qwen3.7-text-embedding`** — in $0.11 / out ?
  - High-quality multilingual text embeddings for RAG, semantic search, clustering and retrieval.
  - Casos de uso: RAG knowledge bases, Semantic search, Document clustering, Recommendation systems, Multilingual retrieval
- **`qwen3.8-max`** — in $1.84 / out $5.52

### hy (8)

- **`hy-3d-3.0`**
  - Tencent Hunyuan 3D 3.0 — high-quality text/image-to-3D mesh generation with obj and glb output, delivered through an asynchronous task API: submit a prompt, poll for the downloadable model URL.
  - Specs: Mode: Async task; Input: Text / Image; Output: obj (zip) + glb; Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): prompt=a cute cartoon dog
- **`hy-3d-3.1`**
  - Tencent Hunyuan 3D 3.1 — the latest Hunyuan 3D iteration with improved geometry and detail, text/image-to-3D with obj and glb output, delivered through an asynchronous task API.
  - Specs: Mode: Async task; Input: Text / Image; Output: obj (zip) + glb; Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): prompt=a cute cartoon dog
- **`hy-3d-express`**
  - Tencent Hunyuan 3D Express — fast, low-cost text/image-to-3D mesh generation for quick drafts and prototyping, delivered through an asynchronous task API: submit a prompt, poll for the downloadable model URL.
  - Specs: Mode: Async task; Input: Text / Image; Output: obj (zip); Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): prompt=a cute cartoon dog
- **`hy-3d-motion`**
  - Tencent Hunyuan 3D Motion — generates animated 3D motion output (fbx) from a text prompt, delivered through an asynchronous task API: submit a prompt, poll for the downloadable model URL.
  - Specs: Mode: Async task; Input: Text; Output: fbx; Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): prompt=a cute cartoon dog
- **`hy-3d-polygen-image`**
  - Tencent Hunyuan 3D PolyGen — image-to-3D generation with multi-format export (glb, obj and fbx) plus a preview image, delivered through an asynchronous task API: submit an image URL, poll for the downloadable model URLs.
  - Specs: Mode: Async task; Input: Image (required); Output: glb + obj + fbx; Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): image=https://example.com/object.png
- **`hy3`** — in $0.18 / out $0.72
  - Tencent's flagship Hunyuan model. Excellent Chinese comprehension, general reasoning and tool calling, delivered through NovAI's zero-fee gateway.
  - Casos de uso: Chinese-first chat and assistants, General reasoning and analysis, Tool-calling / agentic workflows, Long-document Q&A
- **`hy3-preview`** — in $0.127 / out $0.423
  - Preview build of Tencent Hunyuan Hy3 at the lowest price point - ideal for high-volume and cost-sensitive workloads.
  - Casos de uso: High-volume chat, Cost-sensitive batch processing, Prototyping and testing, Content generation
- **`hy4-preview`** — in $0.834 / out $2.501
  - Tencent's next-generation Hunyuan flagship in preview. A 1M-token context window with strong bilingual reasoning and agentic tool use — served at provider list price with zero platform fee.
  - Casos de uso: Long-document analysis and summarization, Chinese enterprise assistants and customer support, Agentic workflows with tool calling, Research and knowledge synthesis, General high-quality chat

### kimi-k (6)

- **`kimi-k2.5`** — in $0.64 / out $3.35
  - Moonshot Kimi-K2.5 excels at long-context understanding and reasoning. Note: this model requires temperature=1 (handled automatically by NovAI).
  - Casos de uso: Long-doc analysis, Research and reasoning, Knowledge assistants, Complex Q&A
- **`kimi-k2.6`** — in $1.04 / out $4.30
  - Moonshot Kimi-K2.6 upgrades reasoning and coding over K2.5. Requires temperature=1 (handled automatically by NovAI).
  - Casos de uso: Coding assistance, Long-doc reasoning, Agentic tasks, Technical Q&A
- **`kimi-k2.7-code`** — in $1.04 / out $4.30
  - Moonshot Kimi-K2.7-Code is specialized for coding and agentic software workflows. Requires temperature=1 (handled automatically by NovAI).
  - Casos de uso: Code generation & review, Repo-level agents, Test writing, Refactoring
- **`kimi-k2.7-code-highspeed`** — in $2.07 / out $8.61
  - Moonshot Kimi-K2.7-Code HighSpeed is the premium low-latency coding tier for interactive dev tools. Requires temperature=1 (handled automatically). Not on OpenRouter.
  - Casos de uso: Interactive IDE assistants, Latency-critical code agents, Pair-programming tools, Realtime completions
- **`kimi-k2.8-preview`** — in $0.93 / out $3.89
  - Moonshot's Kimi K2.8 preview — next-generation agentic reasoning and coding with a 256K-token context, served at provider list price with zero platform fee.
  - Casos de uso: Agentic software-development workflows, Complex multi-step reasoning, Code generation and review, Tool-use agents and orchestration, Long-context analysis
- **`kimi-k3`** — in $2.90 / out $14.50
  - Moonshot Kimi K3 is the flagship 1M-context multimodal reasoning model — Moonshot's most capable release. Cheaper than OpenRouter on NovAI. Requires temperature=1 (handled automatically by NovAI).
  - Casos de uso: Long-document and repo-scale reasoning, Complex multi-step agents, Research, analysis & synthesis, Advanced coding and refactoring

### kling-video (6)

- **`kling-video-o1`** — in $1.54 / 1M / out ?
  - Reasoning-enhanced video generation. Better understanding of complex prompts with logical scene composition.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.092; Est. Cost / 5s Video: $0.46; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`kling-video-v2.5-turbo`** — in $1.54 / 1M / out ?
  - Fast previous-generation Kling. Lowest cost per second in the Kling lineup for budget-conscious production.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.062; Est. Cost / 5s Video: $0.308; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`kling-video-v2.6`** — in $1.54 / 1M / out ?
  - Previous-generation Kling with proven quality. Lower token consumption makes it cost-efficient for production.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.077; Est. Cost / 5s Video: $0.385; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`kling-video-v3`** — in $1.54 / 1M / out ?
  - Kuaishou's flagship video generation model. Cinematic quality with complex motion understanding and strong prompt adherence.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.092; Est. Cost / 5s Video: $0.46; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`kling-video-v3-omni`** — in $1.54 / 1M / out ?
  - Omni variant supporting both text-to-video and image-to-video conditioning for reference-guided generation.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.092; Est. Cost / 5s Video: $0.46; Specs: 5-10s | 768P/1080P | T2V/I2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`kling-video-v3-turbo`** — in $1.54 / 1M / out ?
  - Faster variant of Kling V3. Higher throughput with slightly increased token consumption for speed-optimized workflows.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.123; Est. Cost / 5s Video: $0.62; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset

### minimax-speech (6)

- **`minimax-speech-02-hd`**
  - MiniMax Speech 02 HD offers rich, expressive timbres and clone-ready voices, exposed through NovAI's OpenAI-compatible /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): response_format=url, voice=male-qn-qingse
  - Casos de uso: Character and persona voices, Audiobook narration, Branded voice identity, Game and app voice-over, Expressive marketing audio
- **`minimax-speech-02-turbo`**
  - The quick, economical tier of MiniMax Speech 02 — fast speech generation for high-volume workloads, exposed through NovAI's OpenAI-compatible /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): response_format=url, voice=male-qn-qingse
  - Casos de uso: High-volume speech synthesis, Notification and alert audio, Budget TTS pipelines, Rapid prototyping, Batch content narration
- **`minimax-speech-2.6-hd`**
  - MiniMax Speech 2.6 HD delivers high-definition, multilingual text-to-speech with natural prosody, exposed through NovAI's OpenAI-compatible /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): response_format=url, voice=male-qn-qingse
  - Casos de uso: Multilingual audiobooks, E-learning course narration, Localization and dubbing, Podcast and video voice-over, Assistant and IVR voices
- **`minimax-speech-2.6-turbo`**
  - The cost-optimized tier of MiniMax Speech 2.6 — fast, economical voice synthesis at scale, exposed through NovAI's OpenAI-compatible /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): response_format=url, voice=male-qn-qingse
  - Casos de uso: Bulk content narration, High-volume app voice, Notifications and alerts, Realtime chatbot speech, Cost-sensitive TTS pipelines
- **`minimax-speech-2.8-hd`**
  - MiniMax's latest flagship text-to-speech model, exposed through NovAI's OpenAI-compatible /v1/audio/speech endpoint — studio-grade voices with emotion control and 32kHz output, billed by real token usage with zero platform fee.
  - Parâmetros (exemplos): response_format=url, voice=male-qn-qingse
  - Casos de uso: Audiobook and podcast narration, IVR and voice-assistant responses, Video voice-over and dubbing, Accessibility / screen-reader voices, Premium branded voice experiences
- **`minimax-speech-2.8-turbo`**
  - The fast, low-latency tier of MiniMax Speech 2.8 — built for realtime and streaming voice applications, exposed through NovAI's OpenAI-compatible /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): response_format=url, voice=male-qn-qingse
  - Casos de uso: Realtime voice agents and chatbots, Live narration and streaming TTS, In-app voice feedback, High-volume low-cost synthesis, Interactive voice response (IVR)

### doubao-seed (5)

- **`doubao-seed-2.0-code`** — in $0.45 / out $2.24
  - Code-specialized model with unified input-length-based pricing. Optimized for code generation, review, completion.
  - Casos de uso: IDE auto-complete backends, Automated code review, Code migration & refactoring, Programming education assistants
- **`doubao-seed-2.0-lite`** — in $0.075 / out $0.45
  - Ultra-low-cost high-throughput model. $0.075 per 1M input tokens — one of the cheapest capable models on the market.
  - Casos de uso: Customer service chatbots, High-volume text classification, Real-time content moderation, Lightweight RAG backends
- **`doubao-seed-2.0-pro`** — in $0.40 / out $2.00
  - ByteDance's flagship 3.2-trillion-parameter MoE model. GPT-4-class reasoning, 256K context, state-of-the-art Chinese understanding — via NovAI's zero-platform-fee Hong Kong gateway with an exclusive 10% distributor discount.
  - Specs: Model ID: doubao-seed-2.0-pro; Architecture: Sparse Mixture-of-Experts (MoE) transformer; Total parameters: ~3.2T; Active parameters / token: ~280B; Context window (input): 262,144 tokens (256K); Max output tokens: 16,384
  - Parâmetros (exemplos): temperature=0.7, max_tokens=800
- **`doubao-seed-2.1-pro`** — in $0.4 / out $2
  - ByteDance's flagship general model with 256K context, strong reasoning and agentic tool use.
  - Casos de uso: General chat assistants, Complex reasoning tasks, Agentic workflows, Long-document analysis, Content generation
- **`doubao-seed-2.1-turbo`** — in $0.15 / out $0.9
  - A fast, cost-efficient Doubao variant built for high-throughput production chat workloads.
  - Casos de uso: High-volume chatbots, Budget production assistants, Realtime conversation, Classification and routing, Cost-sensitive deployments

### deepseek-v (4)

- **`deepseek-v4-flash`** — in $0.08 / out $0.17
  - DeepSeek's speed-optimized V4 variant. Fast, ultra-cheap, and still smarter than most mid-tier closed-source models. Perfect for high-QPS production workloads.
  - Casos de uso: High-QPS chatbots and customer service, Real-time coding assistants and auto-complete, Summarization and classification at scale, Cheap RAG backends over large document sets, Voice/streaming agents where every 100ms matters
- **`deepseek-v4-flash-vision`** — in $0.308 / out $1.231
  - DeepSeek V4 Flash Vision is a fast vision-language model (experimental) for image understanding and multimodal chat at Flash-tier cost — zero platform fee.
  - Casos de uso: Image captioning and description, Screenshot and document OCR, Chart and diagram parsing, Visual question answering, Multimodal chat assistants
- **`deepseek-v4-pro`** — in $0.57 / out $1.15
  - State-of-the-art open-weight reasoning model. 680B-parameter MoE. Matches or exceeds GPT-4o on math, coding, and chain-of-thought — at roughly 5% of the price. Available via NovAI's zero-platform-fee Hong Kong gateway.
  - Specs: Model ID: deepseek-v4-pro; Architecture: Sparse Mixture-of-Experts transformer (V4 routing); Total parameters: ~680B; Active parameters / token: ~37B; Number of experts: 256 routed + 1 shared, top-8 routing; Context window (input): 131,072 tokens (128K)
  - Parâmetros (exemplos): temperature=0.2, max_tokens=800
- **`deepseek-v4.1-flash`** — in $0.308 / out $1.231
  - DeepSeek V4.1 Flash is a fast, cost-efficient reasoning LLM for chat, coding and agentic workloads — at provider list price, zero platform fee.
  - Casos de uso: High-volume chat assistants, Code generation and review, Agentic tool-calling pipelines, Summarization and extraction, Cost-sensitive production workloads

### minimax-video (4)

- **`minimax-video-h3`**
  - MiniMax Hailuo H3 text-to-video model. High-fidelity cinematic motion, delivered through an asynchronous task API: submit a prompt, poll for the mp4 URL.
  - Specs: Mode: Async task; Input: Text; Output: Video (mp4 URL); Capabilities: T2V; Resolution: 768P / 1080P; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, resolution=720p, prompt=A red sports car driving along a coastal road at sunset
- **`minimax-video-h3-max`**
  - MiniMax Hailuo H3 Max — the top-tier quality variant of H3 for text-to-video. Maximum fidelity cinematic output via the asynchronous task API.
  - Specs: Mode: Async task; Input: Text; Output: Video (mp4 URL); Capabilities: T2V; Resolution: 768P / 1080P; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, resolution=720p, prompt=A red sports car driving along a coastal road at sunset
- **`minimax-video-v2.3`**
  - MiniMax Hailuo 2.3 text-to-video model. Balanced quality and generation speed via the asynchronous task API: submit a prompt, poll for the mp4 URL.
  - Specs: Mode: Async task; Input: Text; Output: Video (mp4 URL); Capabilities: T2V; Resolution: 768P / 1080P; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, resolution=720p, prompt=A red sports car driving along a coastal road at sunset
- **`minimax-video-v2.3-fast`**
  - MiniMax Hailuo 2.3 Fast — an image-to-video model. Animate a still first-frame image into a short clip via the asynchronous task API. This variant is image-to-video only (a source image is required).
  - Specs: Mode: Async task; Input: Image (+ optional text); Output: Video (mp4 URL); Capabilities: I2V only; Resolution: 768P / 1080P; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, prompt=Animate this scene with smooth cinematic motion

### doubao-seedance (3)

- **`doubao-seedance-2.0`**
  - Flagship video generation model. Multi-modal input supports text, images, video and audio references. Native audio generation sync. Cinematic quality from 480p to 4K.
  - Specs: Duration: 4-15 seconds; Resolution: 480p / 720p / 1080p / 4K; Input: Text + Image + Video + Audio; Audio: Native sync + bgm; Watermark: Optional; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, resolution=720p, prompt=A cat walking through a sunny garden
- **`doubao-seedance-2.0-fast`**
  - Fast variant of Seedance 2.0. Prioritizes speed & cost efficiency, ideal for rapid prototyping and high-volume production. Same multi-modal input support.
  - Specs: Duration: 4-15 seconds; Resolution: 480p / 720p / 1080p / 4K; Input: Text + Image + Video + Audio; Audio: Native sync + bgm; Watermark: Optional; Status: ✅ Available
  - Parâmetros (exemplos): duration=6, resolution=720p, prompt=A drone shot flying over a mountain valley
- **`doubao-seedance-2.5`**
  - ByteDance's 2026 flagship video model. Generates native synchronized audio together with the video — ambient sound, effects and speech in one pass. Cinematic quality at 480p and 720p, clips up to 30 seconds.
  - Specs: Duration: Up to 30 seconds; Resolution: 480p / 720p; Input: Text + Image; Audio: Native synchronized; Billing: Per second; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, resolution=720p, prompt=A paper boat floating on a quiet pond at dusk

### hy-mt (3)

- **`hy-mt2-lite`** — in $0.043 / out $0.172
  - Hunyuan MT2 Lite is the budget tier of Tencent's dedicated translation model — fast, low-cost machine translation across 30+ languages, zero platform fee.
  - Casos de uso: Bulk and high-volume translation, Chat message translation, Real-time localization, User-generated content moderation and translation, Cost-sensitive MT pipelines
- **`hy-mt2-plus`** — in $0.072 / out $0.287
  - Hunyuan MT2 Plus is a dedicated machine-translation model covering 30+ languages with domain-aware, terminology-consistent output — at a low per-token price, zero platform fee.
  - Casos de uso: Document and article translation, Software and content localization, Subtitle translation, Cross-language customer support, E-commerce listing translation
- **`hy-mt2-pro`** — in $0.29 / out $0.87
  - Tencent Hunyuan MT2 Pro is a dedicated machine-translation model covering 30+ languages with domain-aware, context-consistent output. Not available on OpenRouter.
  - Casos de uso: Document and website localization, Subtitle and media translation, Cross-border e-commerce, Multilingual customer support

### mimo-v (3)

- **`mimo-v2.5-pro`** — in $0.427 / out $0.855
  - Xiaomi's MiMo V2.5 Pro flagship reasoning model with a 1M-token context — strong math, code and long-document reasoning at provider list price, zero platform fee.
  - Casos de uso: Math and STEM reasoning, Code generation and analysis, Long-document research assistants, Structured problem solving, General high-quality chat
- **`mimo-v2.6-flash`** — in $0.10 / out $0.28
  - Xiaomi's fast reasoning model. Low latency, cost-efficient for high-volume production workloads.
  - Casos de uso: High-volume chat, Cost-sensitive production, Real-time assistants, Batch text processing, Mobile app backends
- **`mimo-v2.6-pro`** — in $0.43 / out $0.87
  - Xiaomi's flagship reasoning model. Strong multilingual, code, and mathematical performance.
  - Casos de uso: Complex reasoning tasks, Code generation and review, Mathematic problem solving, Multilingual content, Research and analysis

### minimax-m (3)

- **`minimax-m2.5`** — in $0.28 / out $1.13
  - MiniMax-M2.5 is a well-rounded model for chat and content generation with a large context window.
  - Casos de uso: Creative writing, Content generation, General chat, Summarization
- **`minimax-m2.7`** — in $0.30 / out $1.20
  - MiniMax-M2.7 improves reasoning and instruction-following over M2.5 while keeping a friendly price.
  - Casos de uso: General assistants, Content generation, Reasoning tasks, Customer support
- **`minimax-m3`** — in $0.35 / out $1.41
  - MiniMax-M3 is the flagship of the M-series with an ultra-long 512K context window for large-document workloads.
  - Casos de uso: Very long document analysis, Codebase-scale context, Research assistants, Multi-doc synthesis

### pixverse-video (3)

- **`pixverse-video-c1`** — in $1.54 / 1M / out ?
  - Compact fast model. Lowest cost per second in the PixVerse lineup for high-volume and draft generation.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.031; Est. Cost / 5s Video: $0.154; Specs: 5-10s | 768P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`pixverse-video-v5.6`** — in $1.54 / 1M / out ?
  - Previous-generation PixVerse. Reliable quality with proven stability for production workloads.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.041; Est. Cost / 5s Video: $0.20; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`pixverse-video-v6.0`** — in $1.54 / 1M / out ?
  - PixVerse's latest video generation model. High-fidelity motion with strong prompt following at competitive token cost.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.041; Est. Cost / 5s Video: $0.20; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset

### wand-vega (3)

- **`wand-vega-image-flash`**
  - Tencent WAND Vega Image Flash is the balanced mid tier of the Vega image family — strong quality and speed for production workloads, 1K-to-4K output and up to 6 reference images, billed by real token usage.
  - Parâmetros (exemplos): size=1024x1024, n=1, prompt=a futuristic city skyline at night
  - Casos de uso: Production marketing imagery, Multi-reference product shots, Editorial and blog illustrations, Ad creative at scale, Design systems and templates
- **`wand-vega-image-lite`**
  - Tencent WAND Vega Image Lite is the fast, cost-effective entry tier of the Vega image family — 1K-to-4K generation with up to 3 reference images, exposed through NovAI's OpenAI-compatible endpoint and billed by real token usage.
  - Parâmetros (exemplos): size=1024x1024, n=1, prompt=a serene mountain lake at dawn
  - Casos de uso: High-volume low-cost image generation, Thumbnails and social visuals, Rapid prototyping, Batch content pipelines, Simple image editing tasks
- **`wand-vega-image-pro`**
  - Tencent WAND Vega Image Pro is the top tier of the Vega image family — the highest-fidelity output with layer support, 1K-to-4K resolution and up to 6 reference images, billed by real token usage.
  - Parâmetros (exemplos): size=1024x1024, n=1, prompt=an ultra-detailed macro shot of a dewdrop on a leaf
  - Casos de uso: Hero images and flagship visuals, Layered design assets, Print-quality artwork at 4K, Premium brand campaigns, Complex multi-reference compositions

### doubao-seedream (2)

- **`doubao-seedream-4.0`**
  - Cost-effective image generation for high-volume production. 2K resolution, Text-to-Image and Image-to-Image. Great for batch processing and automated workflows.
  - Specs: Resolution: Up to 2K; Input: Text + Reference Images; Output: Image (PNG/JPEG); Batch: 1-8 images/request; Speed: ~3-10s per image; Status: Available
  - Parâmetros (exemplos): size=2048x2048, n=1, prompt=A cozy coffee shop interior
- **`doubao-seedream-4.5`**
  - Latest flagship image generation model. Superior editing consistency, portrait refinement, and small-text rendering. 4K resolution, multi-reference image generation.
  - Specs: Resolution: Up to 4K; Input: Text + Reference Images; Output: Image (PNG/JPEG); Batch: 1-8 images/request; Speed: ~5-15s per image; Status: Available
  - Parâmetros (exemplos): size=2560x1440, n=1, prompt=A serene lake at sunset with mountains

### kinfra-text (2)

- **`kinfra-text-embedding-0.6b`** — in $0.0769 / out ?
  - Tencent Kinfra Text Embedding 0.6B is a fast, compact model producing 1024-dimension text vectors for high-volume retrieval and search — at provider list price, zero platform fee.
  - Casos de uso: High-volume RAG ingestion, Semantic search at scale, Embedding caches and indexes, Classification features, Cost-sensitive retrieval pipelines
- **`kinfra-text-embedding-4b`** — in $0.0923 / out ?
  - Tencent Kinfra Text Embedding 4B produces high-quality 2560-dimension text vectors for retrieval-augmented generation, semantic search and clustering — at provider list price, zero platform fee.
  - Casos de uso: Retrieval-augmented generation (RAG), Semantic search and re-ranking, Document clustering and dedup, Recommendation features, Similarity and classification pipelines

### kinfra-vl (2)

- **`kinfra-vl-embedding-2b`** — in $0.0769 / out ?
  - Tencent Kinfra VL Embedding 2B is a fast, compact multimodal model producing vision-language embeddings across text, image and video — at provider list price, zero platform fee.
  - Casos de uso: High-volume cross-modal search, Multimodal RAG ingestion, Image and video similarity at scale, Cost-sensitive multimodal pipelines, Visual recommendation features
- **`kinfra-vl-embedding-8b`** — in $0.0923 / out ?
  - Tencent Kinfra VL Embedding 8B produces multimodal vision-language embeddings across text, image and video for cross-modal retrieval and search — at provider list price, zero platform fee.
  - Casos de uso: Cross-modal (text-to-image) search, Multimodal RAG over documents and media, Image and video similarity, Visual recommendation features, Multimodal clustering

### minimax-music (2)

- **`minimax-music-v2.6`**
  - MiniMax Music v2.6 turns lyrics into complete songs with configurable style and structure, exposed through NovAI's /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): prompt=upbeat synthwave, response_format=url
  - Casos de uso: Original songs and demos, Background music for content, Jingles and ad audio, App and game soundtracks, Instrumental tracks
- **`minimax-music-v3.0`**
  - MiniMax's latest music generation model — turn lyrics and a style prompt into full songs (vocal or instrumental), exposed through NovAI's /v1/audio/speech endpoint and billed by real token usage.
  - Parâmetros (exemplos): prompt=upbeat synthwave, response_format=url
  - Casos de uso: Original songs and demos, Background music for video, Jingles and ad audio, Game and app soundtracks, Instrumental backing tracks

### qwen-image (2)

- **`qwen-image`**
  - Alibaba's flagship image generation model for photorealistic, highly detailed compositions.
  - Parâmetros (exemplos): size=1024*1024, n=1, prompt=A serene mountain lake at sunrise
  - Casos de uso: Photorealistic imagery, Advertising visuals, High-detail illustrations, Brand assets, Editorial images
- **`qwen-image-plus`**
  - Advanced text-to-image generation with precise prompt following and accurate in-image text rendering.
  - Parâmetros (exemplos): size=1024*1024, n=1, prompt=A serene mountain lake at sunrise
  - Casos de uso: Posters with text, Typography-driven art, Marketing banners, Detailed illustrations, Text-heavy visuals

### qwen-tts (2)

- **`qwen-tts`**
  - Natural multilingual text-to-speech with multiple voices and expressive, human-like prosody.
  - Parâmetros (exemplos): voice=Cherry
  - Casos de uso: Voice assistants, Audiobook narration, Content voiceover, IVR and phone systems, Accessibility tools
- **`qwen-tts-latest`**
  - The latest Qwen text-to-speech build with improved naturalness and voice stability.
  - Parâmetros (exemplos): voice=Cherry
  - Casos de uso: Voice assistants, Audiobook narration, Media voiceover, Conversational agents, Localization voiceovers

### qwen-vl (2)

- **`qwen-vl-max`** — in $0.8 / out $3.2
  - Alibaba's flagship vision-language model for complex image reasoning across documents, charts and photos.
  - Parâmetros (exemplos): image_url={"url":"https://example.com/photo.jpg
  - Casos de uso: Complex document understanding, Financial chart analysis, Detailed visual reasoning, Multimodal research assistants, High-accuracy OCR extraction
- **`qwen-vl-ocr`** — in $0.7 / out $0.7
  - An OCR-specialized vision model delivering high-accuracy text extraction from images, scans and documents.
  - Parâmetros (exemplos): image_url={"url":"https://example.com/photo.jpg
  - Casos de uso: Document digitization, Receipt and invoice extraction, Screenshot text capture, Form processing, Multilingual OCR pipelines

### seedream-image (2)

- **`seedream-image-v5.0-lite`**
  - ByteDance Seedream v5.0 Lite, a fast and cost-effective tier reachable through the TokenHub gateway — 2K-to-4K output, group images and a built-in web-search tool, billed by real token usage.
  - Parâmetros (exemplos): size=2048x2048, n=1, prompt=a group of three friends hiking at sunset
  - Casos de uso: High-volume fast image generation, Group / multi-subject scenes, Web-grounded visual concepts, 4K marketing assets on a budget, Rapid design iteration
- **`seedream-image-v5.0-pro`**
  - ByteDance Seedream v5.0 Pro, reachable through the TokenHub gateway on NovAI's OpenAI-compatible endpoint — layer decomposition, transparent background and up to 10 reference images, billed by real token usage.
  - Parâmetros (exemplos): size=1024x1024, n=1, prompt=a modern minimalist logo of a fox
  - Casos de uso: Design assets with transparent backgrounds, Layered graphics for editors, High-fidelity product visuals, Multi-reference style transfer, Brand and campaign artwork

### tripo (2)

- **`tripo-3d-3.1`**
  - Tripo (VAST) 3D 3.1 — high-quality text/image-to-3D generation with glb output and a rendered preview, delivered through an asynchronous task API: submit a prompt or image, poll for the downloadable model URL.
  - Specs: Mode: Async task; Input: Text / Image; Output: glb; Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): prompt=a cute cartoon dog
- **`tripo-3d-p1`**
  - Tripo (VAST) 3D P1 — text/image-to-3D generation with glb output and a rendered preview, delivered through an asynchronous task API: submit a prompt or image, poll for the downloadable model URL.
  - Specs: Mode: Async task; Input: Text / Image; Output: glb; Endpoint: /v1/three_d/generations; Billing: Flat / generation; Status: ✅ Available
  - Parâmetros (exemplos): prompt=a cute cartoon dog

### vidu-video (2)

- **`vidu-video-q3`** — in $1.54 / 1M / out ?
  - Vidu standard video generation. Balanced quality and token efficiency for production use.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.077; Est. Cost / 5s Video: $0.385; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset
- **`vidu-video-q3-pro`** — in $1.54 / 1M / out ?
  - Vidu's flagship video generation model. High-fidelity output with strong temporal coherence and motion quality.
  - Specs: Token Price: $1.54 / 1M; Est. Cost / Second: $0.092; Est. Cost / 5s Video: $0.46; Specs: 5-10s | 768P/1080P | T2V
  - Parâmetros (exemplos): duration=5, resolution=768P, prompt=A cat walking on the beach at sunset

### wan (2)

- **`wan2.2-t2i-flash`**
  - Fast text-to-image generation delivering high-quality outputs at a low per-image cost.
  - Parâmetros (exemplos): size=1024*1024, n=1, prompt=A serene mountain lake at sunrise
  - Casos de uso: Marketing visuals, Concept art, Product mockups, Social media imagery, High-volume image generation
- **`wan2.5-t2i-preview`**
  - Next-generation Wan text-to-image model (preview) with improved aesthetics and visual coherence.
  - Parâmetros (exemplos): size=1024*1024, n=1, prompt=A serene mountain lake at sunrise
  - Casos de uso: Creative exploration, High-aesthetic visuals, Concept art, Marketing imagery, Early-adopter workflows

### cogvideox-flash (1)

- **`cogvideox-flash`**
  - Generate short video clips from text prompts at zero cost. Async task API: submit a prompt, poll for completion, download the MP4. $0 per video, forever.
  - Parâmetros (exemplos): duration=6, resolution=720p, prompt=A paper boat floating on a quiet pond at dusk
  - Casos de uso: Social media clips and loops at zero marginal cost, Product teasers and marketing B-roll, Animation demos and storyboards in motion, Free-tier video features in your own product

### cogview (1)

- **`cogview-3-flash`**
  - Generate images from text prompts at zero cost. CogView3-Flash is Zhipu's free text-to-image model, served through the standard OpenAI images endpoint - $0 per image, forever.
  - Parâmetros (exemplos): size=1024x1024, prompt=A red fox in a snowy forest at sunrise
  - Casos de uso: Blog thumbnails and social media assets at zero cost, Concept art and mood boards, Prompt-engineering prototyping before paid generation, Free-tier image features in your own product

### hunyuan-role (1)

- **`hunyuan-role`** — in $0.47 / out $1.86
  - Tencent Hunyuan Role is tuned for character role-play and persona-consistent dialogue - ideal for companion apps, games and interactive fiction. Not available on OpenRouter.
  - Casos de uso: AI companions and characters, Game NPC dialogue, Interactive fiction, Brand persona chatbots

### hunyuan-t (1)

- **`hunyuan-t1-vision`** — in $0.55 / out $1.64
  - Tencent's HY-Vision-1.5-Thinking (Hunyuan T1 Vision) is a deep-reasoning vision-language model for OCR, charts, documents and visual question answering — at provider list price, zero platform fee.
  - Casos de uso: Document and screenshot OCR with reasoning, Chart and dashboard analysis, Visual question answering, STEM and engineering image problems, Form and invoice data extraction

### hunyuan-turbos (1)

- **`hunyuan-turbos-vision-video`** — in $0.462 / out $1.385
  - Tencent's Hunyuan Turbos Vision Video understands images and video frames for temporal reasoning, summarization and question answering — at provider list price, zero platform fee.
  - Casos de uso: Video content summarization, Temporal question answering over clips, Frame-level scene understanding, Multimodal media analysis pipelines, Video moderation assist

### hy-asr (1)

- **`hy-asr-3.0-preview`**
  - Tencent Hunyuan ASR 3.0 speech-to-text — accurate transcription with word-level timestamps and SRT subtitles, exposed through NovAI's OpenAI-compatible /v1/audio/transcriptions endpoint and billed by real token usage.
  - Casos de uso: Meeting and interview transcription, Subtitle generation for video, Voice-note to text, Media indexing and search, Call-center analytics

### hy-image (1)

- **`hy-image-v3`**
  - Tencent's flagship Hunyuan Image 3.0 text-to-image model, accessible through NovAI's OpenAI-compatible /v1/images/generations endpoint — synchronous response, built-in prompt rewrite and custom watermark, at real token cost with zero platform fee.
  - Parâmetros (exemplos): size=1024x1024, n=1, prompt=a cute orange cat on a windowsill
  - Casos de uso: Marketing and social-media visuals, Product mockups and concept art, Illustrations and cover images, Image editing with reference photos, High-volume content pipelines

### hy-role (1)

- **`hy-role`** — in $0.369 / out $1.477
  - Tencent's Hunyuan Role is a role-play and character model with strong persona consistency for immersive, in-character dialogue — at provider list price, zero platform fee.
  - Casos de uso: Character chatbots and companions, Interactive fiction and storytelling, Role-play gaming NPCs, Persona-driven customer experiences, Creative writing assistants

### hy-video (1)

- **`hy-video-v1.5`**
  - Tencent Hunyuan Video 1.5 generation model. Supports text-to-video and image-to-video via an asynchronous task API: submit a prompt (and optional image), poll for the mp4 URL.
  - Specs: Mode: Async task; Input: Text + Image; Output: Video (mp4 URL); Capabilities: T2V + I2V; Resolution: 720p / 1080p; Status: ✅ Available
  - Parâmetros (exemplos): duration=5, resolution=720p, prompt=A red sports car driving along a coastal road at sunset

### hy-vision (1)

- **`hy-vision-2.0-instruct`** — in $1.154 / out $2.692
  - Tencent's Hunyuan Vision 2.0 Instruct is a fast multimodal vision-language model for image understanding, OCR and visual question answering — at provider list price, zero platform fee.
  - Casos de uso: Image captioning and description, Screenshot and document OCR, Visual question answering, Chart and infographic parsing, Multimodal chat assistants

### minimax-text (1)

- **`minimax-text-01`**

### qwen-mt (1)

- **`qwen-mt-plus`** — in $0.25 / out $0.75
  - A dedicated machine-translation model covering 90+ languages with domain-aware terminology and intervention support.
  - Casos de uso: Document and article translation, E-commerce listing localization, Subtitle translation, Multilingual customer support, Terminology-controlled translation

### qwen-omni (1)

- **`qwen-omni-turbo`** — in $0.30 / out $0.60
  - Omni-modal turbo model. Text, image, audio and video input through one unified API at lower cost.
  - Casos de uso: Multimodal analysis, Audio transcription + reasoning, Video understanding, Image Q&A at scale, Unified multimodal pipelines

### qwen-plus (1)

- **`qwen-plus`**

### step (1)

- **`step-5-preview`** — in $0.40 / out $1.20
  - StepFun's next-generation flagship preview. Advanced reasoning, multilingual, and agentic capabilities.
  - Casos de uso: Advanced reasoning, Agentic workflows, Multilingual tasks, Complex analysis, Research assistants

### text-embedding (1)

- **`text-embedding-v4`** — in $0.08 / out ?
  - General-purpose multilingual text embeddings with dense and sparse output for hybrid retrieval.
  - Casos de uso: Hybrid search pipelines, RAG retrieval, Semantic similarity, Multilingual search, Large-scale embedding jobs

### vidu-image (1)

- **`vidu-image-q2`**
  - Vidu (Shengshu) Image Q2 delivers 1080p-to-4K image generation with strong multi-reference and editing capability, exposed through NovAI's OpenAI-compatible endpoint — async upstream polled to completion, billed by real token usage.
  - Parâmetros (exemplos): size=1024x1024, n=1, prompt=a detailed painting of a butterfly on a flower
  - Casos de uso: High-resolution posters and banners, Reference-driven image editing, Character consistency across shots, E-commerce product imagery, Design exploration at 2K/4K

### wand-asr (1)

- **`wand-asr-v1`**
  - Tencent WAND ASR v1 offers multilingual speech-to-text with automatic language detection and subtitle output, exposed through NovAI's OpenAI-compatible /v1/audio/transcriptions endpoint and billed by real token usage.
  - Casos de uso: Multilingual media transcription, Subtitle localization, Cross-language meeting notes, Voice content indexing, Global call-center analytics

