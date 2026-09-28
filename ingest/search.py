"""Busca hibrida da FASE 3 — vetorial (HNSW cosine) + lexica (tsvector) -> RRF.

Regras travadas no plano (.planning/PLANO-RAG.md §3 FASE 3, §4b-5):
  - Dois caminhos independentes, cada um top-N (default 50):
      * denso : ORDER BY embedding <=> (:qvec)::halfvec LIMIT N   (usa o HNSW;
                operador <=> exige halfvec_cosine_ops — BUG-002)
      * lexico: tsv @@ websearch_to_tsquery('simple', :q) com ts_rank LIMIT N
                (cobre simbolos/identificadores exatos que o vetorial pode perder)
  - Fusao por Reciprocal Rank Fusion: score = sum 1/(k + rank), k=60 (padrao do
    plano). RRF nao usa as escalas cruas (cosine ~[0,2] vs ts_rank ~[0,1]), so a
    ORDEM de cada lista — robusto e sem tuning.  - S20 (T-RET-2): um TERCEIRO caminho léxico opcional sobre tsv_pt (config
    'portuguese', só kind='doc'), fundido com peso LEXICAL_PT_WEIGHT. Reforca
    recall de prosa pt-BR que o 'simple' (sem stemming) perde. `lexical_pt_weight
    =0` desliga (botão de A/B).  - Ordenacao FINAL deterministica: score desc, desempate por (path, symbol,
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
from . import profiles as _profiles
from .embed import apply_prefix, config_for_profile, config_from_env, embed_texts
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
    score: float          # score RRF combinado (posicional — nao discrimina relevancia)
    vec_rank: int | None  # posicao na lista densa (None = so lexico)
    lex_rank: int | None  # posicao na lista lexica
    dist: float | None = None  # S21: distancia coseno bruta ao chunk denso (None = so lexico)

    def source(self) -> str:
        loc = self.path if not self.symbol else f"{self.path}::{self.symbol}"
        return f"{loc} [{self.kind}]"


# ---------------------------------------------------------------------------
# SQL dos dois caminhos
# ---------------------------------------------------------------------------

_COLS = "id, repo, path, lang, kind, symbol, content, content_hash"

# S32-b (I4): {t} é o nome da tabela do perfil ativo (resolvido via registry em
# search()). Nomes vêm SEMPRE do registry + slug validado (R1), nunca de input cru.
_VECTOR_SQL = f"""
SELECT {_COLS}, (embedding <=> %(qvec)s::halfvec) AS dist
FROM {{t}}
WHERE repo = %(repo)s
  AND gen = %(gen)s
  AND (%(kind)s::text IS NULL OR kind = %(kind)s::text)
  AND (%(path_like)s::text IS NULL OR path LIKE %(path_like)s::text)
ORDER BY embedding <=> %(qvec)s::halfvec
LIMIT %(n)s
"""

_LEXICAL_SQL = f"""
SELECT {_COLS}, ts_rank(tsv, websearch_to_tsquery('simple', %(q)s)) AS r
FROM {{t}}
WHERE repo = %(repo)s
  AND gen = %(gen)s
  AND tsv @@ websearch_to_tsquery('simple', %(q)s)
  AND (%(kind)s::text IS NULL OR kind = %(kind)s::text)
  AND (%(path_like)s::text IS NULL OR path LIKE %(path_like)s::text)
ORDER BY r DESC, id
LIMIT %(n)s
"""

# S20 (T-RET-2): caminho lexical EM PORTUGUÊS, só p/ prosa (kind='doc'). Usa a
# coluna gerada tsv_pt (stemming Snowball + stopwords pt), que o 'simple' não faz
# — "índice" casa com "indices". O predicado `kind='doc'` é EXPLÍCITO no WHERE
# para casar com o índice GIN parcial (chunks_tsv_pt_gin). Roda sempre: p/ queries
# sem filtro kind ele só retorna docs; p/ kind≠doc retorna vazio (custo ~0).
_LEXICAL_PT_SQL = f"""
SELECT {_COLS}, ts_rank(tsv_pt, websearch_to_tsquery('portuguese', %(q)s)) AS r
FROM {{t}}
WHERE repo = %(repo)s
  AND gen = %(gen)s
  AND kind = 'doc'
  AND tsv_pt @@ websearch_to_tsquery('portuguese', %(q)s)
  AND (%(path_like)s::text IS NULL OR path LIKE %(path_like)s::text)
ORDER BY r DESC, id
LIMIT %(n)s
"""

# Peso do caminho léxico pt na fusão RRF, relativo ao léxico simple (1.0).
# DEFAULT 0.0 = DESLIGADO. Decisão S20 (A/B medido 2026-09-25): ligar o caminho
# pt-BR (peso 0.5) NÃO mudou nenhuma métrica da eval (@1/@3/@5/@8/@10/MRR idênticos,
# zero diferença por pergunta) — os chunks doc já eram recuperados pelo denso +
# simple pós-S19. Critério de aceite = "adotar só se melhorar sem regressão" ⇒ não
# adotamos. O mecanismo fica no código, acionável via lexical_pt_weight>0, p/ re-testar
# quando a base de docs crescer ou em tuning de pesos (S21). Coluna tsv_pt + índice GIN
# parcial permanecem (custo ~0, pré-requisito do botão).
LEXICAL_PT_WEIGHT = 0.0

# S21 · `hnsw.ef_search` padrao do pgvector e 40; ele limita a largura da varredura
# no grafo HNSW ANTES do ORDER BY, entao ef_search < vector_topk faz o top-k pedido
# NUNCA ser alcancado (a busca para cedo). Default = VECTOR_TOPK p/ cobrir todo o k
# solicitado; exposto como parametro p/ a curva ef_search x recall medida em S21.
EF_SEARCH_DEFAULT = VECTOR_TOPK

# S21 · limiar de relevancia por DISTANCIA coseno bruta, medido no corpus atual
# (375 chunks, 30 perguntas). As perguntas in-corpus tem distancia do vizinho denso
# mais proximo entre 0,138 e 0,300 (p90=0,260); queries fora-de-corpus ("bolo de
# cenoura", "correia do fusca") ficam em ~0,37 — gap claro de separacao. 0,34 fica
# acima do pior caso legitimo (0,30) com folga e abaixo da zona de nao-relevancia.
# Substitui o antigo MIN_SCORE=0,005 sobre score RRF, que era uma zona morta: o
# score RRF do top-1 e SEMPRE 0,0164 (rank1+rank1 => 1/61+1/61), posicional, e nao
# discrimina relevancia. Usado pelo CLI 'rag --ask' p/ o gate "NAO SEI".
#
# S32 (I4): a fonte canonica do gate AGORA e o perfil (registry). MAX_TOP1_DIST e
# mantido como ALIAS do gate do perfil default (`gemini`) p/ compat — testes e
# chamadas antigas que leem search.MAX_TOP1_DIST continuam valendo. O gate efetivo
# de cada busca vem de `max_gate_for_profile()` quando max_top1_dist e omitido.
MAX_TOP1_DIST = _profiles.PROFILES["gemini"].gate


# S32 (I4): sentinela para pedir "use o gate do perfil ativo" em vez de um numero
# fixo ou None (desligado). O CLI 'rag --ask' passa isto; assim o gate segue o
# espaco vetorial publicado sem hardcode. Comparacao por identidade/valor da string.
PERFIL_GATE = "profile"


def max_gate_for_profile(profile=None) -> float:
    """Gate de distancia do perfil ativo (ou do `profile` dado: slug ou Profile).

    Aceita slug (str), objeto Profile ou None (= ativo). Resolve via registry; um
    Profile já resolvido evita re-lookup e garante que o gate venha do MESMO espaço
    da tabela buscada (S32-b — gate e tabela são sempre do mesmo perfil).
    """
    if isinstance(profile, _profiles.Profile):
        return profile.gate
    if profile:
        return _profiles.resolve(profile).gate
    return _profiles.active_profile().gate


def _resolve_gate(max_top1_dist: float | str | None, profile=None) -> float | None:
    """Normaliza o argumento do gate: None->off, PERFIL_GATE->gate do perfil, float->fixo.

    `profile` (slug ou Profile) é o perfil já resolvido pela busca — passado para
    que o gate venha exatamente do espaço vetorial consultado (S32-b/I4).
    """
    if max_top1_dist is None:
        return None
    if max_top1_dist == PERFIL_GATE:
        return max_gate_for_profile(profile)
    return float(max_top1_dist)



def _row_to_hit(row, score, vec_rank=None, lex_rank=None, dist=None) -> Hit:
    return Hit(
        id=str(row[0]), repo=row[1], path=row[2], lang=row[3], kind=row[4],
        symbol=row[5], content=row[6], score=score,
        vec_rank=vec_rank, lex_rank=lex_rank, dist=dist,
    )


def reciprocal_rank_fusion(
    lists: Sequence[Sequence[tuple]], weights: Sequence[float] | None = None,
    k: int = RRF_K,
) -> dict[str, tuple]:
    """Combina listas ordenadas de (row, ...) via RRF. Retorna {id: (row, score, vr, lr, dist)}.

    Cada lista e um ranking (posicao 1 = melhor). score(id) += w/(k+rank).
    `weights` permite dar mais peso a um caminho (default 1.0 cada).
    Preserva a PRIMEIRA linha vista por id (todas apontam pro mesmo chunk).
    S21: o `dist` (coluna extra da lista DENSA, idx 0) e capturado p/ o gate de
    relevancia por distancia; caminhos lexicais nao tem distancia (None).
    """
    if weights is None:
        weights = [1.0] * len(lists)
    acc: dict[str, list] = {}  # id -> [row, score, vec_rank, lex_rank, dist]
    for idx, ranked in enumerate(lists):
        for rank, row in enumerate(ranked, start=1):
            cid = str(row[0])
            entry = acc.setdefault(cid, [row, 0.0, None, None, None])
            entry[1] += weights[idx] / (k + rank)
            if idx == 0:
                entry[2] = rank
                entry[4] = float(row[-1])  # densa: ultima coluna = distancia coseno
            elif idx == 1:
                entry[3] = rank
    return {cid: (v[0], v[1], v[2], v[3], v[4]) for cid, v in acc.items()}


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
    lexical_pt_weight: float | None = None,
    ef_search: int | None = None,
    max_top1_dist: float | None = None,
    gen: int | None = None,
    profile=None,
) -> list[Hit]:
    """Busca hibrida para `query`. Ou embeda a query (via LiteLLM) ou recebe qvec pronto.

    `qvec` injetavel p/ testes (sem rede). `conn` reusavel (testes/integra); se
    omitido, abre com RAG_DB_URL e fecha ao terminar.
    `lexical_pt_weight`=None usa o default do módulo (LEXICAL_PT_WEIGHT, hoje 0.0
    = desligado — ver nota S20). Passar >0 liga o caminho léxico pt-BR p/ A/B.
    `ef_search`=None usa EF_SEARCH_DEFAULT; controla a largura da varredura HNSW
    (S21). Valores < vector_topk podem truncar o top-k denso realmente retornado.
    `max_top1_dist`=None desliga o gate de distancia (contrato historico — eval
    recall@k mede ordenacao sem corte); um float filtra toda saida quando o
    candidato denso mais proximo esta alem dele (S21). S32 (I4): passar a string
    "profile" (ou PERFIL_GATE) resolve o gate do PERFIL ATIVO via registry, em vez
    de um numero fixo — e como o CLI 'rag --ask' passa a operar (gate por espaco).
    `gen`=None (S29) resolve a geração PUBLICADA do repo (rag_sync_state.published_gen,
    default 0 em volume legado) e filtra por ela — leitores nunca veem uma geração
    parcial em montagem. Passar um int fixa a geração (testes/integração).
    `profile` (S32-b/I4): slug ou Profile do espaço vetorial a buscar; None = ativo
    (RAG_PROFILE > publicado no banco > gemini). A tabela buscada, o gate (quando
    PERFIL_GATE) e o gen filtrado vêm TODOS do mesmo perfil — espaços nunca se misturam.
    """
    own_conn = conn is None
    if own_conn:
        conn = psycopg.connect(db_url_from_env())
    try:
        # S32-b: resolve o perfil UMA vez (usa repo+conn p/ ler o ponteiro publicado).
        # Tabela, gate e geração saem todos deste mesmo Profile → coerência de espaço.
        if profile is None:
            prof = _profiles.active_profile(repo, conn)
        elif isinstance(profile, _profiles.Profile):
            prof = profile
        else:
            prof = _profiles.resolve(profile)
        t = prof.table
        # S29: filtra pela geração publicada (azul/verde) DO PERFIL. gen=0 é o
        # default legado → comportamento idêntico ao pré-S29.
        if gen is None:
            from .store import get_published_gen  # lazy — evita ciclo no topo
            gen = get_published_gen(conn, repo, profile=prof)
        if qvec is None:
            # S32-b: query embedada no MESMO perfil da tabela buscada (prefixo e
            # config vêm do Profile resolvido, não do default global).
            prefixed = apply_prefix(query, "query", policy=prof.prefix_policy)
            qvec = embed_texts([prefixed], cfg=config_for_profile(prof))[0]
        qvec_text = "[" + ",".join(f"{float(x):.6g}" for x in qvec) + "]"
        params_common = {
            "repo": repo, "kind": kind, "gen": gen,
            "path_like": (path_prefix + "%") if path_prefix else None,
        }
        # S21: ajusta a largura da busca HNSW p/ esta transacao antes do scan denso.
        ef = EF_SEARCH_DEFAULT if ef_search is None else ef_search
        conn.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(ef),))
        vec_rows = conn.execute(
            _VECTOR_SQL.format(t=t), {**params_common, "qvec": qvec_text, "n": vector_topk}
        ).fetchall()
        lex_rows = conn.execute(
            _LEXICAL_SQL.format(t=t), {**params_common, "q": query, "n": lexical_topk}
        ).fetchall()
        pt_weight = LEXICAL_PT_WEIGHT if lexical_pt_weight is None else lexical_pt_weight
        # S20: terceira lista — léxico pt-BR p/ docs. Peso 0 => desligado (default).
        lists: Sequence[Sequence[tuple]] = [vec_rows, lex_rows]
        all_weights = list(weights) if weights is not None else [1.0, 1.0]
        if pt_weight > 0:
            lex_pt_rows = conn.execute(
                _LEXICAL_PT_SQL.format(t=t), {**params_common, "q": query, "n": lexical_topk}
            ).fetchall()
            lists.append(lex_pt_rows)
            all_weights.append(lexical_pt_weight)

        fused = reciprocal_rank_fusion(lists, weights=all_weights, k=rrf_k)
        hits = [_row_to_hit(row, score, vr, lr, dist)
                for (row, score, vr, lr, dist) in fused.values()]
        # S21 · gate de relevancia por DISTANCIA bruta (nao por score RRF posicional).
        # So um chunk recuperado pelo caminho DENSO tem `dist`; se o melhor candidato
        # denso esta longe demais (dist > max_top1_dist), nada no indice e relevante.
        # None desliga o gate (default em busca pura); PERFIL_GATE usa o gate do
        # perfil ativo (S32/I4 — CLI 'rag --ask'). Nao afeta a ordem nem o recall@k
        # — so filtra saida nao-relevante.
        gate = _resolve_gate(max_top1_dist, profile=prof)
        if gate is not None:
            dense_dists = [h.dist for h in hits if h.dist is not None]
            if not dense_dists or min(dense_dists) > gate:
                return []
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
    if not stale:
        return None
    # Torna o aviso acionavel: indica o comando exato que resolve (sync do perfil
    # ativo). Import lazy de profiles aqui tambem (evita ciclo no topo do modulo).
    from . import profiles as _profiles  # lazy
    slug = _profiles.active_profile().slug
    return (f"[aviso] indice pode estar desatualizado — {reason}. "
            f"Para sincronizar: rag sync --repo {repo_root} --profile {slug}")
