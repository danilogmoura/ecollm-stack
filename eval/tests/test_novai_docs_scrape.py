"""Testes offline do scraper de documentação do NovAI."""
from __future__ import annotations

from eval.novai_docs_scrape import (
    DocsPage,
    _parse_alerts,
    _parse_code_blocks,
    _parse_table,
    _split_sections,
    _strip_tags,
    parse_docs,
    scrape,
)

DOCS_HTML = """<!DOCTYPE html><html><head>
<title>NovAI API Documentation - OpenAI-Compatible China AI API</title></head><body>
<main>
<h1>API Documentation</h1>
<h2 id="authentication">Authentication</h2>
<p>All API requests require an API key passed via the <span class="inline-code">Authorization</span> header:</p>
<pre><code>Authorization: Bearer nvai-your-api-key-here</code></pre>
<h2 id="chat-completions">Chat Completions</h2>
<p><span class="method method-post">POST</span> <span class="endpoint">/v1/chat/completions</span></p>
<p>Creates a model response for the given conversation.</p>
<h3>Request Body</h3>
<table>
<thead><tr><th>Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
<tbody>
<tr><td><span class="inline-code">model</span></td><td>string</td><td><span class="param-required">Required</span></td><td>Model ID to use</td></tr>
<tr><td><span class="inline-code">temperature</span></td><td>float</td><td><span class="param-optional">Optional</span></td><td>Sampling temperature (0-2). Default: 1.0</td></tr>
</tbody>
</table>
<div class="alert alert-success"><strong>Free model available!</strong> Start building now.</div>
<h3>Example Request</h3>
<pre><code>curl https://aiapi-pro.com/v1/chat/completions -d '{"model":"glm-5"}'</code></pre>
</main></body></html>"""


def test_strip_tags_unescapes_and_collapses():
    assert _strip_tags("<b>a</b>  &amp;  b") == "a & b"


def test_split_sections_levels_and_anchors():
    secs = _split_sections(DOCS_HTML)
    titles = [(lvl, t, a) for lvl, t, a, _ in secs]
    assert (2, "Authentication", "authentication") in titles
    assert (2, "Chat Completions", "chat-completions") in titles
    assert (3, "Request Body", None) in titles


def test_parse_table_headers_and_rows():
    t = _parse_table(
        "<table><thead><tr><th>Parameter</th><th>Type</th></tr></thead>"
        "<tbody><tr><td>model</td><td>string</td></tr></tbody></table>"
    )
    assert t["headers"] == ["Parameter", "Type"]
    assert t["rows"] == [["model", "string"]]


def test_parse_code_blocks_pre_code():
    blocks = _parse_code_blocks(DOCS_HTML)
    assert len(blocks) == 2
    assert "Authorization: Bearer" in blocks[0]["code"]
    assert "chat/completions" in blocks[1]["code"]


def test_parse_alerts():
    alerts = _parse_alerts(DOCS_HTML)
    assert len(alerts) == 1
    assert "Free model available!" in alerts[0]


def test_parse_docs_full():
    p = parse_docs(DOCS_HTML, 200)
    assert p.ok
    assert p.title == "NovAI API Documentation - OpenAI-Compatible China AI API"
    assert len(p.sections) == 4
    chat = next(s for s in p.sections if s.title == "Chat Completions")
    assert chat.method == "POST"
    assert chat.endpoint == "/v1/chat/completions"
    assert "Creates a model response" in chat.text
    body = next(s for s in p.sections if s.title == "Request Body")
    assert body.tables[0]["headers"] == ["Parameter", "Type", "Required", "Description"]
    assert body.tables[0]["rows"][0][0] == "model"
    assert body.alerts and "Free model available!" in body.alerts[0]


def test_parse_docs_empty_is_not_ok():
    p = parse_docs("<html><body><p>nada</p></body></html>", 200)
    assert not p.ok
    assert p.sections == []


def test_scrape_uses_injected_fetcher():
    p = scrape(lambda url: (200, DOCS_HTML))
    assert p.ok
    assert p.http_status == 200
    assert len(p.sections) == 4


def test_scrape_marks_http_error():
    p = scrape(lambda url: (503, ""))
    assert not p.ok
    assert p.http_status == 503
    assert "503" in p.error


def test_scrape_captures_exception():
    def boom(url):
        raise RuntimeError("sem rede")

    p = scrape(boom)
    assert not p.ok
    assert "RuntimeError" in p.error


def test_docs_page_defaults():
    p = DocsPage()
    assert p.url == "https://aiapi-pro.com/docs"
    assert p.ok is False
    assert p.sections == []
