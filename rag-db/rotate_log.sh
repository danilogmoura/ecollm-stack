#!/usr/bin/env bash
# ============================================================================
# S90/B2 — Rotação simples de log (mantém as últimas N linhas).
# ----------------------------------------------------------------------------
# Trunca um arquivo de log quando ele passa de um limite, mantendo as últimas
# `KEEP` linhas. Usado pelo hook pós-commit para o `rag-sync.log` (S87) e o
# `mcp-stderr.log` (S90/B2). Idempotente e barato (só age acima do limite).
#
# Uso:
#   bash rag-db/rotate_log.sh <arquivo> [LIMIT=1000] [KEEP=500]
#
# Exit 0 sempre (best-effort: rotação nunca deve derrubar o chamador).
# ============================================================================
set -uo pipefail

LOG="${1:-}"
LIMIT="${2:-1000}"
KEEP="${3:-500}"

[ -n "$LOG" ] || exit 0
[ -f "$LOG" ] || exit 0

# Só rotaciona acima do limite (evita reescrever a cada chamada).
if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt "$LIMIT" ]; then
  tail -n "$KEEP" "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
fi
exit 0
