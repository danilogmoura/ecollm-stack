"""S18 — testes de rag-db/run_migrations.py (T-OPS-3).

O runner fala com Postgres real para aplicar; aqui exercitamos apenas a LÓGICA
de descoberta/validação dos arquivos (`discover`), que é pura e não toca DB.
Aplicação de verdade + rollback são cobertas pelo aceite manual do plano
(volume fresco → verify_schema íntegro; migração inválida → exit 1 sem ledger).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parents[2] / "rag-db" / "run_migrations.py"
_spec = importlib.util.spec_from_file_location("run_migrations", _MOD_PATH)
rm = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(rm)


def _write(dirpath: Path, *names: str) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    for n in names:
        (dirpath / n).write_text("-- x\n", encoding="utf-8")


def test_discover_ordena_por_nnn(tmp_path):
    d = tmp_path / "migrations"
    _write(d, "002_b.sql", "001_a.sql", "003_c.sql")
    rm.MIGRATIONS_DIR = d
    versions = [v for v, _ in rm.discover()]
    assert versions == ["001", "002", "003"]


def test_discover_rejeita_nome_fora_do_padrao(tmp_path):
    d = tmp_path / "migrations"
    _write(d, "001_ok.sql", "sem_numero.sql")
    rm.MIGRATIONS_DIR = d
    with pytest.raises(ValueError, match="nome de migração inválido"):
        rm.discover()


def test_discover_detecta_lacuna(tmp_path):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql", "003_c.sql")   # falta 002
    rm.MIGRATIONS_DIR = d
    with pytest.raises(ValueError, match="lacuna"):
        rm.discover()


def test_discover_detecta_duplicata(tmp_path):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql", "001_b.sql")
    rm.MIGRATIONS_DIR = d
    with pytest.raises(ValueError, match="lacuna|duplicata"):
        rm.discover()


def test_migrações_reais_do_repo_sao_validas():
    """Sanidade: os arquivos versionados em rag-db/migrations seguem a convenção."""
    rm.MIGRATIONS_DIR = _MOD_PATH.parent / "migrations"
    found = rm.discover()
    assert [v for v, _ in found] == ["001", "002", "003"]
    # todas terminam em .sql e têm conteúdo não-vazio
    for _, p in found:
        assert p.suffix == ".sql"
        assert p.read_text(encoding="utf-8").strip()
