"""S94 — testes do script de sync inteligente (rag-db/sync_if_stale.sh).

O script decide se roda `rag sync` comparando o HEAD do git com o `head_sha`
publicado (via `docker compose exec ... psql`). Aqui exercitamos a LÓGICA de
decisão com stubs de `git`, `docker` e `python` no PATH — sem tocar Postgres,
docker real nem gastar cota de embedding.

Cenários:
  - índice FRESCO (HEAD == publicado) → sai 0 sem sincronizar;
  - índice DEFASADO (HEAD != publicado) → sincroniza;
  - --force → sincroniza mesmo fresco;
  - não é repo git → sai 0;
  - snapshot de custo: atualizado quando o python "funciona", ignorado quando falha.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "rag-db" / "sync_if_stale.sh"


def _make_stub(dirpath: Path, name: str, body: str) -> None:
    """Cria um executável stub no diretório (usado via PATH)."""
    p = dirpath / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _setup(tmp_path: Path, *, head: str, published: str, py_ok: bool = True,
           is_git: bool = True) -> tuple[Path, Path]:
    """Monta um repo fake + stubs. Retorna (repo_root, bin_dir)."""
    repo = tmp_path / "repo"
    (repo / "rag-db").mkdir(parents=True)
    # S101: o snapshot de custo agora mora em `reports/logs/` (era `.planning/`).
    (repo / "reports" / "logs").mkdir(parents=True)
    # O script resolve REPO_ROOT a partir da própria localização → copiamos o script.
    script = repo / "rag-db" / "sync_if_stale.sh"
    script.write_text(_SCRIPT.read_text())
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    # git stub: rev-parse HEAD → head (ou vazio se não-repo).
    if is_git:
        _make_stub(bin_dir, "git", f'echo "{head}"')
    else:
        _make_stub(bin_dir, "git", "exit 1")

    # docker stub: `docker compose exec -T rag-db psql ...` → imprime published.
    _make_stub(bin_dir, "docker", f'echo "{published}"')

    # python stub: registra a invocação; sucesso/falha conforme py_ok.
    log = tmp_path / "py-calls.log"
    if py_ok:
        _make_stub(bin_dir, "python3",
                   f'echo "$@" >> "{log}"\nexit 0')
    else:
        _make_stub(bin_dir, "python3",
                   f'echo "$@" >> "{log}"\nexit 1')
    return repo, bin_dir


def _run(repo: Path, bin_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "PYTHON": str(bin_dir / "python3")}
    return subprocess.run(["bash", str(repo / "rag-db" / "sync_if_stale.sh"), *args],
                          capture_output=True, text=True, env=env, cwd=str(repo))


def test_fresco_nao_sincroniza(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="abc123", published="abc123")
    r = _run(repo, bin_dir)
    assert r.returncode == 0
    assert "FRESCO" in r.stdout
    # python NÃO foi chamado (nada a sincronizar).
    assert not (tmp_path / "py-calls.log").exists()


def test_defasado_sincroniza(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="newsha", published="oldsha")
    r = _run(repo, bin_dir)
    assert r.returncode == 0
    assert "defasado" in r.stdout
    calls = (tmp_path / "py-calls.log").read_text()
    assert "ingest.cli sync" in calls


def test_force_sincroniza_mesmo_fresco(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="abc123", published="abc123")
    r = _run(repo, bin_dir, "--force")
    assert r.returncode == 0
    assert "defasado" in r.stdout
    assert (tmp_path / "py-calls.log").exists()


def test_nao_repo_git_sai_zero(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="", published="", is_git=False)
    r = _run(repo, bin_dir)
    assert r.returncode == 0
    # a mensagem vai para stderr (o script usa `>&2`).
    assert "não é um repo git" in r.stderr


def test_snapshot_atualizado_quando_python_ok(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="newsha", published="oldsha", py_ok=True)
    r = _run(repo, bin_dir)
    assert "snapshot de custo atualizado" in r.stdout


def test_snapshot_ignorado_quando_python_falha(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="newsha", published="oldsha", py_ok=False)
    r = _run(repo, bin_dir)
    # O sync falha (python exit 1) → set -e aborta ANTES do snapshot.
    assert r.returncode != 0


def test_timestamp_no_log(tmp_path):
    repo, bin_dir = _setup(tmp_path, head="abc123", published="abc123")
    r = _run(repo, bin_dir)
    # S88: toda linha tem prefixo [YYYY-MM-DDTHH:MM:SSZ].
    assert "[20" in r.stdout and "Z]" in r.stdout
