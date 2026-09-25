#!/usr/bin/env python3
"""S18 — Aplicador de migrações de schema do índice RAG (T-OPS-3).

Por que existe: ``rag-db/init.sql`` só roda na PRIMEIRA criação do volume
(entrada do docker-entrypoint) e o entrypoint oficial NÃO garante ON_ERROR_STOP
(ver S11). Mudar init.sql num volume existente não aplica nada. Este script dá
o caminho para EVOLUIR o schema depois do bootstrap, de forma versionada e
idempotente.

Convenção (ver rag-db/migrations/README.md):
  - Um arquivo por mudança: ``NNN_descricao.sql`` (NNN = inteiro de 3 dígitos,
    crescente, sem lacunas). Nunca se edita uma migração já aplicada; correção
    vira N+1.
  - Cada arquivo deve ser IDEMPOTENTE (IF NOT EXISTS / IF EXISTS / ON CONFLICT),
    pois pode rodar tanto num volume novo (init.sql já criou tudo → no-op) quanto
    num antigo.
  - O runner registra cada NNN aplicado na tabela ``schema_migrations``; uma
    segunda execução pula o que já foi aplicado (por isso é seguro re-rodar).

Cada migração roda em sua PRÓPRIA transação com ON_ERROR_STOP efetivo (psycopg3
autocommit=off + commit por arquivo): se um passo falhar, faz rollback daquela
migração e PARA — nunca deixa metade aplicada nem marca como concluída.

Uso:
    python rag-db/run_migrations.py                 # aplica pendentes (lê .env)
    python rag-db/run_migrations.py --dry-run       # mostra o que aplicaria
    python rag-db/run_migrations.py --url postgresql://... # override da URL
    python rag-db/run_migrations.py --status        # lista aplicadas x pendentes

Saída: uma linha por migração (APLICADA/PULADA/falha); exit != 0 em erro.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from ingest.store import db_url_from_env  # reaproveita load_dotenv + default
except Exception:  # pragma: no cover - ambiente mínimo sem deps do ingest
    def db_url_from_env() -> str:  # type: ignore
        import os
        return os.environ.get("RAG_DB_URL", "postgresql://rag:rag_secret@localhost:5433/rag")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_NAME_RE = re.compile(r"^(\d{3})_[A-Za-z0-9_\-]+\.sql$")

# Tabela de controle: guarda o NNN de cada migração já aplicada.
_ENSURE_CONTROL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,           -- NNN (ex.: '001')
    filename    text   NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def discover() -> list[tuple[str, Path]]:
    """Migrações no diretório, ordenadas por NNN. Ignora README/arquivos soltos."""
    out: list[tuple[str, Path]] = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _NAME_RE.match(p.name)
        if not m:
            raise ValueError(
                f"nome de migração inválido: {p.name!r} (esperado NNN_descricao.sql)"
            )
        out.append((m.group(1), p))
    # Sem lacunas/duplicatas: a sequência de NNN deve ser 001,002,... contínua.
    nums = [int(n) for n, _ in out]
    if nums and nums != list(range(nums[0], nums[0] + len(nums))):
        raise ValueError(f"sequência de migrações com lacuna/duplicata: {nums}")
    return out


def applied_versions(conn) -> set[str]:
    conn.execute(_ENSURE_CONTROL)
    return {r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version").fetchall()}


def run(url: str, *, dry_run: bool = False, status_only: bool = False) -> int:
    import psycopg

    migrations = discover()
    with psycopg.connect(url) as conn:  # autocommit OFF → transação por arquivo
        done = applied_versions(conn)
        pending = [(v, p) for v, p in migrations if v not in done]

        if status_only:
            print(f"[migrations] {len(migrations)} no total, {len(done)} aplicadas, "
                  f"{len(pending)} pendentes")
            for v, p in migrations:
                mark = "x" if v in done else " "
                print(f"  [{mark}] {v}  {p.name}")
            return 0

        if not pending:
            print("[migrations] nada a aplicar — schema já está na última versão "
                  f"({max((v for v, _ in migrations), default='—')})")
            return 0

        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            if dry_run:
                print(f"[dry-run] aplicaria {version} · {path.name}")
                continue
            try:
                conn.execute(sql)                       # uma transação p/ esta migração
                conn.execute(
                    "INSERT INTO schema_migrations (version, filename) VALUES (%s, %s) "
                    "ON CONFLICT (version) DO NOTHING", (version, path.name))
                conn.commit()
                print(f"[migrations] ✅ aplicada {version} · {path.name}")
            except Exception as exc:                    # noqa: BLE001
                conn.rollback()
                print(f"[migrations] ❌ FALHOU {version} · {path.name}: {exc}",
                      file=sys.stderr)
                print("  (rollback desta migração; nenhuma outra foi tocada)",
                      file=sys.stderr)
                return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aplica migrações de schema (S18)")
    ap.add_argument("--url", default=None, help="URL do rag-db (default: RAG_DB_URL/.env)")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run",
                    help="mostra o que seria aplicado, sem escrever")
    ap.add_argument("--status", action="store_true",
                    help="lista aplicadas x pendentes e sai")
    args = ap.parse_args(argv)
    url = args.url or db_url_from_env()
    return run(url, dry_run=args.dry_run, status_only=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
