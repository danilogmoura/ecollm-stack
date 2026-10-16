"""Testes offline do scraper de páginas de modelo do NovAI.

Cobrem os dois formatos de página:
  - chat: <pre><code> + <code> inline + tabela 'Technical specifications'
  - vídeo/imagem/3D: <div class="code-block"> + <div class="spec-item">

Nenhum teste toca a rede: o transporte é injetado.
"""
from __future__ import annotations

from eval.novai_scrape_models import (
    ModelPage,
    parse_page,
    scrape,
    _parse_code_blocks,
    _parse_specs,
    _parse_use_cases,
    _parse_overview,
    _strip_tags,
)

# --- amostras de HTML -------------------------------------------------------

CHAT_HTML = """<!DOCTYPE html><html><head>
<title>DeepSeek-V4-Pro - NovAI API</title></head><body>
<div class="container">
<h1>DeepSeek-V4-Pro</h1>
<div><span class="tag">DeepSeek</span>
<span class="badge badge-green">Flagship</span></div>
<div class="price-box">
  <div class="price-row"><span class="price-label">Input</span><span class="price-value">$0.55</span></div>
  <div class="price-row"><span class="price-label">Output</span><span class="price-value">$2.19</span></div>
</div>
<h2>Model overview</h2>
<p>DeepSeek-V4-Pro is the flagship release of DeepSeek AI.</p>
<h2>Technical specifications</h2>
<table>
<tr><th>Property</th><th>Value</th></tr>
<tr><td>Context window (input)</td><td>131,072 tokens (128K)</td></tr>
<tr><td>Max output tokens</td><td>8,192</td></tr>
<tr><td>Streaming</td><td>Server-Sent Events</td></tr>
</table>
<h2>Best use cases</h2>
<ul><li>Coding assistant</li><li>Structured reasoning</li></ul>
<h2>Quick start</h2>
<h3>cURL</h3>
<pre><code>curl https://aiapi-pro.com/v1/chat/completions -d '{
    "model": "deepseek-v4-pro",
    "temperature": 0.2,
    "max_tokens": 800
  }'</code></pre>
<h3>Python (OpenAI SDK)</h3>
<pre><code>from openai import OpenAI
client = OpenAI(base_url="https://aiapi-pro.com/v1")
resp = client.chat.completions.create(model="deepseek-v4-pro")</code></pre>
</div></body></html>"""

VIDEO_HTML = """<!DOCTYPE html><html><head>
<title>Kling V3 - NovAI API</title></head><body>
<div class="container">
<h1>Kling V3</h1>
<div><span class="tag">Kuaishou (Kling)</span></div>
<div class="card"><h2>Specifications &amp; Pricing</h2>
<div class="spec-grid">
<div class="spec-item"><div class="spec-label">Token Price</div><div class="spec-value">$1.54 / 1M</div></div>
<div class="spec-item"><div class="spec-label">Specs</div><div class="spec-value">5-10s | 768P/1080P | T2V</div></div>
</div></div>
<div class="card"><h2>Quick start</h2>
<h3 style="font-size:1rem">Submit video generation task</h3>
<div class="code-block">curl -X POST https://aiapi-pro.com/v1/video/generations \\
  -d '{"model": "kling-video-v3", "duration": 5, "resolution": "768P"}'</div>
</div></div></body></html>"""


# --- helpers ----------------------------------------------------------------

def test_strip_tags_collapses_whitespace():
    assert _strip_tags("<b>a</b>\n  <i>b</i>") == "a b"


def test_parse_specs_table_format():
    specs = _parse_specs(CHAT_HTML)
    assert specs["Context window (input)"] == "131,072 tokens (128K)"
    assert specs["Max output tokens"] == "8,192"
    assert "Property" not in specs  # cabeçalho ignorado


def test_parse_specs_spec_item_format():
    specs = _parse_specs(VIDEO_HTML)
    assert specs["Token Price"] == "$1.54 / 1M"
    assert specs["Specs"] == "5-10s | 768P/1080P | T2V"


def test_parse_code_blocks_pre_code():
    blocks = _parse_code_blocks(CHAT_HTML)
    assert len(blocks) == 2
    assert blocks[0]["lang"] == "cURL"
    assert "deepseek-v4-pro" in blocks[0]["code"]
    assert blocks[1]["lang"] == "Python (OpenAI SDK)"


def test_parse_code_blocks_div_code_block():
    blocks = _parse_code_blocks(VIDEO_HTML)
    assert len(blocks) == 1
    assert blocks[0]["lang"] == "Submit video generation task"
    assert "kling-video-v3" in blocks[0]["code"]


def test_parse_use_cases_list():
    assert _parse_use_cases(CHAT_HTML) == ["Coding assistant", "Structured reasoning"]


def test_parse_overview():
    ov = _parse_overview(CHAT_HTML)
    assert ov is not None and "flagship release" in ov


# --- parse_page -------------------------------------------------------------

def test_parse_page_chat_full():
    p = parse_page("deepseek-v4-pro", CHAT_HTML, 200)
    assert p.ok
    assert p.title == "DeepSeek-V4-Pro"
    assert p.vendor == "DeepSeek"
    assert p.badges == ["Flagship"]
    assert p.price_input == "$0.55"
    assert p.price_output == "$2.19"
    assert p.params["temperature"] == "0.2"
    assert p.params["max_tokens"] == "800"
    assert p.specs["Max output tokens"] == "8,192"
    assert p.use_cases == ["Coding assistant", "Structured reasoning"]
    assert len(p.code_blocks) == 2


def test_parse_page_video_full():
    p = parse_page("kling-video-v3", VIDEO_HTML, 200)
    assert p.ok
    assert p.title == "Kling V3"
    assert p.vendor == "Kuaishou (Kling)"
    assert p.specs["Token Price"] == "$1.54 / 1M"
    assert p.params["duration"] == "5"
    assert p.params["resolution"] == "768P"
    assert len(p.code_blocks) == 1


def test_parse_page_no_price_no_crash():
    p = parse_page("x", "<html><body><h1>X</h1></body></html>", 200)
    assert p.ok
    assert p.price_input is None
    assert p.code_blocks == []


def test_price_cell_ignores_context_and_max_output():
    """price-cell com 4 células: Input/Output por 1M + Context window + Max output.

    Só as duas primeiras são preço; 'Max output' (16K) não pode virar price_output.
    """
    html = (
        '<html><body><h1>M</h1><div class="price-grid">'
        '<div class="price-cell"><div class="num">FREE</div>'
        '<div class="label">Input / 1M tokens</div></div>'
        '<div class="price-cell"><div class="num">FREE</div>'
        '<div class="label">Output / 1M tokens</div></div>'
        '<div class="price-cell"><div class="num">202K</div>'
        '<div class="label">Context window</div></div>'
        '<div class="price-cell"><div class="num">16K</div>'
        '<div class="label">Max output</div></div>'
        '</div></body></html>'
    )
    p = parse_page("m", html, 200)
    assert p.price_input == "FREE"
    assert p.price_output == "FREE"


# --- scrape (transporte injetado) -------------------------------------------

def test_scrape_uses_injected_fetcher():
    pages = {"a": (200, CHAT_HTML), "b": (200, VIDEO_HTML)}
    out = scrape(["a", "b"], lambda slug: pages[slug])
    assert [p.slug for p in out] == ["a", "b"]
    assert all(p.ok for p in out)


def test_scrape_marks_http_error():
    out = scrape(["x"], lambda slug: (404, "not found"))
    assert len(out) == 1
    assert not out[0].ok
    assert out[0].error == "HTTP 404"


def test_scrape_captures_exception():
    def boom(slug):
        raise RuntimeError("network down")

    out = scrape(["x"], boom)
    assert not out[0].ok
    assert "network down" in out[0].error


def test_scrape_progress_callback():
    seen = []
    scrape(["a"], lambda s: (200, CHAT_HTML), progress=lambda i, n, p: seen.append((i, n, p.slug)))
    assert seen == [(1, 1, "a")]


def test_model_page_defaults():
    p = ModelPage(slug="s", url="u")
    assert p.ok is False
    assert p.params == {} and p.specs == {} and p.code_blocks == []
