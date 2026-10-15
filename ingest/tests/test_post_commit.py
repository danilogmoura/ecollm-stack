"""S94 — testes do hook pós-commit (rag-db/post-commit.sample).

O hook: (1) resolve o repo root; (2) rotaciona o rag-sync.log e o mcp-stderr.log;
(3) dispara o sync_if_stale.sh em BACKGROUND (nunca trava o commit). Exercitado
com stubs de `git` e `bash` no PATH — sem tocar o repo real nem gastar cota.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "rag-db" / "post-commit.sample"


def _make_stub(dirpath: Path, name: str, body: str) -> None:
    p = dirpath / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "rag-db").mkdir(parents=True)
    (repo / ".planning").mkdir()
    hook = repo / "rag-db" / "post-commit.sample"
    hook.write_text(_SCRIPT.read_text())
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    # O hook chama rotate_log.sh e sync_if_stale.sh → copiamos os reais.
    ragdb = _SCRIPT.parent
    for dep in ("rotate_log.sh", "sync_if_stale.sh"):
        (repo / "rag-db" / dep).write_text((ragdb / dep).read_text())

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # git stub: rev-parse --show-toplevel → o repo fake.
    _make_stub(bin_dir, "git", f'echo "{repo}"')
    # stubs p/ o sync em background não tocar docker/python reais.
    _make_stub(bin_dir, "docker", "exit 0")
    _make_stub(bin_dir, "python3", "exit 0")
    return repo, bin_dir


def _run(repo: Path, bin_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(repo / "rag-db" / "post-commit.sample")],
                          capture_output=True, text=True, env=env, cwd=str(repo))


def test_hook_sai_zero(tmp_path):
    repo, bin_dir = _setup(tmp_path)
    r = _run(repo, bin_dir)
    assert r.returncode == 0


def test_hook_rotaciona_rag_sync_log(tmp_path):
    repo, bin_dir = _setup(tmp_path)
    log = repo / ".planning" / "rag-sync.log"
    log.write_text("".join(f"l{i}\n" for i in range(1200)))
    _run(repo, bin_dir)
    # rotação: 1200 → 500 linhas.
    assert len(log.read_text().splitlines()) == 500


def test_hook_rotaciona_mcp_log(tmp_path):
    repo, bin_dir = _setup(tmp_path)
    log = repo / ".planning" / "mcp-stderr.log"
    log.write_text("".join(f"l{i}\n" for i in range(1200)))
    _run(repo, bin_dir)
    assert len(log.read_text().splitlines()) == 500


def test_hook_nao_falha_sem_logs(tmp_path):
    # Sem os logs, a rotação é no-op e o hook ainda sai 0.
    repo, bin_dir = _setup(tmp_path)
    r = _run(repo, bin_dir)
    assert r.returncode == 0
