# S117 — Contrato de API NovAI (shape OpenAI)

Data: **2026-10-18** · checks: 12

## resumo

- `pass`: 11
- `diverged`: 1

## conformidade por endpoint × alvo

| endpoint | gateway | proxy | veredito |
| --- | --- | --- | --- |
| chat.completion | ✅ | ✅ | ✅ |
| chat.completion.chunk | ✅ | ✅ | ✅ |
| embeddings | ✅ | ✅ | ✅ |
| images.generation | ✅ | ✅ | ✅ |
| models.list | ✅ | ✅ | ✅ |
| error.openai | ⚠️ | ✅ | ⚠️ |

## checks

| endpoint | alvo | modelo | status | latência | evidência |
| --- | --- | --- | --- | --- | --- |
| chat.completion | gateway | glm-5 | pass | 3509 ms | conforme chat.completion (OpenAI) |
| chat.completion.chunk | gateway | glm-5 | pass | 3264 ms | conforme chat.completion.chunk (20 chunks + [DONE]) |
| embeddings | gateway | glm-5 | pass | 2096 ms | conforme embeddings (dim=1024) |
| images.generation | gateway | glm-5 | pass | 17479 ms | conforme images (item0 via url) |
| models.list | gateway | — | pass | 1144 ms | conforme models list (n=121) |
| error.openai | gateway | glm-5 | diverged | 711 ms | FastAPI {detail} no gateway (HTTP 400) — divergência documentada: "Model 'xxx-nao-existe-s117' not supported. Available: glm-5," |
| chat.completion | proxy | novai-glm-4.7-flash | pass | 21787 ms | conforme chat.completion (OpenAI) |
| chat.completion.chunk | proxy | novai-glm-4.7-flash | pass | 8941 ms | conforme chat.completion.chunk (122 chunks + [DONE]) |
| embeddings | proxy | novai-glm-4.7-flash | pass | 28 ms | conforme embeddings (dim=1024) |
| images.generation | proxy | novai-glm-4.7-flash | pass | 17055 ms | conforme images (item0 via url) |
| models.list | proxy | — | pass | 59 ms | conforme models list (n=152) |
| error.openai | proxy | novai-glm-4.7-flash | pass | 29 ms | OpenAI error shape (HTTP 400): '/chat/completions: Invalid model name passed in model=novai-' |

## divergências documentadas

- **error.openai @ gateway**: FastAPI {detail} no gateway (HTTP 400) — divergência documentada: "Model 'xxx-nao-existe-s117' not supported. Available: glm-5,"
