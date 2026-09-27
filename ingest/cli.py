"""CLI da FASE 3 — `rag` (busca/ask) e `rag-sync` (ingest).

Comandos (plano §3 FASE 3):
  rag "pergunta"            -> busca hibrida, imprime top-k chunks com fonte+score
  rag --ask "pergunta"      -> busca + gera resposta via ASK_MODEL_DEFAULT
                               (qwen3.8-flash-fast) citando [n]; se nada
                               relevante no indice, responde "NAO SEI".
  rag-sync [--repo PATH]    -> roda o ingest (FASE 2); --dry-run repassa.

`rag` usa o repo do cwd por default (mesmo identificador `repo` gravado pelo
ingest = nome do diretorio). Config de conexao/env vem do .env do repo root.
Sem framework: argparse + requests p/ o chat (o embed/search ja estao prontos).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

from . import embed, ingest as ingest_mod, profiles, search
from .search import Hit


# Modelo de geracao do --ask: o plano (§3 FASE 3) pede o agente RAPIDO com
# thinking OFF. `qwen3.8-flash-fast` responde em ~2s; `rag-chat` faz fallback
# p/ ollama local quando o roteador Gemini da 503 (~10s), estourando a meta.
ASK_MODEL_DEFAULT = "qwen3.8-flash-fast"
TIMEOUT_S = 60
# S21 · limiar de relevancia p/ o "NAO SEI". O antigo MIN_SCORE=0,005 media o score
# RRF do top-1, mas esse score e POSICIONAL e sempre sai 0,0164 (rank1+rank1 =>
# 1/61+1/61) — uma zona morta que so disparava quando a lista ficava VAZIA, nunca
# separando "relevante" de "fora-do-assunto". Passamos a medir a DISTANCIA coseno bruta
# do vizinho denso mais proximo (search.MAX_TOP1_DIST), calibrada no corpus atual.
# S32 (I6): o gate agora e POR PERFIL. MIN_SCORE mantido como alias do perfil default
# (`gemini`) p/ compat com testes antigos; o CLI usa search.PERFIL_GATE (resolve o
# perfil ativo em runtime) ao chamar a busca, entao trocar RAG_PROFILE troca o gate.
MIN_SCORE = search.MAX_TOP1_DIST


def _chat_cfg() -> dict:
    embed.load_dotenv()
    return {
        "base_url": os.environ.get("LITELLM_BASE_URL", embed.DEFAULT_BASE_URL).rstrip("/"),
        "api_key": os.environ.get("LITELLM_MASTER_KEY", ""),
        "model": os.environ.get("RAG_CHAT_MODEL", ASK_MODEL_DEFAULT),
    }


# ---------------------------------------------------------------------------
# saida humana
# ---------------------------------------------------------------------------

def format_hits(hits: list[Hit], *, show_content: int = 280) -> str:
    if not hits:
        return "(nenhum resultado)"
    lines = []
    for i, h in enumerate(hits, 1):
        vr = "-" if h.vec_rank is None else str(h.vec_rank)
        lr = "-" if h.lex_rank is None else str(h.lex_rank)
        snippet = h.content.strip().replace("\n", " ")
        if show_content and len(snippet) > show_content:
            snippet = snippet[:show_content] + "…"
        head = f"[{i}] {h.source()}  score={h.score:.4f} (vec#{vr} lex#{lr})"
        lines.append(head if not show_content else f"{head}\n    {snippet}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# rag --ask: montagem de contexto deterministica + geracao com citação
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Você é um assistente que responde APENAS com base nos trechos de código, "
    "config e documentação fornecidos abaixo, numerados como [1], [2], ... "
    "Cite sempre a fonte entre colchetes ao usar um trecho. Se os trechos não "
    "contiverem informação suficiente para responder, diga exatamente "
    "'NÃO SEI' e nada mais. Não invente."
)


def build_context(hits: list[Hit]) -> str:
    # ordem já determinística (search._sort_final). Nada de timestamp/random aqui
    # para preservar estabilidade de prefixo (plano 4b-5).
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] FONTE: {h.source()}\n{h.content.strip()}")
    return "\n\n---\n\n".join(blocks)


def ask_llm(question: str, context: str, cfg: dict | None = None) -> str:
    cfg = cfg or _chat_cfg()
    url = f"{cfg['base_url']}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    user = f"CONTEXTO:\n{context}\n\nPERGUNTA: {question}"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# comandos
# ---------------------------------------------------------------------------

def _set_profile_env(args) -> None:
    """S32 (I6): se --profile foi dado, fixa RAG_PROFILE p/ este processo.

    Assim embed/search/recall resolvem o perfil via registry sem editar .env.
    Validamos cedo (fail-fast) — um slug invalido deve abortar antes de qualquer
    chamada de rede/DB. Sem --profile, o ambiente decide (RAG_PROFILE > publicado).
    """
    slug = getattr(args, "profile", None)
    if slug:
        profiles.validate_slug(slug)  # R1: recusa antes de usar
        profiles.resolve(slug)        # levanta se desconhecido no registry
        os.environ["RAG_PROFILE"] = slug


def cmd_rag(args) -> int:
    _set_profile_env(args)
    repo_root = Path(args.repo).resolve()
    repo = ingest_mod.repo_name(repo_root)
    # S14: avisa ANTES do resultado se o indice pode estar desatualizado.
    warn = search.staleness_warning(repo_root, repo)
    if warn:
        print(warn, file=sys.stderr)
    qvec = None
    if args.ask:
        # embeda a query uma vez; reusa p/ busca (evita dupla chamada ao proxy)
        prefixed = embed.apply_prefix(args.query, "query")
        qvec = embed.embed_texts([prefixed], cfg=embed.config_from_env())[0]
    hits = search.search(
        args.query, repo=repo, qvec=qvec, kind=args.kind,
        path_prefix=args.path, final_k=args.k, max_top1_dist=search.PERFIL_GATE,
    )
    print(format_hits(hits, show_content=0 if args.no_snippet else 280))
    if not args.ask:
        return 0
    # S21: com o gate por distancia ativo na busca, uma saida vazia ja significa
    # "nada relevante" (vizinho denso mais proximo alem de MAX_TOP1_DIST). Mantem o
    # fallback por seguranca caso hits venha de um caminho sem distancia.
    if not hits:
        print("\nNÃO SEI (nada relevante no índice).")
        return 0
    answer = ask_llm(args.query, build_context(hits))
    print("\n" + answer)
    return 0


def cmd_sync(args) -> int:
    _set_profile_env(args)
    try:
        report = ingest_mod.run_ingest(args.repo, dry_run=args.dry_run,
                                       verbose=not args.quiet,
                                       skip_gitleaks=args.skip_gitleaks,
                                       profile=getattr(args, "profile", None))
    except SystemExit as exc:
        print(f"[abort] codigo {exc.code}", file=sys.stderr)
        return int(exc.code or 0)
    if not args.dry_run:
        print(report.summary())
    return 0


# ---------------------------------------------------------------------------
# S32-b (I6): `rag profile {list,use,switch,status}` — gestão do espaço vetorial.
# O flip de perfil é um ato EXPLÍCITO de publicação (invariante 7): nunca há
# fallback automático. `use` é FAIL-CLOSED (R6): recusa publicar um perfil cujo
# índice não existe, está vazio, ou cujo HEAD diverge do repo atual.
# ---------------------------------------------------------------------------

def _profile_status_rows(conn, repo: str) -> list[dict]:
    """Por perfil do registry: tabela existe? tem chunks publicados? head_sha/dirty."""
    out = []
    for slug in sorted(profiles.PROFILES):
        prof = profiles.PROFILES[slug]
        row = {"slug": slug, "table": prof.table, "dim": prof.dim,
              "model": prof.model, "exists": False, "chunks": 0,
              "published_gen": None, "head_sha": None, "dirty": None}
        try:
            exists = conn.execute(
                "SELECT to_regclass(%s) IS NOT NULL", (prof.table,)).fetchone()[0]
        except Exception:  # noqa: BLE001
            exists = False
        row["exists"] = bool(exists)
        if exists:
            try:
                row["chunks"] = store_count(conn, repo, prof)
            except Exception:  # noqa: BLE001
                row["chunks"] = 0
        st = conn.execute(
            "SELECT published_gen, head_sha, dirty FROM rag_sync_state "
            "WHERE repo = %s AND profile = %s", (repo, slug)).fetchone()
        if st:
            row["published_gen"], row["head_sha"], row["dirty"] = st[0], st[1], st[2]
        out.append(row)
    return out


def store_count(conn, repo: str, prof) -> int:
    """Chunks na geração publicada deste perfil (0 se sem estado)."""
    gen_row = conn.execute(
        "SELECT published_gen FROM rag_sync_state WHERE repo = %s AND profile = %s",
        (repo, prof.slug)).fetchone()
    gen = gen_row[0] if gen_row else 0
    return conn.execute(
        f"SELECT count(*) FROM {prof.table} WHERE repo = %s AND gen = %s",
        (repo, gen)).fetchone()[0]


def cmd_profile(args) -> int:
    from . import store  # local — só os comandos de perfil precisam do DB
    action = args.action
    repo_root = Path(args.repo).resolve()
    repo = ingest_mod.repo_name(repo_root)

    if action == "list":
        cur = profiles.active_profile().slug
        for slug in sorted(profiles.PROFILES):
            p = profiles.PROFILES[slug]
            mark = "*" if slug == cur else " "
            print(f"{mark} {slug:10} table={p.table:14} dim={p.dim:<5} "
                  f"gate={p.gate} model={p.model}")
        return 0

    # demais ações exigem conexão com o índice
    conn = store.connect()
    try:
        if action == "status":
            pub = store.get_published_profile(conn, repo)
            print(f"repo={repo} publicado={pub} ativo={profiles.active_profile(repo, conn).slug}")
            for r in _profile_status_rows(conn, repo):
                flag = "PUB" if r["slug"] == pub else ("   " if r["exists"] else "  ")
                print(f"  [{flag}] {r['slug']:10} existe={r['exists']!s:5} "
                      f"chunks={r['chunks']:<6} gen={r['published_gen']} "
                      f"head={(r['head_sha'] or '-')[:8]} dirty={r['dirty']}")
            return 0

        if action in ("use", "switch"):
            return _cmd_profile_set(conn, args, repo, repo_root, action)

        print(f"ação desconhecida: {action}", file=sys.stderr)
        return 2
    finally:
        conn.close()


def _cmd_profile_set(conn, args, repo: str, repo_root, action: str) -> int:
    """`use` (flip puro, fail-closed) e `switch` (sync se preciso + flip)."""
    from . import store
    slug = args.slug
    profiles.validate_slug(slug)          # R1
    prof = profiles.resolve(slug)         # levanta se fora do registry
    head, dirty = ingest_mod._git_state(repo_root)

    if action == "switch":
        # garante índice no alvo antes de publicar (re-embed automático se faltar).
        rc = cmd_sync(argparse.Namespace(repo=str(repo_root), dry_run=False,
                                         quiet=args.quiet, skip_gitleaks=args.skip_gitleaks,
                                         profile=slug))
        if rc != 0:
            print(f"[switch] sync do perfil '{slug}' falhou (código {rc}) — "
                  "nada publicado.", file=sys.stderr)
            return rc

    # --- checks fail-closed (R6) ---
    exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL",
                          (prof.table,)).fetchone()[0]
    if not exists:
        print(f"[use] perfil '{slug}' não tem índice (tabela {prof.table} ausente). "
              f"Rode: rag sync --profile {slug}  (ou: rag profile switch {slug})",
              file=sys.stderr)
        return 3
    n = store_count(conn, repo, prof)
    if n == 0:
        print(f"[use] índice de '{slug}' está vazio (0 chunks publicados). "
              f"Rode: rag sync --profile {slug}", file=sys.stderr)
        return 3
    st = conn.execute(
        "SELECT head_sha FROM rag_sync_state WHERE repo = %s AND profile = %s",
        (repo, slug)).fetchone()
    synced_head = st[0] if st else None
    if head is not None and synced_head is not None and synced_head != head:
        print(f"[use] índice de '{slug}' está DESATUALIZADO (sync={synced_head[:8]} "
              f"atual={head[:8]}). Recusei publicar por segurança (R6). "
              f"Rode: rag sync --profile {slug}", file=sys.stderr)
        return 3

    store.set_published_profile(conn, repo, slug)
    conn.commit()
    print(f"[ok] perfil publicado: {slug} (tabela {prof.table}, {n} chunks).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rag", description="RAG ecollm-stack (FASE 3)")
    sub = ap.add_subparsers(dest="cmd")

    p_search = sub.add_parser("search", help="busca híbrida por pergunta")
    p_search.add_argument("query")
    p_search.add_argument("--repo", default=".")
    p_search.add_argument("-k", type=int, default=search.DEFAULT_FINAL_K)
    p_search.add_argument("--kind", choices=["code", "doc", "config"])
    p_search.add_argument("--path", help="prefixo de caminho p/ filtrar")
    p_search.add_argument("--profile", choices=sorted(profiles.PROFILES),
                          help="perfil de embedding a usar (default: RAG_PROFILE > "
                               "publicado > gemini). Troca gate/prefixo/dim sem editar .env.")
    p_search.add_argument("--ask", action="store_true", help="gera resposta com citação")
    p_search.add_argument("--no-snippet", action="store_true")
    p_search.set_defaults(func=cmd_rag)

    p_sync = sub.add_parser("sync", help="ingest (FASE 2)")
    p_sync.add_argument("--repo", default=".")
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--quiet", action="store_true")
    p_sync.add_argument("--profile", choices=sorted(profiles.PROFILES),
                        help="espaço vetorial a sincronizar (default: RAG_PROFILE > "
                             "publicado > gemini). Cria a tabela do perfil se faltar.")
    p_sync.add_argument("--skip-gitleaks", action="store_true",
                        help="pule o gate de segredos se o binário estiver ausente "
                             "(fail-closed por default; NÃO cobre segredos achados)")
    p_sync.set_defaults(func=cmd_sync)

    # S32-b (I6): rag profile {list,use,switch,status}
    p_prof = sub.add_parser("profile", help="gerência dos perfis de embedding (S32)")
    p_prof.add_argument("--repo", default=".")
    p_prof.add_argument("--quiet", action="store_true")
    p_prof.add_argument("--skip-gitleaks", action="store_true",
                        help="repassado ao sync interno de 'switch'")
    prof_sub = p_prof.add_subparsers(dest="action", required=True)
    prof_sub.add_parser("list", help="lista os perfis do registry")
    p_status = prof_sub.add_parser("status", help="estado por perfil (tabela/chunks/HEAD)")
    p_status.add_argument("slug", nargs="?", default=None)
    p_use = prof_sub.add_parser("use", help="publica um perfil (fail-closed, R6)")
    p_use.add_argument("slug")
    p_switch = prof_sub.add_parser("switch", help="sync do alvo se preciso + publica")
    p_switch.add_argument("slug")
    p_prof.set_defaults(func=cmd_profile)
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # conveniência: `rag "pergunta"` == `rag search "pergunta"`; `rag-sync` idem
    if argv and argv[0] not in ("search", "sync", "profile", "-h", "--help"):
        argv.insert(0, "search")
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
