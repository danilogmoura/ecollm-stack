"""S94 — testes do harness de bootstrap (rag-db/test_bootstrap.sh).

O harness sobe um Postgres efêmero (docker real) — não rodamos isso aqui. Mas as
PRÉ-CHECAGENS (lógica pura) são testáveis com stubs: init.sql/verify_schema.py
ausentes → exit 2; docker ausente → exit 2. Também validamos que o script define
`trap cleanup EXIT` (garante remoção do container mesmo em falha).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "rag-db" / "test_bootstrap.sh"
_BASH = shutil.which("bash") or "/bin/bash"


def _make_stub(dirpath: Path, name: str, body: str) -> None:
    p = dirpath / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _setup(tmp_path: Path, *, with_init: bool = True, with_verify: bool = True,
           with_docker: bool = True) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "rag-db").mkdir(parents=True)
    script = repo / "rag-db" / "test_bootstrap.sh"
    script.write_text(_SCRIPT.read_text())
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    if with_init:
        (repo / "rag-db" / "init.sql").write_text("-- init\n")
    if with_verify:
        (repo / "rag-db" / "verify_schema.py").write_text("# verify\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if with_docker:
        _make_stub(bin_dir, "docker", "exit 0")
    # python3 stub: o script checa `command -v python3` se PY não for executável.
    _make_stub(bin_dir, "python3", "exit 0")
    return repo, bin_dir


def _coreutils_only_path(tmp_path: Path) -> str:
    """PATH com os coreutils necessários (dirname, seq, grep, ...) MAS sem docker.

    Cria um diretório com symlinks p/ os binários usados pelo script, exceto
    docker — assim `command -v docker` falha sem quebrar o resto.
    """
    d = tmp_path / "coreutils"
    d.mkdir(exist_ok=True)
    for tool in ("dirname", "basename", "seq", "grep", "sleep", "tr", "awk",
                 "cat", "tail", "head", "wc", "mv", "rm", "date", "command"):
        src = shutil.which(tool)
        if src:
            (d / tool).symlink_to(src)
    return str(d)


def _run(repo: Path, bin_dir: Path, *, minimal_path: bool = False,
         tmp_path: Path | None = None) -> subprocess.CompletedProcess:
    # minimal_path: PATH com coreutils mas SEM docker p/ testar a ausência dele.
    if minimal_path and tmp_path is not None:
        path = f"{bin_dir}:{_coreutils_only_path(tmp_path)}"
    else:
        path = f"{bin_dir}:{os.environ['PATH']}"
    env = {**os.environ, "PATH": path}
    return subprocess.run([_BASH, str(repo / "rag-db" / "test_bootstrap.sh")],
                          capture_output=True, text=True, env=env, cwd=str(repo))


def test_init_sql_ausente_exit_2(tmp_path):
    repo, bin_dir = _setup(tmp_path, with_init=False)
    r = _run(repo, bin_dir)
    assert r.returncode == 2
    assert "init.sql não encontrado" in r.stderr


def test_verify_ausente_exit_2(tmp_path):
    repo, bin_dir = _setup(tmp_path, with_verify=False)
    r = _run(repo, bin_dir)
    assert r.returncode == 2
    assert "verify_schema.py não encontrado" in r.stderr


def test_docker_ausente_exit_2(tmp_path):
    repo, bin_dir = _setup(tmp_path, with_docker=False)
    r = _run(repo, bin_dir, minimal_path=True, tmp_path=tmp_path)
    assert r.returncode == 2
    assert "docker não encontrado" in r.stderr


def test_script_tem_trap_cleanup():
    # Garante que o container é removido mesmo em falha/interrupção.
    src = _SCRIPT.read_text()
    assert "trap cleanup EXIT" in src
    assert "docker rm -f" in src
