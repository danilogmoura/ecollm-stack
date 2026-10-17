# S116 — Os 12 fails da matriz: 9 são corrigíveis por config

> Data: 2026-10-17 · Origem: pergunta "o que ainda falta fazer" no `PLANO-TESTES-NOVAI.md`
> Escopo: reanálise dos 12 fails da matriz `reports/novai-test-matrix.csv`

## 1. Resumo

Dos **12 fails** da matriz, **9 são corrigíveis por config nossa** e **3 são bug de
contabilidade do upstream**. A classificação anterior ("todos de upstream") estava
**errada** para 9 deles.

| Grupo | N | Causa real | Acionável? |
| --- | --- | --- | --- |
| Kimi `-fast` | 5 | `thinking:{type:disabled}` rejeitado pelo Moonshot | ✅ **sim** |
| ZhiPu `-fast` | 4 | `thinking:{type:disabled}` rejeitado pelo ZhiPu | ✅ **sim** |
| MiniMax/Step | 3 | `reasoning_tokens=0` com `reasoning_content` preenchido | ❌ upstream |

## 2. O que estava errado na análise anterior

A matriz registrava os 8 primeiros como "classe B — contrato quebrado no upstream
(Kimi/ZhiPu sem modo thinking-off)". A premissa era: *o upstream não suporta desligar
o thinking, então a rota `-fast` é inviável*.

**Isso é falso.** Medido ao vivo:

| Chamada | Resultado |
| --- | --- |
| `kimi-k2.8-preview` sem `thinking` | **200** — `content` + `reasoning_content` |
| `kimi-k2.8-preview` + `thinking:{type:disabled}` | **400** — "rejected by an internal MaaS component" |
| `kimi-k2.8-preview` + `reasoning_effort:"low"` | **200** — `content="ok"` |
| `kimi-k2.8-preview` + `reasoning_effort:"minimal"` | **200** — `content="Alright?"` |

O modelo **funciona**. O que quebra é o **campo `thinking`** que o nosso `-fast`
injeta via `extra_body`. O upstream rejeita o campo, não o modelo.

## 3. A correção: `reasoning_effort` em vez de `thinking`

Testado nos **9 modelos** que falhavam, com `reasoning_effort:"low"`:

| Modelo | Resultado | `content` | `reasoning_chars` |
| --- | --- | --- | --- |
| `kimi-k2.8-preview` | ✅ 200 | `'ok'` | 129 |
| `kimi-k2.7-code` | ✅ 200 | `'ok'` | 137 |
| `kimi-k2.7-code-highspeed` | ✅ 200 | `'ok'` | 82 |
| `kimi-k2.6` | ✅ 200 | `'ok'` | 183 |
| `kimi-k2.5` | ✅ 200 | `'ok'` | 604 |
| `glm-5.3` | ✅ 200 | `'ok'` | **0** |
| `glm-5.3-flash` | ✅ 200 | `'ok'` | 316 |
| `glm-5-turbo` | ✅ 200 | `'ok'` | **0** |
| `glm-5.3-flashx` | ✅ 200 | `'ok'` | 225 |

**9/9 passam.** Nenhum 400.

### 3a. Nuance por família

| Família | `thinking:{type:disabled}` | `reasoning_effort:"low"` | `reasoning_effort:"minimal"` |
| --- | --- | --- | --- |
| Kimi (Moonshot) | ❌ 400 | ✅ 200 | ✅ 200 |
| ZhiPu `glm-5.3` / `glm-5-turbo` | ❌ 400 | ✅ 200 (`reasoning=0`) | ❌ 400 |
| ZhiPu `glm-5.3-flash` / `-flashx` | ❌ 400 | ✅ 200 (`reasoning>0`) | ❌ 400 |

`reasoning_effort:"low"` é o **único valor aceito pelas duas famílias**. `minimal`
funciona no Kimi mas o ZhiPu rejeita.

### 3b. Mensagem do ZhiPu é enganosa

O erro diz *"该模型始终思考，不支持关闭思考；请使用 low、high 或 max"* ("este modelo
sempre pensa, não suporta desligar o thinking; use low, high ou max"). Mas
`thinking:{type:"low"}` **também** retorna 400. O que ele quer dizer é
`reasoning_effort`, não `thinking.type` — a mensagem confunde os dois campos.

## 4. Os 3 fails que NÃO são corrigíveis

| Modelo | `content` | `reasoning_content` | `reasoning_tokens` |
| --- | --- | --- | --- |
| `minimax-m2.7` | `'ok'` | 91 chars | **0** |
| `minimax-m2.5` | `'\n\nok'` | 137 chars | 28 |
| `step-5-preview` | `'ok'` | 135 chars | **0** |

O modelo **pensa** (o `reasoning_content` vem preenchido) mas o upstream **não conta**
os tokens de reasoning no `usage`. É bug de contabilidade do MiniMax/Step, não do
nosso stack. `reasoning_effort:"low"` não muda nada.

**Ação:** nenhuma do nosso lado. O veredito do harness está correto em reprovar
(`reasoning_tokens` é o campo contratual).

## 5. Correção proposta no `config.yaml`

Trocar, nos 8 grupos `-fast` afetados:

```yaml
      extra_body:
        thinking:
          type: disabled
```

por:

```yaml
      extra_body:
        reasoning_effort: low
```

Grupos afetados (9):

- `novai-kimi-k2.8-preview-fast`
- `novai-kimi-k2.7-code-fast`
- `novai-kimi-k2.7-code-highspeed-fast`
- `novai-kimi-k2.6-fast`
- `novai-kimi-k2.5-fast`
- `novai-glm-5.3-fast`
- `novai-glm-5.3-flash-fast`
- `novai-glm-5-turbo-fast`
- `novai-glm-5.3-flashx-fast`

**Risco:** `reasoning_effort` é campo OpenAI nativo; o LiteLLM pode já repassá-lo sem
`extra_body`. Testar as duas formas antes de commitar.

**Não afeta** os `-fast` que já passam (ex.: `glm-4.7-flash-fast` usa `thinking` e
funciona) — a troca deve ser **cirúrgica**, só nos 9 que falham.

## 6. Impacto esperado na matriz

| Antes | Depois |
| --- | --- |
| 103 pass / 26 skipped / 16 removed / **12 fail** | 112 pass / 26 skipped / 16 removed / **3 fail** |

Os 3 restantes são bug de contabilidade do upstream (MiniMax/Step), documentados.

## 7. Próximo passo

1. Aplicar a troca nos 9 grupos (cirúrgica, sem tocar nos que passam).
2. `docker compose up -d --force-recreate litellm` (config só é lida no boot).
3. Re-rodar `--family chat --live` nos 9 grupos.
4. Atualizar a matriz + este relatório com o resultado.
