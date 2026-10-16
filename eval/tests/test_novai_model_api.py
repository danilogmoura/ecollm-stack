"""Testes offline do extrator de metadados por modelo via API."""
from __future__ import annotations

import json

from eval.novai_model_api import (
    ModelInfo,
    PROBES_BY_MODALITY,
    extract,
    fetch_models,
    probe_chat,
    probe_embedding,
    probe_image,
    probe_tools,
)


class FakeResp:
    def __init__(self, status, payload=None, content=b""):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else ""
        self.content = content

    def json(self):
        return self._payload


def _sender(routes):
    """routes: dict path -> FakeResp (ou callable(body)->FakeResp)."""
    def _send(path, *, json_body=None, data=None, files=None, stream=False):
        r = routes.get(path)
        if callable(r):
            return r(json_body)
        return r
    return _send


MODELS_PAYLOAD = {"object": "list", "data": [
    {"id": "glm-5", "object": "model", "owned_by": "zhipu", "pricing": "paid"},
    {"id": "glm-4.6v-flash", "object": "model", "owned_by": "zhipu", "pricing": "free"},
]}


def test_fetch_models_returns_data():
    s = _sender({"/models": FakeResp(200, MODELS_PAYLOAD)})
    data = fetch_models(s)
    assert len(data) == 2
    assert data[0]["id"] == "glm-5"


def test_fetch_models_raises_on_http_error():
    s = _sender({"/models": FakeResp(500, {"error": "boom"})})
    try:
        fetch_models(s)
        assert False, "deveria levantar"
    except RuntimeError as exc:
        assert "500" in str(exc)


def test_probe_chat_ok():
    s = _sender({"/chat/completions": FakeResp(200, {
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})})
    r = probe_chat(s, "glm-5")
    assert r["ok"] is True
    assert r["status"] == 200


def test_probe_chat_http_error():
    s = _sender({"/chat/completions": FakeResp(404, {"error": "no model"})})
    r = probe_chat(s, "x")
    assert r["ok"] is False
    assert r["status"] == 404


def test_probe_chat_network_exception():
    def boom(path, **kw):
        raise ConnectionError("sem proxy")

    r = probe_chat(boom, "x")
    assert r["ok"] is False
    assert "erro rede" in r["evidence"]


def test_probe_tools_detects_tool_call():
    s = _sender({"/chat/completions": FakeResp(200, {
        "choices": [{"message": {"tool_calls": [
            {"function": {"name": "noop", "arguments": "{}"}}]},
            "finish_reason": "tool_calls"}]})})
    r = probe_tools(s, "glm-5")
    assert r["ok"] is True


def test_probe_embedding_ok():
    s = _sender({"/embeddings": FakeResp(200, {
        "data": [{"embedding": [0.1, 0.2, 0.3]}]})})
    r = probe_embedding(s, "emb")
    assert r["ok"] is True


def test_probe_image_ok():
    s = _sender({"/images/generations": FakeResp(200, {
        "data": [{"url": "https://x/img.png"}]})})
    r = probe_image(s, "img")
    assert r["ok"] is True


def test_extract_merges_api_and_inventory():
    routes = {
        "/models": FakeResp(200, MODELS_PAYLOAD),
        "/chat/completions": FakeResp(200, {
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}),
    }
    rows = [{"group": "novai-glm-5", "modality": "chat", "upstream_id": "glm-5"}]
    infos = extract(_sender(routes), rows)
    by_id = {i.id: i for i in infos}
    assert by_id["glm-5"].owned_by == "zhipu"
    assert by_id["glm-5"].group == "novai-glm-5"
    assert by_id["glm-5"].modality == "chat"
    assert by_id["glm-5"].probes["chat"]["ok"] is True
    # glm-4.6v-flash está na API mas não no inventário -> sem sondas
    assert by_id["glm-4.6v-flash"].probes == {}


def test_extract_progress_callback():
    routes = {"/models": FakeResp(200, MODELS_PAYLOAD),
              "/chat/completions": FakeResp(200, {
                  "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})}
    seen = []
    extract(_sender(routes), [], progress=lambda i, n, mid: seen.append(mid))
    assert "glm-5" in seen and "glm-4.6v-flash" in seen


def test_extract_novai_only_filters_local_models():
    routes = {"/models": FakeResp(200, MODELS_PAYLOAD),
              "/chat/completions": FakeResp(200, {
                  "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})}
    rows = [{"group": "novai-glm-5", "modality": "chat", "upstream_id": "glm-5"}]
    infos = extract(_sender(routes), rows, novai_only=True)
    assert [i.id for i in infos] == ["glm-5"]


def test_probe_captures_observed_usage():
    s = _sender({"/chat/completions": FakeResp(200, {
        "model": "glm-5",
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2}})})
    r = probe_chat(s, "glm-5")
    assert r["observed"]["usage"]["prompt_tokens"] == 5
    assert r["observed"]["finish_reason"] == "stop"


def test_probes_by_modality_covers_all():
    for mod in ("chat", "chat-fast", "embedding", "image", "tts", "asr"):
        assert mod in PROBES_BY_MODALITY


def test_model_info_defaults():
    m = ModelInfo(id="x")
    assert m.probes == {}
    assert m.errors == []
    assert m.owned_by is None
