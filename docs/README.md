# Documentação operacional — ecollm-stack

Diagnósticos, runbooks e resoluções de problemas reais desta stack
(Ollama + LiteLLM + Postgres/pgvector + MCP `rag_search` + agentes Copilot/Roo Code).

| Doc | Tema | Status |
| --- | ---- | ------ |
| [`runbook-sync-gate.md`](./runbook-sync-gate.md) | Runbook operacional: `sync` (índice = código) e `gate` (trava de regressão recall@8) | ✅ Ativo |
| [`2026-09-28-roo-code-hang-ripgrep.md`](./2026-09-28-roo-code-hang-ripgrep.md) | Roo Code trava em "API Request…" para sempre — causa raiz: `ripgrep` ausente | ✅ Resolvido |
