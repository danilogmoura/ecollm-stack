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
