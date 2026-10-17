# NovAI — Fase K: agentes E2E (T25 Copilot BYOK · T26 Roo Code)

**Data:** 2026-10-17 · **Trilha:** S103 (PLANO-TESTES-NOVAI §9) · **Custo:** baixo
**Alvo:** proxy LiteLLM `http://localhost:4000/v1` (caminho real do agente)
**Harness:** `eval/novai_test.py` → `--agent MODEL [--client copilot|roo|both]`

---

## 1. O que a fase prova (e o que não prova)

O agente **não é simulado**: o harness reproduz o request que o cliente manda de
fato e valida a resposta que ele consome. O que se prova é o **contrato** que o
agente depende; o clique na extensão é manual e está registrado no §6.

| Prova | Como |
| --- | --- |
| System prompt longo não quebra a rota | ~2,7 kB de instruções em **toda** request |
| `tools` + `tool_choice:"auto"` são aceitos | 2 funções (`read_file`, `run_tests`) |
| `stream:true` devolve SSE canônico | `data: {...}` separado por `\n\n` + `[DONE]` |
| O modelo **age** (não só conversa) | exige `tool_calls` consolidados |
| `temperature` do Roo não é rejeitada | `temperature:0` no corpo do Roo |

**Não prova:** o comportamento da UI da extensão (renderização, aprovação de
tool call, retry do cliente). Isso é manual (§6).

---

## 2. Contrato reproduzido por cliente

| Campo | Copilot BYOK | Roo Code |
| --- | --- | --- |
| `messages[0]` | system longo | system longo |
| `tools` | 2 funções | 2 funções |
| `tool_choice` | `"auto"` | `"auto"` |
| `stream` | `true` | `true` |
| `temperature` | **ausente** | `0` |
| `max_tokens` | 256 | 256 |

Fonte: `build_agent_body()` — puro, testável offline.

---

## 3. Resultado

**10/10 verde** (4 modelos × 2 clientes), 0 divergência entre clientes.

| Modelo | Cliente | Latência | Evidência |
| --- | --- | --- | --- |
| `novai-deepseek-v4-flash` | copilot | 1353 ms | `chunks=43 chars=0 tools=1 (read_file)` |
| `novai-deepseek-v4-flash` | roo | 1201 ms | `chunks=13 chars=0 tools=1 (read_file)` |
| `novai-deepseek-v4-flash-fast` | copilot | 1300 ms | `chunks=22 chars=29 tools=1 (read_file)` |
| `novai-deepseek-v4-flash-fast` | roo | 1144 ms | `chunks=21 chars=27 tools=1 (read_file)` |
| `novai-glm-4.7-flash-fast` | copilot | 33989 ms | `chunks=2 chars=0 tools=1 (read_file)` |
| `novai-glm-4.7-flash-fast` | roo | 25113 ms | `chunks=2 chars=0 tools=1 (read_file)` |
| `novai-qwen3.8-max-fast` | copilot | 2134 ms | `chunks=8 chars=0 tools=1 (read_file)` |
| `novai-qwen3.8-max-fast` | roo | 1846 ms | `chunks=8 chars=0 tools=1 (read_file)` |

Log bruto: `reports/logs/2026-10-17-novai-agent.jsonl` (10 registros, 0
credenciais — `grep -c "sk-"` = 0, `grep -c "Bearer"` = 0).

### Leitura dos números

- **`chars=0` é normal, não falha.** O modelo escolheu **agir** em vez de
  conversar: emitiu `tool_calls` e nenhum texto. O veredito aceita
  texto **ou** tool call — exigir os dois reprovaria um agente saudável.
- **`deepseek-v4-flash` (thinking ON) gasta o orçamento em reasoning** e chega
  ao tool call sem texto; o `-fast` (thinking OFF) ainda emite 27–29 chars de
  preâmbulo. Mesmo padrão da Fase I (I1/I2).
- **`glm-4.7-flash-fast` é ~25× mais lento** (25–34 s vs ~1,2 s) com o mesmo
  payload. Não é falha, mas é um dado de escolha de modelo para agente: o
  cliente fica 30 s sem primeiro token útil.
- **`qwen3.8-max-fast`** fica no meio (1,8–2,1 s) e também age sem texto.

---

## 4. Achados

### K1 — bug NOSSO (classe H): contagem de `tool_calls` inflada e nome perdido

O stream fragmenta a chamada: o **primeiro** fragmento traz `id` + `name`, os
seguintes trazem **só pedaços de `arguments`**, sem `name`. A primeira versão do
veredito contava fragmentos crus:

```
tools=11 (?,read_file)     ← 11 fragmentos = 1 chamada; 10 deles sem nome
```

Corrigido com `merge_tool_calls()` (consolida por `index`, concatena
`arguments`, preserva o `name` do primeiro fragmento):

```
tools=1 (read_file)        ← correto
```

Impacto se não fosse corrigido: qualquer agente com `arguments` longo passaria
com contagem absurda e o nome da ferramenta se perderia na evidência — o
veredito "passou" esconderia que o cliente não sabe **qual** ferramenta chamar.

### K2 — upstream: `glm-4.7-flash-fast` tem TTFT de ~25 s com system prompt longo

Mesmo payload, mesmo proxy: `deepseek-v4-flash` responde em ~1,2 s e o GLM em
25–34 s. Não é timeout nem erro — é latência de primeiro token. Registrado como
dado de seleção de modelo, não como bug.

### K3 — observação: `chars=0` domina

3 dos 4 modelos devolveram **só** tool call, sem texto. É o comportamento
correto para "leia o arquivo e diga o que o projeto faz" (o agente age primeiro),
mas significa que **validação de agente não pode exigir texto** — daí o veredito
aceitar `texto OU tool_calls`.

---

## 5. Verificação

```
RAG_PROFILE=qwen37 .venv/bin/python -m pytest
→ 814 passed
```

`eval/tests/test_novai_test.py`: **215 passed** (+19 da Fase K).
Gate `eval.recall --gate`: **r@8 0,933 ≥ 0,900** (MRR 0,714).
Invariante 7 preservado: nenhum `novai-*` entrou em `rag-chat`/`fallbacks`/
embeddings do RAG — a fase só **testa** o gateway.

---

## 6. Passo manual (o que o harness não cobre)

O contrato está provado; falta o clique na extensão. Roteiro:

1. **Copilot BYOK** — em `settings.json`, apontar o provider OpenAI-compatível
   para `http://localhost:4000/v1` com `LITELLM_MASTER_KEY` e modelo
   `novai-deepseek-v4-flash-fast`. Abrir o chat, pedir "leia o README.md e
   resuma". Esperado: tool call `read_file` renderizada + resposta coerente.
2. **Roo Code** — mesmo endpoint/chave no provider "OpenAI Compatible"; pedir a
   mesma tarefa. Esperado: idem, com `temperature:0` no request.
3. Conferir em `reports/logs/2026-10-17-novai-agent.jsonl` que a chamada da
   extensão aparece com `test_id=agent-*`.

Se a extensão falhar onde o harness passou, o problema é do **cliente**
(renderização/parse), não da rota — é exatamente a separação que a fase queria.
