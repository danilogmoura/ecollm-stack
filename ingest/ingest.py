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
# Estado de sync (S14 / T-OPS-2 — staleness do índice sinalizada)
# ---------------------------------------------------------------------------

def _git_state(repo_root: Path) -> tuple[str | None, bool]:
    """(HEAD sha, working_tree_dirty). HEAD=None se nao for repo git.

    dirty = ha mudanca em ARQUIVO VERSIONADO (staged/unstaged/untracked versionado).
    Arquivos ignorados (.env, .venv) NAO contam — o corpus e `git ls-files`, entao
    o que nao esta versionado nunca entra no indice e nao deve marcar stale.
    """
    try:
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() or None
    except subprocess.CalledProcessError:
        head = None
    try:
        # -u=no: nao listar untracked (são irrelevantes p/ o corpus versionado);
        # comparamos apenas tracked modifications contra HEAD.
        porcelain = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, check=True,
        ).stdout
        dirty = bool(porcelain.strip())
    except subprocess.CalledProcessError:
        dirty = False
    return head, dirty


def is_index_stale(conn, repo: str, repo_root: str | Path) -> tuple[bool, str]:
    """Compara estado atual do git vs último sync registrado (tabela rag_sync_state).

    Retorna (stale, motivo_legivel). Nunca levanta — falha vira aviso conservador
    ('nao sabemos', stale=True) para NUNCA dar falsa garantia de frescor. Se nao
    houver registro de sync (indice legado pré-S14), tratamos como desconhecido.
    """
    repo_root = Path(repo_root).resolve()
    if conn is None:
        return True, "sem conexao com o indice — impossivel confirmar frescor"
    try:
        row = conn.execute(
            "SELECT head_sha, dirty FROM rag_sync_state WHERE repo = %s",
            (repo,),
        ).fetchone()
    except Exception as exc:  # tabela ausente (schema pré-S14) etc.
        return True, f"estado de sync indisponivel ({exc.__class__.__name__})"
    if row is None:
        return True, ("nenhum registro de sync encontrado — rode 'rag-sync' para "
                      "registrar o HEAD e habilitar o aviso de desatualizacao")
    synced_head, synced_dirty = row[0], row[1]
    head, dirty = _git_state(repo_root)
    if head is None:
        return True, "diretorio nao e um repo git — impossivel comparar com o sync"
    if head != synced_head:
        return True, (f"HEAD mudou desde o ultimo sync "
                      f"(sync={synced_head[:8]} atual={head[:8]})")
    if dirty and not synced_dirty:
        return True, "ha mudancas nao commitadas em arquivos versionados desde o sync"
    return False, f"indice sincronizado com HEAD {head[:8]}"


# ---------------------------------------------------------------------------
# Gate gitleaks (§1, nota §5)
# ---------------------------------------------------------------------------

def _stage_corpus(repo_root: Path, entries: list[loader.FileEntry], dest: Path) -> None:
    for e in entries:
        src = repo_root / e.path
        dst = dest / e.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def gitleaks_gate(repo_root: Path, entries: list[loader.FileEntry],
                  *, skip: bool = False) -> tuple[bool, str]:
    """Roda gitleaks no corpus versionado. Retorna (ok, mensagem).

    ok=False => abortar ingest. O gate é FAIL-CLOSED (S13/T-ENV-6): se o
    binário não estiver disponível, ABORTA — nunca embedamos um corpus sem
    varredura de segredos por comodidade de ambiente. A única saída é a
    decisão EXPLÍCITA do operador via ``skip=True`` (flag ``--skip-gitleaks``)
    ou env ``RAG_SKIP_GITLEAKS=1``, que rebaixa o ausentismo a AVISO. Achados
    reais de segredo abortam SEMPRE, mesmo com skip pedido (skip só cobre o
    binário faltando, não segredos encontrados). Superficie escaneada =
    exatamente o que seria embedado (só `git ls-files`).
    """
    gitleaks = shutil.which("gitleaks") or os.path.expanduser("~/.local/bin/gitleaks")
    if not os.path.isfile(gitleaks) and not shutil.which("gitleaks"):
        if skip:
            return True, ("gitleaks ausente — gate PULADO por decisão explícita "
                          "(--skip-gitleaks / RAG_SKIP_GITLEAKS=1). AVISO: corpus "
                          "embedado SEM varredura de segredos.")
        return False, ("gitleaks AUSENTE e gate é fail-closed (S13) — abortando "
                       "ingest. Instale o binário (ex.: ~/.local/bin/gitleaks) ou, "
                       "assumindo o risco, rode com --skip-gitleaks / "
                       "RAG_SKIP_GITLEAKS=1.")
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

# ---------------------------------------------------------------------------
# S29 · helpers do sync blue-green (extraídos p/ teste unitário, padrão R5)
# ---------------------------------------------------------------------------

def _acquire_sync_lock(conn, repo: str) -> None:
    """Lock advisory por repo: impede dois writers montarem gerações concorrentes.

    Leitores NÃO bloqueiam (lock só entre writers). Liberação no finally; lock de
    sessão morre junto com a conexão de qualquer forma (R3).
    """
    conn.execute("SELECT pg_advisory_lock(hashtext(%s))", ("rag_sync:" + repo,))


def _release_sync_lock(conn, repo: str) -> None:
    try:
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("rag_sync:" + repo,))
    except Exception:  # noqa: BLE001 — conexão pode já estar morta; lock de sessão morre sozinho
        pass


def _embed_and_upsert_file(conn, repo: str, plan: PlanFile, gen: int,
                           cfg: dict, report: store.SyncReport) -> None:
    """Embeda e sobe os chunks de UM arquivo na geração `gen`, em transação própria.

    COMMIT por arquivo = átomo de retomada (§3.3): se um 429 estourar aqui, os
    arquivos anteriores já commitados persistem e a próxima execução retoma deste.
    """
    pairs = [(c.content, c.kind) for c in plan.chunks]
    vectors = embed.embed_documents(pairs, cfg=cfg) if pairs else []
    rows = store.build_rows(repo, plan.entry.blob_sha, plan.chunks, vectors, gen=gen)
    ins, unch = store.upsert_rows(conn, rows)
    conn.commit()  # transação deste arquivo — commit() explícito (não `with conn:`,
    #                que FECHARIA a conexão em psycopg3 e quebraria o próximo arquivo).
    report.inserted += ins
    report.unchanged += unch


def _parity_ok(conn, repo: str, published_gen: int, new_gen: int,
               unchanged_paths: list[str]) -> bool:
    """R2: toda path unchanged presente na publicada deve existir na nova ANTES do flip.

    Se o copy-forward deixou um arquivo inalterado de fora, abortamos o flip —
    senão ele sumiria do índice ao publicar. Compara por PATH (um arquivo pode ter
    nº de chunks diferente só se seu conteúdo mudou, o que o tiraria de unchanged).
    """
    if not unchanged_paths:
        return True
    missing = conn.execute(
        "SELECT DISTINCT path FROM chunks WHERE repo = %s AND gen = %s "
        "AND path = ANY(%s) AND path NOT IN ("
        "  SELECT path FROM chunks WHERE repo = %s AND gen = %s)",
        (repo, published_gen, unchanged_paths, repo, new_gen),
    ).fetchall()
    return not missing


def run_ingest(repo_root: str | Path, *, dry_run: bool = False,
               db_url: str | None = None, cfg: dict | None = None,
               verbose: bool = True, skip_gitleaks: bool | None = None) -> store.SyncReport:
    """Sync incremental RETOMÁVEL com publicação atômica (S29 / T-OPS-7).

    Blue-green por geração (SPEC-S29 §3): monta gen=published_gen+1 copiando os
    arquivos inalterados (copy-forward, 0 cota) e embedando new/changed em
    transação POR ARQUIVO (retomável); publica com um único UPDATE (flip) e faz GC
    da geração anterior. Leitores veem sempre published_gen → nunca uma geração
    parcial. Um 429 no meio PRESERVA o progresso (diferente do rollback total antigo).
    """
    repo_root = Path(repo_root).resolve()
    repo = repo_name(repo_root)
    cfg = cfg or embed.config_from_env()
    # S13: permissão de pular o gate vem da flag OU do env (fail-closed por default).
    if skip_gitleaks is None:
        skip_gitleaks = os.environ.get("RAG_SKIP_GITLEAKS", "").strip().lower() in ("1", "true", "yes")

    # 1) gate de segredos SEMPRE antes de qualquer saida de texto do host
    entries_all = loader.load_corpus(repo_root)
    ok, gate_msg = gitleaks_gate(repo_root, entries_all, skip=skip_gitleaks)
    if verbose:
        print(f"[gate] {gate_msg}")
    if not ok:
        raise SystemExit(2)

    # 2) estado atual do DB p/ sync incremental
    conn = None if dry_run else store.connect(db_url)
    try:
        # I6: dry-run lê a geração publicada real (conexão read-only não é aberta
        # aqui — existing abaixo usa gen=None legado p/ o plano, suficiente p/ mostrar
        # o que MUDARIA; o caminho escrito usa published_gen correto).
        existing = store.existing_file_hashes(conn, repo) if conn else {}
        plans = plan_sync(repo_root, existing)

        to_embed = [p for p in plans if p.action in ("new", "changed")]
        unchanged_plans = [p for p in plans if p.action == "unchanged"]
        live_paths = [p.entry.path for p in plans]
        stored_paths = set(existing.keys())
        removed = sorted(stored_paths - set(live_paths))

        report = store.SyncReport(repo=repo, files_seen=len(plans))
        report.changed_files = [p.entry.path for p in plans if p.action == "changed"]
        report.removed_files = removed

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
        _acquire_sync_lock(conn, repo)
        try:
            published_gen, new_gen = store.next_generation(conn, repo)
            store.begin_generation(conn, repo, new_gen)
            conn.commit()

            # 3) copy-forward: arquivos inalterados da publicada → nova (0 cota).
            #    Paths removidas NÃO entram aqui nem no embed → somem da geração nova.
            unchanged_paths = [p.entry.path for p in unchanged_plans]
            store.copy_forward_unchanged(conn, repo, published_gen, new_gen, unchanged_paths)
            conn.commit()

            # 4) embeda new/changed POR ARQUIVO (transação própria = retomável).
            for p in to_embed:
                if store.file_in_generation(conn, repo, new_gen, p.entry.path,
                                            p.entry.blob_sha):
                    # resume: este arquivo já foi commitado nesta geração → pula.
                    report.unchanged += len(p.chunks)
                    continue
                _embed_and_upsert_file(conn, repo, p, new_gen, cfg, report)

            # contagem de unchanged dos arquivos inalterados (relatório fiel).
            report.unchanged += sum(len(p.chunks) for p in unchanged_plans)

            # 5) paridade ANTES do flip (R2): nenhum unchanged pode ter ficado de fora.
            if not _parity_ok(conn, repo, published_gen, new_gen, unchanged_paths):
                raise SystemExit(
                    "[abort] paridade unchanged falhou antes do flip — geração nova "
                    "incompleta; publicação cancelada (índice publicado intacto)."
                )

            # 6) FLIP atômico + registro de frescor (I5: head_sha gravado NO flip).
            #    commit() explícito — NÃO usar `with conn:` (em psycopg3 o bloco
            #    FECHA a conexão ao sair, matando GC/count/finally abaixo).
            head_sha, dirty = _git_state(repo_root)
            store.publish_generation(conn, repo, new_gen)
            store.record_sync_state(conn, repo, head_sha, dirty)
            conn.commit()

            # 7) GC da geração anterior, em transação separada, APÓS o flip (R4).
            report.deleted = store.gc_old_generations(conn, repo, new_gen)
            conn.commit()

            report.chunks_total = store.count_chunks(conn, repo, gen=new_gen)
            return report
        finally:
            # Libera o ponteiro em andamento se abortamos no meio (crash/429): a
            # próxima execução recomeça esta geração do zero (copy-forward idempotente).
            try:
                store.set_in_progress_gen(conn, repo, None)
                conn.commit()
            except Exception:  # noqa: BLE001
                pass
            _release_sync_lock(conn, repo)
    finally:
        if conn is not None:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rag-ingest", description="FASE 2: ingest RAG")
    ap.add_argument("--repo", default=".", help="repo root a indexar (default: cwd)")
    ap.add_argument("--dry-run", action="store_true", help="nao embeda nem escreve no DB")
    ap.add_argument("--skip-gitleaks", action="store_true",
                    help="pule o gate por binário ausente (assumindo o risco; segredo achado aborta sempre)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = run_ingest(args.repo, dry_run=args.dry_run, verbose=not args.quiet,
                            skip_gitleaks=args.skip_gitleaks)
    except SystemExit as exc:  # gate abortou
        print(f"[abort] codigo {exc.code}", file=sys.stderr)
        return int(exc.code or 0)
    if not args.dry_run:
        print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
