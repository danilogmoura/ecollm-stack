"""Baseline recall@k da FASE 4 (.planning/PLANO-RAG.md §3 FASE 4).

Le eval/dataset.jsonl (perguntas curadas a mao + alvo esperado), roda a busca
hibrida (ingest.search) contra o indice real e calcula:

  - recall@k  : fracao das perguntas cujo alvo esperado aparece no top-k.
                Como cada pergunta tem UM alvo (o chunk certo), recall@k ==
                hit-rate@k aqui. Alvo = qualquer chunk que case com expect_paths
                E (se dado) expect_symbols E (se dado) expect_kinds.
  - MRR       : media do reciproco da posicao do PRIMEIRO acerto (1/rank), 0 se
                nao acertou. Mede quao alto o alvo certo sobe.
  - breakdown por kind (code/doc/config) da pergunta, p/ ver onde o retriever
    e fraco (o plano pede metricas por kind).

Criterio de corte do plano: recall@8 >= 0.7 com Gemini = baseline aceito.

Gate de regressao (S15 / T-EVAL-1): `python -m eval.recall --gate` roda a eval
contra o indice e SAI 1 se recall@8 cair abaixo do piso registrado
(BASELINE_RECALL_AT_8 - MARGEM_REGRESSAO ~ 0,90). Rodar SEMPRE que mexer em
ingest/search/chunker/embeddings — ver .planning/PLANO-SANEAMENTO.md S15.

S23 · Eval v2 — o dataset ganha tres eixos (ver campos em Query):
  - multi-target : perguntas com varios alvos corretos; alem de hit-rate mede-se
                   COBERTURA (@k = % dos alvos distintos no top-k).
  - recusa       : perguntas fora-do-assunto (should_refuse=true) cuja resposta
                   certa e a busca devolver NADA; valida o gate de distancia
                   MAX_TOP1_DIST (S21). Recusa entra na curva recall@k como acerto
                   quando a lista vem vazia, entao o gate S15 tambem pune vazamento.
  - fonte        : source="external" (>=15 perguntas de fonte independente do autor)
                   tem recall reportado a parte (breakdown by_source) p/ expor
                   overfitting das perguntas curadas.

Design testavel: as metricas sao funcoes puras (hit_for_query, aggregate); a
retrieval e injetavel via `retrieve` (default = ingest.search.search real). Os
unit tests exercitam as metricas sem tocar em rede/DB.

Saida: relatorio markdown -> .planning/relatorio-avaliacao-<YYYYMMDD>.md
(override --out). Rodar:  python -m eval.recall [--k 1,3,5,8,10] [--json] [--gate]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
DEFAULT_DATASET = EVAL_DIR / "dataset.jsonl"
DEFAULT_PLANNING_DIR = REPO_ROOT / ".planning"

# k's avaliados por default (plano pede recall@1/3/5/8/10)
DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 8, 10)


# ---------------------------------------------------------------------------
# dataset
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    id: str
    question: str
    expect_paths: tuple[str, ...]
    expect_symbols: tuple[str, ...]
    expect_kinds: tuple[str, ...]
    note: str = ""
    # S23 · Eval v2 — três eixos novos no esquema do dataset:
    #   source        : "curated" (default, autor do código) | "external"
    #                   (fonte independente). Recall externo é reportado à parte
    #                   p/ expor overfitting das perguntas curadas.
    #   should_refuse : True = pergunta fora-do-assunto; a resposta certa é NÃO
    #                   achar nada (recusa). Mede a precisão do gate de distância.
    #   expect_targets: nº de alvos distintos que DEVEM aparecer no top-k (mede
    #                   cobertura multi-chunk); default = len(expect_paths).
    source: str = "curated"
    should_refuse: bool = False
    expect_targets: int = 0

    @property
    def targets(self) -> int:
        """Quantos alvos distintos esta pergunta exige no top-k (multi-target)."""
        return self.expect_targets or len(self.expect_paths)

    def is_negative(self) -> bool:
        return self.should_refuse

    def matches(self, path: str, symbol: str | None, kind: str) -> bool:
        """Um chunk de saida e 'o alvo' desta pergunta?

        path deve estar em expect_paths; se a pergunta fixou symbols/kinds, o
        chunk tambem precisa casar (None na saida nunca casa com um esperado).
        """
        if path not in self.expect_paths:
            return False
        if self.expect_symbols and (symbol or "") not in self.expect_symbols:
            return False
        if self.expect_kinds and kind not in self.expect_kinds:
            return False
        return True


def load_dataset(path: Path = DEFAULT_DATASET) -> list[Query]:
    out: list[Query] = []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rec = json.loads(line)
            out.append(Query(
                id=rec["id"],
                question=rec["question"],
                expect_paths=tuple(rec.get("expect_paths", [])),
                expect_symbols=tuple(rec.get("expect_symbols", [])),
                expect_kinds=tuple(rec.get("expect_kinds", [])),
                note=rec.get("note", ""),
                source=rec.get("source", "curated"),
                should_refuse=bool(rec.get("should_refuse", False)),
                expect_targets=int(rec.get("expect_targets", 0)),
            ))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}:{ln}: registro invalido: {exc}") from exc
    if not out:
        raise ValueError(f"dataset vazio: {path}")
    return out


# ---------------------------------------------------------------------------
# metricas puras
# ---------------------------------------------------------------------------

def first_hit_rank(query: Query, results: Sequence[tuple[str, str | None, str]]) -> int | None:
    """Posicao (1-based) do primeiro chunk que casa com o alvo; None se nenhum."""
    for rank, (path, symbol, kind) in enumerate(results, 1):
        if query.matches(path, symbol, kind):
            return rank
    return None


def recall_at_k(rank: int | None, k: int) -> float:
    """0/1: o alvo aparece no top-k? (recall unitario p/ pergunta de alvo unico)."""
    return 1.0 if (rank is not None and rank <= k) else 0.0


def reciprocal_rank(rank: int | None) -> float:
    return (1.0 / rank) if rank else 0.0


@dataclass(frozen=True)
class PerQuery:
    id: str
    question: str
    kind_group: str          # bucket p/ breakdown = primeiro expect_kind ou "mixed"
    rank: int | None         # posicao do primeiro acerto (None = miss total)
    ks: tuple[int, ...]
    # S23 · campos opcionais (defaultados p/ tras-compatibilidade dos testes):
    source: str = "curated"       # "curated" | "external"
    is_negative: bool = False     # pergunta de recusa (fora-do-assunto)
    refused: bool = False         # a busca devolveu lista VAZIA (gate cortou tudo)
    targets: int = 1              # nº de alvos distintos exigidos (multi-target)
    covered: int = 0              # quantos alvos distintos caíram no top-k max(ks)

    @property
    def rr(self) -> float:
        return reciprocal_rank(self.rank)

    def recall(self, k: int) -> float:
        """Hit-rate@k p/ perguntas positivas; p/ negativas vale a RECUSA.

        Pergunta de recusa (S23): o "acerto" é a busca não devolver nada — o
        gate de distância (MAX_TOP1_DIST) deve cortar o fora-do-assunto. Assim
        recusa entra na MESMA curva recall@k e no gate S15 sem trair o piso.
        """
        if self.is_negative:
            return 1.0 if self.refused else 0.0
        return recall_at_k(self.rank, k)

    def coverage(self, k: int) -> float:
        """Fração dos alvos distintos que aparecem no top-k (multi-chunk).

        Só faz sentido p/ perguntas positivas multi-alvo; single-target dá 0/1
        igual a recall(). Negativas retornam 1.0 por convenção (nada a cobrir).
        """
        if self.is_negative or self.targets <= 0:
            return 1.0
        return min(1.0, self.covered / self.targets)


def _count_targets(query: Query, results: Sequence[tuple[str, str | None, str]],
                   kmax: int) -> int:
    """Quantos caminhos esperados distintos aparecem no top-`kmax`."""
    seen: set[str] = set()
    for (path, symbol, kind) in results[:kmax]:
        if query.matches(path, symbol, kind):
            seen.add(path)
    return len(seen)


def _kind_group(query: Query) -> str:
    kinds = set(query.expect_kinds)
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def evaluate(
    queries: Sequence[Query],
    retrieve: Callable[[Query], Sequence[tuple[str, str | None, str]]],
    ks: Sequence[int] = DEFAULT_KS,
) -> list[PerQuery]:
    """Roda `retrieve` p/ cada pergunta e produz o resultado por-pergunta.

    `retrieve` devolve a lista ordenada de (path, symbol, kind) do top-k max(k).
    S23: registra também se a busca recusou (lista vazia) e quantos alvos
    distintos caíram no top-k (cobertura multi-chunk), além da fonte da pergunta.
    """
    ks_t = tuple(sorted(set(ks)))
    kmax = max(ks_t) if ks_t else 0
    rows: list[PerQuery] = []
    for q in queries:
        results = retrieve(q)
        rank = first_hit_rank(q, results)
        rows.append(PerQuery(
            id=q.id, question=q.question, kind_group=_kind_group(q),
            rank=rank, ks=ks_t, source=q.source, is_negative=q.is_negative(),
            refused=len(results) == 0, targets=max(1, q.targets),
            covered=_count_targets(q, results, kmax),
        ))
    return rows


def aggregate(rows: Sequence[PerQuery], ks: Sequence[int] | None = None) -> dict:
    """Resumo global + por kind + por fonte (S23): recall@k, MRR, cobertura e recusa."""
    ks_t = tuple(sorted(set(ks))) if ks else tuple(sorted({k for r in rows for k in r.ks}))

    def summarize(subset: Sequence[PerQuery]) -> dict:
        n = len(subset)
        if n == 0:
            return {"n": 0, "recall": {}, "mrr": 0.0, "coverage": {},
                    "refusal": None}
        pos = [r for r in subset if not r.is_negative]
        neg = [r for r in subset if r.is_negative]
        return {
            "n": n,
            "recall": {k: round(statistics.fmean(r.recall(k) for r in subset), 4) for k in ks_t},
            "mrr": round(statistics.fmean(r.rr for r in pos), 4) if pos else 0.0,
            # cobertura média só das positivas multi-alvo (targets>1)
            "coverage": {k: round(statistics.fmean(r.coverage(k) for r in pos), 4)
                         for k in ks_t} if pos else {},
            # taxa de recusa = % das negativas que a busca devolveu vazia
            "refusal": (round(statistics.fmean(1.0 if r.refused else 0.0 for r in neg), 4)
                        if neg else None),
        }

    by_kind: dict[str, dict] = {}
    for grp in sorted({r.kind_group for r in rows}):
        by_kind[grp] = summarize([r for r in rows if r.kind_group == grp])
    # S23 · breakdown por FONTE: curadas vs externas (overfitting) — só positivas
    # têm recall; recusa aparece no grupo onde as negativas foram lançadas.
    by_source: dict[str, dict] = {}
    for src in sorted({r.source for r in rows}):
        by_source[src] = summarize([r for r in rows if r.source == src])
    return {"overall": summarize(rows), "by_kind": by_kind, "by_source": by_source,
            "misses": [r.id for r in rows
                       if (r.is_negative and not r.refused) or (not r.is_negative and r.rank is None)]}


# ---------------------------------------------------------------------------
# gate de regressão (S15 / T-EVAL-1)
# ---------------------------------------------------------------------------

# Baseline registrado da FASE 4 (recall@8 = 0,933). Margem de tolerância à
# flutuação (chamadas reais de embedding variam): o gate reprova abaixo de
# BASELINE_RECALL_AT_8 - MARGEM_REGRESSAO (~0,90). Ver .planning/PLANO-RAG.md §5b.
BASELINE_RECALL_AT_8 = 0.933
MARGEM_REGRESSAO = 0.033
GATE_K = 8


def gate_threshold() -> float:
    """Piso do gate: baseline menos a margem de tolerância."""
    return round(BASELINE_RECALL_AT_8 - MARGEM_REGRESSAO, 4)


def check_gate(agg: dict, *, k: int = GATE_K, threshold: float | None = None) -> dict:
    """Decisão do gate de regressão sobre métricas já agregadas.

    Puro (sem DB/rede): recebe o dict de `aggregate` e compara recall@k contra o
    piso. Retorna dict com a medição, o piso e o veredito — nunca levanta, para
    que o chamador (CLI/teste) decida o que fazer com `passed=False`.
    """
    thr = gate_threshold() if threshold is None else threshold
    recall = agg.get("overall", {}).get("recall", {})
    medido = recall.get(k)
    # Sem perguntas (ou k não avaliado) NÃO é 'aprovado' — falha conservadora.
    passed = medido is not None and medido >= thr
    return {
        "k": k,
        "medido": medido,
        "piso": thr,
        "baseline": BASELINE_RECALL_AT_8,
        "margem": MARGEM_REGRESSAO,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# retrieval real (usa ingest.search + DB/env)
# ---------------------------------------------------------------------------

def make_live_retriever(repo: str, final_k: int,
                        lexical_pt_weight: float | None = None,
                        ef_search: int | None = None, rrf_k: int | None = None,
                        vector_topk: int | None = None,
                        max_top1_dist: float | None = None,
                        ) -> Callable[[Query], list[tuple[str, str | None, str]]]:
    """Retriever que chama a busca hibrida real (rede LiteLLM + Postgres).

    Encaminha os knobs de tuning de retrieval (S20/S21) p/ search.search() para que
    o harness meça curvas sem editar código. None em cada um => default do módulo.
    `lexical_pt_weight` (S20): 0.0 desliga o caminho léxico pt-BR (lado B do A/B).
    `max_top1_dist` (S23): limiar de distancia do gate de recusa (S21). Default None
        deixa o gate DESLIGADO (recall@k mede só ordenacao). Para medir RECUSA nas
        perguntas negativas, passe MAX_TOP1_DIST (= comportamento do CLI em prod):
        assim uma negativa fora-do-assunto volta lista vazia e conta como recusa.
    """
    from ingest import search as search_mod

    kw: dict[str, Any] = {}
    if lexical_pt_weight is not None:
        kw["lexical_pt_weight"] = lexical_pt_weight
    if ef_search is not None:
        kw["ef_search"] = ef_search
    if rrf_k is not None:
        kw["rrf_k"] = rrf_k
    if vector_topk is not None:
        kw["vector_topk"] = vector_topk
    if max_top1_dist is not None:
        kw["max_top1_dist"] = max_top1_dist

    def _retrieve(q: Query) -> list[tuple[str, str | None, str]]:
        hits = search_mod.search(q.question, repo=repo, final_k=final_k, **kw)
        return [(h.path, h.symbol, h.kind) for h in hits]

    return _retrieve


# ---------------------------------------------------------------------------
# relatorio markdown
# ---------------------------------------------------------------------------

def render_report(rows: Sequence[PerQuery], agg: dict, *, ks: Sequence[int],
                  dataset_path: Path, repo: str, embedder: str) -> str:
    today = date.today().isoformat()
    overall = agg["overall"]
    lines: list[str] = []
    lines.append(f"# Relatório de avaliação RAG — baseline recall@k")
    lines.append("")
    lines.append(f"- Data: **{today}**")
    lines.append(f"- Repo indexado: `{repo}`")
    lines.append(f"- Embedder: `{embedder}`")
    try:
        ds_disp = dataset_path.relative_to(REPO_ROOT)
    except ValueError:
        ds_disp = dataset_path
    lines.append(f"- Dataset: `{ds_disp}` ({len(rows)} perguntas)")
    lines.append(f"- Busca: híbrida (HNSW cosine + tsvector BM25 → RRF k=60), "
                 f"final_k={max(ks)}")
    gate = overall["recall"].get(8)
    verdict = ("✅ ACEITO" if (gate is not None and gate >= 0.7)
               else "❌ ABAIXO DO CORTE (recall@8 < 0.7)")
    lines.append(f"- Critério de corte (plano §FASE 4): recall@8 ≥ 0.7 → **{verdict}**")
    lines.append("")
    lines.append("## Métricas globais")
    lines.append("")
    lines.append("| k | recall@k |")
    lines.append("| --- | --- |")
    for k in sorted(ks):
        lines.append(f"| @{k} | {overall['recall'].get(k, float('nan')):.3f} |")
    lines.append(f"| MRR | {overall['mrr']:.3f} |")
    lines.append("")
    lines.append("## Por tipo de alvo (kind)")
    lines.append("")
    header = "| kind | n | " + " | ".join(f"r@{k}" for k in sorted(ks)) + " | MRR |"
    sep = "| --- | --- | " + " | ".join("---" for _ in ks) + " | --- |"
    lines += [header, sep]
    for grp, d in agg["by_kind"].items():
        cells = " | ".join(f"{d['recall'].get(k, float('nan')):.2f}" for k in sorted(ks))
        lines.append(f"| {grp} | {d['n']} | {cells} | {d['mrr']:.2f} |")
    lines.append("")
    # S23 · recall por FONTE (curadas vs externas): expõe overfitting.
    if agg.get("by_source"):
        lines.append("## Por fonte da pergunta (overfitting)")
        lines.append("")
        lines.append("`external` = perguntas de fonte independente do autor do código;")
        lines.append("recall externo mais baixo que o curado indica sobre-ajuste ao crivo local.")
        lines.append("")
        lines.append("| fonte | n | " + " | ".join(f"r@{k}" for k in sorted(ks)) + " | MRR | cobertura@" + str(max(ks)) + " | recusa |")
        lines.append("| --- | --- | " + " | ".join("---" for _ in ks) + " | --- | --- | --- |")
        for src, d in agg["by_source"].items():
            cells = " | ".join(f"{d['recall'].get(k, float('nan')):.2f}" for k in sorted(ks))
            cov = d["coverage"].get(max(ks), float("nan"))
            ref = "—" if d["refusal"] is None else f"{d['refusal']:.2f}"
            lines.append(f"| {src} | {d['n']} | {cells} | {d['mrr']:.2f} | {cov:.2f} | {ref} |")
        lines.append("")
    lines.append("## Acertos por pergunta")
    lines.append("")
    lines.append("| id | rank | RR | grupo | fonte | alvos | cobertos | pergunta |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(rows, key=lambda x: (x.rank is None, x.rank or 999, x.id)):
        rank = "-" if r.rank is None else str(r.rank)
        qtxt = r.question.replace("|", "\\|")
        neg = " 🚫" if r.is_negative else ""
        cov = f"{r.covered}/{r.targets}" if not r.is_negative else ("recusada" if r.refused else "VAZOU")
        lines.append(f"| {r.id}{neg} | {rank} | {r.rr:.2f} | {r.kind_group} | "
                     f"{r.source} | {r.targets} | {cov} | {qtxt} |")
    lines.append("")
    if agg["misses"]:
        lines.append("### Perguntas sem acerto no top-" + str(max(ks)))
        lines.append("")
        for mid in agg["misses"]:
            row = next(r for r in rows if r.id == mid)
            lines.append(f"- `{mid}` — {row.question}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Baseline recall@k da FASE 4")
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--repo", default=None, help="nome do repo no índice (default: pasta raiz)")
    ap.add_argument("--k", default=",".join(str(x) for x in DEFAULT_KS),
                    help="lista de k separada por vírgula (ex: 1,3,5,8,10)")
    ap.add_argument("--out", type=Path, default=None, help="caminho do relatório md")
    ap.add_argument("--json", action="store_true", help="imprime métricas em JSON no stdout")
    ap.add_argument("--gate", action="store_true",
                    help="modo regressão (S15): sai 1 se recall@8 < piso "
                         "(baseline - margem). Use após mexer em ingest/search/chunker.")
    ap.add_argument("--min-recall", type=float, default=None, dest="min_recall",
                    help="override do piso do gate (default: baseline-margem)")
    ap.add_argument("--lexical-pt", type=float, default=None, dest="lexical_pt",
                    help="peso do caminho léxico pt-BR (S20). 0 = desliga (A/B off); "
                         "omitido = default do search.")
    # S21 · knobs de tuning de retrieval p/ curvas medidas (ef_search, RRF k, top-k).
    ap.add_argument("--ef-search", type=int, default=None, dest="ef_search",
                    help="S21: hnsw.ef_search (largura da varredura HNSW). Omitir usa "
                         "o default do modulo (= vector_topk).")
    ap.add_argument("--rrf-k", type=int, default=None, dest="rrf_k",
                    help="S21: constante k do RRF (default do modulo = 60).")
    ap.add_argument("--vector-topk", type=int, default=None, dest="vector_topk",
                    help="S21: tamanho do candidato denso que alimenta a fusao "
                         "(default do modulo = 50).")
    # S23 · gate de recusa (distancia) para medir as perguntas negativas.
    ap.add_argument("--gate-dist", action="store_true", dest="gate_dist",
                    help="S23: aplica o gate de distancia do PERFIL (= comportamento "
                         "do CLI em prod) para que as negativas fora-do-assunto sejam "
                         "cortadas e a RECUSA seja medida. Sem isto o gate fica desligado.")
    # S32 (I7) · perfil de embedding avaliado. Default = perfil ativo (RAG_PROFILE >
    # publicado > gemini). Troca gate/prefixo/dim da eval sem editar codigo/.env.
    ap.add_argument("--profile", default=None,
                    help="S32: slug do perfil de embedding (ex.: qwen37). Omitido usa "
                         "o perfil ativo. Define o gate usado por --gate-dist e e citado "
                         "no relatorio.")
    args = ap.parse_args(argv)

    ks = tuple(int(x) for x in str(args.k).split(",") if x.strip())
    # No modo gate o k vigiado (@8) DEVE ser avaliado, mesmo se --k não o liste.
    if args.gate and GATE_K not in ks:
        ks = tuple(sorted(set(ks) | {GATE_K}))
    queries = load_dataset(args.dataset)

    from ingest import ingest as ingest_mod
    from ingest import profiles as _profiles
    repo = args.repo or ingest_mod.repo_name(REPO_ROOT)
    # S32: resolve o perfil (valida slug cedo — R1) e fixa RAG_PROFILE p/ o processo,
    # assim search/embed resolvem tudo via registry (gate, prefixo, dim, modelo).
    prof = _profiles.resolve(args.profile) if args.profile else _profiles.active_profile()
    os.environ["RAG_PROFILE"] = prof.slug
    from ingest import search as _search_mod
    # S32/I7: gate de recusa vem do PERFIL (nao mais MAX_TOP1_DIST hardcoded).
    gate_dist = prof.gate if args.gate_dist else None
    retriever = make_live_retriever(repo, final_k=max(ks), lexical_pt_weight=args.lexical_pt,
                                    ef_search=args.ef_search, rrf_k=args.rrf_k,
                                    vector_topk=args.vector_topk, max_top1_dist=gate_dist)
    rows = evaluate(queries, retriever, ks=ks)
    agg = aggregate(rows, ks=ks)

    gate = check_gate(agg, k=GATE_K, threshold=args.min_recall) if args.gate else None

    if args.json:
        payload = {"repo": repo, "profile": prof.slug, "ks": list(ks), **agg}
        if gate is not None:
            payload["gate"] = gate
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    report = render_report(rows, agg, ks=ks, dataset_path=args.dataset, repo=repo,
                           embedder=f"{prof.slug}:{prof.model}")
    out = args.out or (DEFAULT_PLANNING_DIR / f"relatorio-avaliacao-{date.today().strftime('%Y%m%d')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    if not args.json:
        o = agg["overall"]
        print(f"[eval] {len(rows)} perguntas | repo={repo}")
        for k in sorted(ks):
            print(f"  recall@{k} = {o['recall'][k]:.3f}")
        print(f"  MRR = {o['mrr']:.3f}")
        # S23 · recusa + recall por fonte (overfitting)
        if o.get("refusal") is not None:
            print(f"  recusa (negativas cortadas) = {o['refusal']:.3f}")
        for src, d in agg.get("by_source", {}).items():
            ext = " (externas)" if src == "external" else ""
            print(f"  [{src}{ext}] n={d['n']} "
                  f"recall@8={d['recall'].get(8, float('nan')):.3f} MRR={d['mrr']:.3f}")
        if agg["misses"]:
            print(f"  misses: {', '.join(agg['misses'])}")
    print(f"[eval] relatório -> {out}")

    if gate is not None:
        med = "n/a" if gate["medido"] is None else f"{gate['medido']:.3f}"
        if gate["passed"]:
            print(f"[gate] ✅ recall@{gate['k']} = {med} ≥ piso {gate['piso']:.3f} "
                  f"(baseline {gate['baseline']:.3f} − margem {gate['margem']:.3f})")
            return 0
        print(f"[gate] ❌ REPROVADO: recall@{gate['k']} = {med} < piso "
              f"{gate['piso']:.3f} — possível regressão em ingest/search/chunker.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
