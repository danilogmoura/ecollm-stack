"""S69 — Lockstep do schema: `rail-db/init.sql` × `_PROFILE_DDL_TEMPLATE` (store.py).

O schema de `chunks` vive em 2 lugares que DEVEM ficar em sincronia:
  1. `rag-db/init.sql` — cria a tabela baseline (`chunks`) em volume NOVO.
  2. `ingest/store.py::_PROFILE_DDL_TEMPLATE` — cria as tabelas de perfil
     (`chunks_qwen37`, `chunks_bgem3`) sob demanda.

Bug real (S69): as duas divergiram — o template tinha `meta`, o init.sql não. Como
as migrações são MANUAIS (não rodam no boot), um volume novo criava `chunks` sem
`meta` e o copy-forward/upsert quebravam. Este teste trava a recorrência: qualquer
coluna a mais/menos de um lado FALHA aqui, antes de virar bug de bootstrap.

Não toca DB nem rede: lê os DOIS arquivos como texto e compara o conjunto de colunas.
"""

from __future__ import annotations

import re
from pathlib import Path

from ingest import store

_ROOT = Path(__file__).resolve().parents[2]
_INIT_SQL = _ROOT / "rag-db" / "init.sql"

# colunas de uma tabela (linha "    nome  tipo ...") dentro de um CREATE TABLE ...
_COL_RE = re.compile(r"^\s+([a-z_][a-z0-9_]*)\s+(?:uuid|text|char|halfvec|bigint|timestamptz|jsonb|tsvector|int|boolean)\b")


def _columns_from_create(block: str) -> set[str]:
    """Extrai os nomes de coluna de um bloco CREATE TABLE (ignora CONSTRAINT)."""
    cols: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith(("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK")):
            continue
        m = _COL_RE.match(line)
        if m:
            cols.add(m.group(1))
    return cols


def _init_sql_chunks_columns() -> set[str]:
    """Colunas de `CREATE TABLE ... chunks (...)` no init.sql (não as de perfil)."""
    sql = _INIT_SQL.read_text(encoding="utf-8")
    # primeiro CREATE TABLE IF NOT EXISTS chunks ( seguido de "("
    m = re.search(r"CREATE TABLE IF NOT EXISTS\s+chunks\s*\((.*?)\n\);",
                  sql, re.DOTALL)
    assert m, "não achei o CREATE TABLE chunks no init.sql"
    return _columns_from_create(m.group(1))


def _template_columns() -> set[str]:
    """Colunas do template de perfil (substitui {t} por um nome dummy)."""
    block = store._PROFILE_DDL_TEMPLATE.format(t="chunks_probe", dim=1024)
    # recorta só o CREATE TABLE (até o primeiro ");")
    m = re.search(r"CREATE TABLE IF NOT EXISTS\s+chunks_probe\s*\((.*?)\n\);",
                  block, re.DOTALL)
    assert m, "não achei o CREATE TABLE no template"
    return _columns_from_create(m.group(1))


def test_init_sql_e_template_tem_as_mesmas_colunas():
    """S69: `chunks` (init.sql) e as tabelas de perfil (template) DEVEM ter as
    mesmas colunas — senão o volume novo (init.sql) e o runtime (template) divergem."""
    init_cols = _init_sql_chunks_columns()
    tpl_cols = _template_columns()
    assert init_cols == tpl_cols, (
        f"drift de schema! só no init.sql: {init_cols - tpl_cols}; "
        f"só no template: {tpl_cols - init_cols}"
    )


def test_meta_presente_nos_dois():
    """Regressão direta do bug S69: `meta` (migração 002) tem de estar nos DOIS."""
    assert "meta" in _init_sql_chunks_columns()
    assert "meta" in _template_columns()
