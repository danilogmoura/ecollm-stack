"""Gera relatório Markdown dos metadados por modelo (via API).

Lê `reports/novai-model-api.json` (saída de eval.novai_model_api) e produz
`reports/2026-10-16-novai-model-api.md`.

Uso:
    python -m eval.novai_model_api_report
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

IN = "reports/novai-model-api.json"
OUT = "reports/2026-10-16-novai-model-api.md"


def _probe_cell(p: dict | None) -> str:
    if not p:
        return "—"
    mark = "✅" if p.get("ok") else "❌"
    ev = (p.get("evidence") or "").replace("|", "\\|")
    if len(ev) > 60:
        ev = ev[:57] + "…"
    return f"{mark} {ev}"


def build(models: list[dict]) -> str:
    lines: list[str] = []
    a = lines.append
    a("# NovAI — Metadados por modelo (via API)")
    a("")
    a("Fonte: `GET /v1/models` (via proxy LiteLLM) + sondas de capacidade por modelo.")
    a(f"Modelos: **{len(models)}**")
    a("")
    a("Cada modelo traz: metadados do `/v1/models` (`owned_by`, `pricing`, `type`), "
      "o grupo/modalidade do inventário local, e o resultado das sondas de "
      "capacidade (chat, thinking, tools, embedding, image, tts, asr).")
    a("")

    # resumo por modalidade
    by_mod: dict[str, list[dict]] = defaultdict(list)
    for m in models:
        by_mod[m.get("modality") or "(sem inventário)"].append(m)
    a("## Resumo por modalidade")
    a("")
    a("| Modalidade | Modelos |")
    a("|---|---|")
    for mod in sorted(by_mod):
        a(f"| {mod} | {len(by_mod[mod])} |")
    a("")

    # resumo de sondas
    probe_names = sorted({k for m in models for k in (m.get("probes") or {})})
    if probe_names:
        a("## Sucesso das sondas")
        a("")
        a("| Sonda | ok | total |")
        a("|---|---|---|")
        for name in probe_names:
            tot = sum(1 for m in models if name in (m.get("probes") or {}))
            ok = sum(1 for m in models if (m.get("probes") or {}).get(name, {}).get("ok"))
            a(f"| {name} | {ok} | {tot} |")
        a("")

    # detalhe por modelo
    a("## Detalhe por modelo")
    a("")
    for m in sorted(models, key=lambda x: x["id"]):
        a(f"### `{m['id']}`")
        a("")
        meta = []
        if m.get("owned_by"):
            meta.append(f"owned_by: `{m['owned_by']}`")
        if m.get("pricing"):
            meta.append(f"pricing: `{m['pricing']}`")
        if m.get("type"):
            meta.append(f"type: `{m['type']}`")
        if m.get("group"):
            meta.append(f"grupo: `{m['group']}`")
        if m.get("modality"):
            meta.append(f"modalidade: `{m['modality']}`")
        if meta:
            a("- " + " · ".join(meta))
        probes = m.get("probes") or {}
        if probes:
            a("")
            a("| Sonda | Resultado |")
            a("|---|---|")
            for name in sorted(probes):
                a(f"| {name} | {_probe_cell(probes[name])} |")
        if m.get("errors"):
            a("")
            a(f"- ⚠️ erros: {'; '.join(m['errors'])}")
        a("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    src = Path(IN)
    if not src.exists():
        print(f"faltando {IN}; rode eval.novai_model_api --live primeiro", file=sys.stderr)
        return 1
    models = json.loads(src.read_text(encoding="utf-8"))
    md = build(models)
    Path(OUT).write_text(md, encoding="utf-8")
    print(f"salvo: {OUT} ({len(md)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
