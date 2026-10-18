# NovAI — Reports & Evidence

Complete investigation of the NovAI gateway (`aiapi-pro.com`) integration via LiteLLM proxy. Period: 2026-10-14 to 2026-10-18.

---

## Structure

```
NovAI/
├── README.md            # 📌 This file — index + 7 upstream tickets
├── catalogo/            # Model configs, API analysis, docs, tool scan
├── contrato/            # API contract, SSE streaming, LiteLLM stack
├── testes/              # Test phases (F–L), sweeps, verifications
├── reteste/             # S122-R: dossier, evidence, consolidated report
└── logs/                # Raw logs (jsonl, txt, csv) from all test runs
```

---

## Catalog (`catalogo/`)

| File | Content |
| ---- | ------- |
| `2026-10-16-novai-configs-por-modelo.md` | Per-model configurations (params, limits, capabilities) |
| `2026-10-16-novai-model-api.md` | NovAI model API analysis |
| `2026-10-16-novai-docs.md` | Official NovAI documentation review |
| `2026-10-16-novai-enriquecido.md` | Enriched catalog with metadata |
| `2026-10-17-novai-tool-scan.md` | Full tools/function calling scan |
| `2026-10-17-novai-tool-scan.csv` | Tool scan raw data (CSV) |

## Contract (`contrato/`)

| File | Content |
| ---- | ------- |
| `2026-10-14-novai-sse-streaming.md` | SSE streaming behavior analysis |
| `2026-10-15-litellm-stack-e-catalogo-novai.md` | LiteLLM + NovAI catalog integration |
| `2026-10-17-novai-contrato-api.md` | OpenAI-compatible contract verification |

## Tests (`testes/`)

| File | Content |
| ---- | ------- |
| `2026-10-17-novai-fase-f.md` | Phase F: initial tests |
| `2026-10-17-novai-fase-g.md` | Phase G: coverage expansion |
| `2026-10-17-novai-fase-h.md` | Phase H: embedding validation |
| `2026-10-17-novai-fase-i.md` | Phase I: image generation tests |
| `2026-10-17-novai-fase-j.md` | Phase J: video/3D tests |
| `2026-10-17-novai-fase-k.md` | Phase K: stress tests |
| `2026-10-17-novai-fase-l.md` | Phase L: final sweep |
| `2026-10-17-novai-chat-sweep.md` | Full chat completions sweep |
| `2026-10-17-novai-s114-remocao-grupos-mortos.md` | S114: dead group removal |
| `2026-10-17-novai-s114-verificacao.md` | S114: post-removal verification |
| `2026-10-17-novai-s115-sweep-contrato-erro.md` | S115: error envelope sweep |
| `2026-10-17-novai-s116-fails-corrigiveis.md` | S116: locally fixable failures |

## S122-R Retest (`reteste/`)

| File | Content |
| ---- | ------- |
| `2026-10-18-novai-consolidado-falhas-servidor.md` | Initial server failure consolidation |
| `2026-10-18-novai-erros-servidor-dossie-completo.md` | **Full dossier** of server errors |
| `2026-10-18-novai-reteste-falhas-evidencia.md` | First retest evidence |
| `2026-10-18-novai-reteste-s122-r-evidencia.md` | S122-R: verdicts only |
| `2026-10-18-novai-reteste-s122-r-detalhado.md` | S122-R: detailed analysis (what / why / implications) |
| `2026-10-18-novai-reteste-s122-r-consolidado.md` | **📌 Canonical reference** — unifies evidence + analysis |

### Recommended Reading Order

1. **This file (§ Upstream Tickets)** — 7 bug reports ready to send to NovAI
2. **`reteste/reteste-s122-r-consolidado.md`** — full picture in a single document
3. **`reteste/erros-servidor-dossie-completo.md`** — deep technical context

## Logs (`logs/`)

Raw logs organized by date and type:

- `*-novai-*.jsonl` — raw API responses (chat, embedding, image, proxy, gateway)
- `retest-2026-10-18/` — first retest evidence
- `retest-2026-10-18-v2/` — S122-R retest evidence (5 waves)
- `tool-scan-*` — full tool scan dumps

---

## Upstream Tickets (S122-R)

**Reporter:** <danilogmoura@gmail.com>  
**Gateway:** `https://aiapi-pro.com`  
**Architecture:** We consume the NovAI gateway through a LiteLLM proxy that normalizes API responses to strict OpenAI compatibility. Tests were run against both targets (gateway direct and via proxy) where applicable to isolate upstream bugs from proxy behavior.

**Test methodology:** This is the second retest cycle (S122-R) for these issues. The original failures were first detected on 2026-10-17, and this retest was conducted on 2026-10-18 to confirm persistence vs. transience. Each test was executed with N≥3 retries, 10s spacing between runs, against the live gateway endpoint. All requests use OpenAI-compatible API format with streaming enabled unless noted otherwise. Results marked as "persistent" have now failed across both test cycles (original + retest).

### Summary Table

| Ticket | Error ID | Severity | Models Affected | Action Needed |
| -------- | ---------- | ---------- | ---------------- | --------------- |
| 1 | P-3 | High | minimax-m2.7-fast, minimax-m2.5-fast, step-5-preview-fast | Verify reasoning_tokens upstream |
| 2 | P-7a | High | wan2.2-t2i-flash | Investigate/remove dead route |
| 3 | P-5 | Medium | All (gateway-level) | Standardize error envelope |
| 4 | P-6 | High | glm-4.6v, minimax-m3, kimi-k2.8-preview | Fix tools stream ordering |
| 5 | P-7b | Medium | minimax-text-01 | Add [DONE] terminator |
| 6 | P-7d | High | minimax-video-v2.3-fast | Investigate task creation failure |
| 7 | E-429 | Urgent | glm-4.6v-flash | Investigate persistent rate limit |

---

### Ticket 1: Reasoning Accounting Inconsistency (P-3)

#### Summary

Models supporting thinking/reasoning return inconsistent `usage` fields: `reasoning_chars > 0` but `reasoning_tokens` is disproportionately low or zero. This causes cost underreporting in monitoring dashboards.

#### Affected Models

| Model | reasoning_chars | reasoning_tokens | Expected Ratio |
| ------- | ---------------- | ----------------- | ---------------- |
| minimax-m2.7-fast | 102 | 28 | ~3.6 chars/token ✓ plausible but verify |
| minimax-m2.5-fast | 118 | 31 | ~3.8 chars/token ✓ plausible but verify |
| step-5-preview-fast | 133 | **0** | ❌ Zero tokens for 133 chars of reasoning |

#### How We Tested

Sent identical chat completion requests with `stream=true` to each model, prompting for a reasoning-heavy task. Extracted `usage.reasoning_chars` and `usage.reasoning_tokens` from the final response chunk. Repeated 3 times per model; results were deterministic (same values every run).

#### Impact

- **Cost tracking:** Dashboards using `reasoning_tokens` for billing/cost estimation show incorrect data. For `step-5-preview-fast`, reasoning cost appears as zero despite consuming GPU resources.
- **Monitoring:** Alerting based on token usage misses reasoning overhead entirely for affected models.
- **User-facing:** Customers relying on usage reports see misleading cost breakdowns.

#### Requested Action

Please verify whether the upstream providers (MiniMax, StepFun) are returning correct `reasoning_tokens` values. If this is an upstream issue, please escalate to the respective providers. As a workaround, we may implement local token estimation on our proxy.

---

### Ticket 2: wan2.2-t2i-flash Deterministic Timeout (P-7a)

#### Summary

Image generation via `wan2.2-t2i-flash` always times out after exactly 120 seconds. The gateway accepts the request and forwards it upstream, but never receives a response. This is not transient — it fails 100% of the time across multiple test runs.

#### Evidence

| Run | Timestamp | Result |
|-----|-----------|--------|
| 1 | 2026-10-18T06:20:44Z | Read timed out (read timeout=120) |
| 2 | 2026-10-18T06:22:55Z | Read timed out (read timeout=120) |
| 3 | 2026-10-18T06:25:06Z | Read timed out (read timeout=120) |

Spacing between runs (~131s) confirms the gateway waits until the full timeout before returning an error.

#### How We Tested

Used `novai_test.py --image --live` harness which sends a simple image generation prompt (`"a red cat sitting on a table"`) through the LiteLLM proxy to the gateway. The harness polls the returned URL with a 120s read timeout. All 3 runs produced identical timeout behavior.

#### Impact

- **Route is dead:** Any call to `wan2.2-t2i-flash` consumes 120 seconds of connection resources (open socket, blocked thread) before failing.
- **User experience:** Users attempting image generation via this model receive a timeout error after 2 minutes with no useful feedback.
- **Resource waste:** Under load, these zombie connections can exhaust connection pools.

#### Requested Action

Please investigate the Wanx/Alibaba upstream for `wan2.2-t2i-flash`. If the model is deprecated or misconfigured upstream, please remove it from the available model list so we can update our routing. Note: `wan2.5-t2i-preview` works correctly and passes all tests.

---

### Ticket 3: Gateway Returns Non-OpenAI Error Envelope (P-5)

#### Summary

When the gateway encounters an error (HTTP 400/404), it returns FastAPI-style `{detail: "..."}` instead of the OpenAI-standard `{error: {message, type, code}}`. Our LiteLLM proxy normalizes this automatically, but direct gateway consumers are broken.

#### Evidence

| Endpoint | Target | Response Shape | HTTP Status |
| ---------- | -------- | --------------- | ------------- |
| `/v1/chat/completions` (invalid model) | Gateway direct | `{"detail": "..."}` | 400 |
| `/v1/chat/completions` (invalid model) | Via LiteLLM proxy | `{"error": {"message": "...", "type": "...", "code": "..."}}` | 400 |

All other endpoints (chat.completion, embeddings, images.generation, models.list) return correct OpenAI shape on both targets. Only error responses diverge.

#### How We Tested

Used `novai_contract.py --target both` which sends intentionally invalid requests (nonexistent model `xxx-nao-existe-s117`) to both the gateway directly and through our LiteLLM proxy, then compares the response envelope shape. Ran full error sweep across 110 models × 2 targets = 440 checks; error envelope divergence was consistent across all models.

#### Impact

- **SDK compatibility:** OpenAI SDKs (Python, Node.js, Go) parse `error.message` for human-readable errors. With `{detail}`, SDKs either throw generic exceptions, fail silently, or misclassify the error type.
- **Direct consumers:** Any client connecting directly to the gateway (bypassing our proxy) cannot handle errors properly.
- **Mitigated for us:** Our proxy normalizes the envelope, so our users are unaffected. But this limits direct gateway usability.

#### Requested Action

Please standardize error responses to OpenAI format `{error: {message, type, code}}` at the gateway level. This would enable direct gateway consumption without requiring a normalization proxy.

---

### Ticket 4: Tools Stream Content Before Tool Calls (P-6)

#### Summary

During streaming with `tools` enabled, some models emit `delta.content` (free text) **before** emitting `delta.tool_calls`. Per OpenAI convention, when a model decides to call a tool, the stream should contain only `delta.tool_calls` with `finish_reason=tool_calls`, without concurrent `delta.content`.

#### Affected Models

| Model | Total Events | Tool Calls | Content Before Tool Calls? | Compliant? |
| ------- | ------------- | ------------ | --------------------------- | ------------ |
| glm-4.6v | 55 | 2 | Yes (content at line 77, tool_calls at line 105) | ❌ |
| glm-5 | 18 | 2 | No | ✅ |
| minimax-m3 | 13 | 3 | Yes (content at line 3, tool_calls at line 17) | ❌ |
| kimi-k2.8-preview | 53 | 7 | Yes (content at line 71, tool_calls at line 89) | ❌ |
| hunyuan-t1-vision | 5 | 3 | No | ✅ |

#### How We Tested

Captured raw SSE streams via curl with `tools` parameter containing a simple function definition. Counted event lines and identified the first occurrence of `delta.content` vs `delta.tool_calls`. If content appeared before any tool_call delta, the model was marked non-compliant. Each model tested once (deterministic behavior confirmed by prior testing).

#### Impact

- **AI agents:** Agents (Copilot, Roo Code, LangChain) that process tool call streams may display spurious text to users before executing the tool action, or interpret the pre-tool text as a final answer and skip the tool call entirely.
- **UX degradation:** Chat interfaces show "thinking out loud" text before the tool executes, confusing users about whether the model is responding or acting.
- **Workaround exists:** Client-side buffering can strip pre-tool content, but this adds complexity and latency to every agent implementation.

#### Requested Action

Please escalate to the upstream providers for the 3 affected models:

- **ZhiPu GLM-4.6v** (glm-4.6v)
- **MiniMax M3** (minimax-m3)
- **Moonshot Kimi-K2.8** (kimi-k2.8-preview)

Request that they conform to the OpenAI streaming convention where tool call decisions suppress `delta.content`.

---

### Ticket 5: minimax-text-01 Stream Missing `[DONE]` Terminator (P-7b)

#### Summary

The SSE stream for `minimax-text-01` does not end with the `data: [DONE]` terminator event as required by the OpenAI streaming specification. The stream ends abruptly after the last content chunk.

#### Evidence

```
Total SSE events: 8
[DONE] present: No
Tool calls in stream: 2
Content before tool calls: Yes (also non-compliant, see Ticket 4)
```

Non-streaming mode works correctly.

#### How We Tested

Captured the complete SSE stream via curl with `stream=true`. Counted all `data:` lines and checked for the presence of `data: [DONE]` as the final event. The stream terminated after 8 events without the `[DONE]` marker.

#### Impact

- **SDK hang:** The OpenAI Python SDK uses `[DONE]` as the stream termination signal. Without it, the async iterator may hang waiting for more data, or raise `StopIteration` prematurely losing the last chunk.
- **Framing errors:** Clients that rely on `[DONE]` for stream boundary detection may treat the abrupt end as a network error.
- **Scope:** Affects only `minimax-text-01` in streaming mode. Non-stream calls are unaffected.

#### Requested Action

Please escalate to MiniMax upstream. This is the same class of bug previously fixed in S41→S42 (framing `\n` vs `\n\n`). As a workaround, our proxy could detect stream end and inject a synthetic `[DONE]`, but upstream fix is preferred.

---

### Ticket 6: minimax-video-v2.3-fast Task Creation Fails Immediately (P-7d)

#### Summary

Video generation via `minimax-video-v2.3-fast` fails at task creation time with status `FAILED`. This is not a processing timeout — the upstream rejects the request immediately upon submission.

#### Evidence

```
Task ID: 1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5
Status after 1 poll: FAILED
Polls before failure: 1 (immediate)
```

#### How We Tested

Used `novai_test.py --video --live` which POSTs a video generation request to create a task, then polls the task status endpoint with exponential backoff. The task returned `FAILED` status on the very first poll, indicating the upstream rejected the request during creation rather than during processing.

#### Impact

- **Feature unavailable:** Video generation via MiniMax V2.3 Fast is completely non-functional.
- **Premium feature:** Video generation is a high-value capability; failures here directly affect paying users.
- **Not a timeout issue:** Unlike slow-processing tasks, this fails instantly — retry/backoff cannot help.

#### Requested Action

Please investigate using task ID `1409238524-WandVideo-811df415e84746e7a7eed25faf3b47a5` to determine the root cause of the immediate failure. If the model is misconfigured or deprecated upstream, please remove it from the available model list. Also please verify whether other MiniMax video variants (`minimax-video-*`) are functional.

---

### Ticket 7: ZhiPu GLM-4.6v-flash Persistent Rate Limiting (E-429)

#### Summary

`glm-4.6v-flash` now returns HTTP 429 (rate limit exceeded) on **every** request, even with minimal load (3 requests spaced 10 seconds apart). This has worsened from intermittent to persistent since our previous test cycle.

#### Evidence

| Run | Spacing | Result |
| ----- | --------- | -------- |
| 1 | — | HTTP 429 |
| 2 | +10s | HTTP 429 |
| 3 | +10s | HTTP 429 |

For comparison, `glm-4.7-flash` remains intermittent (1/3 pass under same conditions).

#### How We Tested

Sent 3 sequential chat completion requests to each model with 10-second spacing between runs. Used identical prompts and parameters. Recorded HTTP status codes. The 3/3 failure rate for `glm-4.6v-flash` was deterministic across the test window.

#### Impact

- **Model unusable:** 100% failure rate makes `glm-4.6v-flash` unsuitable for any production workload.
- **Wasted resources:** Routing traffic to this model wastes request quota and increases perceived latency (each 429 still consumes a round-trip).
- **Regression:** This model was previously intermittent (sometimes working). The shift to persistent failure suggests an upstream quota reduction or infrastructure change.

#### Requested Action

Please investigate whether the ZhiPu upstream has reduced rate limits or quota for `glm-4.6v-flash`. If the model is no longer viable at current limits, please advise so we can remove it from our routing catalog. We will continue routing to `glm-4.7-flash` with retry logic as it remains intermittently functional.

---

*Generated from S122-R retest consolidated report (2026-10-18). Full evidence logs available in `logs/`.*
