"""Scrape da documentação do NovAI (https://aiapi-pro.com/docs).

Extrai a estrutura da página de docs: seções (h2/h3), endpoints, tabelas de
parâmetros, blocos de código e alertas. Produz JSON consumível por
`eval.novai_docs_report`.

Padrão do repo: parse PURO + transporte INJETÁVEL (fetcher) para testes offline.
Rede só com `--live`.

Uso:
    python -m eval.novai_docs_scrape --live
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DOCS_URL = "https://aiapi-pro.com/docs"
OUT_DEFAULT = "reports/novai-docs.json"


def _strip_tags(s: str) -> str:
    """Remove tags, desescapa entidades e colapsa espaços."""
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class DocSection:
    """Uma seção da documentação (h2 ou h3)."""

    level: int = 2
    title: str = ""
    anchor: str | None = None
    text: str = ""
    endpoint: str | None = None
    method: str | None = None
    tables: list[dict] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


@dataclass
class DocsPage:
    url: str = DOCS_URL
    ok: bool = False
    http_status: int | None = None
    error: str | None = None
    title: str | None = None
    sections: list[DocSection] = field(default_factory=list)
    bytes: int = 0


def _parse_table(table_html: str) -> dict:
    """Converte um <table> em {headers: [...], rows: [[...], ...]}."""
    headers: list[str] = []
    thead = re.search(r"<thead>(.*?)</thead>", table_html, re.S)
    if thead:
        headers = [_strip_tags(th) for th in re.findall(r"<th[^>]*>(.*?)</th>", thead.group(1), re.S)]
    rows: list[list[str]] = []
    tbody = re.search(r"<tbody>(.*?)</tbody>", table_html, re.S)
    body = tbody.group(1) if tbody else table_html
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [_strip_tags(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if cells:
            rows.append(cells)
    return {"headers": headers, "rows": rows}


def _parse_code_blocks(html: str) -> list[dict]:
    """Extrai <pre><code>...</code></pre> como {code: ...}."""
    out: list[dict] = []
    for m in re.finditer(r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>", html, re.S):
        code = _html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip("\n")
        if code.strip():
            out.append({"code": code})
    return out


def _parse_alerts(html: str) -> list[str]:
    """Extrai textos de <div class="alert ...">."""
    out: list[str] = []
    for m in re.finditer(r'<div class="alert[^"]*"[^>]*>(.*?)</div>', html, re.S):
        txt = _strip_tags(m.group(1))
        if txt:
            out.append(txt)
    return out


def _split_sections(html: str) -> list[tuple[int, str, str | None, str]]:
    """Divide o HTML em (level, title, anchor, inner_html) por h2/h3.

    Retorna na ordem do documento. O inner_html vai até o próximo h2/h3.
    """
    marks = list(re.finditer(r"<h([23])(?:\s+id=\"([^\"]*)\")?[^>]*>(.*?)</h\1>", html, re.S))
    out: list[tuple[int, str, str | None, str]] = []
    for i, m in enumerate(marks):
        level = int(m.group(1))
        anchor = m.group(2)
        title = _strip_tags(m.group(3))
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(html)
        out.append((level, title, anchor, html[start:end]))
    return out


def parse_docs(html: str, http_status: int | None = None) -> DocsPage:
    """Parse puro da página de docs."""
    p = DocsPage(http_status=http_status, bytes=len(html))
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        p.title = _strip_tags(m.group(1))

    for level, title, anchor, inner in _split_sections(html):
        sec = DocSection(level=level, title=title, anchor=anchor)
        # endpoint + método (ex.: <span class="method method-post">POST</span> <span class="endpoint">/v1/...</span>)
        mm = re.search(r'<span class="method[^"]*">([^<]+)</span>\s*<span class="endpoint">([^<]+)</span>', inner)
        if mm:
            sec.method = _strip_tags(mm.group(1))
            sec.endpoint = _strip_tags(mm.group(2))
        # texto corrido (parágrafos), sem tabelas/código
        paras = re.findall(r"<p[^>]*>(.*?)</p>", inner, re.S)
        sec.text = " ".join(_strip_tags(x) for x in paras if _strip_tags(x))
        sec.tables = [_parse_table(t) for t in re.findall(r"<table[^>]*>.*?</table>", inner, re.S)]
        sec.code_blocks = _parse_code_blocks(inner)
        sec.alerts = _parse_alerts(inner)
        p.sections.append(sec)

    p.ok = bool(p.sections)
    return p


def scrape(fetcher, url: str = DOCS_URL) -> DocsPage:
    """Baixa e faz parse; marca ok=False em erro HTTP/exceção."""
    try:
        status, html = fetcher(url)
    except Exception as exc:  # noqa: BLE001 - transporte injetável
        return DocsPage(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")
    if status != 200:
        return DocsPage(url=url, ok=False, http_status=status, error=f"HTTP {status}")
    return parse_docs(html, http_status=status)


def _http_fetcher(timeout: float = 20.0):
    import requests

    def _f(url: str):
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "ecollm-stack/1.0 (+novai-docs)"})
        return r.status_code, r.text

    return _f


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape da documentação do NovAI")
    ap.add_argument("--url", default=DOCS_URL)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--live", action="store_true", help="faz requisição real")
    args = ap.parse_args(argv)

    if not args.live:
        print("modo offline: use --live para baixar", file=sys.stderr)
        return 2

    page = scrape(_http_fetcher(), args.url)
    if not page.ok:
        print(f"falha: {page.error}", file=sys.stderr)
        return 1

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(asdict(page), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    n_tab = sum(len(s.tables) for s in page.sections)
    n_code = sum(len(s.code_blocks) for s in page.sections)
    print(f"ok: {len(page.sections)} seções, {n_tab} tabelas, {n_code} blocos de código")
    print(f"salvo: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
