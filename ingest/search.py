"""Busca hibrida da FASE 3 — vetorial (HNSW cosine) + lexica (tsvector) -> RRF.

Regras travadas no plano (.planning/PLANO-RAG.md §3 FASE 3, §4b-5):
  - Dois caminhos independentes, cada um top-N (default 50):
      * denso : ORDER BY embedding <=> (:qvec)::halfvec LIMIT N   (usa o HNSW;
                operador <=> exige halfvec_cosine_ops — BUG-002)
      * lexico: tsv @@ websearch_to_tsquery('simple', :q) com ts_rank LIMIT N
                (cobre simbolos/identificadores exatos que o vetorial pode perder)
  - Fusao por Reciprocal Rank Fusion: score = sum 1/(k + rank), k=60 (padrao do
    plano). RRF nao usa as escalas cruas (cosine ~[0,2] vs ts_rank ~[0,1]), so a
    ORDEM de cada lista — robusto e sem tuning.
  - Ordenacao FINAL deterministica: score desc, desempate por (path, symbol,
    content_hash). Motivo (plano 4b-5): estabilidade de prefixo p/ prompt cache
    do agente — mesma query => mesma ordem, sem timestamp/random no topo.
  - Filtro opcional por kind e/ou prefixo de path (WHERE antes do top-N).

A query embedada usa o prefixo ASSIMETRICO "query:" (embed.apply_prefix), nunca
"doc:" — e o lado query da busca par doc/query validada no demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import psycopg

from .chunker import Chunk
from .embed import apply_prefix, config_from_env, embed_texts
from .store import db_url_from_env

VECTOR_TOPK = 50         # candidatos do caminho denso
LEXICAL_TOPK = 50        # candidatos do caminho lexico
RRF_K = 60               # constante de suavizacao do RRF (plano)
DEFAULT_FINAL_K = 8


@dataclass(frozen=True)
class Hit:
    id: str
    repo: str
    path: str
    lang: str | None
    kind: str
    symbol: str | None
    content: str
    score: float          # score RRF combinado
    vec_rank: int | None  # posicao na lista densa (None = so lexico)
    lex_rank: int | None  # posicao na lista lexica

    def source(self) -> str:
        loc = self.path if not self.symbol else f"{self.path}::{self.symbol}"
        return f"{loc} [{self.kind}]"


# ---------------------------------------------------------------------------
# SQL dos dois caminhos
# ---------------------------------------------------------------------------

_COLS = "id, repo, path, lang, kind, symbol, content, content_hash"

_VECTOR_SQL = f"""
SELECT {_COLS}, (embedding <=> %(qvec)s::halfvec) AS dist
FROM chunks
WHERE repo = %(repo)s
  AND (%(kind)s::text IS NULL OR kind = %(kind)s::text)
  AND (%(path_like)s::text IS NULL OR path LIKE %(path_like)s::text)
ORDER BY embedding <=> %(qvec)s::halfvec
LIMIT %(n)s
"""

_LEXICAL_SQL = f"""
SELECT {_COLS}, ts_rank(tsv, websearch_to_tsquery('simple', %(q)s)) AS r
FROM chunks
WHERE repo = %(repo)s
  AND tsv @@ websearch_to_tsquery('simple', %(q)s)
  AND (%(kind)s::text IS NULL OR kind = %(kind)s::text)
  AND (%(path_like)s::text IS NULL OR path LIKE %(path_like)s::text)
ORDER BY r DESC, id
LIMIT %(n)s
"""


def _row_to_hit(row, score, vec_rank=None, lex_rank=None) -> Hit:
    return Hit(
        id=str(row[0]), repo=row[1], path=row[2], lang=row[3], kind=row[4],
        symbol=row[5], content=row[6], score=score,
        vec_rank=vec_rank, lex_rank=lex_rank,
    )


def reciprocal_rank_fusion(
    lists: Sequence[Sequence[tuple]], weights: Sequence[float] | None = None,
    k: int = RRF_K,
) -> dict[str, tuple]:
    """Combina listas ordenadas de (row, ...) via RRF. Retorna {id: (row, score, vr, lr)}.

    Cada lista e um ranking (posicao 1 = melhor). score(id) += w/(k+rank).
    `weights` permite dar mais peso a um caminho (default 1.0 cada).
    Preserva a PRIMEIRA linha vista por id (todas apontam pro mesmo chunk).
    """
    if weights is None:
        weights = [1.0] * len(lists)
    acc: dict[str, list] = {}  # id -> [row, score, vec_rank, lex_rank]
    for idx, ranked in enumerate(lists):
        for rank, row in enumerate(ranked, start=1):
            cid = str(row[0])
            entry = acc.setdefault(cid, [row, 0.0, None, None])
            entry[1] += weights[idx] / (k + rank)
            if idx == 0:
                entry[2] = rank
            elif idx == 1:
                entry[3] = rank
    return {cid: (v[0], v[1], v[2], v[3]) for cid, v in acc.items()}


def _sort_final(hits: list[Hit], final_k: int) -> list[Hit]:
    # score desc; desempate deterministico por (path, symbol, id) — plano 4b-5
    return sorted(
        hits,
        key=lambda h: (-h.score, h.path, h.symbol or "", h.id),
    )[:final_k]


def search(
    query: str,
    *,
    repo: str,
    conn: psycopg.Connection | None = None,
    qvec: Sequence[float] | None = None,
    kind: str | None = None,
    path_prefix: str | None = None,
    vector_topk: int = VECTOR_TOPK,
    lexical_topk: int = LEXICAL_TOPK,
    final_k: int = DEFAULT_FINAL_K,
    weights: Sequence[float] | None = None,
    rrf_k: int = RRF_K,
) -> list[Hit]:
    """Busca hibrida para `query`. Ou embeda a query (via LiteLLM) ou recebe qvec pronto.

    `qvec` injetavel p/ testes (sem rede). `conn` reusavel (testes/integra); se
    omitido, abre com RAG_DB_URL e fecha ao terminar.
    """
    own_conn = conn is None
    if own_conn:
        conn = psycopg.connect(db_url_from_env())
    try:
        if qvec is None:
            prefixed = apply_prefix(query, "query")
            qvec = embed_texts([prefixed], cfg=config_from_env())[0]
        qvec_text = "[" + ",".join(f"{float(x):.6g}" for x in qvec) + "]"
        params_common = {
            "repo": repo, "kind": kind,
            "path_like": (path_prefix + "%") if path_prefix else None,
        }
        vec_rows = conn.execute(
            _VECTOR_SQL, {**params_common, "qvec": qvec_text, "n": vector_topk}
        ).fetchall()
        lex_rows = conn.execute(
            _LEXICAL_SQL, {**params_common, "q": query, "n": lexical_topk}
        ).fetchall()

        fused = reciprocal_rank_fusion([vec_rows, lex_rows], weights=weights, k=rrf_k)
        hits = [_row_to_hit(row, score, vr, lr)
                for (row, score, vr, lr) in fused.values()]
        return _sort_final(hits, final_k)
    finally:
        if own_conn:
            conn.close()


# ---------------------------------------------------------------------------
# Aviso de desatualizacao (S14 / T-OPS-2)
# ---------------------------------------------------------------------------

def staleness_warning(repo_root: str | Path, repo: str,
                      conn: psycopg.Connection | None = None) -> str | None:
    """Retorna uma mensagem de aviso se o indice pode estar desatualizado, senao None.

    Compara o git atual (HEAD/arvore) contra o ultimo sync registrado em
    rag_sync_state. Usado pelo CLI (`rag`) e pelo servidor MCP (`rag_search`) para
    NUNCA apresentar resultado como fresco quando o codigo mudou desde o ingest.
    Import de ingest feito aqui (lazy) para evitar ciclo no topo do modulo.
    Nunca levanta: qualquer falha vira aviso conservador (nao dar falsa garantia).
    """
    from . import ingest as _ingest  # lazy — evita ciclo de import no topo

    own = conn is None
    try:
        if own:
            conn = psycopg.connect(db_url_from_env())
        stale, reason = _ingest.is_index_stale(conn, repo, repo_root)
    except Exception as exc:  # DB fora, etc. — melhor avisar do que silenciar
        return f"[aviso] nao foi possivel verificar frescor do indice ({exc.__class__.__name__})"
    finally:
        if own and conn is not None:
            conn.close()
    return f"[aviso] indice pode estar desatualizado — {reason}" if stale else None
