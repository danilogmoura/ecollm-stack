# S117 — Contrato de API NovAI (shape OpenAI)

Data: **2026-10-17** · checks: 12

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
| chat.completion | gateway | glm-5 | pass | 3291 ms | conforme chat.completion (OpenAI) |
| chat.completion.chunk | gateway | glm-5 | pass | 5154 ms | conforme chat.completion.chunk (26 chunks + [DONE]) |
| embeddings | gateway | glm-5 | pass | 1382 ms | conforme embeddings (dim=1024) |
| images.generation | gateway | glm-5 | pass | 21124 ms | conforme images (item0 via url) |
| models.list | gateway | — | pass | 691 ms | conforme models list (n=121) |
| error.openai | gateway | glm-5 | diverged | 725 ms | FastAPI {detail} no gateway (HTTP 400) — divergência documentada: "Model 'xxx-nao-existe-s117' not supported. Available: glm-5," |
| chat.completion | proxy | novai-glm-4.7-flash | pass | 14804 ms | conforme chat.completion (OpenAI) |
| chat.completion.chunk | proxy | novai-glm-4.7-flash | pass | 3582 ms | conforme chat.completion.chunk (115 chunks + [DONE]) |
| embeddings | proxy | novai-glm-4.7-flash | pass | 21 ms | conforme embeddings (dim=1024) |
| images.generation | proxy | novai-glm-4.7-flash | pass | 17032 ms | conforme images (item0 via url) |
| models.list | proxy | — | pass | 56 ms | conforme models list (n=152) |
| error.openai | proxy | novai-glm-4.7-flash | pass | 26 ms | OpenAI error shape (HTTP 400): '/chat/completions: Invalid model name passed in model=novai-' |

## divergências documentadas

- **error.openai @ gateway**: FastAPI {detail} no gateway (HTTP 400) — divergência documentada: "Model 'xxx-nao-existe-s117' not supported. Available: glm-5,"
