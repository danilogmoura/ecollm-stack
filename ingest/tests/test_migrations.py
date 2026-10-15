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
    # S32-b: migração 005 (perfis de embedding) entra na sequência lockstep.
    assert [v for v, _ in found] == ["001", "002", "003", "004", "005"]
    # todas terminam em .sql e têm conteúdo não-vazio
    for _, p in found:
        assert p.suffix == ".sql"
        assert p.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# S84 — cobertura de applied_versions / run() / main() (FakeConn, sem DB real)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Conexão fake: registra SQL executado, simula schema_migrations."""

    def __init__(self, applied=(), fail_on=None):
        self.applied = set(applied)
        self.fail_on = fail_on          # substring do SQL que deve falhar
        self.executed: list[str] = []
        self.committed = 0
        self.rolled_back = 0

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("boom")
        if sql.strip().startswith("SELECT version FROM schema_migrations"):
            return _FakeCur([(v,) for v in sorted(self.applied)])
        if sql.strip().startswith("INSERT INTO schema_migrations"):
            self.applied.add(params[0])
        return _FakeCur([])

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeCur:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def _patch_connect(monkeypatch, conn):
    """Faz `import psycopg; psycopg.connect(url)` devolver o FakeConn."""
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda url: conn)


def test_applied_versions_le_o_ledger(monkeypatch):
    conn = _FakeConn(applied={"001", "002"})
    assert rm.applied_versions(conn) == {"001", "002"}
    # garante que a tabela de controle é criada antes de ler
    assert any("CREATE TABLE IF NOT EXISTS schema_migrations" in s for s in conn.executed)


def test_run_dry_run_nao_aplica(monkeypatch, tmp_path):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql", "002_b.sql")
    rm.MIGRATIONS_DIR = d
    conn = _FakeConn()
    _patch_connect(monkeypatch, conn)
    rc = rm.run("postgresql://x", dry_run=True)
    assert rc == 0
    assert conn.applied == set()          # nada aplicado
    assert conn.committed == 0


def test_run_status_only_lista(monkeypatch, tmp_path, capsys):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql", "002_b.sql")
    rm.MIGRATIONS_DIR = d
    conn = _FakeConn(applied={"001"})
    _patch_connect(monkeypatch, conn)
    rc = rm.run("postgresql://x", status_only=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 aplicadas" in out and "1 pendentes" in out
    assert "[x] 001" in out and "[ ] 002" in out


def test_run_aplica_pendentes_e_registra(monkeypatch, tmp_path):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql", "002_b.sql")
    rm.MIGRATIONS_DIR = d
    conn = _FakeConn(applied={"001"})     # 001 já aplicada
    _patch_connect(monkeypatch, conn)
    rc = rm.run("postgresql://x")
    assert rc == 0
    assert conn.applied == {"001", "002"}  # 002 aplicada + registrada
    assert conn.committed == 1             # só a pendente


def test_run_nada_pendente_retorna_zero(monkeypatch, tmp_path, capsys):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql")
    rm.MIGRATIONS_DIR = d
    conn = _FakeConn(applied={"001"})
    _patch_connect(monkeypatch, conn)
    rc = rm.run("postgresql://x")
    assert rc == 0
    assert "nada a aplicar" in capsys.readouterr().out


def test_run_falha_faz_rollback_e_para(monkeypatch, tmp_path, capsys):
    d = tmp_path / "migrations"
    (d).mkdir(parents=True, exist_ok=True)
    (d / "001_a.sql").write_text("SELECT boom;\n", encoding="utf-8")
    (d / "002_b.sql").write_text("-- ok\n", encoding="utf-8")
    rm.MIGRATIONS_DIR = d
    conn = _FakeConn(fail_on="SELECT boom")
    _patch_connect(monkeypatch, conn)
    rc = rm.run("postgresql://x")
    assert rc == 1                          # falhou
    assert conn.rolled_back == 1            # rollback da migração que falhou
    assert "002" not in conn.applied        # NÃO aplicou a seguinte
    assert "FALHOU" in capsys.readouterr().err


def test_main_usa_url_do_arg(monkeypatch, tmp_path):
    d = tmp_path / "migrations"
    _write(d, "001_a.sql")
    rm.MIGRATIONS_DIR = d
    conn = _FakeConn()
    _patch_connect(monkeypatch, conn)
    rc = rm.main(["--url", "postgresql://custom", "--dry-run"])
    assert rc == 0
