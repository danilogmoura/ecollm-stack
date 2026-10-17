# Fase F — contrato/TTFT/JSON/erros/params (S103)

- Data: **2026-10-17**
- Harness: `eval/novai_test.py` (`--contract --target both --live`)
- Alvos: **gateway** `aiapi-pro.com/v1` + **proxy** LiteLLM `:4000/v1`
- Grupo: `novai-glm-4.7-flash-fast` (upstream `glm-4.7-flash`)
- Log bruto: `reports/logs/2026-10-17-novai-both.jsonl` (32 registros)
- Matriz: `reports/novai-test-matrix.csv`

## Resultado por alvo

| alvo | success | failure |
| --- | --- | --- |
| proxy | 13 | 3 |
| gateway | 2 | 14 |

## Achados

### A1 — BUG NOSSO (classe H): gateway recebia o nome do grupo LiteLLM

O gateway NovAI **não conhece** o nome do grupo (`novai-<slug>[-fast]`); ele só
aceita o `upstream_id` (`<slug>`). A primeira rodada mandou
`novai-glm-4.7-flash-fast` e recebeu:

```
{"detail":"Model 'novai-glm-4.7-flash-fast' not supported. Available: glm-5, ..."}
```

**Corrigido** em `run_one` e `run_contract_suite` (`model = upstream_id` quando
`target == "gateway"`), com 3 testes de regressão. O relatório continua falando
do **grupo** (`r.group = grp`), só o `model` enviado muda.

### A2 — BUG NOSSO (classe H): captura do jsonl desalinhada

O `sink` do `make_capturing_sender` é limpo a cada chamada. A captura era
anexada **depois do batch inteiro**, então **todos** os registros da bateria de
contrato ficavam com o `request`/`body_raw` do **último** check (`error_400`).

Sintoma observado: `param_forwarding` passou com evidência
`stop=['quatro'] respeitado; completion_tokens=24<=max_tokens=24`, mas o
`request` gravado era `{"model": ..., "max_tokens": 8}` (sem `messages`, sem
`stop`) — o corpo do `error_400`.

**Corrigido**: `run_contract_suite` agora aceita `sink=` e anexa a captura
**imediatamente após cada check**. Teste de regressão:
`test_run_contract_suite_captures_each_check_separately`.

> ⚠️ **Os registros de `reports/logs/2026-10-17-novai-both.jsonl` anteriores a
> esta correção têm `request`/`body_raw` contaminados** para os testes da
> bateria de contrato. Os **vereditos** (`status`, `evidence`) são válidos — só
> a captura bruta está errada. Re-rodar a Fase F regenera o log limpo.

### A3 — Divergência de contrato de erro 404 (gateway, não nosso)

| alvo | resposta ao modelo inexistente |
| --- | --- |
| gateway | **HTTP 400** + `{"detail": "Model '...' not supported. Available: ..."}` (shape FastAPI) |
| proxy | **HTTP 400** + `{"error": {"message": "/chat/completions: Invalid model name passed in ..."}}` |

Nenhum dos dois devolve **404**. O gateway também não usa o envelope `error`
padrão OpenAI (`detail` em vez de `error`). Classificação: **divergência do
gateway**, não bug nosso — o veredito `error_404` falha corretamente nos dois.

### A4 — Rate limit do upstream ZhiPu (classe E)

O gateway devolveu 429 do provedor em `chat`, `json_strict` e em 2 de 4
requisições de `concurrency`:

```
{"error":{"message":"[ZhiPu (智谱)] 该模型当前访问量过大，请您稍后再试",
          "type":"upstream_provider_error","provider":"ZhiPu (智谱)","code":429}}
```

Não é bug nosso nem do gateway — é cota do provedor. O proxy absorveu melhor
(1 de 2 rodadas de `concurrency` passou com `n=4 ok=4`).

### A5 — Gateway devolve 400 "输入不能为空" para payloads válidos

`ttft`, `json_strict`, `needle` e `concurrency` no gateway receberam
`{"error":{"message":"[ZhiPu (智谱)] 输入不能为空", ...}}` ("input cannot be
empty") mesmo com `messages` preenchido. Suspeita: o gateway não repassa
`messages` corretamente para o upstream ZhiPu em alguns caminhos, ou o
`max_tokens` baixo (8) dispara validação do provedor. **A investigar na Fase I**
(com payload maior e `max_tokens` normal).

## Resultado detalhado — proxy (válido)

| teste | status | evidência |
| --- | --- | --- |
| chat | ✅ | `no-reasoning OK len(content)=2` |
| ttft | ✅ | `ttft_ms=875.6` / `1836.0` |
| json_strict | ✅ | `json_object keys=['n','ok']` |
| param_forwarding | ✅ | `stop=['quatro'] respeitado; completion_tokens=17<=24` |
| needle | ✅ | `agulha em pos=0 len=11` |
| concurrency | ⚠️ | `n=4 ok=2` (429×2) na 1ª; `n=4 ok=4` na 2ª |
| error_404 | ❌ | `status=400 esperado=404` (A3) |
| error_400 | ✅ | `Missing required parameter: 'messages'` |

## Custo

Baixo: ~16 chamadas por alvo, `max_tokens` ≤ 512, 1 grupo. Rodada completa
levou **~2min27s** (04:59:05 → 05:01:32 UTC).

## Próximo passo

Re-rodar a Fase F com a captura corrigida para regenerar o jsonl limpo, depois
seguir para a **Fase G** (mídia).
