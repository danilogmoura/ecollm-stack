"""Gera relatório Markdown da documentação do NovAI.

Lê `reports/novai-docs.json` (saída de eval.novai_docs_scrape) e produz
`reports/2026-10-16-novai-docs.md`.

Uso:
    python -m eval.novai_docs_report
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

IN = "reports/novai-docs.json"
OUT = "reports/2026-10-16-novai-docs.md"


def _md_table(t: dict) -> list[str]:
    headers = t.get("headers") or []
    rows = t.get("rows") or []
    if not headers and not rows:
        return []
    ncol = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 0
    if ncol == 0:
        return []
    head = headers + [""] * (ncol - len(headers))
    out = ["| " + " | ".join(h or " " for h in head) + " |",
           "|" + "|".join(["---"] * ncol) + "|"]
    for r in rows:
        cells = r + [""] * (ncol - len(r))
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return out


def build(page: dict) -> str:
    lines: list[str] = []
    a = lines.append
    a("# NovAI — Documentação da API (scrape)")
    a("")
    a(f"Fonte: `{page.get('url')}`")
    a(f"Título: {page.get('title')}")
    a(f"Seções: **{len(page.get('sections', []))}** · "
      f"Tabelas: **{sum(len(s.get('tables', [])) for s in page.get('sections', []))}** · "
      f"Blocos de código: **{sum(len(s.get('code_blocks', [])) for s in page.get('sections', []))}**")
    a("")
    a("## Índice")
    a("")
    for s in page.get("sections", []):
        indent = "  " * (s.get("level", 2) - 2)
        anchor = s.get("anchor")
        link = f"[{s['title']}](#{anchor})" if anchor else s["title"]
        a(f"{indent}- {link}")
    a("")

    for s in page.get("sections", []):
        lvl = s.get("level", 2)
        a(f"{'#' * (lvl + 1)} {s['title']}")
        a("")
        if s.get("method") and s.get("endpoint"):
            a(f"`{s['method']} {s['endpoint']}`")
            a("")
        if s.get("text"):
            a(s["text"])
            a("")
        for alert in s.get("alerts", []):
            a(f"> ⚠️ {alert}")
            a("")
        for t in s.get("tables", []):
            tbl = _md_table(t)
            if tbl:
                lines.extend(tbl)
                a("")
        for cb in s.get("code_blocks", []):
            a("```")
            a(cb.get("code", ""))
            a("```")
            a("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    src = Path(IN)
    if not src.exists():
        print(f"faltando {IN}; rode eval.novai_docs_scrape --live primeiro", file=sys.stderr)
        return 1
    page = json.loads(src.read_text(encoding="utf-8"))
    md = build(page)
    Path(OUT).write_text(md, encoding="utf-8")
    print(f"salvo: {OUT} ({len(md)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
