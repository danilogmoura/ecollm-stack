"""Testes do CONTRATO de API S117 (eval/novai_contract.py) — modo A, SEM rede.

Fixtures = shapes reais medidos na calibração 2026-10-17 (proxy :4000 e gateway
aiapi-pro.com). Validam que:
  - os payloads conformes passam (extra="allow": campos extras nunca falham);
  - violação de tipo/campo obrigatório falha com mensagem útil;
  - erro é target-aware (OpenAI no proxy; FastAPI detail no gateway = diverged);
  - a tabela de conformidade e o relatório são determinísticos.
Modo C (SDK real) fica atrás de skipif — openai não está instalado no venv.
"""

from __future__ import annotations

import json

import pytest

from eval import novai_contract as nc
from eval.novai_test import TARGETS

# ---------------------------------------------------------------------------
# Fixtures: shapes REAIS (calibração S117) — ordem canônica, não reordenar
# ---------------------------------------------------------------------------


def _chat_payload(**drop):
    p = {
        "id": "chatcmpl-abc123",
        "object": "chat.completion",
        "created": 1792275825,
        "model": "novai-glm-4.7-flash",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "OK"},
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                  "total_tokens": 15},
    }
    for k in drop.get("keys", []):
        p.pop(k, None)
    return p


CHAT_PROXY_EXTRA = {
    # proxy real traz request_id/provider_specific_fields/reasoning_content —
    # extras NÃO podem derrubar a validação (armadilha 3, extra="allow").
    "id": "chatcmpl-x", "object": "chat.completion", "created": 1,
    "model": "m", "request_id": "req-1",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": "",
                             "reasoning_content": "pensei",
                             "provider_specific_fields": {"refusal": None}},
                 "provider_specific_fields": {}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
              "prompt_tokens_details": {"cached_tokens": 2},
              "completion_tokens_details": {"reasoning_tokens": 1}},
}

EMBED_GATEWAY = {"id": "2026x", "object": "list",
                 "model": "text-embedding-v4",
                 "data": [{"index": 0, "object": "embedding",
                           "embedding": [0.1, 0.2, 0.3]}],
                 "usage": {"prompt_tokens": 4, "total_tokens": 4}}

EMBED_PROXY = {"object": "list", "model": "novai-embed-text-embedding-v4",
               "data": [{"index": 0, "object": "embedding",
                         "embedding": [0.5] * 1024}],
               "usage": {"prompt_tokens": 4, "completion_tokens": 0,
                         "total_tokens": 4,
                         "prompt_tokens_details": None,
                         "completion_tokens_details": None}}

IMAGES_GATEWAY = {"created": 1792276000, "id": "img-1",
                  "data": [{"url": "https://oss.example/img.png"}],
                  "usage": {"total_tokens": 45000}}

IMAGES_PROXY = {"created": 1792276000,
                "data": [{"b64_json": "aGVsbG8=", "url": "https://x/y.png",
                          "revised_prompt": "um gato",
                          "provider_specific_fields": {}}],
                "usage": {"total_tokens": 45000, "input_tokens": 0}}

MODELS_LIST = {"object": "list",
               "data": [{"id": "novai-glm-4.7-flash", "object": "model",
                         "created": 1, "owned_by": "novai"},
                        {"id": "glm-5", "object": "model"}]}

ERR_OPENAI_400 = {"error": {"message": "Invalid model name",
                            "type": "invalid_request_error",
                            "param": None, "code": 400}}

ERR_FASTAPI_400 = {"detail": "Model 'xxx' not supported. Available: glm-5"}

SSE_TWO_CHUNKS = (
    'data: {"id":"1","object":"chat.completion.chunk","created":2,'
    '"model":"m","choices":[{"index":0,"delta":{"role":"assistant",'
    '"content":"O"}}]}\n\n'
    'data: {"id":"1","object":"chat.completion.chunk","created":2,'
    '"model":"m","choices":[{"index":0,"delta":{"content":"K"},'
    '"finish_reason":"stop"}],"usage":{"prompt_tokens":1,'
    '"completion_tokens":2,"total_tokens":3}}\n\n'
    "data: [DONE]\n\n"
)


# ---------------------------------------------------------------------------
# validate_payload — mecanismo base
# ---------------------------------------------------------------------------


def test_extra_field_nunca_falha():
    """extra='allow': campo desconhecido em qualquer nível não viola (armadilha 3)."""
    p = _chat_payload()
    p["campo_novo"] = {"qualquer": "coisa"}
    p["choices"][0]["extra_x"] = 1
    assert nc.validate_payload(p, nc.SCHEMA_CHAT_COMPLETION) == []


def test_violacao_de_tipo_aparece_na_mensagem():
    p = _chat_payload()
    p["created"] = "agora"
    errs = nc.validate_payload(p, nc.SCHEMA_CHAT_COMPLETION)
    assert errs and "created" in errs[0]


def test_bool_nao_passa_como_integer():
    p = _chat_payload()
    p["usage"]["total_tokens"] = True
    assert any("total_tokens" in e for e in
               nc.validate_payload(p, nc.SCHEMA_CHAT_COMPLETION))


# ---------------------------------------------------------------------------
# chat.completion
# ---------------------------------------------------------------------------


def test_chat_conforme_proxy():
    ok, ev = nc.verdict_chat_completion(CHAT_PROXY_EXTRA)
    assert ok, ev


def test_chat_conforme_gateway_minimo():
    ok, ev = nc.verdict_chat_completion(_chat_payload())
    assert ok, ev


@pytest.mark.parametrize("key", ["id", "object", "created", "model",
                                 "choices", "usage"])
def test_chat_required_faltando_falha(key):
    p = _chat_payload(keys=[key])
    ok, ev = nc.verdict_chat_completion(p)
    assert not ok and key in ev


def test_chat_object_errado_falha():
    p = _chat_payload()
    p["object"] = "text_completion"
    ok, _ = nc.verdict_chat_completion(p)
    assert not ok


def test_chat_content_null_falha():
    """Medido: content é str "" mesmo em thinking-only; null quebra SDK."""
    p = _chat_payload()
    p["choices"][0]["message"]["content"] = None
    ok, ev = nc.verdict_chat_completion(p)
    assert not ok and "content" in ev


# ---------------------------------------------------------------------------
# chunk SSE
# ---------------------------------------------------------------------------


def test_chunks_conformes_com_usage_opcional():
    ok, ev = nc.verdict_chunks(SSE_TWO_CHUNKS)
    assert ok, ev
    assert "2 chunks" in ev


def test_chunks_sem_done_falha():
    body = SSE_TWO_CHUNKS.split("data: [DONE]")[0]
    ok, ev = nc.verdict_chunks(body)
    assert not ok and "[DONE]" in ev


def test_chunk_objeto_invalido_falha():
    ok, ev = nc.verdict_chunks('data: {"id":"1"}\n\ndata: [DONE]\n\n')
    assert not ok and "object" in ev


def test_chunk_finish_reason_null_ok():
    body = ('data: {"id":"1","object":"chat.completion.chunk","created":2,'
            '"model":"m","choices":[{"index":0,"delta":{},"finish_reason":null}]}'
            '\n\ndata: [DONE]\n\n')
    ok, ev = nc.verdict_chunks(body)
    assert ok, ev


# ---------------------------------------------------------------------------
# embeddings / images / models
# ---------------------------------------------------------------------------


def test_embeddings_gateway_sem_id_conforma():
    """id só existe no gateway → nunca pode ser required (cold-start)."""
    ok, ev = nc.verdict_embeddings(EMBED_GATEWAY)
    assert ok, ev
    p = dict(EMBED_GATEWAY)
    p.pop("id")
    assert nc.verdict_embeddings(p)[0]


def test_embeddings_proxy_com_details():
    ok, ev = nc.verdict_embeddings(EMBED_PROXY)
    assert ok and "dim=1024" in ev


def test_embeddings_sem_embedding_lista_falha():
    p = json.loads(json.dumps(EMBED_GATEWAY))
    p["data"][0]["embedding"] = "abc"
    ok, _ = nc.verdict_embeddings(p)
    assert not ok


def test_images_url_ou_b64():
    assert nc.verdict_images(IMAGES_GATEWAY)[0]
    assert nc.verdict_images(IMAGES_PROXY)[0]


def test_images_item_sem_url_nem_b64_falha():
    ok, _ = nc.verdict_images({"created": 1, "data": [{"revised_prompt": "x"}]})
    assert not ok


def test_models_created_opcional():
    """gateway não devolve created nos items (medido) → não é required."""
    ok, ev = nc.verdict_models(MODELS_LIST)
    assert ok and "n=2" in ev


def test_models_data_vazia_falha():
    ok, _ = nc.verdict_models({"object": "list", "data": []})
    assert not ok


# ---------------------------------------------------------------------------
# erro target-aware (armadilha 1)
# ---------------------------------------------------------------------------


def test_erro_openai_no_proxy_passa():
    ok, ev = nc.verdict_error(400, ERR_OPENAI_400, "proxy")
    assert ok is True and "OpenAI" in ev


def test_erro_detail_no_gateway_e_divergido_nao_fail():
    ok, ev = nc.verdict_error(400, ERR_FASTAPI_400, "gateway")
    assert ok == nc.DIVERGED and "divergência documentada" in ev


def test_erro_detail_no_proxy_e_fail():
    ok, ev = nc.verdict_error(400, ERR_FASTAPI_400, "proxy")
    assert ok is False and "esperado OpenAI" in ev


def test_erro_sem_envelope_algum_falha_dos_dois_lados():
    ok, ev = nc.verdict_error(500, {"oops": True}, "proxy")
    assert ok is False and "sem envelope" in ev


def test_erro_openai_no_gateway_tambem_conforma():
    """Se um dia o gateway corrigir para OpenAI shape, conta como pass."""
    ok, _ = nc.verdict_error(400, ERR_OPENAI_400, "gateway")
    assert ok is True


# ---------------------------------------------------------------------------
# tabela de conformidade + relatório
# ---------------------------------------------------------------------------


def _r(ep, tgt, st):
    return nc.ContractResult(ep, tgt, "m", st, "ev")


def test_marca_celula_prioriza_fail():
    rs = [_r("chat.completion", "proxy", "pass"),
          _r("chat.completion", "gateway", nc.DIVERGED),
          _r("chat.completion", "proxy", "fail")]
    assert nc.conformance_mark(rs) == nc.NAO_CONFORME
    assert nc.conformance_mark(rs[:2]) == nc.DIVERGENTE
    assert nc.conformance_mark(rs[:1]) == nc.CONFORME
    assert nc.conformance_mark([]) == nc.AUSENTE


def test_tabela_ordem_canonica_endpoints():
    rows = nc.conformance_table([_r("embeddings", "proxy", "pass")])
    ids = [row[0] for row in rows[1:]]
    assert ids == [s.id for s in nc.ENDPOINTS]
    # Colunas seguem TARGETS (gateway, proxy) — não a ordem de chegada dos dados.
    gi, pi = (TARGETS.index(t) + 1 for t in ("gateway", "proxy"))
    emb = rows[1 + ids.index("embeddings")]
    assert emb[pi] == nc.CONFORME and emb[gi] == nc.AUSENTE


def test_relatorio_contem_divergencias():
    results = [_r("error.openai", "gateway", nc.DIVERGED),
               _r("chat.completion", "proxy", "pass")]
    md = nc.build_report(results)
    assert "divergências documentadas" in md
    assert "| error.openai |" in md or "error.openai" in md
    assert "`diverged`: 1" in md


# ---------------------------------------------------------------------------
# live com sender fake (transport injetável — sem rede)
# ---------------------------------------------------------------------------


class FakeResp:
    def __init__(self, status=200, payload=None, text=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_run_live_endpoint_chat_ok():
    seen = {}

    def sender(path, *, json_body=None, stream=False, method="POST"):
        seen.update(path=path, body=json_body, stream=stream, method=method)
        return FakeResp(payload=_chat_payload())

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("chat.completion"),
                             "proxy")
    assert r.status == "pass" and seen["path"] == "/chat/completions"
    assert seen["body"]["model"] == nc.CHAT_MODEL["proxy"]


def test_run_live_endpoint_models_usa_get():
    """POST /models responde 405 (armadilha 2) → harness usa GET."""
    seen = {}

    def sender(path, **kw):
        seen.update(kw, path=path)
        return FakeResp(payload=MODELS_LIST)

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("models.list"), "proxy")
    assert r.status == "pass" and seen["method"] == "GET"


def test_run_live_endpoint_erro_diverge_no_gateway():
    def sender(path, *, json_body=None, stream=False):
        return FakeResp(status=400, payload=ERR_FASTAPI_400)

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("error.openai"),
                             "gateway")
    assert r.status == nc.DIVERGED


def test_run_live_endpoint_http_inesperado_e_fail():
    def sender(path, *, json_body=None, stream=False):
        return FakeResp(status=502, text="bad gateway")

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("chat.completion"),
                             "proxy")
    assert r.status == "fail" and "502" in r.evidence


def test_run_live_endpoint_erro_de_transporte_e_fail():
    class Boom:
        status_code = 200
        text = ""
        error = "connection reset"

    def sender(path, **kw):
        return Boom()

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("models.list"), "proxy")
    assert r.status == "fail" and "transport" in r.evidence


def test_run_live_endpoint_error_com_corpo_invalido_e_fail():
    """Endpoint de erro com corpo não-JSON → payload {} → violação real."""
    def sender(path, **kw):
        return FakeResp(status=400, payload=None)

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("error.openai"), "proxy")
    assert r.status == "fail"


def test_run_live_endpoint_chunk_invalido_no_meio_do_fluxo():
    sse = ('data: {"id":"a","object":"chat.completion.chunk","created":1,'
           '"model":"m","choices":[{"index":0,"delta":{}}]}\n\n'
           "data: isso-nao-e-json\n\ndata: [DONE]\n\n")

    def sender(path, **kw):
        return FakeResp(text=sse)

    r = nc.run_live_endpoint(sender,
                             nc.endpoint_by_id("chat.completion.chunk"),
                             "proxy")
    assert r.status == "fail" and "JSON inválido" in r.evidence


def test_run_live_endpoint_viacao_de_schema_popula_violations():
    p = _chat_payload()
    del p["usage"]

    def sender(path, **kw):
        return FakeResp(payload=p)

    r = nc.run_live_endpoint(sender, nc.endpoint_by_id("chat.completion"),
                             "proxy")
    assert r.status == "fail" and any("usage" in v for v in r.violations)


def test_endpoint_by_id_desconhecido_falha():
    with pytest.raises(KeyError):
        nc.endpoint_by_id("nao.existe")


def test_verdict_error_corpo_nao_objeto():
    ok, ev = nc.verdict_error(500, "string", "proxy")
    assert ok is False and "não é objeto" in ev


def test_fluxo_so_com_done_e_fail_nenhum_chunk():
    ok, ev = nc.verdict_chunks("data: [DONE]\n\n")
    assert ok is False and "nenhum chunk JSON" in ev


def test_run_live_suite_com_sleep(monkeypatch):
    """sleep_s > 0 aplica pausa entre calls (rate limit 60 rpm)."""
    slept = []
    monkeypatch.setattr(nc.time, "sleep", lambda s: slept.append(s))

    def sender(path, **kw):
        return FakeResp(payload=MODELS_LIST)

    rs = nc.run_live_suite("proxy", sender=sender, sleep_s=0.7,
                           endpoints=(nc.endpoint_by_id("models.list"),
                                      nc.endpoint_by_id("models.list")))
    assert all(r.status == "pass" for r in rs)
    assert slept == [0.7]


def test_fluxo_so_com_done_e_fail_nenhum_chunk():
    ok, ev = nc.verdict_chunks("data: [DONE]\n\n")
    assert ok is False and "nenhum chunk JSON" in ev


def test_run_live_suite_com_sleep(monkeypatch):
    """sleep_s > 0 aplica pausa entre calls (rate limit 60 rpm)."""
    slept = []
    monkeypatch.setattr(nc.time, "sleep", lambda s: slept.append(s))

    def sender(path, **kw):
        return FakeResp(payload=MODELS_LIST)

    rs = nc.run_live_suite("proxy", sender=sender, sleep_s=0.7,
                           endpoints=(nc.endpoint_by_id("models.list"),
                                      nc.endpoint_by_id("models.list")))
    assert all(r.status == "pass" for r in rs)
    assert slept == [0.7]


def test_passed_property():
    assert nc.ContractResult("e", "t", "m", "pass", "").passed
    assert not nc.ContractResult("e", "t", "m", "fail", "").passed


def test_run_live_suite_dry_skips_tudo():
    rs = nc.run_live_suite("proxy")
    assert len(rs) == len(nc.ENDPOINTS)
    assert all(r.status == "skipped" for r in rs)


def test_main_dry_retorna_zero(capsys):
    assert nc.main(["--target", "both"]) == 0
    out = capsys.readouterr().out
    assert "modo dry" in out


def test_main_list_endpoints(capsys):
    assert nc.main(["--list-endpoints"]) == 0
    assert "chat.completion.chunk" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# modo C — SDK real (opt-in; skipif quando ausente, fora do gate)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not nc.sdk_available(), reason="pacote 'openai' não instalado")
def test_sdk_roundtrip():  # pragma: no cover — só roda com openai instalado
    cfg = nc.proxy_config()
    r = nc.run_sdk_check(cfg, nc.CHAT_MODEL["proxy"])
    assert r.status in ("pass", "fail")


def test_sdk_skip_quando_ausente(monkeypatch):
    monkeypatch.setattr(nc, "sdk_available", lambda: False)
    r = nc.run_sdk_check({"base_url": "x", "api_key": "y"}, "m")
    assert r.status == "skipped"
