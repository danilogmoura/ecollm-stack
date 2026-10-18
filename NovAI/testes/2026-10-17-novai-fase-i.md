# S103 — Fase I: contexto longo + stress (T19 estendido, T20 estendido)

**Data:** 2026-10-17 · **Escopo:** fechar A5/A7 herdados da Fase F e exercitar
contexto longo (needle em 3 posições) e stress de concorrência.
**Alvo:** `novai-deepseek-v4-flash` (gateway `aiapi-pro.com` e proxy LiteLLM).
**Custo:** baixo (`max_tokens` 16–256, 11 checks por rodada).

## 1. O que foi entregue

### Funções puras novas (`eval/novai_test.py`)

| Função | Papel |
| --- | --- |
| `build_needle_context(needle, *, filler_tokens, position, filler)` | monta contexto longo com a agulha em posição relativa ∈ [0,1]; determinístico; `ValueError` fora do intervalo |
| `verdict_needle_position(assembled, needle, *, position)` | delega a `verdict_needle` e prefixa a evidência com `pos=<x> ::` |
| `summarize_stress(results)` | agrega N chamadas: `n, ok, p50_ms, p95_ms, p99_ms, errors, error_rate, throughput_rps, degraded` |
| `verdict_stress(summary, *, max_error_rate, allow_degraded)` | fail-closed: `n==0` ⇒ fail; `error_rate > max_error_rate` ⇒ fail; `allow_degraded=False` e `degraded` ⇒ fail |

Percentil nearest-rank (`ceil(p·n)-1`), mesma convenção de `summarize_concurrency`
e `eval/mcp_report.py`. `degraded = p95 > 2×p50`.

### Runners novos

- `run_needle_positions(sender, group, *, filler_tokens=2000, positions=(0.0,0.5,1.0))`
  → **lista** de `CheckResult` (`needle@0`, `needle@0.5`, `needle@1`). Um fail não
  aborta os outros.
- `run_stress(sender, group, *, n=12, workers=6, max_error_rate=0.0)` →
  `CheckResult(test="stress")` com p99, taxa de erro e throughput.

### Integração

- `run_contract_suite(..., stress=False, needle_positions=False)` — aceita steps
  que devolvem **lista** (needle em N posições) além de `CheckResult` único.
- CLI: `--context` liga `stress=True` e `needle_positions=True`.

## 2. Achados

### I1 — `max_tokens=64` truncava o needle (classe H, NOSSO bug) — **corrigido**

O modelo de reasoning gastava o orçamento pensando e o `content` saía cortado:

```
finish_reason=length · content="AGULHA-7" · completion_tokens=64
```

O check reprovava por **orçamento**, não por perda de contexto. `max_tokens`
64 → **256**. Após a correção: **needle 3/3 verde em 3 rodadas consecutivas**.

### I2 — `content=""` com resposta em `reasoning_content` (classe H) — **corrigido**

O gateway às vezes devolve `content=""` e coloca o texto em `reasoning_content`
(o modelo "pensou" a resposta e não emitiu o canal final). O veredito lia só
`content` e reprovava com `len=0` mesmo com `body_raw` contendo `"AGULHA-7F3A"`.

Fallback aplicado **só quando `content` está vazio** — content preenchido nunca é
substituído (evita mascarar resposta errada).

### I3 — A7 fechado

`verdict_param_forwarding` agora exige `content` não-vazio como **primeiro**
critério. `run_param_forwarding` subiu `max_tokens` 24 → 256 (com 24 o gateway
gastava tudo em reasoning: `content=""`, `finish_reason=length`, `stop` nunca
exercitado).

### I4 — A5 não reproduzido

Com `max_tokens` normal, o `400 "输入不能为空"` da Fase F não apareceu em nenhuma
rodada. Era o mesmo artefato de orçamento de reasoning do I1/I3.

### I5 — A6 permanece aberto (gateway)

Gateway continua ignorando `extra_body.thinking:{type:disabled}`
(`reasoning_tokens` > 0 no gateway, 0 no proxy). Fora do escopo da Fase I.

### I6 — Contrato de erro 404 divergente (gateway, herdado A3)

Gateway devolve **400** com shape FastAPI `{"detail": "Model '...' not supported"}`
em vez de **404** com `{"error": {...}}`. Proxy devolve 400 com `error` (LiteLLM).
Confirmado nas duas rodadas.

## 3. Resultado ao vivo

`--live --contract --context --id novai-deepseek-v4-flash --target gateway`

| Check | Resultado |
| --- | --- |
| `chat` | ✅ |
| `ttft` | ✅ |
| `json_strict` | ✅ |
| `param_forwarding` | ✅ (A7 fechado) |
| `needle@0` | ✅ |
| `needle@0.5` | ✅ |
| `needle@1` | ✅ |
| `concurrency` (N=4) | ✅ p50 ≈ 1,2–1,5 s |
| `stress` (N=12, 6 workers) | ✅ p50 ≈ 1,3 s · p95 ≈ 2,0 s · err 0% |
| `error_404` | ❌ 400 em vez de 404 (I6) |
| `error_400` | ✅ |

**10/11 verde.** O único fail é divergência do gateway (I6), não do nosso stack.
Sob carga sustentada apareceram 429 do upstream (classe E) — comportamento
esperado, registrado no jsonl.

## 4. Verificação

- Suíte completa: **776 passed** (era 756; +20 testes novos).
- `eval/tests/test_novai_test.py`: **177 passed**.
- Invariante 7 preservado (nenhum `novai-*` em `rag-chat`/`fallbacks`/embeddings).

## 5. Arquivos tocados

- `eval/novai_test.py` — 4 funções puras, 2 runners, `--context`, integração na suíte.
- `eval/tests/test_novai_test.py` — +20 testes (needle posições, stress, A7).
- `.planning/PLANO-TESTES-NOVAI.md` — Fase I marcada executada; §9b atualizado.
