# Roo Code BYOK (S115-d) — causa raiz do travamento em "API Request…"

**Data:** 2026-10-18 (noite, UTC). **Veredito:** stack 100% saudável; o bloqueio era
**credencial errada no perfil LiteLLM do Roo** + um segundo problema conhecido
(ripgrep ausente) reaparecido.

## Evidência forense (LiteLLM SpendLogs)

A coluna `metadata->>'user_agent'` separa os clientes que passam pelo proxy:

| user_agent | origem |
|---|---|
| `GitHubCopilotChat/0.70.0` | sessão Copilot (tráfego pesado, prompts 30k–105k) |
| `python-requests/2.34.2` | harness `eval/novai_*.py` (smoke tests) |
| `curl/8.5.0` | testes manuais de endpoint |
| `RooCode/3.54.0` | **extensão Roo** — só 4 linhas, todas `failure` |

As 4 linhas do Roo (`call_type=/v1/models`, 2026-10-17 16:42–16:43 UTC):

```
error_code: 401
error_message: "401: LiteLLM Virtual Key expected.
  Received=lite****cret, expected to start with 'sk-'."
normalized_error: 401_AUTHENTICATION_FAILED
```

⇒ A API key digitada no perfil NovAI do Roo era o **placeholder** `lite-...secret`
(mostrado pela UI como exemplo de formato), não uma chave real. O preflight
`GET /v1/model/info`/`/v1/models` do handler LiteLLM falha com 401 **antes** de
qualquer stream de chat → a task congela em `api_req_started` sem nunca emitir
`POST /v1/chat/completions`. Por isso nenhuma linha novai-* pertence ao Roo.

## Segundo defeito (independente, reaplicado)

`ripgrep not found` no log do Roo = regressão do fix de 2026-09-28
(`docs/2026-09-28-roo-code-hang-ripgrep.md`): o diretório
`<appRoot>/node_modules/@vscode/ripgrep/bin/` nem existia mais. Reaplicado:

```bash
APPROOT=~/.vscode-server/bin/6d62b1d5dace93a33b3a6d3eca1317bd5e15bcb1
mkdir -p "$APPROOT/node_modules/@vscode/ripgrep/bin"
cp "$APPROOT/node_modules/@vscode/ripgrep-universal/bin/linux-x64/rg" \
   "$APPROOT/node_modules/@vscode/ripgrep/bin/rg"
chmod +x "$APPROOT/node_modules/@vscode/ripgrep/bin/rg"
```

⚠ Refazer a cada update do vscode-server (muda o hash do appRoot).

## Correção entregue ao usuário

Virtual key dedicada criada via `/key/generate` (master key do `.env`):

- alias `roo-code-s115`, modelos `novai-deepseek-v4-flash` e `-fast`, sem expiração
- valor gerado em `/tmp/roo_key.txt` (efêmero; **nunca versionar**)
- validação imediata: `GET /v1/model/info` → **200**; `POST /v1/chat/completions`
  (`novai-deepseek-v4-flash`) → resposta normal

## Como aplicar no Roo

1. Configurações do Roo → perfil **NovAI** (provider `LiteLLM`):
   - Base URL: `http://localhost:4000` (sem `/v1`)
   - API Key: colar a chave `sk-…` nova (NÃO o placeholder da UI)
2. Recarregar a janela (o handler é criado no boot da task).
3. Novo teste "Teste" — sucesso = mensagem do modelo aparece na UI **e** surge
   linha `user_agent=RooCode/3.54.0` com `status=success` na SpendLogs:

```sql
SELECT "startTime", model_group, prompt_tokens, completion_tokens, status
FROM "LiteLLM_SpendLogs"
WHERE metadata::jsonb->>'user_agent'='RooCode/3.54.0'
ORDER BY "startTime" DESC LIMIT 10;
```

## Critério de aceitação S115-d

Clique manual registrado = linha RooCode success na SpendLogs + texto do assistente
renderizado na UI da task. Até agora: **0 linhas RooCode success** (só as 4 falhas
401 de 16:42–16:43 de 17/10). Aguarda re-teste com a chave correta.
