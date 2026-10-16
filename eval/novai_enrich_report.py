"""Gera relatório Markdown do catálogo NovAI enriquecido.

Lê `reports/novai-enriched.json` (saída de eval.novai_enrich) e produz
`reports/2026-10-16-novai-enriquecido.md`.

Uso:
    python -m eval.novai_enrich_report
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

IN = "reports/novai-enriched.json"
OUT = "reports/2026-10-16-novai-enriquecido.md"


def _fmt(v) -> str:
    return "—" if v in (None, "", []) else str(v)


def build(models: list[dict]) -> str:
    lines: list[str] = []
    a = lines.append

    n = len(models)
    n_owned = sum(1 for m in models if m.get("owned_by"))
    n_type = sum(1 for m in models if m.get("type"))
    n_mod = sum(1 for m in models if m.get("modalities"))
    n_page = sum(1 for m in models if m.get("has_page"))
    n_ld = sum(1 for m in models if m.get("ld_price"))
    n_cmd = sum(len(m.get("code_commands") or []) for m in models)

    a("# NovAI — Catálogo enriquecido (todas as fontes cruzadas)")
    a("")
    a("Fonte: `eval.novai_enrich` — cruza 5 fontes por modelo:")
    a("")
    a("1. **`GET /models` do gateway direto** (`https://aiapi-pro.com`) — "
      "metadados reais: `owned_by` (provedor), `pricing`, `type`. O proxy "
      "LiteLLM mascara tudo como `owned_by: openai`, por isso usamos o upstream.")
    a("2. **Listas autoritativas por modalidade** — cada endpoint revela, no "
      "erro 400 (`Available: ...`), a lista de modelos daquela modalidade.")
    a("3. **JSON-LD schema.org** das páginas `/models/<slug>.html` — `brand`, "
      "`price`, `priceCurrency`, `availability`, `priceValidUntil`, "
      "`description`.")
    a("4. **Modelos fantasma** — páginas/listas que existem mas não aparecem no "
      "`/models`.")
    a("5. **Comandos da tag code** — exemplos cURL/Python/Node extraídos de cada "
      "página.")
    a("")
    a("## Cobertura")
    a("")
    a("| Fonte | Modelos com dado |")
    a("|---|---|")
    a(f"| Total de modelos | {n} |")
    a(f"| `owned_by` (gateway `/models`) | {n_owned} |")
    a(f"| `type` (gateway `/models`) | {n_type} |")
    a(f"| Modalidade (via erro 400) | {n_mod} |")
    a(f"| Página HTML baixada | {n_page} |")
    a(f"| JSON-LD com preço | {n_ld} |")
    a(f"| Comandos de código extraídos | {n_cmd} |")
    a("")

    # provedores
    a("## Provedores (`owned_by`)")
    a("")
    a("| Provedor | Modelos |")
    a("|---|---|")
    for prov, cnt in Counter(m.get("owned_by") for m in models).most_common():
        a(f"| {_fmt(prov)} | {cnt} |")
    a("")

    # tipos
    a("## Tipos (`type` do gateway)")
    a("")
    a("| Tipo | Modelos |")
    a("|---|---|")
    for t, cnt in Counter(m.get("type") for m in models).most_common():
        a(f"| {_fmt(t)} | {cnt} |")
    a("")

    # modalidades
    a("## Modalidades (via lista `Available:` do erro 400)")
    a("")
    a("| Modalidade | Modelos |")
    a("|---|---|")
    for mod, cnt in Counter(
            x for m in models for x in (m.get("modalities") or [])).most_common():
        a(f"| {mod} | {cnt} |")
    a("")

    # fantasmas
    ghosts = [m for m in models if not m.get("owned_by")]
    a("## Modelos fantasma (fora do `/models`)")
    a("")
    if ghosts:
        a("| ID | Modalidade | Tem página |")
        a("|---|---|---|")
        for m in ghosts:
            mods = ", ".join(m.get("modalities") or []) or "—"
            a(f"| `{m['id']}` | {mods} | {'sim' if m.get('has_page') else 'não'} |")
    else:
        a("_Nenhum._")
    a("")

    # tabela completa
    a("## Tabela completa por modelo")
    a("")
    a("| ID | Provedor | Tipo | Modalidade | Marca | Preço | Moeda | "
      "Disponível | Válido até | Comandos |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for m in sorted(models, key=lambda x: x["id"]):
        mods = ", ".join(m.get("modalities") or []) or "—"
        cmds = len(m.get("code_commands") or [])
        a(f"| `{m['id']}` | {_fmt(m.get('owned_by'))} | {_fmt(m.get('type'))} | "
          f"{mods} | {_fmt(m.get('brand'))} | {_fmt(m.get('ld_price'))} | "
          f"{_fmt(m.get('ld_currency'))} | {_fmt(m.get('availability'))} | "
          f"{_fmt(m.get('price_valid_until'))} | {cmds} |")
    a("")

    # comandos por tipo
    a("## Comandos de código por linguagem")
    a("")
    a("| Tipo | Total |")
    a("|---|---|")
    for k, cnt in Counter(
            c.get("kind") for m in models
            for c in (m.get("code_commands") or [])).most_common():
        a(f"| {k} | {cnt} |")
    a("")

    # resultados dos testes de código (--test-code)
    tests = [t for m in models for t in (m.get("code_tests") or [])]
    if tests:
        n_models_tested = sum(1 for m in models if m.get("code_tests"))
        n_ok = sum(1 for t in tests if t.get("ok"))
        n_fail = len(tests) - n_ok
        a("## Testes de execução dos comandos (`--test-code`)")
        a("")
        a(f"- Modelos com testes: **{n_models_tested}**")
        a(f"- Comandos executados: **{len(tests)}** "
          f"(ok: {n_ok}, falha: {n_fail})")
        a("")
        a("| Motivo | Total |")
        a("|---|---|")
        reasons = Counter(
            (t.get("reason") or "sem motivo") for t in tests if not t.get("ok"))
        for r, cnt in reasons.most_common():
            a(f"| {r} | {cnt} |")
        a("")
        a("> Nota: apenas comandos `curl` são executados (segurança); "
          "exemplos Python/Node são extraídos mas não rodados. `ok` reflete "
          "apenas o exit code do `curl` — erros de upstream (ex.: 429) ainda "
          "retornam `ok: true` com o erro no `stdout`.")
        a("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    src = Path(IN)
    if not src.exists():
        print(f"faltando {IN}; rode eval.novai_enrich --live primeiro",
              file=sys.stderr)
        return 2
    models = json.loads(src.read_text(encoding="utf-8"))
    md = build(models)
    Path(OUT).write_text(md, encoding="utf-8")
    print(f"salvo: {OUT} ({len(md)} bytes, {len(models)} modelos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
