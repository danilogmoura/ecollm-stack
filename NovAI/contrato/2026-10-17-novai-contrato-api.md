# S117 — Contrato de API NovAI (shape OpenAI)

Data: **2026-10-17** · checks: 13

## resumo

- `pass`: 11
- `diverged`: 1
- `skipped`: 1

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
| chat.completion | gateway | glm-5 | pass | 3590 ms | conforme chat.completion (OpenAI) |
| chat.completion.chunk | gateway | glm-5 | pass | 3715 ms | conforme chat.completion.chunk (22 chunks + [DONE]) |
| embeddings | gateway | glm-5 | pass | 1393 ms | conforme embeddings (dim=1024) |
| images.generation | gateway | glm-5 | pass | 18243 ms | conforme images (item0 via url) |
| models.list | gateway | — | pass | 1328 ms | conforme models list (n=121) |
| error.openai | gateway | glm-5 | diverged | 719 ms | FastAPI {detail} no gateway (HTTP 400) — divergência documentada: "Model 'xxx-nao-existe-s117' not supported. Available: glm-5," |
| chat.completion | proxy | novai-glm-4.7-flash | pass | 22210 ms | conforme chat.completion (OpenAI) |
| chat.completion.chunk | proxy | novai-glm-4.7-flash | pass | 21879 ms | conforme chat.completion.chunk (134 chunks + [DONE]) |
| embeddings | proxy | novai-glm-4.7-flash | pass | 21 ms | conforme embeddings (dim=1024) |
| images.generation | proxy | novai-glm-4.7-flash | pass | 18089 ms | conforme images (item0 via url) |
| models.list | proxy | — | pass | 59 ms | conforme models list (n=152) |
| error.openai | proxy | novai-glm-4.7-flash | pass | 24 ms | OpenAI error shape (HTTP 400): '/chat/completions: Invalid model name passed in model=novai-' |
| sdk.chat.completion | proxy | novai-glm-4.7-flash | skipped |  | pacote 'openai' não instalado (modo C opt-in) |

## divergências documentadas

- **error.openai @ gateway**: FastAPI {detail} no gateway (HTTP 400) — divergência documentada: "Model 'xxx-nao-existe-s117' not supported. Available: glm-5,"
