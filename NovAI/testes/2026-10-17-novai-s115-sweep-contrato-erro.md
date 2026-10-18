# S115 — Sweep do contrato de erro (T15/T16) em todos os grupos de chat

> Data: 2026-10-17 · Harness: `eval/novai_error_sweep.py` · Commit: ver §6
> Alvos: `gateway` (NovAI direto) e `proxy` (LiteLLM :4000) · 110 grupos × 2 casos × 2 alvos

## 1. Motivação

Até S115 o contrato de erro (`error_404`, `error_400`) só tinha rodado em **1 grupo**
(`novai-deepseek-v4-flash`, 22 repetições na Fase F). Com o fix de S115 — aceitar
**400 ou 404** no caso 404 e o shape FastAPI `{"detail": ...}` — a premissa do teste
mudou, e ficou em aberto se o comportamento de erro é **uniforme entre upstreams**
(Kimi/ZhiPu/ByteDance podem usar envelopes diferentes).

Custo: **zero token no upstream** (modelo inexistente / payload inválido). O sweep é
praticamente grátis.

## 2. Método

Para cada grupo de chat, em cada alvo:

| Caso | Request | Aceite |
| --- | --- | --- |
| `error_404` | `model = <slug>-nao-existe-<ts>`, `messages` válido | HTTP **400 ou 404** + corpo com `error` **ou** `detail` legível |
| `error_400` | `model` válido, **sem** `messages` | HTTP **400** + corpo com `error` **ou** `detail` legível |

O corpo cru de cada resposta é classificado por `envelope_class()`:

- `openai` — `{"error": {...}}` (envelope OpenAI/LiteLLM)
- `fastapi` — `{"detail": ...}` (shape FastAPI do gateway NovAI)
- `both` / `other` / `empty` — anomalias

## 3. Resultado

**440 checks · 440 pass · 0 fail.**

| Alvo | Teste | Pass | Envelope |
| --- | --- | --- | --- |
| gateway | `error_404` | **110/110** | `fastapi` (110) |
| gateway | `error_400` | **110/110** | `openai` (110) |
| proxy | `error_404` | **110/110** | `openai` (110) |
| proxy | `error_400` | **110/110** | `openai` (110) |

### 3a. Achado principal — o gateway usa DOIS envelopes

O gateway NovAI **não** é uniforme: o shape depende de **onde o erro é detectado**.

| Erro | Quem detecta | Shape |
| --- | --- | --- |
| modelo inexistente | gateway (roteamento) | `{"detail": "Model 'x' not supported. Available: ..."}` |
| payload inválido | **upstream** (ZhiPu/ByteDance/...) | `{"error": {"message": "[ZhiPu (智谱)] 输入不能为空"}}` |

Ou seja: o gateway **repassa** o envelope do upstream quando o erro vem de lá, e usa
o shape FastAPI quando o erro é dele próprio. O proxy LiteLLM normaliza **tudo** para
o envelope OpenAI — inclusive o `detail` do gateway.

**Consequência prática:** o fix de S115 (aceitar `detail`) era **necessário e
suficiente**. Sem ele, 110/110 `error_404` no gateway reprovariam; com ele, 440/440
passam. Nenhum upstream usa um terceiro shape.

### 3b. Mensagens de erro por família (amostra)

| Família | `error_400` (mensagem do upstream) |
| --- | --- |
| ZhiPu (`glm-*`) | `[ZhiPu (智谱)] 输入不能为空` |
| ByteDance (`doubao-*`) | `[ByteDance (火山引擎)] The parameter \`messages\` specified in the...` |
| Proxy (todos) | `/chat/completions: Missing required parameter: 'messages'.` |

Todas legíveis e distinguíveis — o contrato de erro está **satisfeito** em todos os
110 grupos.

## 4. Artefatos

- `eval/novai_error_sweep.py` — harness do sweep (CLI + `envelope_class` + `summarize` puros)
- `eval/tests/test_novai_error_sweep.py` — 12 testes offline
- `reports/logs/2026-10-17-novai-error-sweep.jsonl` — 440 registros (sucesso e falha)

Reproduzir:

```bash
set -a && . ./.env && set +a
RAG_PROFILE=qwen37 .venv/bin/python -m eval.novai_error_sweep --target both --sleep 0.35
```

## 5. Conclusão

O item de escopo aberto "contrato de erro só testado em 1 grupo" está **fechado**.
O contrato de erro é uniforme nos 110 grupos de chat, nos dois alvos, com a ressalva
documentada de que o gateway alterna entre `detail` (erro próprio) e `error` (erro
repassado do upstream).

Nenhuma ação de config necessária. Nenhum bug nosso encontrado.

## 6. Commits

- `50217ee` — fix do `error_404` (aceita 400 + shape `detail`)
- (este relatório) — sweep + testes
