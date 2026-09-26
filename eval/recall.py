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

Design testavel: as metricas sao funcoes puras (hit_for_query, aggregate); a
retrieval e injetavel via `retrieve` (default = ingest.search.search real). Os
unit tests exercitam as metricas sem tocar em rede/DB.

Saida: relatorio markdown -> .planning/relatorio-avaliacao-<YYYYMMDD>.md
(override --out). Rodar:  python -m eval.recall [--k 1,3,5,8,10] [--json] [--gate]
"""

from __future__ import annotations

import argparse
import json
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

    @property
    def rr(self) -> float:
        return reciprocal_rank(self.rank)

    def recall(self, k: int) -> float:
        return recall_at_k(self.rank, k)


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
    """
    ks_t = tuple(sorted(set(ks)))
    rows: list[PerQuery] = []
    for q in queries:
        results = retrieve(q)
        rank = first_hit_rank(q, results)
        rows.append(PerQuery(id=q.id, question=q.question, kind_group=_kind_group(q),
                             rank=rank, ks=ks_t))
    return rows


def aggregate(rows: Sequence[PerQuery], ks: Sequence[int] | None = None) -> dict:
    """Resumo global + por kind: recall@k medio e MRR."""
    ks_t = tuple(sorted(set(ks))) if ks else tuple(sorted({k for r in rows for k in r.ks}))

    def summarize(subset: Sequence[PerQuery]) -> dict:
        n = len(subset)
        if n == 0:
            return {"n": 0, "recall": {}, "mrr": 0.0}
        return {
            "n": n,
            "recall": {k: round(statistics.fmean(r.recall(k) for r in subset), 4) for k in ks_t},
            "mrr": round(statistics.fmean(r.rr for r in subset), 4),
        }

    by_kind: dict[str, dict] = {}
    for grp in sorted({r.kind_group for r in rows}):
        by_kind[grp] = summarize([r for r in rows if r.kind_group == grp])
    return {"overall": summarize(rows), "by_kind": by_kind,
            "misses": [r.id for r in rows if r.rank is None]}


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
                        ) -> Callable[[Query], list[tuple[str, str | None, str]]]:
    """Retriever que chama a busca hibrida real (rede LiteLLM + Postgres).

    Encaminha os knobs de tuning de retrieval (S20/S21) p/ search.search() para que
    o harness meça curvas sem editar código. None em cada um => default do módulo.
    `lexical_pt_weight` (S20): 0.0 desliga o caminho léxico pt-BR (lado B do A/B).
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
    lines.append(f"- Dataset: `{dataset_path.relative_to(REPO_ROOT)}` ({len(rows)} perguntas)")
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
    lines.append("## Acertos por pergunta")
    lines.append("")
    lines.append("| id | rank | RR | grupo | pergunta |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in sorted(rows, key=lambda x: (x.rank is None, x.rank or 999, x.id)):
        rank = "-" if r.rank is None else str(r.rank)
        qtxt = r.question.replace("|", "\\|")
        lines.append(f"| {r.id} | {rank} | {r.rr:.2f} | {r.kind_group} | {qtxt} |")
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
    args = ap.parse_args(argv)

    ks = tuple(int(x) for x in str(args.k).split(",") if x.strip())
    # No modo gate o k vigiado (@8) DEVE ser avaliado, mesmo se --k não o liste.
    if args.gate and GATE_K not in ks:
        ks = tuple(sorted(set(ks) | {GATE_K}))
    queries = load_dataset(args.dataset)

    from ingest import ingest as ingest_mod
    repo = args.repo or ingest_mod.repo_name(REPO_ROOT)
    retriever = make_live_retriever(repo, final_k=max(ks), lexical_pt_weight=args.lexical_pt,
                                    ef_search=args.ef_search, rrf_k=args.rrf_k,
                                    vector_topk=args.vector_topk)
    rows = evaluate(queries, retriever, ks=ks)
    agg = aggregate(rows, ks=ks)

    gate = check_gate(agg, k=GATE_K, threshold=args.min_recall) if args.gate else None

    if args.json:
        payload = {"repo": repo, "ks": list(ks), **agg}
        if gate is not None:
            payload["gate"] = gate
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    report = render_report(rows, agg, ks=ks, dataset_path=args.dataset, repo=repo,
                           embedder="gemini-embedding-2")
    out = args.out or (DEFAULT_PLANNING_DIR / f"relatorio-avaliacao-{date.today().strftime('%Y%m%d')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    if not args.json:
        o = agg["overall"]
        print(f"[eval] {len(rows)} perguntas | repo={repo}")
        for k in sorted(ks):
            print(f"  recall@{k} = {o['recall'][k]:.3f}")
        print(f"  MRR = {o['mrr']:.3f}")
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
