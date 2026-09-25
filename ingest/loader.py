"""Loader da FASE 1 — corpus via git, com filtros e hash de conteudo.

Regras travadas no plano (.planning/PLANO-RAG.md §1):
  - Corpus = `git ls-files` (so o que esta versionado; .env etc. ja ficam fora
    por .gitignore — a primeira linha de defesa contra segredo embedado).
  - Extensoes aceitas: py, js/ts/tsx, go, sh/bash, md, yaml/yml, toml, json.
  - Binarios detectados por NUL byte nos primeiros 8 KiB (nao por extensao).
  - file_hash = git blob sha (mesmo calculo do `git hash-object`): muda so
    quando o conteudo muda -> base do sync incremental da FASE 2.
  - Arquivos acima de MAX_BYTES sao pulados com aviso (candidatos a lockfile
    gerado: package-lock.json tem extensao .json mas nao e corpus humano).

Sem dependencia de framework: stdlib + subprocess git.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

# extensao -> kind (a mesma taxonomia da tabela chunks)
EXT_KIND: dict[str, str] = {
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".tsx": "code",
    ".go": "code",
    ".sh": "code",
    ".bash": "code",
    ".md": "doc",
    ".markdown": "doc",
    ".yaml": "config",
    ".yml": "config",
    ".toml": "config",
    ".json": "config",
}

# nomes de arquivo sem extensao (ou ambigua) que queremos indexar
NAME_KIND: dict[str, str] = {
    "dockerfile": "code",
    "makefile": "code",
    "readme": "doc",
}

# lockfiles/gerados conhecidos — nunca entram no corpus
EXCLUDE_NAMES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "cargo.lock",
    "composer.lock",
    "requirements.txt",  # lista de deps, nao conhecimento
}

# diretorios excluidos por prefixo de caminho
EXCLUDE_DIR_PARTS: set[str] = {"vendor", "node_modules", ".venv", "dist", "build"}

MAX_BYTES = 512 * 1024  # 512 KiB por arquivo


@dataclass(frozen=True)
class FileEntry:
    path: str          # relativo ao repo root, sempre com "/"
    kind: str          # code | doc | config
    lang: str | None   # python|javascript|typescript|go|bash|markdown|yaml|toml|json
    blob_sha: str      # git blob sha (40 hex)
    size: int          # bytes no disco


_LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".go": "go", ".sh": "bash", ".bash": "bash", ".md": "markdown",
    ".markdown": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".json": "json",
}


def _classify(relpath: str) -> tuple[str, str | None] | None:
    """Retorna (kind, lang) ou None se o arquivo nao entra no corpus."""
    p = Path(relpath)
    name = p.name.lower()
    if name in EXCLUDE_NAMES:
        return None
    if any(part in EXCLUDE_DIR_PARTS for part in p.parts[:-1]):
        return None
    ext = p.suffix.lower()
    if ext in EXT_KIND:
        return EXT_KIND[ext], _LANG_BY_EXT.get(ext)
    if not ext and name in NAME_KIND:
        return NAME_KIND[name], None
    return None


def _looks_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:8192]


def _git_blob_sha(repo_root: Path, relpath: str) -> str:
    """git hash-object <path> — identico ao sha interno do blob no objeto git."""
    out = subprocess.run(
        ["git", "-C", str(repo_root), "hash-object", "--", relpath],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def load_corpus(repo_root: str | Path) -> list[FileEntry]:
    """Varre o repo versionado e devolve os arquivos que serao chunked.

    Ordenacao deterministica (git ls-files ja vem em ordem lexica de path);
    duas execucoes no mesmo commit produzem listas identicas (teste de
    idempotencia da FASE 1).
    """
    repo_root = Path(repo_root).resolve()
    res = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True, check=True,
    )
    entries: list[FileEntry] = []
    for raw in res.stdout.split(b"\0"):
        if not raw:
            continue
        relpath = raw.decode("utf-8", "surrogateescape")
        cls = _classify(relpath)
        if cls is None:
            continue
        f = repo_root / relpath
        if not f.is_file():  # symlink quebrado, submodule sujo...
            continue
        size = f.stat().st_size
        if size > MAX_BYTES:
            print(f"[loader] SKIP grande demais ({size} B): {relpath}")
            continue
        head = f.open("rb").read(8193)
        if _looks_binary(head):
            print(f"[loader] SKIP binario (NUL byte): {relpath}")
            continue
        kind, lang = cls
        entries.append(FileEntry(
            path=relpath, kind=kind, lang=lang,
            blob_sha=_git_blob_sha(repo_root, relpath), size=size,
        ))
    return entries


def read_file(repo_root: str | Path, entry: FileEntry) -> str:
    """Le o conteudo como texto (utf-8 com substituicao defensiva)."""
    return (Path(repo_root).resolve() / entry.path).read_text(
        encoding="utf-8", errors="replace"
    )


def content_sha256(text: str) -> str:
    """sha256 do texto PURO do chunk/arquivo — usado em content_hash.

    IMPORTANTE (plano §2): o hash e do conteudo SEM task-prefix, assim mudar
    a string de task na hora do embed nao invalida o indice inteiro.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
