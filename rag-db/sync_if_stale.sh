#!/usr/bin/env bash
# ============================================================================
# S77 — Sync inteligente: roda `rag sync` SÓ SE o índice estiver defasado.
# ----------------------------------------------------------------------------
# Compara o HEAD do git com o `head_sha` publicado em `rag_sync_state`. Se forem
# iguais, sai 0 SEM gastar cota de embedding. Se diferirem, roda o sync do perfil
# ativo (RAG_PROFILE do .env, default qwen37).
#
# Seguro p/ agendar (hook pós-commit, timer systemd, cron): idempotente e barato
# quando não há mudança. O custo só aparece quando há código novo de fato.
#
# Uso:
#   bash rag-db/sync_if_stale.sh            # perfil do .env (RAG_PROFILE)
#   RAG_PROFILE=bgem3 bash rag-db/sync_if_stale.sh
#   bash rag-db/sync_if_stale.sh --force    # sincroniza mesmo se fresco
#
# Exit 0 = fresco (nada a fazer) OU sync OK. Exit ≠0 = sync falhou.
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"

# Perfil: env explícito > RAG_PROFILE do .env > qwen37 (default do stack).
PROFILE="${RAG_PROFILE:-$(awk -F= '/^RAG_PROFILE=/{print $2}' .env 2>/dev/null || true)}"
PROFILE="${PROFILE:-qwen37}"

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

# HEAD atual do git.
HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
if [ -z "$HEAD_SHA" ]; then
  echo "[sync-if-stale] não é um repo git — nada a fazer." >&2
  exit 0
fi

# head_sha publicado no índice (via psql no container rag-db).
PUBLISHED="$(docker compose exec -T rag-db psql -U rag -d rag -tA \
  -c "SELECT head_sha FROM rag_sync_state WHERE repo='$(basename "$REPO_ROOT")' AND profile='${PROFILE}';" \
  2>/dev/null | tr -d '[:space:]' || true)"

if [ "$FORCE" -eq 0 ] && [ -n "$PUBLISHED" ] && [ "$PUBLISHED" = "$HEAD_SHA" ]; then
  echo "[sync-if-stale] índice FRESCO (${HEAD_SHA:0:7} == publicado) — nada a fazer."
  exit 0
fi

echo "[sync-if-stale] defasado (publicado=${PUBLISHED:0:7} atual=${HEAD_SHA:0:7}) — sincronizando perfil '$PROFILE'..."
RAG_PROFILE="$PROFILE" "$PY" -m ingest.cli sync --repo "$REPO_ROOT"
echo "[sync-if-stale] OK."
