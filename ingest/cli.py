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

from . import embed, ingest as ingest_mod, search
from .search import Hit


# Modelo de geracao do --ask: o plano (§3 FASE 3) pede o agente RAPIDO com
# thinking OFF. `qwen3.8-flash-fast` responde em ~2s; `rag-chat` faz fallback
# p/ ollama local quando o roteador Gemini da 503 (~10s), estourando a meta.
ASK_MODEL_DEFAULT = "qwen3.8-flash-fast"
TIMEOUT_S = 60
# limiar conservador: score RRF maximo ~ 1/(k+1)+1/(k+1) ~ 0.033 (k=60). Abaixo
# disto nenhum chunk apareceu em NENHUM dos dois rankings relevantes -> "NAO SEI".
MIN_SCORE = 0.005


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

def cmd_rag(args) -> int:
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
        path_prefix=args.path, final_k=args.k,
    )
    print(format_hits(hits, show_content=0 if args.no_snippet else 280))
    if not args.ask:
        return 0
    if not hits or hits[0].score < MIN_SCORE:
        print("\nNÃO SEI (nada relevante no índice).")
        return 0
    answer = ask_llm(args.query, build_context(hits))
    print("\n" + answer)
    return 0


def cmd_sync(args) -> int:
    try:
        report = ingest_mod.run_ingest(args.repo, dry_run=args.dry_run,
                                       verbose=not args.quiet,
                                       skip_gitleaks=args.skip_gitleaks)
    except SystemExit as exc:
        print(f"[abort] codigo {exc.code}", file=sys.stderr)
        return int(exc.code or 0)
    if not args.dry_run:
        print(report.summary())
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
    p_search.add_argument("--ask", action="store_true", help="gera resposta com citação")
    p_search.add_argument("--no-snippet", action="store_true")
    p_search.set_defaults(func=cmd_rag)

    p_sync = sub.add_parser("sync", help="ingest (FASE 2)")
    p_sync.add_argument("--repo", default=".")
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--quiet", action="store_true")
    p_sync.add_argument("--skip-gitleaks", action="store_true",
                        help="pule o gate de segredos se o binário estiver ausente "
                             "(fail-closed por default; NÃO cobre segredos achados)")
    p_sync.set_defaults(func=cmd_sync)
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # conveniência: `rag "pergunta"` == `rag search "pergunta"`; `rag-sync` idem
    if argv and argv[0] not in ("search", "sync", "-h", "--help"):
        argv.insert(0, "search")
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
