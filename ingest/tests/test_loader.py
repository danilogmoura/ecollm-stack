"""Testes do loader da FASE 1.

Cobrem as invariantes travadas no plano (.planning/PLANO-RAG.md §3):
  - classificacao por extensao/nome + exclusao de lockfiles e dirs gerados;
  - binario detectado por NUL byte (nao por extensao);
  - idempotencia: duas execucoes no mesmo commit -> MESMA lista (path, blob_sha).
Usamos um repositorio git temporario para nao depender do estado do workspace.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ingest import loader


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")
    return r


def _commit_files(repo: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")


# ---------------------------------------------------------------------------
# _classify — taxonomia sem tocar no disco
# ---------------------------------------------------------------------------

def test_classify_por_extensao():
    assert loader._classify("a/b.py") == ("code", "python")
    assert loader._classify("README.md") == ("doc", "markdown")
    assert loader._classify("conf/app.yaml") == ("config", "yaml")
    assert loader._classify("i18n/e.json") == ("config", "json")


def test_classify_por_nome_sem_extensao():
    assert loader._classify("Dockerfile") == ("code", None)
    assert loader._classify("docs/readme") == ("doc", None)


def test_classify_exclui_lockfiles_e_dirs():
    assert loader._classify("package-lock.json") is None
    assert loader._classify("requirements.txt") is None
    assert loader._classify("node_modules/x/index.js") is None
    assert loader._classify(".venv/lib/y.py") is None
    # extensao desconhecida fora das listas -> de fora
    assert loader._classify("data/blob.bin") is None


# ---------------------------------------------------------------------------
# load_corpus — integracao com git real em repo temporario
# ---------------------------------------------------------------------------

def test_load_corpus_filtra_e_classifica(repo: Path):
    _commit_files(repo, {
        "src/app.py": b"print('oi')\n",
        "docs/guide.md": b"# Guia\n\ntexto.\n",
        "config.yml": b"key: value\n",
        "package-lock.json": b"{}\n",          # lockfile -> fora
        "vendor/dep.go": b"package x\n",        # dir excluido -> fora
        "img.png": b"\x00\x01\x02binary",      # binario -> fora
    })
    entries = loader.load_corpus(repo)
    paths = {e.path for e in entries}
    assert paths == {"src/app.py", "docs/guide.md", "config.yml"}
    kinds = {e.path: e.kind for e in entries}
    assert kinds["src/app.py"] == "code"
    assert kinds["docs/guide.md"] == "doc"
    assert kinds["config.yml"] == "config"


def test_binario_detectado_por_nul(repo: Path):
    _commit_files(repo, {"fake.py": b"x\x00y\x00z"})
    assert loader.load_corpus(repo) == []


def test_idempotencia_mesma_lista_no_mesmo_commit(repo: Path):
    _commit_files(repo, {
        "a.py": b"a = 1\n",
        "b.md": b"# B\n",
        "c.json": b'{"k": 1}\n',
    })
    first = loader.load_corpus(repo)
    second = loader.load_corpus(repo)
    assert [(e.path, e.blob_sha) for e in first] == \
           [(e.path, e.blob_sha) for e in second]


def test_blob_sha_muda_so_com_conteudo(repo: Path):
    _commit_files(repo, {"a.py": b"a = 1\n"})
    before = {e.path: e.blob_sha for e in loader.load_corpus(repo)}
    # reordena/toca mtime de outro arquivo, sem mudar conteudo versionado
    (repo / "a.py").touch()
    after = {e.path: e.blob_sha for e in loader.load_corpus(repo)}
    assert before == after
    # agora muda o conteudo de verdade
    _commit_files(repo, {"a.py": b"a = 2\n"})
    changed = {e.path: e.blob_sha for e in loader.load_corpus(repo)}
    assert changed["a.py"] != before["a.py"]


# ---------------------------------------------------------------------------
# content_sha256 — hash do texto PURO (sem task-prefix)
# ---------------------------------------------------------------------------

def test_content_sha_estavel_e_sensivel():
    assert loader.content_sha256("ola mundo") == loader.content_sha256("ola mundo")
    assert loader.content_sha256("a") != loader.content_sha256("b")
