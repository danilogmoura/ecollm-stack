#!/usr/bin/env bash
# ============================================================================
# S71 — Harness de teste do BOOTSTRAP isolado (init.sql num Postgres efêmero).
# ----------------------------------------------------------------------------
# Prova que um VOLUME NOVO nasce íntegro: sobe um pgvector descartável numa
# porta separada, monta o init.sql em docker-entrypoint-initdb.d/ (como o
# compose faz), espera readiness e roda verify_schema.py contra ELE.
#
# SEGURANÇA (zero impacto no sistema atual):
#   - container EFÊMERO (--rm), SEM volume nomeado;
#   - porta SEPARADA (5544), nunca a 5433 de produção;
#   - `trap ... EXIT` derruba o container MESMO em falha/interrupção.
#   Não toca ecollm-stack_rag_db_data nem o rag-db de produção.
#
# Uso:
#   bash rag-db/test_bootstrap.sh            # porta 5544
#   RAG_BOOTSTRAP_PORT=5545 bash rag-db/test_bootstrap.sh
#
# Exit 0 = volume novo nasce íntegro (verify_schema OK).
# Exit ≠0 = bootstrap quebrado (init.sql inválido/incompleto).
# ============================================================================
set -euo pipefail

PORT="${RAG_BOOTSTRAP_PORT:-5544}"
CTR="rag-bootstrap-test"
IMG="pgvector/pgvector:pg17"
DB_USER="rag"; DB_PASS="rag_secret"; DB_NAME="rag"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INIT_SQL="$REPO_ROOT/rag-db/init.sql"
VERIFY="$REPO_ROOT/rag-db/verify_schema.py"
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"

cleanup() {
  # Idempotente: --rm já remove ao parar, mas garantimos o kill mesmo em falha.
  docker rm -f "$CTR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[bootstrap] pré-checagens"
[ -f "$INIT_SQL" ] || { echo "ERRO: init.sql não encontrado em $INIT_SQL" >&2; exit 2; }
[ -f "$VERIFY" ]   || { echo "ERRO: verify_schema.py não encontrado em $VERIFY" >&2; exit 2; }
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
  [ -n "$PY" ] || { echo "ERRO: nenhum python encontrado (defina PYTHON=...)" >&2; exit 2; }
fi
command -v docker >/dev/null 2>&1 || { echo "ERRO: docker não encontrado no PATH" >&2; exit 2; }

# Se já houver um container com esse nome (run anterior interrompido), remove.
cleanup

echo "[bootstrap] subindo Postgres efêmero '$CTR' na porta $PORT (imagem $IMG)"
docker run -d --rm --name "$CTR" \
  -p "127.0.0.1:${PORT}:5432" \
  -e "POSTGRES_USER=${DB_USER}" \
  -e "POSTGRES_PASSWORD=${DB_PASS}" \
  -e "POSTGRES_DB=${DB_NAME}" \
  -v "${INIT_SQL}:/docker-entrypoint-initdb.d/init.sql:ro" \
  "$IMG" >/dev/null

echo "[bootstrap] aguardando readiness (pg_isready)"
ready=0
for _ in $(seq 1 60); do
  if docker exec "$CTR" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "ERRO: Postgres não ficou pronto em 60s. Logs:" >&2
  docker logs "$CTR" 2>&1 | tail -30 >&2 || true
  exit 3
fi

# O entrypoint do Postgres roda init.sql de forma ASSÍNCRONA em relação ao
# pg_isready (init scripts rodam após o server aceitar conexões). Dá uma janela
# curta e checa se o schema apareceu; se não, espera mais.
echo "[bootstrap] aguardando init.sql materializar o schema"
schema_ok=0
for _ in $(seq 1 30); do
  if docker exec "$CTR" psql -U "$DB_USER" -d "$DB_NAME" -tA \
       -c "SELECT to_regclass('chunks') IS NOT NULL" 2>/dev/null | grep -q '^t$'; then
    schema_ok=1; break
  fi
  sleep 1
done
if [ "$schema_ok" -ne 1 ]; then
  echo "ERRO: init.sql não criou a tabela 'chunks' (bootstrap quebrado). Logs:" >&2
  docker logs "$CTR" 2>&1 | tail -40 >&2 || true
  exit 4
fi

echo "[bootstrap] rodando verify_schema.py contra o volume NOVO (:${PORT})"
set +e
"$PY" "$VERIFY" --url "postgresql://${DB_USER}:${DB_PASS}@localhost:${PORT}/${DB_NAME}"
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  echo "[bootstrap] ✅ volume NOVO nasce íntegro (verify_schema exit 0)"
else
  echo "[bootstrap] ❌ bootstrap QUEBRADO (verify_schema exit $rc)" >&2
fi
exit "$rc"
