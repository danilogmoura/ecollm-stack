# Sonda thinking-ON/OFF por modelo NovAI — a rota `-fast` faz sentido?

- **Data:** 2026-10-16 (varredura iniciada 2026-10-15)
- **Escopo:** S102 — responder "faz sentido ter `fast` e `thinking` para todos os
  modelos?" medindo, por par `base`/`-fast`, se o modo ON realmente raciocina e o
  modo OFF realmente zera o reasoning.
- **Fonte:** sonda `eval/novai_test.py --thinking` (commit `f54034e`) via proxy
  LiteLLM `:4000` → gateway NovAI `https://aiapi-pro.com/v1`.
- **Logs brutos:** `reports/logs/2026-10-15-thinking-sense-sweep.log` (61 pares),
  `...-retry.log` (16 falhos), `2026-10-16-thinking-sense-retry2.log` (16 falhos,
  2 passadas).
- **Natureza:** diagnóstico local (gitignored). Não é governança.

---

## 1. Convenção testada

- **`base`** = thinking **ON** (herda o default do upstream, **sem** `extra_body`).
- **`-fast`** = thinking **OFF** via `extra_body.thinking:{type:disabled}`.

A sonda dispara os dois modos e classifica:

| Categoria | Significado | Veredito |
| --- | --- | --- |
| `funciona` | ON raciocina **e** OFF zera | dualidade real — **manter as duas rotas** |
| `nao-suporta` | ON==OFF==0 | modelo **não tem thinking** — `-fast` **redundante** |
| `so-on` | ON raciocina, OFF **não** zera | flag `disabled` não pega |
| `so-off` | invertido (OFF raciocina, ON não) | anomalia |
| `sonda falhou` | erro no disparo (HTTP) | não-sondável |

---

## 2. Resultado — 61 pares chat

| Categoria | Qtd |
| --- | --- |
| ✅ `funciona` | **24** |
| ⚪ `nao-suporta` | 17 |
| 🔴 `so-on` | 4 |
| ❌ `sonda falhou` | 16 |

**Resposta:** **não**, `fast`+`thinking` **não** faz sentido para todos. Só
**24/61** têm dualidade real; 17 não têm thinking nenhum (a rota `-fast` é
redundante) e 16 sequer são sondáveis.

### 2.1 ✅ `funciona` (24) — manter as duas rotas

`glm-4.7-flash` · `doubao-seed-2.0-pro` · `deepseek-v4.1-flash` · `deepseek-v4-pro`
· `deepseek-v4-flash` · `deepseek-v4-flash-vision` · `qwen3.8-max` · `qwen3.7-max`
· `doubao-seed-2.1-pro` · `doubao-seed-2.0-code` · `doubao-seed-2.1-turbo` ·
`doubao-seed-2.0-lite` · `minimax-m3` · `kimi-k3` · `hy4-preview` · `hy3` ·
`mimo-v2.5-pro` · `mimo-v2.6-pro` · `mimo-v2.6-flash` · `glm-5.2` · `glm-5.1` ·
`glm-5` · `glm-5v-turbo` · `glm-4.6v`

> Nota: `minimax-m3` marca `funciona` só via `reasoning_content` (tok=0) —
> reasoning presente mas não contabilizado em tokens.

### 2.2 ⚪ `nao-suporta` (17) — `-fast` redundante

`qwen3-vl-plus` · `qwen3.5-ocr` · `qwen-vl-ocr` · `qwen-mt-plus` · `qwen-plus` ·
`qwen3-coder-flash` · `qwen3-omni-flash` · `minimax-text-01` · `hunyuan-t1-vision`
· `hy-vision-2.0-instruct` · `hunyuan-turbos-vision-video` · `hy-mt2-pro` ·
`hy-mt2-plus` · `hunyuan-role` · `hy-role` · `hy3-preview` · `hy-mt2-lite`

### 2.3 🔴 `so-on` (4) — flag OFF não zera

`minimax-m2.7` · `minimax-m2.5` · `step-5-preview` · `glm-4.1v-thinking-flash`

### 2.4 ❌ `sonda falhou` (16) — não-sondáveis

Confirmado por **3 tentativas** (sweep + retry + retry2 com 2 passadas idênticas):
**nada é transitório**, exceto o 429 (overload do próprio modelo).

| Causa | Qtd | Modelos |
| --- | --- | --- |
| HTTP **404** — rota morta no upstream | 6 | `qwen3.6-max-preview`, `qwen3-max`, `qwen3-coder-plus`, `qwen-vl-max`, `qwen3-vl-flash`, `qwen-omni-turbo` |
| HTTP **400** — "request rejected" (rejeitam o payload) | 7 | `kimi-k2.8-preview`, `kimi-k2.7-code`, `kimi-k2.7-code-highspeed`, `kimi-k2.6`, `kimi-k2.5`, `glm-5-turbo`, `glm-5.3-flashx` |
| HTTP **400** — "始终思考" (sempre pensam, desligar impossível) | 2 | `glm-5.3`, `glm-5.3-flash` |
| HTTP **429** — overload ZhiPu (persiste nas 3 tentativas) | 1 | `glm-4.6v-flash` |

---

## 3. Recomendações

1. **Manter** as duas rotas para os **24 `funciona`**.
2. **Reavaliar remoção** da rota `-fast` para os **17 `nao-suporta`** (redundante —
   mesmo comportamento com/sem a flag).
3. **Investigar** os **4 `so-on`**: a flag `thinking:{type:disabled}` não está
   surtindo efeito nesses modelos (talvez exijam outro mecanismo de desligamento).
4. **Rotas mortas (6× 404)**: candidatas a remoção do `config.yaml` — o upstream
   não as expõe mais.
5. **`glm-5.3`/`glm-5.3-flash`**: sempre pensam; a rota `-fast` é estruturalmente
   inválida (upstream manda usar `low`/`high`/`max`).
6. **`glm-4.6v-flash`**: re-testar noutro horário (429 = overload do modelo).

> **Invariante 7 preservado:** testar ≠ adotar. Nenhuma rota foi alterada por este
> diagnóstico.
