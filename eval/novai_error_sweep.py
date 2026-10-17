"""S115 — sweep do contrato de erro (T15/T16) em TODOS os grupos de chat.

Motivação: até S115 o contrato de erro só tinha rodado em **1 grupo**
(``novai-deepseek-v4-flash``, 22 repetições). Com o fix de S115 (aceitar 400 no
caso 404 e o shape FastAPI ``{"detail": ...}``), vale medir se o comportamento
de erro é uniforme entre upstreams — Kimi/ZhiPu podem usar envelopes
diferentes.

Escopo: **só** ``error_404`` e ``error_400``. Nenhum token é gasto no upstream
(modelo inexistente / payload inválido), então o sweep é praticamente grátis.

Uso::

    .venv/bin/python -m eval.novai_error_sweep --target both --sleep 0.3
    .venv/bin/python -m eval.novai_error_sweep --target gateway --family chat

Saída: resumo por classe de envelope + jsonl em ``reports/logs/``.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict

from eval.novai_test import (
    CheckResult,
    attach_capture,
    load_groups,
    make_capturing_sender,
    resolve_targets,
    run_error_contract,
    target_config,
)


def envelope_class(body_raw: str) -> str:
    """Classifica o envelope de erro observado (puro, testável offline).

    Recebe o corpo cru (JSON em texto) e devolve:

    - ``openai``   — ``{"error": {...}}`` (envelope OpenAI/LiteLLM)
    - ``fastapi``  — ``{"detail": ...}`` (shape FastAPI do gateway NovAI)
    - ``both``     — traz os dois campos
    - ``other``    — nenhum dos dois (contrato quebrado)
    - ``empty``    — corpo vazio/ilegível
    """
    import json

    if not body_raw or not body_raw.strip():
        return "empty"
    try:
        body = json.loads(body_raw)
    except ValueError:
        return "other"
    if not isinstance(body, dict):
        return "other"
    has_error = isinstance(body.get("error"), (dict, str))
    has_detail = "detail" in body
    if has_error and has_detail:
        return "both"
    if has_error:
        return "openai"
    if has_detail:
        return "fastapi"
    return "other"


def summarize(results: list[CheckResult], classes: dict[tuple[str, str], str]
              ) -> dict:
    """Agrega o sweep por (target, test_id) e por classe de envelope.

    ``classes`` mapeia ``(target, test_id)`` → classe do envelope observado.
    A classe é contada **uma vez por chave** (é propriedade do alvo+teste, não
    de cada repetição). Devolve contadores prontos para impressão/relatório.
    """
    by_test: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in results:
        key = (r.target or "?", r.test)
        by_test[key]["pass" if r.passed else "fail"] += 1
    for key, cls in classes.items():
        if key in by_test:
            by_test[key][f"env:{cls}"] += 1
    return {k: dict(v) for k, v in by_test.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", default="both",
                    choices=["gateway", "proxy", "both"],
                    help="gateway | proxy | both (default: both)")
    ap.add_argument("--family", default="chat", help="família a varrer (default: chat)")
    ap.add_argument("--sleep", type=float, default=0.3,
                    help="pausa (s) entre grupos; respeita 60 rpm")
    ap.add_argument("--limit", type=int, default=0,
                    help="limita N grupos (0 = todos); útil p/ smoke")
    args = ap.parse_args(argv)

    rows = [r for r in load_groups() if r["modality"].startswith(args.family)]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print(f"nenhum grupo de modalidade {args.family!r}", file=sys.stderr)
        return 2

    targets = resolve_targets(args.target)
    print(f"# sweep de contrato de erro — {len(rows)} grupos × {len(targets)} alvo(s)")

    results: list[CheckResult] = []
    classes: dict[tuple[str, str], str] = {}
    for target in targets:
        cfg = target_config(target)
        sink: dict = {}
        sender = make_capturing_sender(cfg, sink)
        for i, r in enumerate(rows):
            if i and args.sleep > 0:
                time.sleep(args.sleep)
            model = (r.get("upstream_id") or r["group"]
                     if target == "gateway" else r["group"])
            for case in ("404", "400"):
                t0 = time.monotonic()
                res = run_error_contract(sender, model, case=case)
                res.group = r["group"]
                res.target = target
                res.latency_ms = (time.monotonic() - t0) * 1000.0
                # run_error_contract não anexa a captura (a suíte faz isso);
                # aqui anexamos para poder classificar o envelope.
                attach_capture(res, sink)
                results.append(res)
                classes[(target, res.test)] = envelope_class(res.body_raw or "")
                mark = "✅" if res.passed else "❌"
                print(f"  {mark} [{target}] {r['group']} :: {res.test} — {res.evidence}")

    summary = summarize(results, classes)
    print("\n# resumo por (alvo, teste)")
    for (target, test), counts in sorted(summary.items()):
        parts = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  {target:8s} {test:10s} {parts}")

    # Envelopes distintos por alvo — o ponto do sweep.
    print("\n# envelopes observados")
    for target in targets:
        seen = Counter(c for (t, _), c in classes.items() if t == target)
        print(f"  {target:8s} {dict(seen)}")

    from eval.novai_log import log_results
    p = log_results(results, family="error-sweep")
    if p:
        print(f"# log: {p}")

    nfail = sum(1 for r in results if not r.passed)
    print(f"\n# {len(results)} checks · {len(results) - nfail} pass · {nfail} fail")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
