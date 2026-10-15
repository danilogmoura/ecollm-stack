"""S94 — testes do entrypoint do Ollama (ollama/entrypoint.sh).

O script sobe `ollama serve`, espera a porta 11434 responder e faz `ollama pull`
dos modelos (chat fallback + bge-m3). Aqui exercitamos a LÓGICA com stubs de
`ollama` e um `/dev/tcp` simulado — sem subir o Ollama real nem baixar modelos.

Nota: o script usa `while !</dev/tcp/localhost/11434` (bash nativo). Testamos que
ele faz o pull dos DOIS modelos esperados e mantém o container vivo (`wait $pid`).
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "ollama" / "entrypoint.sh"


def _make_stub(dirpath: Path, name: str, body: str) -> None:
    p = dirpath / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Monta um script com /bin/ollama e /dev/tcp stubados. Retorna (script, bin, log)."""
    # O script chama /bin/ollama (caminho absoluto) → criamos um /bin fake via
    # reescrita do caminho no script copiado.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "ollama-calls.log"
    _make_stub(bin_dir, "ollama", f'echo "$@" >> "{log}"\nexit 0')

    # Copia o script trocando /bin/ollama e /dev/tcp por versões testáveis.
    src = _SCRIPT.read_text()
    src = src.replace("/bin/ollama", str(bin_dir / "ollama"))
    # Substitui o loop de /dev/tcp por um no-op (a porta não existe no teste).
    src = src.replace("while !</dev/tcp/localhost/11434; do\n    sleep 2\ndone",
                      "true  # /dev/tcp stubado")
    script = tmp_path / "entrypoint.sh"
    script.write_text(src)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, bin_dir, log


def _run(script: Path, bin_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    # timeout: o script termina em `wait $pid` (serve stubado sai logo).
    return subprocess.run(["bash", str(script)], capture_output=True, text=True,
                          env=env, timeout=30)


def test_entrypoint_faz_pull_dos_modelos(tmp_path):
    script, bin_dir, log = _setup(tmp_path)
    r = _run(script, bin_dir)
    assert r.returncode == 0
    calls = log.read_text()
    assert "pull qwen3:4b-instruct-2507-q4_K_M" in calls
    assert "pull bge-m3" in calls


def test_entrypoint_sobe_serve(tmp_path):
    script, bin_dir, log = _setup(tmp_path)
    _run(script, bin_dir)
    assert "serve" in log.read_text()


def test_entrypoint_mensagem_de_inicio(tmp_path):
    script, bin_dir, _ = _setup(tmp_path)
    r = _run(script, bin_dir)
    assert "Ollama started successfully" in r.stdout
    assert "Initialization complete" in r.stdout


def test_entrypoint_sem_warmup(tmp_path):
    # Decisão 2026-09-25: NÃO faz warmup (não pina VRAM no boot).
    src = _SCRIPT.read_text()
    assert "NO WARMUP by design" in src
