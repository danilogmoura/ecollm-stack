"""Orquestrador da FASE 2 — loader -> chunker -> embed -> store.

Fluxo (plano §3 FASE 2):
  1. Gate gitleaks no CORPUS versionado (nunca embedar segredo). Usa
     `gitleaks dir` sobre uma area de staging com SO os arquivos do
     `git ls-files` — NAO `gitleaks detect` (varre historico e daria falso
     positivo pos-rotacao; ver nota do gate em PLANO-RAG.md §5).
  2. loader.load_corpus -> FileEntry[] (com git blob sha por arquivo).
  3. Sync incremental SIMPLES por blob_sha (decisao §4b-3, sem Merkle tree):
       - arquivo novo           -> embeda todos os chunks
       - blob_sha mudou         -> apaga chunks antigos daquele path, re-embeda
       - blob_sha igual         -> pula (0 embeddings; cache Redis ainda protege)
       - path sumiu do corpus   -> delete_stale/delete_removed remove os huérfãos
  4. embed.embed_documents (batch 32, retry/backoff, task-prefix doc/query).
  5. store.upsert_rows + delete_* dentro de UMA transacao; commit no fim.

--dry-run: roda loader+chunker+gate e imprime o plano (o que seria embedado),
sem tocar LiteLLM nem o DB. exit code != 0 em falha parcial/aborto.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import embed, loader, store
from .chunker import Chunk, chunk_file


@dataclass
class PlanFile:
    entry: loader.FileEntry
    action: str            # "new" | "changed" | "unchanged"
    chunks: list[Chunk]


def repo_name(repo_root: Path) -> str:
    """Identificador estavel do repo na coluna `repo`: nome do diretorio."""
    return repo_root.resolve().name


# ---------------------------------------------------------------------------
# Gate gitleaks (§1, nota §5)
# ---------------------------------------------------------------------------

def _stage_corpus(repo_root: Path, entries: list[loader.FileEntry], dest: Path) -> None:
    for e in entries:
        src = repo_root / e.path
        dst = dest / e.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def gitleaks_gate(repo_root: Path, entries: list[loader.FileEntry]) -> tuple[bool, str]:
    """Roda gitleaks no corpus versionado. Retorna (ok, mensagem).

    ok=False => abortar ingest. Se o binario nao estiver disponivel, o gate e
    um AVISO (nao bloqueia) — ambiente sem sudo pode nao ter gitleaks; o
    registro disso fica no relatorio. Superficie escaneada = exatamente o que
    seria embedado (so `git ls-files`).
    """
    gitleaks = shutil.which("gitleaks") or os.path.expanduser("~/.local/bin/gitleaks")
    if not os.path.isfile(gitleaks) and not shutil.which("gitleaks"):
        return True, "gitleaks ausente — gate pulado (AVISO)"
    tmp = Path(tempfile.mkdtemp(prefix="rag-gate-"))
    try:
        _stage_corpus(repo_root, entries, tmp)
        res = subprocess.run(
            [gitleaks, "dir", str(tmp), "--exit-code", "1", "--no-banner", "--redact"],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            return True, "gitleaks: 0 achados no corpus"
        out = (res.stdout + res.stderr)[-2000:]
        return False, "gitleaks ACHOU segredo(s) no corpus — abortando ingest:\n" + out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# planejamento do sync
# ---------------------------------------------------------------------------

def plan_sync(repo_root: Path, existing: dict[str, str]) -> list[PlanFile]:
    """Classifica cada arquivo do corpus como new/changed/unchanged + seus chunks."""
    entries = loader.load_corpus(repo_root)
    plans: list[PlanFile] = []
    for e in entries:
        prev_hash = existing.get(e.path)
        if prev_hash == e.blob_sha:
            action = "unchanged"
        elif prev_hash is None:
            action = "new"
        else:
            action = "changed"
        chunks: list[Chunk] = []
        if action in ("new", "changed"):
            source = loader.read_file(repo_root, e)
            chunks = chunk_file(e.path, e.kind, e.lang, source)
        else:
            # unchanged: nao embedamos nem gravamos, mas contamos os chunks que
            # ja estao no indice (para o relatorio unchanged sair correto).
            source = loader.read_file(repo_root, e)
            chunks = chunk_file(e.path, e.kind, e.lang, source)
        plans.append(PlanFile(entry=e, action=action, chunks=chunks))
    return plans


# ---------------------------------------------------------------------------
# execucao
# ---------------------------------------------------------------------------

def run_ingest(repo_root: str | Path, *, dry_run: bool = False,
               db_url: str | None = None, cfg: dict | None = None,
               verbose: bool = True) -> store.SyncReport:
    repo_root = Path(repo_root).resolve()
    repo = repo_name(repo_root)
    cfg = cfg or embed.config_from_env()

    # 1) gate de segredos SEMPRE antes de qualquer saida de texto do host
    entries_all = loader.load_corpus(repo_root)
    ok, gate_msg = gitleaks_gate(repo_root, entries_all)
    if verbose:
        print(f"[gate] {gate_msg}")
    if not ok:
        raise SystemExit(2)

    # 2) estado atual do DB p/ sync incremental
    conn = None if dry_run else store.connect(db_url)
    try:
        existing = store.existing_file_hashes(conn, repo) if conn else {}
        plans = plan_sync(repo_root, existing)

        to_embed = [p for p in plans if p.action in ("new", "changed")]
        live_paths = [p.entry.path for p in plans]
        stored_paths = set(existing.keys())
        removed = sorted(stored_paths - set(live_paths))

        report = store.SyncReport(repo=repo, files_seen=len(plans))

        if dry_run:
            n_chunks = sum(len(p.chunks) for p in to_embed)
            print("[dry-run] plano de ingest:")
            for p in plans:
                if p.action != "unchanged":
                    print(f"  {p.action:9} {p.entry.path} ({len(p.chunks)} chunks)")
            for rp in removed:
                print(f"  removed   {rp}")
            print(f"[dry-run] embedariam {n_chunks} chunks de {len(to_embed)} arquivos; "
                  f"{sum(1 for p in plans if p.action=='unchanged')} inalterados; "
                  f"{len(removed)} arquivos removidos.")
            return report

        assert conn is not None
        with conn:  # transacao unica: tudo ou nada
            # 3a) apaga chunks de arquivos alterados (blob mudou) ANTES de reinserir
            changed_paths = [p.entry.path for p in to_embed if p.action == "changed"]
            report.deleted += store.delete_stale(conn, repo, changed_paths)
            # 3b) apaga huérfãos (paths que sumiram do corpus)
            report.deleted += store.delete_removed(conn, repo, live_paths)

            # 4) embeda em lote unico (aproveita batch/cache do proxy)
            pairs: list[tuple[str, str]] = []
            owner: list[tuple[str, str]] = []  # (path, file_hash) alinhado a pairs
            for p in to_embed:
                for c in p.chunks:
                    pairs.append((c.content, c.kind))
                    owner.append((p.entry.path, p.entry.blob_sha))
            vectors = embed.embed_documents(pairs, cfg=cfg) if pairs else []

            # 5) monta linhas por arquivo e faz upsert
            rows: list[store.Row] = []
            idx = 0
            for p in to_embed:
                nv = len(p.chunks)
                sub_vecs = vectors[idx:idx + nv]
                idx += nv
                rows.extend(store.build_rows(repo, p.entry.blob_sha, p.chunks, sub_vecs))
            ins, unch = store.upsert_rows(conn, rows)
            report.inserted = ins
            report.unchanged = unch + sum(len(p.chunks) for p in plans if p.action == "unchanged")
            report.chunks_total = store.count_chunks(conn, repo)
            report.changed_files = changed_paths
            report.removed_files = removed
        return report
    finally:
        if conn is not None:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rag-ingest", description="FASE 2: ingest RAG")
    ap.add_argument("--repo", default=".", help="repo root a indexar (default: cwd)")
    ap.add_argument("--dry-run", action="store_true", help="nao embeda nem escreve no DB")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = run_ingest(args.repo, dry_run=args.dry_run, verbose=not args.quiet)
    except SystemExit as exc:  # gate abortou
        print(f"[abort] codigo {exc.code}", file=sys.stderr)
        return int(exc.code or 0)
    if not args.dry_run:
        print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
