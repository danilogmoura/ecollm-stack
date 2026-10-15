"""S90/B2 — testes do script de rotação de log (rag-db/rotate_log.sh).

O script é puro (bash + coreutils): trunca um arquivo quando passa do limite,
mantendo as últimas KEEP linhas. Exercitado via subprocess com arquivos temporários.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "rag-db" / "rotate_log.sh"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(_SCRIPT), *args],
                          capture_output=True, text=True)


def test_rotaciona_acima_do_limite(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("".join(f"linha {i}\n" for i in range(1200)))
    rc = _run(str(log), "1000", "500")
    assert rc.returncode == 0
    lines = log.read_text().splitlines()
    assert len(lines) == 500
    assert lines[-1] == "linha 1199"  # mantém as ÚLTIMAS linhas


def test_nao_rotaciona_abaixo_do_limite(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("".join(f"linha {i}\n" for i in range(100)))
    _run(str(log), "1000", "500")
    assert len(log.read_text().splitlines()) == 100  # intacto


def test_arquivo_ausente_nao_falha(tmp_path):
    rc = _run(str(tmp_path / "nao-existe.log"), "1000", "500")
    assert rc.returncode == 0


def test_sem_argumento_nao_falha():
    rc = _run()
    assert rc.returncode == 0


def test_limite_exato_nao_rotaciona(tmp_path):
    # exatamente LIMIT linhas → não rotaciona (só ACIMA do limite).
    log = tmp_path / "x.log"
    log.write_text("".join(f"l{i}\n" for i in range(1000)))
    _run(str(log), "1000", "500")
    assert len(log.read_text().splitlines()) == 1000
