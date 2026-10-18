# NovAI gateway: malformed SSE framing breaks all streaming responses

**To:** <support@aiapi-pro.com>
**Subject:** Streaming endpoint emits non-conformant SSE (events separated by single `\n`), breaking every OpenAI-compatible client
**Base URL:** `https://aiapi-pro.com/v1`
**Date:** 2026-10-14

## ✅ RESOLVIDO (validado ao vivo nesta stack)

Reportado à NovAI e **corrigido**. Verificação com o harness SSE forte
(`eval/novai_test.py --stream --live`, parser tolerante + checagem de conformidade):

| Modelo (via proxy :4000) | chunks JSON | bad | [DONE] | `\n\n` | `\n` simples | veredito |
| --- | --: | --: | --: | --: | --: | --- |
| glm-4.6v | 48 | 0 | sim | 49 | 0 | ✅ conforme |
| deepseek-v4-flash | 52 | 0 | sim | 53 | 0 | ✅ conforme |
| glm-5-turbo | 2 | 0 | sim | 3 | 0 | ✅ conforme |
| kimi-k2.7-code | 32 | 0 | sim | 33 | 0 | ✅ conforme |
| qwen3-coder-flash* | 3 | 0 | sim | 4 | 0 | ✅ conforme |

Fronteira real observada no wire agora: `}}]}\n\ndata:` (antes era `}}]}\ndata:`).
Zero eventos separados por `\n` simples em todas as amostras. *qwen3-coder-flash é o
modelo do report original; seu caso SSE está conforme (a falha paralela de `chat`
não-stream desse modelo é thinking ON/OFF, assunto separado — não SSE).

O teste agora **exige** `\n\n` e marca `\n` simples como REGRESSÃO. Abaixo o report
original preservado para histórico.

## Problem

`POST /v1/chat/completions` with `stream: true` returns HTTP 200 and
`Content-Type: text/event-stream; charset=utf-8`, but the Server-Sent Events
framing is invalid. Events are separated by a **single** `\n` instead of the
blank line (`\n\n`) required by the SSE spec and by the OpenAI streaming format.

Raw bytes observed on the wire:

```
data: {"id":...,"choices":[{"delta":{"content":"..."}}]}\ndata: {"id":...,"choices":[{"delta":{"content":"..."}}]}\n
```

Correct framing requires a blank line between events:

```
data: {...}\n\ndata: {...}\n\n
```

Because there is no `\n\n`, a spec-compliant parser treats two consecutive
`data:` lines as a **single** multi-line event and concatenates the JSON
objects, producing:

```
json.JSONDecodeError: Extra data: line 2 column 1 (char 168)
```

This is a framing bug, not a payload bug — each individual JSON object is valid.

## Impact

- **Non-streaming (`stream: false`) works fine** (HTTP 200, valid JSON). Only streaming is broken.
- Any client that strictly parses SSE fails. Confirmed failures through the LiteLLM proxy (`streaming_handler.py`): every stream request to your gateway raises `APIConnectionError` → HTTP 500 to the end user.
- GitHub Copilot always sends `stream: true`, so **no NovAI model is usable in Copilot** through this gateway.
- Setting `Accept: text/event-stream` explicitly does **not** change the output.

## Scope

Not model-specific. Streaming framing is malformed for every model tested:

| Model (slug) | non-stream | stream |
| --- | --- | --- |
| `glm-4.7-flash` | 200 OK | malformed SSE (HTTP 500 upstream on some calls) |
| `glm-4.1v-thinking-flash` | 200 OK | malformed SSE |
| `deepseek-v4-flash` | 200 OK | malformed SSE |
| `qwen3-coder-flash` | 200 OK | malformed SSE |

## Reproduction

```bash
curl -N https://aiapi-pro.com/v1/chat/completions \
  -H "Authorization: Bearer $NOVAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-4.1v-thinking-flash","stream":true,
       "messages":[{"role":"user","content":"hi"}]}' \
  | xxd | grep -o '0a0a'   # no \n\n between events => framing invalid
```

Compare against a conformant endpoint (e.g. OpenAI, Google, Ollama): there the
bytes show `...7d 0a 0a 64 61 74 61 3a...` (`}\n\ndata:`) between events.

## Request

Terminate each SSE event with a blank line (`\n\n`) as required by the WHATWG
EventSource spec and the OpenAI streaming format, so standard clients
(OpenAI SDK, LiteLLM, Copilot) can parse the stream. Your documentation states
streaming is supported, but the wire format currently contradicts it.

Environment: Linux, OpenAI-compatible clients, LiteLLM proxy 1.102.x.

---

## Follow-up (2026-10-14) — obrigado, mas o framing ainda não foi corrigido

Hi NovAI Team,

Thanks for the fast turnaround and for confirming the key/balance are fine. I re-tested
after your fix. **Progress is real but incomplete:**

- ✅ The opaque **HTTP 500 is gone**. A direct `stream: true` call to
  `https://aiapi-pro.com/v1/chat/completions` for `glm-4.7-flash` now returns **HTTP 200**
  with a genuine `chat.completion.chunk` payload (previously it was a bare 500).
- ❌ The **SSE event terminator is still wrong**, so streaming still breaks every
  spec-compliant client. Inspecting the raw response bytes of the 200 stream:

  ```
  b'}\ndata:'  -> 49 occurrences   (single newline between events)
  b'}\n\ndata:' ->  0 occurrences   (blank line — REQUIRED, still absent)
  b'\n\n'       ->  1 occurrence    (only after the final `data: [DONE]`)
  ```

  Each individual `data:` JSON object is valid; the problem is purely that events are
  separated by a **single `\n`** instead of the blank line (`\n\n`) mandated by the
  WHATWG EventSource spec and the OpenAI streaming format. A conformant parser therefore
  treats the whole stream as one multi-line event and fails on `json.loads`:

  ```
  json.JSONDecodeError: Extra data: line 2 column 1 (char 168)
  ```

  Through our LiteLLM proxy this surfaces as `APIConnectionError → HTTP 500`, and GitHub
  Copilot (which always sends `stream: true`) still cannot use **any** NovAI model —
  confirmed on both `glm-4.7-flash` and `glm-4.1v-thinking-flash`.

**Request:** terminate **each** SSE event with a blank line (`\n\n`), matching what
OpenAI/Google/Ollama emit (`...7d 0a 0a 64 61 74 61 3a...`). The re-route to Zhipu fixed
the upstream error, but the gateway's SSE serializer is still joining events with one
`\n`. Once `\n\n` is used between events, standard clients will parse the stream.

Happy to re-verify the moment it's deployed. Thanks again.

— Danilo
