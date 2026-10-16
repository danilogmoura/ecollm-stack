"""Gera relatório Markdown das configurações de modelo do NovAI.

Lê `reports/novai-model-configs.json` (saída de eval.novai_scrape_models) e
produz `reports/2026-10-16-novai-configs-por-modelo.md`.

Uso:
    python -m eval.novai_configs_report
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

IN = "reports/novai-model-configs.json"
OUT = "reports/2026-10-16-novai-configs-por-modelo.md"


def _fam(slug: str) -> str:
    import re

    m = re.match(r"([a-z]+(?:-[a-z]+)?)", slug)
    return m.group(1) if m else slug


def build(pages: list[dict]) -> str:
    ok = [p for p in pages if p.get("ok")]
    lines: list[str] = []
    a = lines.append

    a("# NovAI — Configurações por modelo (scrape das páginas \"Try\")")
    a("")
    a(f"Fonte: `https://aiapi-pro.com/models/<slug>.html` (links \"Try\" do "
      f"`docs/novai-model-marketplace.html`).")
    a(f"Modelos: **{len(ok)}/{len(pages)}** baixados com sucesso.")
    a("")
    a("Cada página de modelo expõe, quando disponível:")
    a("")
    a("- **Preço** (input/output por 1M tokens) — formato `price-cell` (chat) ou "
      "`spec-item` \"Token Price\" (vídeo/imagem/3D).")
    a("- **Specs técnicas** — tabela `Technical specifications` (chat) ou card "
      "`Specifications & Pricing` (vídeo/imagem/3D).")
    a("- **Exemplos de código** — blocos `<pre><code>` (chat) ou "
      "`<div class=\"code-block\">` (vídeo/imagem/3D), com o `model` ID e os "
      "parâmetros de uso sugeridos pela NovAI.")
    a("- **Casos de uso** — seção `Best use cases`.")
    a("")
    a("> Observação: as páginas **não** trazem um bloco formal de \"configuração "
      "sugerida\" (temperature/top_p/etc.). Os parâmetros aparecem apenas dentro "
      "dos exemplos de código, quando a NovAI os inclui.")
    a("")

    # resumo de cobertura
    a("## Cobertura da extração")
    a("")
    a("| Campo | Modelos com dado |")
    a("|---|---|")
    a(f"| Preço (input) | {sum(1 for p in ok if p.get('price_input'))} |")
    a(f"| Preço (output) | {sum(1 for p in ok if p.get('price_output'))} |")
    a(f"| Descrição/subtítulo | {sum(1 for p in ok if p.get('subtitle'))} |")
    a(f"| Vendor | {sum(1 for p in ok if p.get('vendor'))} |")
    a(f"| Specs técnicas | {sum(1 for p in ok if p.get('specs'))} |")
    a(f"| Casos de uso | {sum(1 for p in ok if p.get('use_cases'))} |")
    a(f"| Blocos de código | {sum(1 for p in ok if p.get('code_blocks'))} |")
    a(f"| Parâmetros em exemplos | {sum(1 for p in ok if p.get('params'))} |")
    a("")

    # agrupa por família
    fams: dict[str, list[dict]] = defaultdict(list)
    for p in ok:
        fams[_fam(p["slug"])].append(p)

    a("## Modelos por família")
    a("")
    for fam in sorted(fams, key=lambda k: (-len(fams[k]), k)):
        models = sorted(fams[fam], key=lambda p: p["slug"])
        a(f"### {fam} ({len(models)})")
        a("")
        for p in models:
            title = p.get("title") or p["slug"]
            price = ""
            if p.get("price_input") or p.get("price_output"):
                price = f" — in {p.get('price_input') or '?'} / out {p.get('price_output') or '?'}"
            a(f"- **`{p['slug']}`**{price}")
            if p.get("subtitle"):
                a(f"  - {p['subtitle']}")
            if p.get("specs"):
                specs = "; ".join(f"{k}: {v}" for k, v in list(p["specs"].items())[:6])
                a(f"  - Specs: {specs}")
            if p.get("params"):
                params = ", ".join(f"{k}={v}" for k, v in p["params"].items())
                a(f"  - Parâmetros (exemplos): {params}")
            if p.get("use_cases"):
                a(f"  - Casos de uso: {', '.join(p['use_cases'][:5])}")
        a("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    src = Path(IN)
    if not src.exists():
        print(f"faltando {IN}; rode eval.novai_scrape_models --live primeiro", file=sys.stderr)
        return 1
    pages = json.loads(src.read_text(encoding="utf-8"))
    md = build(pages)
    Path(OUT).write_text(md, encoding="utf-8")
    print(f"salvo: {OUT} ({len(md)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
