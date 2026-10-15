"""Testes unitários do harness NovAI (eval/novai_test.py) — SEM rede.

Exercitam as funções PURAS de veredito (chat/thinking/tools/stream/embed/image/
audio/asr/passthrough) e o orquestrador run_chat/run_embedding com um ``sender``
fake injetável. Nada aqui toca :4000 nem gasta saldo.
"""

from __future__ import annotations

import base64

from eval import novai_test as nt


class _FakeResp:
    def __init__(self, status=200, json_data=None, text="", content=b""):
        self.status_code = status
        self._json = json_data if json_data is not None else {}
        self.text = text
        self.content = content

    def json(self):
        return self._json


def _sender_factory(resp):
    def _send(path, **kw):
        return resp
    return _send


# --- verdict_chat ----------------------------------------------------------

def test_verdict_chat_ok():
    resp = {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}
    ok, ev = nt.verdict_chat(resp)
    assert ok and "len(content)=2" in ev


def test_verdict_chat_empty_is_fail():
    resp = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    ok, ev = nt.verdict_chat(resp)
    assert not ok and "finish=length" in ev


def test_verdict_chat_no_choices():
    ok, _ = nt.verdict_chat({"error": "boom"})
    assert not ok


# --- thinking ON/OFF -------------------------------------------------------

def test_verdict_thinking_on_by_tokens():
    resp = {"choices": [{"message": {"content": "x", "reasoning_content": ""}}],
            "usage": {"completion_tokens_details": {"reasoning_tokens": 42}}}
    ok, ev = nt.verdict_thinking_on(resp)
    assert ok and "reasoning_tokens=42" in ev


def test_verdict_thinking_on_by_content():
    resp = {"choices": [{"message": {"content": "x", "reasoning_content": "pensei"}}]}
    ok, _ = nt.verdict_thinking_on(resp)
    assert ok


def test_verdict_thinking_off_clean():
    resp = {"choices": [{"message": {"content": "resposta"}}],
            "usage": {"completion_tokens_details": {"reasoning_tokens": 0}}}
    ok, ev = nt.verdict_thinking_off(resp)
    assert ok and "no-reasoning OK" in ev


def test_verdict_thinking_off_but_has_reasoning_fails():
    resp = {"choices": [{"message": {"content": "r", "reasoning_content": "pensei"}}]}
    ok, _ = nt.verdict_thinking_off(resp)
    assert not ok


# --- tool calls ------------------------------------------------------------

def test_verdict_tool_calls_ok():
    resp = {"choices": [{"finish_reason": "tool_calls",
                         "message": {"tool_calls": [
                             {"function": {"name": "noop", "arguments": "{}"}}]}}]}
    ok, ev = nt.verdict_tool_calls(resp)
    assert ok and "args_json_ok" in ev


def test_verdict_tool_calls_bad_args():
    resp = {"choices": [{"finish_reason": "tool_calls",
                         "message": {"tool_calls": [
                             {"function": {"name": "n", "arguments": "{bad"}}]}}]}
    ok, _ = nt.verdict_tool_calls(resp)
    assert not ok


# --- stream ----------------------------------------------------------------

def test_split_sse_events_and_verdict():
    raw = 'data: {"choices":[{"delta":{"content":"O"}}]}\n\ndata: {"choices":[{"delta":{"content":"K"}}]}\n\ndata: [DONE]\n\n'
    events = nt.split_sse_events(raw)
    ok, ev = nt.verdict_stream(events)
    assert ok and "parsed=2" in ev and "done=True" in ev


def test_verdict_stream_bad_json():
    events = ["data: {nao-json}", "data: [DONE]"]
    ok, ev = nt.verdict_stream(events)
    assert not ok and "bad=1" in ev


def test_verdict_stream_no_done():
    events = ['data: {"choices":[]}']
    ok, _ = nt.verdict_stream(events)
    assert not ok


# --- embeddings ------------------------------------------------------------

def test_verdict_embeddings_ok_with_dim():
    resp = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    ok, ev = nt.verdict_embeddings(resp, expected_dim=3)
    assert ok and "dim=3" in ev


def test_verdict_embeddings_wrong_dim():
    resp = {"data": [{"embedding": [0.1, 0.2]}]}
    ok, _ = nt.verdict_embeddings(resp, expected_dim=1024)
    assert not ok


def test_verdict_embeddings_missing():
    ok, _ = nt.verdict_embeddings({"error": "x"})
    assert not ok


# --- image -----------------------------------------------------------------

def test_verdict_image_b64():
    payload = base64.b64encode(b"\x00\x01\x02img").decode()
    ok, ev = nt.verdict_image({"data": [{"b64_json": payload}]})
    assert ok and "b64 bytes=6" in ev


def test_verdict_image_url():
    ok, ev = nt.verdict_image({"data": [{"url": "https://x/y.png"}]})
    assert ok and "url=" in ev


def test_verdict_image_empty():
    ok, _ = nt.verdict_image({"data": []})
    assert not ok


# --- audio -----------------------------------------------------------------

def test_verdict_audio_wav():
    ok, ev = nt.verdict_audio(b"RIFF" + b"\x00" * 8 + b"data")
    assert ok and "wav" in ev


def test_verdict_audio_empty():
    ok, _ = nt.verdict_audio(b"")
    assert not ok


# --- asr / passthrough -----------------------------------------------------

def test_verdict_asr_ok():
    ok, ev = nt.verdict_asr({"text": "Hello."})
    assert ok and "text_len=6" in ev


def test_verdict_passthrough_queued():
    ok, ev = nt.verdict_passthrough({"id": "cgt-123", "status": "queued"})
    assert ok and "status=queued" in ev


def test_verdict_passthrough_no_id():
    ok, _ = nt.verdict_passthrough({"status": "queued"})
    assert not ok


# --- orquestrador com sender fake -----------------------------------------

def test_run_chat_text_pass_via_fake_sender():
    resp = _FakeResp(json_data={
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {},
    })
    res = nt.run_chat(_sender_factory(resp), "novai-glm-4.6")
    assert res.passed and res.modality == "chat" and res.test == "chat"


def test_run_chat_http_error_is_fail():
    resp = _FakeResp(status=402, text="insufficient balance")
    res = nt.run_chat(_sender_factory(resp), "novai-x")
    assert not res.passed and "HTTP 402" in res.evidence


def test_run_embedding_pass_via_fake_sender():
    resp = _FakeResp(json_data={"data": [{"embedding": [0.1] * 1024}]})
    res = nt.run_embedding(_sender_factory(resp), "novai-embed-text-embedding-v4")
    assert res.passed and "dim=1024" in res.evidence


# --- seleção / dry-run -----------------------------------------------------

def test_select_family_chat_includes_on_and_off():
    rows = [
        {"group": "novai-a", "modality": "chat", "upstream_id": "a"},
        {"group": "novai-a-fast", "modality": "chat-fast", "upstream_id": "a"},
        {"group": "novai-embed-x", "modality": "embedding", "upstream_id": "x"},
    ]
    chat = nt.select(rows, "chat", None)
    assert {r["group"] for r in chat} == {"novai-a", "novai-a-fast"}
    emb = nt.select(rows, "embedding", None)
    assert len(emb) == 1


def test_run_one_dry_is_skipped():
    row = {"group": "novai-a", "modality": "chat", "upstream_id": "a"}
    out = nt.run_one(row, None, live=False)
    assert len(out) == 1 and out[0].skipped and out[0].status() == "skipped"
