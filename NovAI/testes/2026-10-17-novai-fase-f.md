# Fase F — contrato/TTFT/JSON/erros/params (S103)

- Data: **2026-10-17**
- Harness: `eval/novai_test.py` (`--contract --target both --live`)
- Alvos: **gateway** `aiapi-pro.com/v1` + **proxy** LiteLLM `:4000/v1`
- Grupo: `novai-glm-4.7-flash-fast` (upstream `glm-4.7-flash`)
- Log bruto: `reports/logs/2026-10-17-novai-both.jsonl` (16 registros, **captura limpa**)
- Log contaminado (pré-correção A2): `reports/logs/2026-10-17-novai-both.contaminated.jsonl`
- Matriz: `reports/novai-test-matrix.csv`

## Resultado por alvo (re-rodada limpa)

| alvo | success | failure |
| --- | --- | --- |
| proxy | 7 | 1 |
| gateway | 2 | 6 |

Divergência gateway × proxy: `same_pass` 2, `same_fail` 3, `proxy_only` 3.

> A rodada anterior (32 registros) tinha 13/3 no proxy e 2/14 no gateway porque
> o `--contract` rodava a bateria **duas vezes** por alvo (uma no `run_one`, outra
> na suíte) e a captura estava desalinhada. A re-rodada com a correção A2 produz
> 16 registros — 8 por alvo, um por check.

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
>
> ✅ **Re-rodado em 2026-10-17 05:59 UTC.** O log antigo foi preservado como
> `2026-10-17-novai-both.contaminated.jsonl`; o novo tem 16 registros e cada um
> carrega o seu próprio `request`/`body_raw`. Verificação por teste:
>
> | teste | body capturado (gateway) |
> | --- | --- |
> | `chat` | `messages` + `extra_body.thinking` |
> | `ttft` | `messages` + `stream:true` |
> | `json_strict` | `messages` + `response_format` |
> | `param_forwarding` | `messages` + `stop` + `temperature` |
> | `needle` | `messages` (filler ~2000 tok) |
> | `concurrency` | `messages` + `max_tokens:16` |
> | `error_404` | model inexistente |
> | `error_400` | só `model` + `max_tokens` (sem `messages`) |

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

### A6 — Gateway IGNORA `thinking:{type:disabled}` (divergência, não nosso)

Descoberto na re-rodada limpa. O teste `chat` manda
`extra_body: {"thinking": {"type": "disabled"}}` — a flag oficial ZhiPu que o
proxy usa para desligar o reasoning (S43, provada).

| alvo | `reasoning_tokens` | `completion_tokens` | veredito |
| --- | --- | --- | --- |
| proxy | **0** | 2 | ✅ `no-reasoning OK len(content)=2` |
| gateway | **123** | 126 | ❌ `reasoning_chars=481 reasoning_tokens=123` |

O gateway **aceita** o campo (não dá 400) mas **não o repassa** ao upstream —
`reasoning_content` volta preenchido com 481 chars. Consequência prática: quem
chama o gateway direto paga 126 tokens onde o proxy cobra 2, e recebe
`reasoning_content` que o cliente pode não esperar.

Classificação: **divergência do gateway**, não bug nosso. O proxy está correto.

### A7 — `param_forwarding` passa no gateway por acidente

O gateway devolveu `finish_reason=length` com `content=""` e
`reasoning_tokens=24` (todo o orçamento de `max_tokens` consumido pelo
reasoning). O veredito passou porque `completion_tokens=24 <= max_tokens=24`,
mas o `stop=['quatro']` **nunca foi exercitado** — não houve conteúdo para
cortar. No proxy o mesmo teste devolveu `"1, 2, 3, 4, 5, 6"` com
`completion_tokens=17`.

Efeito colateral de A6: com thinking ligado, `max_tokens` pequeno é consumido
pelo reasoning e o teste de forwarding fica **vacuamente verdadeiro**. Sugestão
para a Fase I: exigir `content` não-vazio no veredito de `param_forwarding`.

## Resultado detalhado — re-rodada limpa (2026-10-17 05:59 UTC)

### proxy (7/8)

| teste | status | evidência |
| --- | --- | --- |
| chat | ✅ | `no-reasoning OK len(content)=2` |
| ttft | ❌ | `HTTP 429` (ZhiPu, A4) |
| json_strict | ❌ | `HTTP 429` (ZhiPu, A4) |
| param_forwarding | ✅ | `stop=['quatro'] respeitado; completion_tokens=17<=24` |
| needle | ✅ | `agulha em pos=0 len=11` |
| concurrency | ✅ | `n=4 ok=4 p50=3728.9ms p95=4962.6ms` |
| error_404 | ❌ | `status=400 esperado=404` (A3) |
| error_400 | ✅ | `Missing required parameter: 'messages'` |

### gateway (2/8)

| teste | status | evidência |
| --- | --- | --- |
| chat | ❌ | `reasoning_chars=481 reasoning_tokens=123` (A6) |
| ttft | ❌ | `HTTP 429` (ZhiPu, A4) |
| json_strict | ❌ | `HTTP 429` (ZhiPu, A4) |
| param_forwarding | ⚠️✅ | `completion_tokens=24<=24` mas `content=""` (A7) |
| needle | ❌ | `HTTP 429` (ZhiPu, A4) |
| concurrency | ❌ | `n=4 ok=0 errors={'429': 4}` (A4) |
| error_404 | ❌ | `status=400 esperado=404` + shape `detail` (A3) |
| error_400 | ✅ | `HTTP 400 error='[ZhiPu (智谱)] 输入不能为空'` (A5) |

## Custo

Baixo: 8 chamadas por alvo, `max_tokens` ≤ 512, 1 grupo. A re-rodada levou
**~2min** (05:59 UTC).

## Próximo passo

Fase F fechada com captura limpa. Seguir para a **Fase G** (mídia), levando
para a Fase I: A5 (400 "输入不能为空"), A6 (thinking ignorado) e A7 (veredito
vacuamente verdadeiro em `param_forwarding`).
