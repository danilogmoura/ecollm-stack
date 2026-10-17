"""Testes unitários do harness NovAI (eval/novai_test.py) — SEM rede.

Exercitam as funções PURAS de veredito (chat/thinking/tools/stream/embed/image/
audio/asr/passthrough) e o orquestrador run_chat/run_embedding com um ``sender``
fake injetável. Nada aqui toca :4000 nem gasta saldo.
"""

from __future__ import annotations

import base64
import json

import pytest

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


# --- stream FORTE (parser tolerante + veredito com diagnóstico de framing) --

def _chunk(content):
    return f'data: {{"choices":[{{"delta":{{"content":"{content}"}}}}]}}'


def test_parse_sse_lines_conformant_double_newline():
    raw = f'{_chunk("O")}\n\n{_chunk("K")}\n\ndata: [DONE]\n\n'
    info = nt.parse_sse_lines(raw)
    assert info["json_ok"] == 2 and info["done"] and info["json_bad"] == 0
    # 3 terminadores \n\n, 0 eventos quebrados por \n simples.
    assert info["sep_blank"] == 3 and info["sep_single"] == 0


def test_parse_sse_lines_tolerates_single_newline_bug():
    # Framing bugado NovAI (\\n simples): parser ainda extrai os chunks.
    raw = f'{_chunk("O")}\n{_chunk("K")}\ndata: [DONE]'
    info = nt.parse_sse_lines(raw)
    assert info["json_ok"] == 2 and info["done"]
    # Nenhum \n\n; 2 pares de eventos vizinhos separados só por \n simples.
    assert info["sep_blank"] == 0 and info["sep_single"] == 2


def test_assemble_stream_text_concatenates_deltas():
    payloads = [
        '{"choices":[{"delta":{"content":"Ol"}}]}',
        '{"choices":[{"delta":{"content":"á!"}}]}',
        "[DONE]",
    ]
    assert nt.assemble_stream_text(payloads) == "Olá!"


def test_verdict_stream_strong_pass_conformant():
    raw = f'{_chunk("O")}\n\n{_chunk("K")}\n\ndata: [DONE]\n\n'
    ok, ev = nt.verdict_stream_strong(nt.parse_sse_lines(raw), expect_substr="OK")
    assert ok and "texto=" in ev


def test_verdict_stream_strong_flags_framing_regression():
    # Payload bom mas \\n simples sem \\n\\n => REGRESSÃO do bug já corrigido.
    raw = f'{_chunk("O")}\n{_chunk("K")}\ndata: [DONE]'
    ok, ev = nt.verdict_stream_strong(nt.parse_sse_lines(raw))
    assert not ok and "REGRESSÃO" in ev


def test_verdict_stream_strong_bad_json_chunk():
    raw = 'data: {nao-json}\n\ndata: [DONE]\n\n'
    ok, ev = nt.verdict_stream_strong(nt.parse_sse_lines(raw))
    assert not ok and "JSON inválido" in ev


def test_verdict_stream_strong_empty_text():
    raw = 'data: {"choices":[{"delta":{}}]}\n\ndata: [DONE]\n\n'
    ok, ev = nt.verdict_stream_strong(nt.parse_sse_lines(raw))
    assert not ok and "texto montado vazio" in ev


def test_verdict_stream_strong_missing_done():
    raw = f'{_chunk("OI")}\n\n'
    ok, ev = nt.verdict_stream_strong(nt.parse_sse_lines(raw))
    assert not ok and "faltou [DONE]" in ev


def test_run_chat_stream_live_uses_strong_verdict():
    raw = f'{_chunk("O")}\n\n{_chunk("K")}\n\ndata: [DONE]\n\n'
    resp = _FakeResp(200, text=raw)
    sender = _sender_factory(resp)
    res = nt.run_chat(sender, "novai-x", stream=True)
    assert res.passed and res.test == "chat.stream"


# --- embeddings ------------------------------------------------------------

def test_verdict_embeddings_ok():
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


# --- vision (T22 / Fase G) ------------------------------------------------

def test_verdict_vision_pt():
    resp = {"choices": [{"message": {"content": "A cor é vermelha."}}]}
    ok, ev = nt.verdict_vision(resp, "red")
    assert ok and "cor=red" in ev


def test_verdict_vision_en():
    resp = {"choices": [{"message": {"content": "The image is BLUE."}}]}
    ok, ev = nt.verdict_vision(resp, "blue")
    assert ok and "cor=blue" in ev


def test_verdict_vision_zh():
    resp = {"choices": [{"message": {"content": "红色"}}]}
    ok, _ = nt.verdict_vision(resp, "red")
    assert ok


def test_verdict_vision_wrong_color_is_fail():
    resp = {"choices": [{"message": {"content": "azul"}}]}
    ok, ev = nt.verdict_vision(resp, "red")
    assert not ok and "ausente" in ev


def test_verdict_vision_empty_content_is_fail():
    resp = {"choices": [{"message": {"content": ""}}]}
    ok, ev = nt.verdict_vision(resp, "red")
    assert not ok and "vazio" in ev


def test_verdict_vision_no_choices_is_fail():
    ok, ev = nt.verdict_vision({"error": "x"}, "red")
    assert not ok and "sem choices" in ev


def test_run_vision_pass_via_fake_sender():
    resp = _FakeResp(json_data={
        "choices": [{"message": {"content": "vermelho"}}],
    })
    res = nt.run_vision(_sender_factory(resp), "novai-qwen3-vl-plus")
    assert res.passed and res.test == "vision" and res.modality == "chat"


def test_run_vision_missing_fixture_is_skipped(tmp_path):
    res = nt.run_vision(_sender_factory(_FakeResp()), "novai-x",
                        fixture=tmp_path / "nope.png")
    assert res.skipped and res.status() == "skipped"


def test_run_vision_http_error_is_fail():
    resp = _FakeResp(status=404, text="model not exist")
    res = nt.run_vision(_sender_factory(resp), "novai-x")
    assert not res.passed and "HTTP 404" in res.evidence


def test_run_vision_sends_data_uri():
    seen = {}

    def _send(path, **kw):
        seen["path"] = path
        seen["body"] = kw.get("json_body")
        return _FakeResp(json_data={"choices": [{"message": {"content": "red"}}]})

    nt.run_vision(_send, "novai-x")
    assert seen["path"] == "/chat/completions"
    parts = seen["body"]["messages"][0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


# --- seleção de mídia (Fase G) --------------------------------------------

def test_select_media_picks_one_per_endpoint():
    rows = [
        {"group": "novai-qwen3-vl-plus", "modality": "chat", "upstream_id": "q"},
        {"group": "novai-image-wand-vega-image-flash", "modality": "image",
         "upstream_id": "w"},
        {"group": "novai-tts-minimax-speech-2.8-hd", "modality": "tts",
         "upstream_id": "m"},
        {"group": "novai-asr-hy-asr-3.0-preview", "modality": "asr",
         "upstream_id": "h"},
        {"group": "novai-image-outro", "modality": "image", "upstream_id": "o"},
    ]
    sel = nt.select_media(rows)
    assert [r["group"] for r in sel] == list(nt.MEDIA_REPRESENTATIVES.values())


def test_select_media_omits_missing_groups():
    rows = [{"group": "novai-image-wand-vega-image-flash", "modality": "image",
             "upstream_id": "w"}]
    sel = nt.select_media(rows)
    assert len(sel) == 1 and sel[0]["modality"] == "image"


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


# --- extract_reasoning -----------------------------------------------------

def _resp(reasoning_content="", reasoning_tokens=0, output_tokens=None, content="ok"):
    det = {}
    if reasoning_tokens:
        det["reasoning_tokens"] = reasoning_tokens
    usage = {"completion_tokens_details": det}
    if output_tokens is not None:
        usage["output_tokens_details"] = {"reasoning_tokens": output_tokens}
    return {"choices": [{"message": {"content": content,
                                     "reasoning_content": reasoning_content}}],
            "usage": usage}


def test_extract_reasoning_from_completion_details():
    c, t = nt.extract_reasoning(_resp(reasoning_tokens=42))
    assert (c, t) == (0, 42)


def test_extract_reasoning_from_content_chars():
    c, t = nt.extract_reasoning(_resp(reasoning_content="pensei bastante"))
    assert c == len("pensei bastante") and t == 0


def test_extract_reasoning_sums_both_positions():
    # LiteLLM pode reportar em completion OU output details — somar evita subcontar.
    c, t = nt.extract_reasoning(_resp(reasoning_tokens=10, output_tokens=5))
    assert t == 15


def test_extract_reasoning_empty_response():
    c, t = nt.extract_reasoning({})
    assert (c, t) == (0, 0)


# --- verdict_thinking_sense ------------------------------------------------

def test_sense_funciona_on_has_off_zero():
    cat, ev = nt.verdict_thinking_sense(_resp(reasoning_tokens=100), _resp())
    assert cat == "funciona" and "tok=100" in ev


def test_sense_nao_suporta_ambos_zero():
    cat, _ = nt.verdict_thinking_sense(_resp(), _resp())
    assert cat == "nao-suporta"


def test_sense_so_on_off_nao_zera():
    # OFF ainda tem reasoning → alavanca disabled não funciona aqui.
    cat, _ = nt.verdict_thinking_sense(_resp(reasoning_tokens=50),
                                       _resp(reasoning_tokens=30))
    assert cat == "so-on"


def test_sense_so_off_invertido():
    cat, _ = nt.verdict_thinking_sense(_resp(), _resp(reasoning_tokens=7))
    assert cat == "so-off"


def test_sense_erro_empty_choices_list():
    # choices=[] explícito → sem escolha válida → erro (não confunde com nao-suporta).
    cat, ev = nt.verdict_thinking_sense({"choices": []}, _resp())
    assert cat == "erro" and "sem choices" in ev


def test_sense_erro_error_dict():
    # dict de erro (sem message válido) → erro, NÃO nao-suporta.
    cat, ev = nt.verdict_thinking_sense({"error": "boom"}, _resp())
    assert cat == "erro" and "sem choices" in ev


# --- pair_chat_models ------------------------------------------------------

def test_pair_chat_models_complete_pairs_only():
    rows = [
        {"group": "novai-a", "modality": "chat", "upstream_id": "a"},
        {"group": "novai-a-fast", "modality": "chat-fast", "upstream_id": "a"},
        {"group": "novai-b", "modality": "chat", "upstream_id": "b"},  # sem -fast
        {"group": "novai-c-fast", "modality": "chat-fast", "upstream_id": "c"},  # órfã
        {"group": "novai-embed-x", "modality": "embedding", "upstream_id": "x"},
    ]
    pairs = nt.pair_chat_models(rows)
    assert pairs == [("novai-a", "novai-a-fast")]


def test_pair_chat_models_preserves_order():
    rows = [
        {"group": "novai-z", "modality": "chat", "upstream_id": "z"},
        {"group": "novai-z-fast", "modality": "chat-fast", "upstream_id": "z"},
        {"group": "novai-a", "modality": "chat", "upstream_id": "a"},
        {"group": "novai-a-fast", "modality": "chat-fast", "upstream_id": "a"},
    ]
    assert nt.pair_chat_models(rows) == [("novai-z", "novai-z-fast"),
                                         ("novai-a", "novai-a-fast")]


# --- run_thinking_probe (sender injetável, SEM rede) -----------------------

def _probe_sender(on_resp, off_resp):
    """Sender fake: primeira chamada (=ON, sem extra_body) devolve on_resp;
    segunda (=OFF, com extra_body thinking.disabled) devolve off_resp."""
    calls = []

    def _send(path, **kw):
        body = kw.get("json_body", {})
        off = bool(body.get("extra_body"))
        calls.append(off)
        return _FakeResp(200, off_resp if off else on_resp)
    return _send, calls


def test_run_thinking_probe_funciona_passes():
    sender, calls = _probe_sender(_resp(reasoning_tokens=88), _resp())
    res = nt.run_thinking_probe(sender, "novai-a", "novai-a-fast")
    assert res.passed and res.test == "thinking-sense"
    assert res.evidence.startswith("funciona")
    # ON disparado sem extra_body, OFF com extra_body → ordem correta dos modos.
    assert calls == [False, True]


def test_run_thinking_probe_nao_suporta_fails_but_classifies():
    sender, _ = _probe_sender(_resp(), _resp())
    res = nt.run_thinking_probe(sender, "novai-a", "novai-a-fast")
    assert not res.passed and res.evidence.startswith("nao-suporta")


def test_run_thinking_probe_http_error_reports():
    def _send(path, **kw):
        return _FakeResp(402, json_data={}, text="insufficient balance")
    res = nt.run_thinking_probe(_send, "novai-a", "novai-a-fast")
    assert not res.passed and "sonda falhou" in res.evidence and "402" in res.evidence


# ===========================================================================
# S103 / P1 — vereditos novos (TTFT, JSON estrito, contrato de erro, params,
# needle, concorrência). Tudo offline: sender fake, zero rede.
# ===========================================================================

# --- verdict_ttft / measure_stream_timing ----------------------------------

def test_verdict_ttft_ok():
    ok, ev = nt.verdict_ttft(120.0, 900.0)
    assert ok and "ttft_ms=120.0" in ev and "total_ms=900.0" in ev


def test_verdict_ttft_none_is_fail():
    ok, ev = nt.verdict_ttft(None)
    assert not ok and "sem primeiro token" in ev


def test_verdict_ttft_greater_than_total_is_fail():
    ok, _ = nt.verdict_ttft(500.0, 400.0)
    assert not ok


def test_measure_stream_timing_with_stamps():
    payloads = ['{"choices":[{"delta":{"role":"assistant"}}]}',
                '{"choices":[{"delta":{"content":"O"}}]}',
                '{"choices":[{"delta":{"content":"K"}}]}',
                "[DONE]"]
    stamps = [0.05, 0.20, 0.30, 0.31]
    t = nt.measure_stream_timing(payloads, t0=0.0, stamps=stamps)
    assert t["n_content_chunks"] == 2
    assert abs(t["ttft_ms"] - 200.0) < 1e-6   # 1º chunk COM content (índice 1)
    assert abs(t["total_ms"] - 310.0) < 1e-6


def test_measure_stream_timing_without_stamps_is_none():
    # Corpo recebido de uma vez: TTFT não observável ⇒ None (fail-closed).
    t = nt.measure_stream_timing(['{"choices":[{"delta":{"content":"O"}}]}'], t0=0.0)
    assert t["ttft_ms"] is None and t["n_content_chunks"] == 1


def test_measure_stream_timing_no_content_chunks():
    t = nt.measure_stream_timing(["[DONE]"], t0=0.0, stamps=[0.1])
    assert t["ttft_ms"] is None and t["n_content_chunks"] == 0


# --- verdict_json_strict ---------------------------------------------------

def test_verdict_json_strict_ok():
    resp = {"choices": [{"message": {"content": '{"ok": true, "n": 1}'}}]}
    ok, ev = nt.verdict_json_strict(resp)
    assert ok and "json_object" in ev


def test_verdict_json_strict_array_is_fail():
    resp = {"choices": [{"message": {"content": "[1, 2, 3]"}}]}
    ok, ev = nt.verdict_json_strict(resp)
    assert not ok and "não é objeto" in ev


def test_verdict_json_strict_markdown_fence_is_fail():
    resp = {"choices": [{"message": {"content": '```json\n{"a":1}\n```'}}]}
    ok, _ = nt.verdict_json_strict(resp)
    assert not ok


def test_verdict_json_strict_empty_is_fail():
    resp = {"choices": [{"message": {"content": "   "}}]}
    ok, ev = nt.verdict_json_strict(resp)
    assert not ok and "vazio" in ev


# --- verdict_error_contract ------------------------------------------------

def test_error_contract_404_ok():
    ok, ev = nt.verdict_error_contract(
        404, {}, {"error": {"message": "model not found", "type": "not_found"}})
    assert ok and "HTTP 404" in ev


def test_error_contract_400_ok():
    ok, _ = nt.verdict_error_contract(400, {}, {"error": {"message": "messages required"}})
    assert ok


def test_error_contract_429_requires_retry_after():
    body = {"error": {"message": "rate limited"}}
    ok, ev = nt.verdict_error_contract(429, {}, body)
    assert not ok and "Retry-After" in ev
    ok2, ev2 = nt.verdict_error_contract(429, {"Retry-After": "5"}, body)
    assert ok2 and "Retry-After=5" in ev2


def test_error_contract_429_retry_after_in_body():
    body = {"error": {"message": "cooldown", "retry_after": 5}}
    ok, _ = nt.verdict_error_contract(429, {}, body)
    assert ok


def test_error_contract_500_is_out_of_contract():
    ok, ev = nt.verdict_error_contract(500, {}, {"error": {"message": "boom"}})
    assert not ok and "fora do contrato" in ev


def test_error_contract_missing_error_field():
    ok, ev = nt.verdict_error_contract(404, {}, {"detail": "nope"})
    assert not ok and "sem campo 'error'" in ev


# --- verdict_param_forwarding ----------------------------------------------

def _chat_resp(content="um dois tres", completion_tokens=3):
    return {"choices": [{"message": {"content": content}}],
            "usage": {"completion_tokens": completion_tokens}}


def test_param_forwarding_stop_respected():
    ok, ev = nt.verdict_param_forwarding({"stop": ["quatro"], "max_tokens": 24},
                                         _chat_resp("um dois tres"))
    assert ok and "respeitado" in ev


def test_param_forwarding_stop_leaked_is_fail():
    ok, ev = nt.verdict_param_forwarding({"stop": ["quatro"]},
                                         _chat_resp("um dois tres quatro"))
    assert not ok and "apareceu no texto" in ev


def test_param_forwarding_max_tokens_exceeded_is_fail():
    ok, ev = nt.verdict_param_forwarding({"max_tokens": 2},
                                         _chat_resp(completion_tokens=9))
    assert not ok and "> max_tokens" in ev


def test_param_forwarding_temperature_not_judged():
    ok, ev = nt.verdict_param_forwarding({"temperature": 0.0}, _chat_resp())
    assert ok and "sem eco no corpo" in ev


# --- verdict_needle --------------------------------------------------------

def test_verdict_needle_found():
    ok, ev = nt.verdict_needle("bla AGULHA-7F3A bla", "agulha-7f3a")
    assert ok and "pos=4" in ev


def test_verdict_needle_missing():
    ok, ev = nt.verdict_needle("nada aqui", "AGULHA-7F3A")
    assert not ok and "ausente" in ev


def test_verdict_needle_empty_needle_is_invalid():
    ok, ev = nt.verdict_needle("texto", "")
    assert not ok and "agulha vazia" in ev


def test_verdict_needle_respects_max_chars():
    ok, _ = nt.verdict_needle("x" * 100 + "AGULHA", "AGULHA", max_chars=50)
    assert not ok


# --- concorrência ----------------------------------------------------------

def test_summarize_concurrency_all_ok():
    s = nt.summarize_concurrency([{"status_code": 200, "latency_ms": v}
                                  for v in (100, 200, 300, 400)])
    assert s["n"] == 4 and s["ok"] == 4 and s["errors"] == {}
    assert s["p50_ms"] == 200 and s["p95_ms"] == 400


def test_summarize_concurrency_with_errors():
    s = nt.summarize_concurrency([
        {"status_code": 200, "latency_ms": 100},
        {"status_code": 429, "latency_ms": 50},
        {"status_code": 429, "latency_ms": 60},
    ])
    assert s["ok"] == 1 and s["errors"] == {"429": 2}


def test_verdict_concurrency_all_ok_passes():
    s = nt.summarize_concurrency([{"status_code": 200, "latency_ms": 10}] * 4)
    ok, ev = nt.verdict_concurrency(s)
    assert ok and "n=4 ok=4" in ev


def test_verdict_concurrency_partial_fails():
    s = nt.summarize_concurrency([{"status_code": 200, "latency_ms": 10},
                                  {"status_code": 500, "latency_ms": 10}])
    ok, _ = nt.verdict_concurrency(s)
    assert not ok


def test_verdict_concurrency_empty_is_fail():
    ok, ev = nt.verdict_concurrency({"n": 0, "ok": 0})
    assert not ok and "nenhuma chamada" in ev


def test_run_concurrency_via_fake_sender():
    resp = _FakeResp(json_data={"choices": [{"message": {"content": "OK"}}]})
    res = nt.run_concurrency(_sender_factory(resp), "novai-x", n=3)
    assert res.passed and res.test == "concurrency" and "n=3 ok=3" in res.evidence


# --- Fase I: contexto longo (needle em N posições) -------------------------

def test_build_needle_context_places_needle_at_start():
    ctx = nt.build_needle_context("AGULHA", filler_tokens=100, position=0.0)
    # position=0 ⇒ corpo vazio antes; a string começa com "\nAGULHA\n".
    assert ctx.lstrip().startswith("AGULHA")


def test_build_needle_context_places_needle_at_end():
    ctx = nt.build_needle_context("AGULHA", filler_tokens=100, position=1.0)
    assert ctx.rstrip().endswith("AGULHA")


def test_build_needle_context_middle_is_not_at_edges():
    ctx = nt.build_needle_context("AGULHA", filler_tokens=100, position=0.5)
    assert not ctx.startswith("AGULHA") and not ctx.rstrip().endswith("AGULHA")
    assert "AGULHA" in ctx


def test_build_needle_context_rejects_bad_position():
    import pytest
    with pytest.raises(ValueError):
        nt.build_needle_context("AGULHA", filler_tokens=10, position=1.5)


def test_build_needle_context_scales_with_filler_tokens():
    small = nt.build_needle_context("AGULHA", filler_tokens=100)
    big = nt.build_needle_context("AGULHA", filler_tokens=1000)
    assert len(big) > len(small)


def test_verdict_needle_position_prefixes_evidence():
    ok, ev = nt.verdict_needle_position("bla AGULHA-7F3A", "AGULHA-7F3A",
                                        position=0.5)
    assert ok and ev.startswith("pos=0.5 :: ")


def test_verdict_needle_position_missing_fails():
    ok, ev = nt.verdict_needle_position("nada", "AGULHA-7F3A", position=1.0)
    assert not ok and ev.startswith("pos=1 :: ")


def test_run_needle_positions_returns_one_result_per_position():
    resp = _FakeResp(json_data={"choices": [{"message": {"content": "AGULHA-7F3A"}}]})
    res = nt.run_needle_positions(_sender_factory(resp), "novai-x",
                                  filler_tokens=50, positions=(0.0, 0.5, 1.0))
    assert [r.test for r in res] == ["needle@0", "needle@0.5", "needle@1"]
    assert all(r.passed for r in res)


def test_run_needle_positions_http_error_does_not_abort_others():
    resp = _FakeResp(status=500, text="boom")
    res = nt.run_needle_positions(_sender_factory(resp), "novai-x",
                                  filler_tokens=50, positions=(0.0, 1.0))
    assert len(res) == 2 and not any(r.passed for r in res)


# --- Fase I: stress --------------------------------------------------------

def test_summarize_stress_percentiles_and_throughput():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": v}
                             for v in (100, 200, 300, 400)])
    assert s["n"] == 4 and s["ok"] == 4
    assert s["p50_ms"] == 200 and s["p95_ms"] == 400 and s["p99_ms"] == 400
    assert s["error_rate"] == 0.0 and s["throughput_rps"] > 0


def test_summarize_stress_flags_degradation():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": v}
                             for v in (10, 10, 10, 500)])
    assert s["degraded"] is True


def test_summarize_stress_no_degradation_when_flat():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": 100}] * 4)
    assert s["degraded"] is False


def test_summarize_stress_counts_errors():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": 10},
                             {"status_code": 429, "latency_ms": 10}])
    assert s["errors"] == {"429": 1} and s["error_rate"] == 0.5


def test_verdict_stress_all_ok_passes():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": 10}] * 4)
    ok, ev = nt.verdict_stress(s)
    assert ok and "n=4" in ev


def test_verdict_stress_empty_is_fail():
    ok, ev = nt.verdict_stress({"n": 0, "ok": 0, "error_rate": 0.0,
                                "degraded": False})
    assert not ok and "nenhuma chamada" in ev


def test_verdict_stress_error_rate_above_threshold_fails():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": 10},
                             {"status_code": 500, "latency_ms": 10}])
    ok, _ = nt.verdict_stress(s, max_error_rate=0.0)
    assert not ok


def test_verdict_stress_degraded_can_be_rejected():
    s = nt.summarize_stress([{"status_code": 200, "latency_ms": v}
                             for v in (10, 10, 10, 500)])
    ok, ev = nt.verdict_stress(s, allow_degraded=False)
    assert not ok and "cauda longa" in ev


def test_run_stress_via_fake_sender():
    resp = _FakeResp(json_data={"choices": [{"message": {"content": "OK"}}]})
    res = nt.run_stress(_sender_factory(resp), "novai-x", n=4, workers=2)
    assert res.passed and res.test == "stress" and "n=4" in res.evidence


# --- Fase I: A7 (content vazio) -------------------------------------------

def test_param_forwarding_empty_content_fails():
    ok, ev = nt.verdict_param_forwarding({"temperature": 0.0},
                                         _chat_resp(content=""))
    assert not ok and "A7" in ev


def test_param_forwarding_whitespace_content_fails():
    ok, ev = nt.verdict_param_forwarding({"temperature": 0.0},
                                         _chat_resp(content="   \n "))
    assert not ok and "A7" in ev


# --- Fase J: vídeo/3D assíncrono (task id + polling) -----------------------

def test_extract_task_id_prefers_id():
    assert nt.extract_task_id({"id": "abc", "request_id": "xyz"}) == "abc"


def test_extract_task_id_accepts_task_id_variants():
    assert nt.extract_task_id({"task_id": "t1"}) == "t1"
    assert nt.extract_task_id({"taskId": "t2"}) == "t2"


def test_extract_task_id_missing_is_none():
    assert nt.extract_task_id({"status": "queued"}) is None
    assert nt.extract_task_id({}) is None
    assert nt.extract_task_id("nao-dict") is None


def test_extract_task_status_normalizes_case():
    assert nt.extract_task_status({"task_status": "processing"}) == "PROCESSING"
    assert nt.extract_task_status({"status": "queued"}) == "QUEUED"
    assert nt.extract_task_status({"state": "Success"}) == "SUCCESS"


def test_extract_task_status_missing_is_empty():
    assert nt.extract_task_status({"id": "x"}) == ""


def test_extract_artifact_url_top_level():
    assert nt.extract_artifact_url({"url": "https://x/v.mp4"}) == "https://x/v.mp4"


def test_extract_artifact_url_nested():
    p = {"data": {"output": {"video_url": "https://x/a.mp4"}}}
    assert nt.extract_artifact_url(p) == "https://x/a.mp4"


def test_extract_artifact_url_in_list():
    p = {"results": [{"url": "https://x/b.mp4"}]}
    assert nt.extract_artifact_url(p) == "https://x/b.mp4"


def test_extract_artifact_url_ignores_non_http():
    assert nt.extract_artifact_url({"url": "/local/path.mp4"}) is None
    assert nt.extract_artifact_url({"url": "data:video/mp4;base64,AAA"}) is None


def test_extract_artifact_url_missing_is_none():
    assert nt.extract_artifact_url({"status": "SUCCESS"}) is None


def test_verdict_video_task_success_with_url():
    ok, ev = nt.verdict_video_task(
        {"task_status": "SUCCESS", "url": "https://x/v.mp4"}, polls=3)
    assert ok and "polls=3" in ev and "artefato=" in ev


def test_verdict_video_task_failed_status():
    ok, ev = nt.verdict_video_task({"task_status": "FAILED"}, polls=1)
    assert not ok and "falhou" in ev


def test_verdict_video_task_success_without_url_fails():
    ok, ev = nt.verdict_video_task({"task_status": "SUCCESS"}, polls=2)
    assert not ok and "sem URL" in ev


def test_verdict_video_task_non_terminal_fails():
    ok, ev = nt.verdict_video_task({"task_status": "PROCESSING"}, polls=0)
    assert not ok and "não-terminal" in ev


def _seq_sender(responses):
    """Sender que devolve respostas em sequência (POST, depois N polls)."""
    it = iter(responses)

    def _send(path, **kw):
        return next(it)
    return _send


def test_run_video_task_happy_path():
    created = _FakeResp(json_data={"id": "t1", "status": "queued"})
    poll1 = _FakeResp(json_data={"task_status": "PROCESSING"})
    poll2 = _FakeResp(json_data={"task_status": "SUCCESS",
                                 "url": "https://x/v.mp4"})
    res = nt.run_video_task(_seq_sender([created, poll1, poll2]), "cogvideox-flash",
                            sleep=lambda _s: None)
    assert res.passed and res.test == "video_task" and "id=t1" in res.evidence


def test_run_video_task_post_error():
    res = nt.run_video_task(_seq_sender([_FakeResp(status=500, text="boom")]),
                            "m", sleep=lambda _s: None)
    assert not res.passed and "POST HTTP 500" in res.evidence


def test_run_video_task_without_task_id():
    res = nt.run_video_task(_seq_sender([_FakeResp(json_data={"status": "queued"})]),
                            "m", sleep=lambda _s: None)
    assert not res.passed and "sem task id" in res.evidence


def test_run_video_task_poll_budget_exhausted_does_not_hang():
    created = _FakeResp(json_data={"id": "t1"})
    stuck = _FakeResp(json_data={"task_status": "PROCESSING"})
    res = nt.run_video_task(_seq_sender([created] + [stuck] * 5), "m",
                            max_polls=3, sleep=lambda _s: None)
    assert not res.passed and "orçamento de polls esgotado (3)" in res.evidence


def test_run_video_task_failed_status_stops_early():
    created = _FakeResp(json_data={"id": "t1"})
    failed = _FakeResp(json_data={"task_status": "FAILED"})
    res = nt.run_video_task(_seq_sender([created, failed]), "m",
                            sleep=lambda _s: None)
    assert not res.passed and "falhou" in res.evidence


# --- orquestradores novos com sender fake ----------------------------------

def test_run_json_strict_via_fake_sender():
    resp = _FakeResp(json_data={"choices": [{"message": {"content": '{"ok": true}'}}]})
    res = nt.run_json_strict(_sender_factory(resp), "novai-x")
    assert res.passed and res.test == "json_strict"


def test_run_error_contract_404_via_fake_sender():
    resp = _FakeResp(status=404, json_data={"error": {"message": "not found"}})
    res = nt.run_error_contract(_sender_factory(resp), "novai-x", case="404")
    assert res.passed and res.test == "error_404"


def test_run_error_contract_wrong_status_is_fail():
    # Pediu 404, veio 500 → fail mesmo com corpo de erro.
    resp = _FakeResp(status=500, json_data={"error": {"message": "boom"}})
    res = nt.run_error_contract(_sender_factory(resp), "novai-x", case="404")
    assert not res.passed and "esperado=404" in res.evidence


def test_run_param_forwarding_via_fake_sender():
    resp = _FakeResp(json_data=_chat_resp("um dois tres"))
    res = nt.run_param_forwarding(_sender_factory(resp), "novai-x")
    assert res.passed and res.test == "param_forwarding"


def test_run_needle_via_fake_sender():
    resp = _FakeResp(json_data={"choices": [{"message": {"content": "AGULHA-7F3A"}}]})
    res = nt.run_needle(_sender_factory(resp), "novai-x", filler_tokens=100)
    assert res.passed and res.test == "needle"


def test_run_ttft_without_iter_lines_is_fail_closed():
    # Corpo inteiro (sem iter_lines) ⇒ TTFT não observável ⇒ fail-closed.
    raw = f'{_chunk("O")}\n\n{_chunk("K")}\n\ndata: [DONE]\n\n'
    res = nt.run_ttft(_sender_factory(_FakeResp(200, text=raw)), "novai-x")
    assert not res.passed and "sem primeiro token" in res.evidence


def test_run_ttft_with_iter_lines_measures():
    class _StreamResp(_FakeResp):
        def iter_lines(self):
            return iter([_chunk("O").encode(), b"", _chunk("K").encode(),
                         b"data: [DONE]"])

    res = nt.run_ttft(_sender_factory(_StreamResp(200)), "novai-x")
    assert res.passed and res.test == "ttft" and "ttft_ms=" in res.evidence


# ---------------------------------------------------------------------------
# S103 / P2 — alvo duplo (gateway × proxy) e classificador de divergência
# ---------------------------------------------------------------------------

def _cr(target, passed, skipped=False):
    return nt.CheckResult("g", "chat", "smoke", passed, "ev", skipped=skipped,
                          target=target)


def test_resolve_targets_both():
    assert nt.resolve_targets("both") == ["gateway", "proxy"]


def test_resolve_targets_single():
    assert nt.resolve_targets("gateway") == ["gateway"]
    assert nt.resolve_targets("proxy") == ["proxy"]


def test_resolve_targets_invalid_raises():
    with pytest.raises(ValueError):
        nt.resolve_targets("nope")


def test_resolve_targets_returns_canonical_order():
    assert nt.resolve_targets("both") == list(nt.TARGETS)


def test_target_config_gateway_uses_env(monkeypatch):
    monkeypatch.setenv("NOVAI_API_KEY", "nvai-abc")
    monkeypatch.delenv("NOVAI_BASE_URL", raising=False)
    cfg = nt.target_config("gateway")
    assert cfg["base_url"] == nt.GATEWAY_BASE_URL
    assert cfg["api_key"] == "nvai-abc"


def test_target_config_gateway_base_url_override(monkeypatch):
    monkeypatch.setenv("NOVAI_BASE_URL", "https://x.test/v1/")
    cfg = nt.target_config("gateway")
    assert cfg["base_url"] == "https://x.test/v1"


def test_target_config_invalid_raises():
    with pytest.raises(ValueError):
        nt.target_config("nope")


def test_target_config_proxy_uses_litellm_env(monkeypatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    cfg = nt.target_config("proxy")
    assert cfg["api_key"] == "sk-test"
    assert cfg["base_url"] == nt.DEFAULT_BASE_URL


def test_classify_same_pass():
    cls, ev = nt.classify_divergence(_cr("gateway", True), _cr("proxy", True))
    assert cls == "same_pass" and "gateway=pass" in ev


def test_classify_same_fail():
    cls, _ = nt.classify_divergence(_cr("gateway", False), _cr("proxy", False))
    assert cls == "same_fail"


def test_classify_gateway_only_is_ours():
    cls, _ = nt.classify_divergence(_cr("gateway", True), _cr("proxy", False))
    assert cls == "gateway_only" and nt.divergence_is_ours(cls)


def test_classify_proxy_only_is_not_ours():
    cls, _ = nt.classify_divergence(_cr("gateway", False), _cr("proxy", True))
    assert cls == "proxy_only" and not nt.divergence_is_ours(cls)


def test_classify_missing_is_incomplete():
    cls, _ = nt.classify_divergence(_cr("gateway", True), None)
    assert cls == "incomplete"


def test_classify_skipped_counts_as_missing():
    cls, _ = nt.classify_divergence(_cr("gateway", True),
                                    _cr("proxy", False, skipped=True))
    assert cls == "incomplete"


def test_pair_results_by_test_groups_targets():
    a = _cr("gateway", True)
    b = _cr("proxy", False)
    pairs = nt.pair_results_by_test([a, b])
    assert list(pairs) == [("g", "smoke")]
    assert pairs[("g", "smoke")]["gateway"] is a
    assert pairs[("g", "smoke")]["proxy"] is b


def test_classify_all_returns_triples():
    out = nt.classify_all([_cr("gateway", True), _cr("proxy", False)])
    assert out == [("g", "smoke", "gateway_only")]


def test_check_result_defaults_target_proxy():
    r = nt.CheckResult("g", "chat", "smoke", True, "ev")
    assert r.target == "proxy" and r.latency_ms is None and r.notes == ""


def test_run_one_dry_marks_target():
    out = nt.run_one({"modality": "chat", "group": "novai-x"}, None, False,
                     target="gateway")
    assert out[0].skipped and out[0].target == "gateway"


def test_run_contract_suite_marks_target_and_runs_all():
    calls = []

    def sender(path, *, json_body=None, data=None, files=None, stream=False):
        calls.append(path)
        return _FakeResp(json_data={"choices": [{"message": {"content": "ok"}}]})

    out = nt.run_contract_suite(sender, "novai-x", target="gateway")
    assert all(r.target == "gateway" for r in out)
    assert {r.test for r in out} >= {"ttft", "json_strict", "param_forwarding",
                                     "needle", "concurrency"}
    assert len(calls) > 0


# ---------------------------------------------------------------------------
# S103 / P3b — captura bruta para o jsonl (spec §12)
# ---------------------------------------------------------------------------

def test_detect_sse_framing_canonical():
    assert nt.detect_sse_framing('data: {"a":1}\n\ndata: [DONE]\n\n') == "\\n\\n"


def test_detect_sse_framing_single_newline_regression():
    assert nt.detect_sse_framing('data: {"a":1}\ndata: [DONE]\n') == "\\n"


def test_detect_sse_framing_not_sse():
    assert nt.detect_sse_framing('{"choices": []}') == ""
    assert nt.detect_sse_framing("") == ""


def test_attach_capture_copies_and_redacts():
    sink = {
        "request": {"method": "POST", "url": "http://x/v1/chat/completions",
                    "body": {"model": "m", "api_key": "nvai-SECRET123"}},
        "headers": {"Authorization": "Bearer sk-SECRET456", "x-req": "1"},
        "body_raw": '{"erro":"nvai-SECRET789"}',
        "sse_framing": "\\n\\n",
    }
    res = nt.attach_capture(_cr("proxy", True), sink)
    assert res.request["method"] == "POST"
    assert res.sse_framing == "\\n\\n"
    blob = f"{res.request}{res.headers}{res.body_raw}"
    assert "SECRET" not in blob


def test_attach_capture_empty_sink_is_noop():
    res = nt.attach_capture(_cr("proxy", True), {})
    assert res.request is None and res.body_raw == ""


def test_make_capturing_sender_records_request(monkeypatch):
    calls = {}

    class _R:
        status_code = 200
        text = 'data: {"a":1}\n\ndata: [DONE]\n\n'
        headers = {"content-type": "text/event-stream"}

    def fake_post(url, **kw):
        calls["url"] = url
        return _R()

    monkeypatch.setattr(nt.requests, "post", fake_post)
    sink = {}
    sender = nt.make_capturing_sender({"base_url": "http://x/v1",
                                       "api_key": "nvai-K"}, sink)
    sender("/chat/completions", json_body={"model": "m"}, stream=True)
    assert calls["url"] == "http://x/v1/chat/completions"
    assert sink["request"]["body"] == {"model": "m"}
    assert sink["sse_framing"] == "\\n\\n"
    assert sink["headers"]["content-type"] == "text/event-stream"


def test_body_raw_limit_truncates(monkeypatch):
    class _R:
        status_code = 200
        text = "x" * (nt.BODY_RAW_LIMIT + 500)
        headers = {}

    monkeypatch.setattr(nt.requests, "post", lambda url, **kw: _R())
    sink = {}
    nt.make_capturing_sender({"base_url": "http://x", "api_key": "k"},
                             sink)("/chat/completions", json_body={})
    assert len(sink["body_raw"]) == nt.BODY_RAW_LIMIT


def test_body_raw_redacts_presigned_url(monkeypatch):
    """S103 / Fase G: URL pré-assinada de imagem não pode ir para o jsonl.

    O GitHub Push Protection bloqueia o push (GH013) quando o log versionado
    carrega ``OSSAccessKeyId``/``q-ak=AKID...``. O ``body_raw`` é redigido no
    próprio sender, antes de chegar ao log.
    """
    class _R:
        status_code = 200
        text = ('{"data":[{"url":"https://b.oss.com/i.png?OSSAccessKeyId=LTAI5t'
                '&Signature=abc"}]}')
        headers = {}

    monkeypatch.setattr(nt.requests, "post", lambda url, **kw: _R())
    sink = {}
    nt.make_capturing_sender({"base_url": "http://x", "api_key": "k"},
                             sink)("/images/generations", json_body={})
    assert "OSSAccessKeyId" not in sink["body_raw"]
    assert "Signature=" not in sink["body_raw"]
    assert "https://b.oss.com/i.png" in sink["body_raw"]  # host+path preservados


# ---------------------------------------------------------------------------
# S103 / Fase F — nome do modelo por alvo (gateway usa upstream_id)
# ---------------------------------------------------------------------------

def test_run_one_gateway_sends_upstream_id():
    """O gateway NovAI não conhece `novai-<slug>`; só o upstream_id."""
    seen = []

    def sender(path, *, json_body=None, data=None, files=None, stream=False):
        seen.append(json_body["model"])
        return _FakeResp(json_data={"choices": [{"message": {"content": "OK"}}]})

    row = {"group": "novai-glm-4.7-flash-fast", "modality": "chat-fast",
           "upstream_id": "glm-4.7-flash"}
    out = nt.run_one(row, sender, True, target="gateway")
    assert seen == ["glm-4.7-flash"]
    assert out[0].group == "novai-glm-4.7-flash-fast"  # relatório usa o grupo


def test_run_one_proxy_sends_group_name():
    seen = []

    def sender(path, *, json_body=None, data=None, files=None, stream=False):
        seen.append(json_body["model"])
        return _FakeResp(json_data={"choices": [{"message": {"content": "OK"}}]})

    row = {"group": "novai-glm-4.7-flash-fast", "modality": "chat-fast",
           "upstream_id": "glm-4.7-flash"}
    nt.run_one(row, sender, True, target="proxy")
    assert seen == ["novai-glm-4.7-flash-fast"]


def test_run_contract_suite_uses_model_override():
    seen = []

    def sender(path, *, json_body=None, data=None, files=None, stream=False):
        seen.append(json_body.get("model"))
        return _FakeResp(json_data={"choices": [{"message": {"content": "OK"}}]})

    out = nt.run_contract_suite(sender, "novai-x", target="gateway",
                                model="glm-4.7-flash")
    # o caso 404 usa de propósito "<model>-nao-existe-<ts>"; os demais usam o model
    assert all(m.startswith("glm-4.7-flash") for m in seen if m)
    assert sum(1 for m in seen if m == "glm-4.7-flash") >= 8
    assert all(r.group == "novai-x" for r in out)


def test_run_contract_suite_captures_each_check_separately():
        """Regressão S103/Fase F: cada check grava SEU request, não o do último.

        O sink do ``make_capturing_sender`` é limpo a cada chamada; se a captura for
        anexada só depois do batch inteiro, todos os registros ficam com o request
        do último check (``error_400``) — evidência contaminada no jsonl.
        """
        sink: dict = {}

        def sender(path, *, json_body=None, data=None, files=None, stream=False):
            sink.clear()
            sink["request"] = {"method": "POST", "url": "http://x/v1" + path,
                               "body": json_body}
            sink["headers"] = {}
            sink["body_raw"] = "{}"
            sink["sse_framing"] = ""
            return _FakeResp(json_data={"choices": [{"message": {"content": "OK"}}]})

        out = nt.run_contract_suite(sender, "novai-x", target="proxy", sink=sink)
        by_test = {r.test: r for r in out}
        # cada check carrega o corpo que ELE enviou
        assert by_test["param_forwarding"].request["body"].get("stop") == ["quatro"]
        assert "messages" in by_test["needle"].request["body"]
        assert "messages" not in by_test["error_400"].request["body"]
        # e nenhum ficou com o corpo do último check
        assert by_test["ttft"].request["body"].get("stream") is True
        assert by_test["json_strict"].request["body"].get("response_format")


# --- S103 / Fase H (T23): embeddings + pgvector isolado ---------------------

class _FakeCursor:
    """Cursor fake: registra o SQL executado e devolve uma linha pré-definida."""

    def __init__(self, row=None, fail_on: str | None = None):
        self.row = row
        self.fail_on = fail_on
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("boom")
        self.executed.append((sql, params))

    def fetchone(self):
        return self.row


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_embedding_input_text_model_is_plain_string():
    assert nt.embedding_input("text-embedding-v4") == ["texto de teste"]


def test_embedding_input_vl_model_is_multimodal():
    """Regressão H1: VL do gateway rejeita lista de strings (400 Tencent)."""
    out = nt.embedding_input("kinfra-vl-embedding-8b")
    assert out == [{"type": "text", "text": "texto de teste"}]


def test_run_embedding_vl_sends_multimodal_payload():
    seen = {}

    def sender(path, *, json_body=None, **kw):
        seen.update(json_body)
        return _FakeResp(json_data={"data": [{"embedding": [0.1] * 2048}]})

    res = nt.run_embedding(sender, "kinfra-vl-embedding-2b")
    assert res.passed and "dim=2048" in res.evidence
    assert seen["input"] == [{"type": "text", "text": "texto de teste"}]


def test_pgvector_table_for_strips_prefix_and_sanitizes():
    assert nt.pgvector_table_for("novai-embed-text-embedding-v4") == \
        "chunks_novai_text_embedding_v4"
    assert nt.pgvector_table_for("novai-embed-qwen3.7-text-embedding") == \
        "chunks_novai_qwen3_7_text_embedding"


def test_pgvector_table_for_never_collides_with_rag_tables():
    for group in ("novai-embed-text-embedding-v4", "novai-embed-kinfra-vl-embedding-8b"):
        t = nt.pgvector_table_for(group)
        assert t.startswith("chunks_novai_")
        assert t not in ("chunks", "chunks_qwen37", "chunks_bgem3")


def test_pgvector_ddl_uses_halfvec_and_hnsw():
    ddl = nt.pgvector_ddl("chunks_novai_x", 1024)
    assert "halfvec(1024)" in ddl
    assert "halfvec_cosine_ops" in ddl
    assert "CREATE TABLE IF NOT EXISTS chunks_novai_x" in ddl


def test_pgvector_ddl_rejects_foreign_table():
    with pytest.raises(ValueError):
        nt.pgvector_ddl("chunks_qwen37", 1024)


def test_pgvector_column_type_halfvec_up_to_4000():
    assert nt.pgvector_column_type(1024) == "halfvec"
    assert nt.pgvector_column_type(4000) == "halfvec"


def test_pgvector_column_type_vector_above_4000():
    """H2: kinfra-vl-embedding-8b tem 4096 dims — acima do teto do halfvec."""
    assert nt.pgvector_column_type(4096) == "vector"


def test_pgvector_ddl_4096_uses_vector_without_hnsw():
    ddl = nt.pgvector_ddl("chunks_novai_x", 4096)
    assert "vector(4096)" in ddl
    assert "halfvec" not in ddl
    assert "hnsw" not in ddl


def test_pgvector_ddl_rejects_invalid_dim():
    with pytest.raises(ValueError):
        nt.pgvector_ddl("chunks_novai_x", 0)


def test_verdict_pgvector_roundtrip_ok():
    v = [0.1, 0.2, 0.3]
    ok, ev = nt.verdict_pgvector_roundtrip(v, v, 0.0, expected_dim=3)
    assert ok and "dim=3" in ev and "distância=0" in ev


def test_verdict_pgvector_roundtrip_fp16_noise_is_ok():
    """halfvec é fp16: distância do vetor consigo mesmo não é exatamente 0."""
    v = [0.1, 0.2, 0.3]
    ok, _ = nt.verdict_pgvector_roundtrip(v, v, 4.2e-4, expected_dim=3)
    assert ok


def test_verdict_pgvector_roundtrip_wrong_dim_fails():
    ok, ev = nt.verdict_pgvector_roundtrip([0.1] * 4, [0.1] * 4, 0.0, expected_dim=3)
    assert not ok and "esperado=3" in ev


def test_verdict_pgvector_roundtrip_truncated_readback_fails():
    ok, ev = nt.verdict_pgvector_roundtrip([0.1] * 4, [0.1] * 3, 0.0)
    assert not ok and "lido=3" in ev


def test_verdict_pgvector_roundtrip_high_distance_fails():
    v = [0.1, 0.2, 0.3]
    ok, ev = nt.verdict_pgvector_roundtrip(v, v, 0.42)
    assert not ok and "distância=0.42" in ev


def test_verdict_pgvector_roundtrip_missing_distance_fails():
    v = [0.1, 0.2, 0.3]
    ok, ev = nt.verdict_pgvector_roundtrip(v, v, None)
    assert not ok and "sem distância" in ev


def test_verdict_pgvector_roundtrip_empty_vectors_fail():
    assert not nt.verdict_pgvector_roundtrip([], [], 0.0)[0]
    assert not nt.verdict_pgvector_roundtrip([0.1], [], 0.0)[0]


def test_parse_pgvector_text_roundtrip():
    assert nt._parse_pgvector_text("[1,2.5,-3]") == [1.0, 2.5, -3.0]
    assert nt._parse_pgvector_text("") == []
    assert nt._parse_pgvector_text("lixo") == []


def test_run_embedding_pgvector_pass_with_fake_conn():
    vec = [0.1] * 8
    cur = _FakeCursor(row=("[0.1,0.1,0.1,0.1,0.1,0.1,0.1,0.1]", 0.0))
    conn = _FakeConn(cur)
    resp = _FakeResp(json_data={"data": [{"embedding": vec}]})

    res = nt.run_embedding_pgvector(_sender_factory(resp), "novai-embed-x",
                                    connect=lambda: conn)
    assert res.passed and res.test == "embed.pgvector"
    assert "tabela=chunks_novai_x" in res.notes
    assert conn.committed and conn.closed
    sqls = " ".join(s for s, _ in cur.executed)
    assert "CREATE TABLE IF NOT EXISTS chunks_novai_x" in sqls
    assert "INSERT INTO chunks_novai_x" in sqls
    assert "ORDER BY embedding <=>" in sqls


def test_run_embedding_pgvector_http_error_is_fail():
    resp = _FakeResp(status=400, text="bad input")
    res = nt.run_embedding_pgvector(_sender_factory(resp), "novai-embed-x",
                                    connect=lambda: _FakeConn(_FakeCursor()))
    assert not res.passed and "HTTP 400" in res.evidence


def test_run_embedding_pgvector_db_error_is_fail_not_raise():
    """Achado é DADO: banco fora ⇒ fail com causa, nunca exceção."""
    cur = _FakeCursor(fail_on="INSERT")
    resp = _FakeResp(json_data={"data": [{"embedding": [0.1] * 4}]})
    res = nt.run_embedding_pgvector(_sender_factory(resp), "novai-embed-x",
                                    connect=lambda: _FakeConn(cur))
    assert not res.passed and "pgvector: RuntimeError" in res.evidence


def test_run_embedding_pgvector_dim_mismatch_is_fail():
    resp = _FakeResp(json_data={"data": [{"embedding": [0.1] * 4}]})
    res = nt.run_embedding_pgvector(_sender_factory(resp), "novai-embed-x",
                                    dim=8, connect=lambda: _FakeConn(_FakeCursor()))
    assert not res.passed and "dim=4 esperado=8" in res.evidence


def test_run_one_pgvector_adds_roundtrip_check():
    row = {"group": "novai-embed-x", "modality": "embedding", "upstream_id": "x"}
    cur = _FakeCursor(row=("[0.1,0.1]", 0.0))
    resp = _FakeResp(json_data={"data": [{"embedding": [0.1, 0.1]}]})
    out = nt.run_one(row, _sender_factory(resp), True, target="proxy",
                     pgvector=True, connect=lambda: _FakeConn(cur))
    assert [r.test for r in out] == ["embed", "embed.pgvector"]
    assert all(r.group == "novai-embed-x" for r in out)


def test_run_one_without_pgvector_keeps_single_check():
    row = {"group": "novai-embed-x", "modality": "embedding", "upstream_id": "x"}
    resp = _FakeResp(json_data={"data": [{"embedding": [0.1, 0.1]}]})
    out = nt.run_one(row, _sender_factory(resp), True, target="proxy")
    assert [r.test for r in out] == ["embed"]


# --- S103 / Fase K: agentes E2E (T25 Copilot BYOK, T26 Roo Code) -----------

def _sse(*chunks, done=True):
    """Monta um corpo SSE canônico a partir de dicts de chunk."""
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return body + ("data: [DONE]\n\n" if done else "")


def _delta(content=None, tool_calls=None):
    d = {}
    if content is not None:
        d["content"] = content
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    return {"choices": [{"delta": d}]}


def test_build_agent_body_copilot_shape():
    body = nt.build_agent_body("m", client="copilot")
    assert body["model"] == "m"
    assert body["stream"] is True
    assert body["tool_choice"] == "auto"
    assert [t["function"]["name"] for t in body["tools"]] == ["read_file",
                                                              "run_tests"]
    assert body["messages"][0]["role"] == "system"
    assert len(body["messages"][0]["content"]) > 1000
    assert "temperature" not in body


def test_build_agent_body_roo_adds_temperature_zero():
    body = nt.build_agent_body("m", client="roo")
    assert body["temperature"] == 0
    assert body["stream"] is True and body["tool_choice"] == "auto"


def test_build_agent_body_rejects_unknown_client():
    with pytest.raises(ValueError, match="cliente desconhecido"):
        nt.build_agent_body("m", client="cursor")


def test_build_agent_body_can_disable_stream_and_tools():
    body = nt.build_agent_body("m", stream=False, tools=False)
    assert "stream" not in body and "tools" not in body
    assert "tool_choice" not in body


def test_parse_sse_chunks_ignores_comments_and_done():
    text = (": keep-alive\n\n"
            'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
            "event: ping\n\n"
            "data: not-json\n\n"
            "data: [DONE]\n\n")
    chunks = nt.parse_sse_chunks(text)
    assert len(chunks) == 1
    assert nt._chunk_text(chunks[0]) == "a"


def test_parse_sse_chunks_empty_body():
    assert nt.parse_sse_chunks("") == []


def test_verdict_agent_response_ok_with_text_and_tools():
    text = _sse(_delta(content="Vou ler o arquivo."),
                _delta(tool_calls=[{"index": 0, "id": "c1",
                                    "function": {"name": "read_file",
                                                 "arguments": "{}"}}]))
    ok, ev = nt.verdict_agent_response(text, client="copilot")
    assert ok and "chunks=2" in ev and "tools=1" in ev and "read_file" in ev


def test_verdict_agent_response_ok_text_only_when_tools_not_expected():
    text = _sse(_delta(content="O projeto indexa código."))
    ok, ev = nt.verdict_agent_response(text, client="roo", expect_tools=False)
    assert ok and "tools=0" in ev


def test_verdict_agent_response_fails_without_tool_calls():
    text = _sse(_delta(content="O projeto indexa código."))
    ok, ev = nt.verdict_agent_response(text, client="copilot")
    assert not ok and "sem tool_calls" in ev


def test_verdict_agent_response_fails_on_empty_response():
    text = _sse(_delta(content=""))
    ok, ev = nt.verdict_agent_response(text, client="copilot",
                                       expect_tools=False)
    assert not ok and "resposta vazia" in ev


def test_verdict_agent_response_fails_without_sse():
    ok, ev = nt.verdict_agent_response('{"choices":[]}', client="copilot")
    assert not ok and "sem chunks SSE" in ev


def test_verdict_agent_response_fails_on_punctuation_only():
    text = _sse(_delta(content="... !!!"))
    ok, ev = nt.verdict_agent_response(text, client="roo", expect_tools=False)
    assert not ok and "alfanumérico" in ev


def test_verdict_agent_response_accepts_message_shape():
    """Alguns proxies devolvem ``message`` em vez de ``delta`` no stream."""
    text = _sse({"choices": [{"message": {"content": "ok",
                                          "tool_calls": [
                                              {"function": {"name": "run_tests"}}]}}]})
    ok, ev = nt.verdict_agent_response(text, client="copilot")
    assert ok and "run_tests" in ev


def test_run_agent_ok():
    text = _sse(_delta(content="Lendo."),
                _delta(tool_calls=[{"function": {"name": "read_file"}}]))
    res = nt.run_agent(_sender_factory(_FakeResp(text=text)), "m",
                       client="copilot")
    assert res.passed and res.test == "agent-copilot" and res.modality == "agent"


def test_run_agent_http_error_is_fail():
    res = nt.run_agent(_sender_factory(_FakeResp(status=429, text="cooldown")),
                       "m", client="roo")
    assert not res.passed and "HTTP 429" in res.evidence


def test_run_agent_sends_stream_and_tools():
    seen = {}

    def _send(path, **kw):
        seen.update(kw)
        return _FakeResp(text=_sse(_delta(content="ok"),
                                   _delta(tool_calls=[{"function":
                                                        {"name": "read_file"}}])))

    nt.run_agent(_send, "m", client="roo")
    assert seen["stream"] is True
    assert seen["json_body"]["temperature"] == 0
    assert seen["json_body"]["tools"]


def test_merge_tool_calls_consolidates_fragments_by_index():
    """K1: o stream manda o nome no 1º fragmento e só arguments depois."""
    chunks = nt.parse_sse_chunks(_sse(
        _delta(tool_calls=[{"index": 0, "id": "c1",
                            "function": {"name": "read_file", "arguments": ""}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": '{"path"'}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": ': "a.md"}'}}]),
    ))
    calls = nt.merge_tool_calls(chunks)
    assert len(calls) == 1
    assert calls[0]["name"] == "read_file"
    assert calls[0]["arguments"] == '{"path": "a.md"}'


def test_merge_tool_calls_keeps_parallel_calls_separate():
    chunks = nt.parse_sse_chunks(_sse(
        _delta(tool_calls=[{"index": 0, "function": {"name": "read_file"}},
                           {"index": 1, "function": {"name": "run_tests"}}]),
    ))
    calls = nt.merge_tool_calls(chunks)
    assert [c["name"] for c in calls] == ["read_file", "run_tests"]


def test_verdict_agent_response_counts_consolidated_calls():
    text = _sse(
        _delta(tool_calls=[{"index": 0, "function": {"name": "read_file"}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": "{}"}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": ""}}]),
    )
    ok, ev = nt.verdict_agent_response(text, client="copilot")
    assert ok and "tools=1" in ev and "read_file" in ev
