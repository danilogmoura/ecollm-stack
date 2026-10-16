"""Testes offline do enriquecedor do catálogo NovAI."""
from __future__ import annotations

import json

from eval.novai_enrich import (
    EnrichedModel,
    enrich,
    fetch_gateway_models,
    fetch_modality_lists,
    gateway_config,
    make_site_getter,
    parse_available,
    parse_code_commands,
    parse_jsonld,
    parse_page_enrich,
    redact_signed_urls,
    run_code_command,
)


class FakeResp:
    def __init__(self, status, payload=None, text=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else (
            json.dumps(payload) if payload is not None else "")

    def json(self):
        return self._payload


def _getter(routes):
    def _get(path, **kwargs):
        return routes.get(path, FakeResp(404, text="not found"))
    return _get


def _poster(routes):
    def _post(path, json_body=None, **kwargs):
        return routes.get(path, FakeResp(404, text="not found"))
    return _post


# ---------------------------------------------------------------------------
# parse_available
# ---------------------------------------------------------------------------


def test_parse_available_extracts_list():
    text = '{"detail":"Model not found. Available: a, b, c"}'
    assert parse_available(text) == ["a", "b", "c"]


def test_parse_available_empty_when_absent():
    assert parse_available('{"detail":"nope"}') == []


def test_parse_available_strips_trailing_quote():
    text = '{"detail":"Available: glm-5, glm-5.1"}'
    assert parse_available(text) == ["glm-5", "glm-5.1"]


# ---------------------------------------------------------------------------
# parse_jsonld
# ---------------------------------------------------------------------------


JSONLD_HTML = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Product","name":"GLM-5","description":"Zhipu flagship",
  "brand":{"@type":"Brand","name":"Zhipu AI"},
  "offers":{"@type":"Offer","price":"0.67","priceCurrency":"USD",
   "availability":"https://schema.org/InStock","priceValidUntil":"2026-12-31"}},
 {"@type":"BreadcrumbList"}]}
</script></head><body></body></html>"""


def test_parse_jsonld_extracts_product_fields():
    ld = parse_jsonld(JSONLD_HTML)
    assert ld["brand"] == "Zhipu AI"
    assert ld["price"] == "0.67"
    assert ld["currency"] == "USD"
    assert ld["availability"] == "InStock"
    assert ld["price_valid_until"] == "2026-12-31"
    assert ld["description"] == "Zhipu flagship"


def test_parse_jsonld_empty_when_absent():
    assert parse_jsonld("<html></html>") == {}


def test_parse_jsonld_handles_bad_json():
    html = '<script type="application/ld+json">{not json}</script>'
    assert parse_jsonld(html) == {}


# ---------------------------------------------------------------------------
# parse_code_commands
# ---------------------------------------------------------------------------


CODE_HTML = """<h3>cURL</h3>
<pre><code>curl https://aiapi-pro.com/v1/chat/completions \\
  -H "Authorization: Bearer $KEY"</code></pre>
<h3>Python</h3>
<pre><code>import requests
r = requests.post("https://aiapi-pro.com/v1/chat/completions")</code></pre>
<h3>Node.js</h3>
<pre><code>fetch("https://aiapi-pro.com/v1/chat/completions")</code></pre>"""


def test_parse_code_commands_classifies_kinds():
    cmds = parse_code_commands(CODE_HTML)
    kinds = [c["kind"] for c in cmds]
    assert kinds == ["curl", "python", "node"]
    assert cmds[0]["lang"] == "cURL"
    assert "curl" in cmds[0]["code"]


def test_parse_code_commands_empty():
    assert parse_code_commands("<html></html>") == []


# ---------------------------------------------------------------------------
# parse_page_enrich
# ---------------------------------------------------------------------------


def test_parse_page_enrich_combines_sources():
    html = JSONLD_HTML + CODE_HTML
    info = parse_page_enrich("glm-5", html)
    assert info["slug"] == "glm-5"
    assert info["brand"] == "Zhipu AI"
    assert info["ld_price"] == "0.67"
    assert len(info["code_commands"]) == 3


# ---------------------------------------------------------------------------
# fetch_gateway_models / fetch_modality_lists
# ---------------------------------------------------------------------------


def test_fetch_gateway_models_returns_data():
    g = _getter({"/models": FakeResp(200, {"data": [
        {"id": "glm-5", "owned_by": "zhipu"}]})})
    data = fetch_gateway_models(g)
    assert data[0]["id"] == "glm-5"


def test_fetch_gateway_models_raises_on_error():
    g = _getter({"/models": FakeResp(500, text="boom")})
    try:
        fetch_gateway_models(g)
        assert False, "deveria levantar"
    except RuntimeError as exc:
        assert "500" in str(exc)


def test_fetch_modality_lists_captures_available():
    p = _poster({
        "/chat/completions": FakeResp(400, text='{"detail":"Available: glm-5, glm-5.1"}'),
        "/images/generations": FakeResp(400, text='{"detail":"Available: qwen-image"}'),
    })
    lists = fetch_modality_lists(p)
    assert lists["chat"] == ["glm-5", "glm-5.1"]
    assert lists["image"] == ["qwen-image"]
    assert lists["embedding"] == []  # 404 default


# ---------------------------------------------------------------------------
# run_code_command
# ---------------------------------------------------------------------------


def test_run_code_command_skips_non_curl():
    r = run_code_command({"kind": "python", "code": "print(1)"})
    assert r["executed"] is False
    assert "cURL" in r["reason"]


def test_run_code_command_runs_curl_echo():
    r = run_code_command({"kind": "curl", "code": "curl --version"})
    assert r["executed"] is True
    assert r["ok"] is True


def test_run_code_command_handles_bad_parse():
    r = run_code_command({"kind": "curl", "code": 'curl "unclosed'})
    assert r["executed"] is False


def test_run_code_command_blocks_output_flag():
    r = run_code_command({"kind": "curl", "code": "curl -o /tmp/x https://a.com"})
    assert r["executed"] is False
    assert "perigosa" in r["reason"]


def test_run_code_command_blocks_upload():
    r = run_code_command({"kind": "curl", "code": "curl --data @/etc/passwd https://a.com"})
    assert r["executed"] is False
    assert "upload" in r["reason"]


def test_run_code_command_substitutes_key_placeholder():
    # usa um comando inofensivo que ecoa a chave via --version não serve;
    # testa a sanitização diretamente via _sanitize_curl_args
    from eval.novai_enrich import _sanitize_curl_args
    args, blocked = _sanitize_curl_args(
        ["curl", "-H", "Authorization: Bearer $KEY", "https://a.com"], "nvai-secret")
    assert blocked is None
    assert "nvai-secret" in args[2]
    assert "$KEY" not in args[2]


# ---------------------------------------------------------------------------
# enrich (orquestração)
# ---------------------------------------------------------------------------


def test_enrich_merges_all_sources():
    g = _getter({
        "/models": FakeResp(200, {"data": [
            {"id": "glm-5", "owned_by": "zhipu", "pricing": "paid"},
            {"id": "qwen-image", "owned_by": "alibaba", "type": "image"},
        ]}),
        "/models/glm-5.html": FakeResp(200, text=JSONLD_HTML + CODE_HTML),
        "/models/qwen-image.html": FakeResp(200, text="<html></html>"),
    })
    p = _poster({
        "/chat/completions": FakeResp(400, text='{"detail":"Available: glm-5"}'),
        "/images/generations": FakeResp(400, text='{"detail":"Available: qwen-image"}'),
    })
    models = enrich(g, p)
    by_id = {m.id: m for m in models}
    assert by_id["glm-5"].owned_by == "zhipu"
    assert by_id["glm-5"].brand == "Zhipu AI"
    assert by_id["glm-5"].modalities == ["chat"]
    assert by_id["qwen-image"].modalities == ["image"]
    assert by_id["qwen-image"].type == "image"
    assert by_id["glm-5"].has_page is True


def test_enrich_includes_ghost_models_from_modality_lists():
    g = _getter({
        "/models": FakeResp(200, {"data": [{"id": "glm-5"}]}),
        "/models/glm-5.html": FakeResp(200, text="<html></html>"),
        "/models/doubao-seedream-4.0.html": FakeResp(200, text="<html></html>"),
    })
    p = _poster({
        "/images/generations": FakeResp(
            400, text='{"detail":"Available: doubao-seedream-4.0"}'),
    })
    models = enrich(g, p)
    ids = {m.id for m in models}
    assert "doubao-seedream-4.0" in ids


def test_enrich_includes_slugs_param():
    g = _getter({
        "/models": FakeResp(200, {"data": [{"id": "glm-5"}]}),
        "/models/glm-5.html": FakeResp(200, text="<html></html>"),
        "/models/doubao-seedream-4.5.html": FakeResp(200, text=JSONLD_HTML),
    })
    p = _poster({})
    models = enrich(g, p, slugs=["doubao-seedream-4.5"])
    by_id = {m.id: m for m in models}
    assert "doubao-seedream-4.5" in by_id
    assert by_id["doubao-seedream-4.5"].brand == "Zhipu AI"


def test_enrich_progress_callback():
    g = _getter({"/models": FakeResp(200, {"data": [{"id": "a"}, {"id": "b"}]}),
                 "/models/a.html": FakeResp(200, text="<html></html>"),
                 "/models/b.html": FakeResp(200, text="<html></html>")})
    p = _poster({})
    seen = []
    enrich(g, p, progress=lambda i, n, mid: seen.append(mid))
    assert len(seen) == 2


def test_enrich_uses_page_cache_offline():
    g = _getter({"/models": FakeResp(200, {"data": [{"id": "glm-5"}]})})
    p = _poster({})
    models = enrich(g, p, pages={"glm-5": JSONLD_HTML})
    assert models[0].brand == "Zhipu AI"
    assert models[0].has_page is True


def test_enriched_model_defaults():
    m = EnrichedModel(id="x")
    assert m.modalities == []
    assert m.code_commands == []
    assert m.has_page is False


# ---------------------------------------------------------------------------
# gateway_config / make_site_getter
# ---------------------------------------------------------------------------


def test_gateway_config_defaults_to_aiapi(monkeypatch):
    # load_dotenv() recarrega o .env, então não dá para zerar a chave; validamos
    # apenas o default do base_url e que a chave é lida do ambiente.
    monkeypatch.delenv("NOVAI_BASE_URL", raising=False)
    cfg = gateway_config()
    assert cfg["base_url"] == "https://aiapi-pro.com/v1"
    assert isinstance(cfg["api_key"], str)


def test_gateway_config_reads_env(monkeypatch):
    monkeypatch.setenv("NOVAI_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("NOVAI_API_KEY", "nvai-abc")
    cfg = gateway_config()
    assert cfg["base_url"] == "https://example.test/v1"  # rstrip "/"
    assert cfg["api_key"] == "nvai-abc"


def test_make_site_getter_strips_v1(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200
        text = "ok"

    def _fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        return _Resp()

    import requests
    monkeypatch.setattr(requests, "get", _fake_get)
    g = make_site_getter({"base_url": "https://aiapi-pro.com/v1",
                          "api_key": "nvai-x"})
    g("/models/glm-5.html")
    assert seen["url"] == "https://aiapi-pro.com/models/glm-5.html"


def test_make_site_getter_keeps_root_without_v1(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200
        text = "ok"

    def _fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        return _Resp()

    import requests
    monkeypatch.setattr(requests, "get", _fake_get)
    g = make_site_getter({"base_url": "https://aiapi-pro.com",
                          "api_key": "nvai-x"})
    g("/models/glm-5.html")
    assert seen["url"] == "https://aiapi-pro.com/models/glm-5.html"


# ---------------------------------------------------------------------------
# S106: redação de URLs pré-assinadas (reports/ passou a ser público)
# ---------------------------------------------------------------------------

def test_redact_ucloud_signed_url():
    out, n = redact_signed_urls(
        "https://maas.ufileos.com/a.png?UCloudPublicKey=TOKEN_x"
        "&Signature=abc%2Fdef&Expires=1792742192")
    assert n == 1
    assert "Signature=" not in out and "UCloudPublicKey=" not in out
    assert out == "https://maas.ufileos.com/a.png?__REDACTED_SIGNED_URL__"


def test_redact_volcano_and_aliyun_signed_urls():
    out, n = redact_signed_urls(
        "https://ark.volces.com/x.jpeg?Algorithm=HMAC-SHA256"
        "&Credential=AKIA1234567890&Signature=zzz&SignedHeaders=host "
        "https://oss.aliyuncs.com/y.png?OSSAccessKeyId=LTAI5tABC&Signature=q%2Bw%3D")
    assert n == 2
    assert "Credential=AKIA" not in out and "OSSAccessKeyId=" not in out


def test_redact_tencent_cos_signed_url():
    # Variante Tencent COS (q-sign-algorithm/q-ak=AKID.../q-signature) — a que
    # o GitHub Secret Scanning sinaliza como credencial real. S106. Valor AKID
    # é fake (não é SecretId real) — o teste exercita só o padrão do regex.
    out, n = redact_signed_urls(
        "https://130852.cos.ap-guangzhou.myqcloud.com/1409238524/img_0.png"
        "?q-sign-algorithm=sha1&q-ak=AKIDEXAMPLEfakeFAKEexample000000000000"
        "&q-sign-time=1792137784;1792180994&q-key-time=1792137784;1792180994"
        "&q-header-list=host&q-url-param-list=&q-signature=1a2b3c4d5e6f")
    assert n == 1
    assert "q-ak=AKID" not in out and "q-signature=" not in out
    assert "AKIDEXAMPLEfake" not in out
    assert out == "https://130852.cos.ap-guangzhou.myqcloud.com/1409238524/img_0.png?__REDACTED_SIGNED_URL__"


def test_redact_leaves_plain_urls_untouched():
    for u in ("https://api.example.com/v1/chat/completions",
              "https://aiapi-pro.com/models/doubao?tab=pricing"):
        out, n = redact_signed_urls(u)
        assert n == 0 and out == u


def test_redact_respects_csv_delimiter():
    out, n = redact_signed_urls(
        "a,b,https://z.oss.com/i.png?OSSAccessKeyId=K&Signature=Q,c,d")
    assert n == 1
    assert "Signature=Q" not in out
    assert out.endswith(",c,d")  # campos vizinhos não fundidos


def test_redact_inside_escaped_stdout():
    payload = json.dumps({"stdout": "url "
        "https://x.ufileos.com/i.png?UCloudPublicKey=T&Signature=S"})
    out, n = redact_signed_urls(payload)
    assert n == 1 and "Signature=S" not in out
    assert json.loads(out)["stdout"].startswith("url ")  # JSON segue válido
