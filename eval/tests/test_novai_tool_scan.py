"""Testes offline do S119 — sweep de contrato de tools (`eval/novai_tool_scan.py`).

Tudo puro: fixtures com as formas MEDIDAS em 2026-10-17 (S118) — gateway
emite fala antes da chamada num chunk de args só; proxy fragmenta args.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.novai_tool_scan import (
    ARG_CHUNK_UNICO,
    ARG_FRAGMENTADO,
    NS_CONFORME,
    NS_ERRO,
    NS_IRREGULAR,
    NS_SEM_TOOLCALL,
    ST_AMBIOS,
    ST_ERRO,
    ST_FALA_ANTES,
    ST_FALA_DEPOIS,
    ST_SEM_TOOLCALL,
    ST_SO_TOOLS,
    ScanRow,
    aggregate_arguments,
    build_report,
    chat_groups_from_matrix,
    chat_models_from_inventory,
    inspect_tool_calls,
    parse_stream_deltas,
    rows_to_csv,
    scan_model,
    verdict_tool_nonstream,
    verdict_tool_stream,
)


def _tc(id_: str = "call_1", name: str = "get_weather", args: str = '{"city":"Tokyo"}'):
    return {"id": id_, "type": "function", "index": 0,
            "function": {"name": name, "arguments": args}}


def _resp(content: str = "", tool_calls=None, finish: str = "stop"):
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"id": "1", "object": "chat.completion", "created": 1,
            "model": "m", "choices": [{"index": 0, "message": msg,
                                       "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                      "total_tokens": 2}}


# --------------------------------------------------------------------------- non-stream


class TestVerdictNonStream:
    def test_conforme(self):
        code, ev = verdict_tool_nonstream(
            _resp(tool_calls=[_tc()], finish="tool_calls"))
        assert code == NS_CONFORME
        assert "get_weather" in ev

    def test_irregular_content_e_tool(self):
        code, _ = verdict_tool_nonstream(
            _resp(content="Vou verificar!", tool_calls=[_tc()],
                  finish="tool_calls"))
        assert code == NS_IRREGULAR

    def test_sem_tool_call(self):
        code, ev = verdict_tool_nonstream(_resp(content="Tokyo: 20C"))
        assert code == NS_SEM_TOOLCALL
        assert "Tokyo" in ev

    def test_args_nao_parseavel_e_erro(self):
        code, _ = verdict_tool_nonstream(
            _resp(tool_calls=[_tc(args="{cidade")], finish="tool_calls"))
        assert code == NS_ERRO

    def test_args_vazios_e_erro(self):
        code, _ = verdict_tool_nonstream(
            _resp(tool_calls=[_tc(args="  ")], finish="tool_calls"))
        assert code == NS_ERRO

    def test_sem_id_e_erro(self):
        tc = _tc()
        del tc["id"]
        code, _ = verdict_tool_nonstream(
            _resp(tool_calls=[tc], finish="tool_calls"))
        assert code == NS_ERRO

    def test_type_errado_e_erro(self):
        tc = _tc()
        tc["type"] = "functionx"
        code, _ = verdict_tool_nonstream(
            _resp(tool_calls=[tc], finish="tool_calls"))
        assert code == NS_ERRO

    def test_http_nao_200_e_erro(self):
        code, ev = verdict_tool_nonstream(_resp(), status_code=502)
        assert code == NS_ERRO
        assert "502" in ev

    def test_resposta_nao_dict(self):
        assert verdict_tool_nonstream("html", 200)[0] == NS_ERRO

    def test_item_tool_call_nao_dict(self):
        code, _ = verdict_tool_nonstream(
            _resp(tool_calls=["x"], finish="tool_calls"))
        assert code == NS_ERRO


class TestInspectToolCalls:
    def test_lista_vazia(self):
        info = inspect_tool_calls([])
        assert info.n == 0 and not info.args_parseavel

    def test_none(self):
        assert inspect_tool_calls(None).n == 0

    def test_multiplas_chamadas(self):
        info = inspect_tool_calls([_tc(), _tc(id_="call_2", name="other")])
        assert info.n == 2 and info.names == ["get_weather", "other"]
        assert info.ids_ok and info.types_function and info.args_parseavel


# --------------------------------------------------------------------------- stream


def _sse(events: list[dict], done: bool = True) -> str:
    out = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    return out + ("data: [DONE]\n\n" if done else "")


def _delta_event(content=None, tool_calls=None, finish=None):
    delta: dict = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    return {"id": "1", "object": "chat.completion.chunk", "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


class TestParseStreamDeltas:
    def test_extrai_ordem_e_finish(self):
        raw = _sse([
            _delta_event(content="V"),
            _delta_event(content="ou"),
            _delta_event(tool_calls=[{"index": 0, "id": "c1",
                                      "function": {"name": "get_weather",
                                                   "arguments": '{"ci'}}]),
            _delta_event(tool_calls=[{"index": 0,
                                      "function": {"arguments": 'ty":"Tokyo"}'}}]),
            _delta_event(finish="tool_calls"),
        ])
        info = parse_stream_deltas(raw)
        assert info["error"] is None
        assert info["has_done"]
        assert info["content_parts"] == ["V", "ou"]
        assert len(info["tool_chunks"]) == 2
        assert info["finish_reasons"] == ["tool_calls"]
        assert info["arg_chunks_por_index"] == {0: 2}

    def test_linha_invalida_vira_error(self):
        info = parse_stream_deltas("data: {nao-json\n\n")
        assert info["error"] is not None

    def test_sem_done(self):
        info = parse_stream_deltas(_sse([_delta_event(content="oi")], done=False))
        assert not info["has_done"]


class TestVerdictStream:
    def test_so_tools_canonico(self):
        raw = _sse([
            _delta_event(tool_calls=[{"index": 0, "id": "c1",
                                      "function": {"name": "get_weather",
                                                   "arguments": '{"city":"Tokyo"}'}}]),
            _delta_event(finish="tool_calls"),
        ])
        code, ev = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_SO_TOOLS
        assert ARG_CHUNK_UNICO in ev

    def test_fala_antes_formato_glm(self):
        # padrão medido S118: fala inteira primeiro, depois tool_call unico
        events = [_delta_event(content=c) for c in ("Vou", " verificar", "!")]
        events.append(_delta_event(tool_calls=[
            {"index": 0, "id": "c1", "function": {"name": "get_weather",
                                                  "arguments": '{"city":"Tokyo"}'}}]))
        events.append(_delta_event(finish="tool_calls"))
        raw = _sse(events)
        code, _ = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_FALA_ANTES

    def test_fala_depois(self):
        raw = _sse([
            _delta_event(tool_calls=[{"index": 0, "id": "c1",
                                      "function": {"name": "f",
                                                   "arguments": "{}"}}]),
            _delta_event(content="depois"),
            _delta_event(finish="tool_calls"),
        ])
        code, _ = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_FALA_DEPOIS

    def test_intercalado(self):
        raw = _sse([
            _delta_event(content="an"),
            _delta_event(tool_calls=[{"index": 0, "id": "c1",
                                      "function": {"name": "f",
                                                   "arguments": "{}"}}]),
            _delta_event(content="tes"),
            _delta_event(finish="tool_calls"),
        ])
        code, _ = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_AMBIOS

    def test_sem_tool_call_no_stream(self):
        raw = _sse([_delta_event(content="resposta longa"),
                    _delta_event(finish="stop")])
        code, _ = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_SEM_TOOLCALL

    def test_args_fragmentados_concatenam(self):
        raw = _sse([
            _delta_event(tool_calls=[{"index": 0, "id": "c1",
                                      "function": {"name": "f",
                                                   "arguments": '{"ci'}}]),
            _delta_event(tool_calls=[{"index": 0,
                                      "function": {"arguments": 'ty":"T'}}]),
            _delta_event(tool_calls=[{"index": 0,
                                      "function": {"arguments": 'okyo"}'}}]),
            _delta_event(finish="tool_calls"),
        ])
        code, ev = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_SO_TOOLS
        assert ARG_FRAGMENTADO in ev and "ok" in ev

    def test_args_nao_parseaveis_sao_erro(self):
        raw = _sse([
            _delta_event(tool_calls=[{"index": 0, "id": "c1",
                                      "function": {"name": "f",
                                                   "arguments": "{cidade"}}]),
            _delta_event(finish="tool_calls"),
        ])
        code, ev = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_ERRO
        assert "nao-parseaveis" in ev

    def test_sem_done_e_erro(self):
        raw = _sse([_delta_event(tool_calls=[
            {"index": 0, "function": {"arguments": "{}"}}])], done=False)
        code, _ = verdict_tool_stream(parse_stream_deltas(raw), raw)
        assert code == ST_ERRO

    def test_corpo_vazio_e_erro(self):
        code, _ = verdict_tool_stream(parse_stream_deltas(""), "")
        assert code == ST_ERRO

    def test_verdict_sem_raw_usa_classificador_puro(self):
        raw = _sse([_delta_event(content="oi"),
                    _delta_event(tool_calls=[{"index": 0,
                                              "function": {"arguments": "{}"}}]),
                    _delta_event(finish="tool_calls")])
        code, _ = verdict_tool_stream(parse_stream_deltas(raw))
        assert code == ST_FALA_ANTES

    def test_linha_invalida_no_reparse_de_offsets(self):
        # primeira passada ve tudo ok? nao: parse_stream_deltas ja marca erro.
        # entao exercitamos o reparse com dado que so ele ve: chamando direto.
        from eval.novai_tool_scan import _classify_stream_sequence_with_offsets
        info = {"error": None, "events": 3, "has_done": True,
                "content_parts": ["a"], "tool_chunks": [{"index": 0}],
                "finish_reasons": ["tool_calls"], "arg_chunks_por_index": {0: 1}}
        raw = ("data: {nao-json\n\n"
               + "data: " + json.dumps(_delta_event(content="a")) + "\n\n"
               + "data: " + json.dumps(_delta_event(tool_calls=[
                   {"index": 0, "function": {"arguments": "{}"}}])) + "\n\n"
               + "data: [DONE]\n\n")
        # content primeiro => fala antes (reparse ignora a linha invalida)
        assert _classify_stream_sequence_with_offsets(raw, info) == ST_FALA_ANTES


class TestRunScanInjetado:
    def test_proxy_com_sender_fake(self, monkeypatch, tmp_path):
        import eval.novai_tool_scan as ts
        mcsv = tmp_path / "m.csv"
        mcsv.write_text(
            "group,modality,upstream_id,status,evidence,target,test_id,latency_ms,notes\n"
            "novai-a,chat,x,pass,,proxy,chat,1,\n", encoding="utf-8")
        monkeypatch.setattr(ts, "MATRIX_CSV", mcsv)
        ns = FakeResp(_resp(tool_calls=[_tc()], finish="tool_calls"))
        raw = _sse([_delta_event(tool_calls=[
            {"index": 0, "function": {"arguments": "{}"}}]),
            _delta_event(finish="tool_calls")])
        st = FakeResp({}, text=raw)
        calls = iter([ns, st])

        def sender(path, *, json_body=None, stream=False, method="POST", **kw):
            return next(calls)
        rows = ts.run_scan(["proxy"], sleep=0, limit=1,
                           sender_factory=lambda t: sender,
                           progress=lambda s: None)
        assert len(rows) == 1 and rows[0].target == "proxy"
        assert rows[0].ns_code == NS_CONFORME and rows[0].st_code == ST_SO_TOOLS

    def test_gateway_usa_inventario(self, monkeypatch):
        import eval.novai_tool_scan as ts
        inv = FakeResp({"data": [{"id": "glm-5"}, {"id": "text-embedding-v4"}]})
        ns = FakeResp(_resp(tool_calls=[_tc()], finish="tool_calls"))
        raw = _sse([_delta_event(content="fala"),
                    _delta_event(tool_calls=[{"index": 0,
                                              "function": {"arguments": "{}"}}]),
                    _delta_event(finish="tool_calls")])
        st = FakeResp({}, text=raw)
        calls = iter([inv, ns, st])

        def sender(path, *, json_body=None, stream=False, method="POST", **kw):
            return next(calls)
        rows = ts.run_scan(["gateway"], sleep=0, limit=5,
                           sender_factory=lambda t: sender,
                           progress=lambda s: None)
        assert [r.model for r in rows] == ["glm-5"]
        assert rows[0].st_code == ST_FALA_ANTES


class TestAggregateArguments:
    def test_sem_chunks(self):
        info = parse_stream_deltas(_sse([_delta_event(content="a")]))
        assert aggregate_arguments(info) == ("ausente", False, "")

    def test_indice_nao_zero_ignorado_no_join(self):
        raw = _sse([_delta_event(tool_calls=[
            {"index": 1, "function": {"arguments": '{"a":1}'}}]),
            _delta_event(finish="tool_calls")])
        frag, parseavel, joined = aggregate_arguments(parse_stream_deltas(raw))
        assert joined == "" and not parseavel
        assert frag == ARG_CHUNK_UNICO or frag == ARG_FRAGMENTADO


# --------------------------------------------------------------------------- catálogo


class TestCatalogo:
    def test_grupos_da_matriz(self, tmp_path: Path):
        p = tmp_path / "m.csv"
        p.write_text(
            "group,modality,upstream_id,status,evidence,target,test_id,latency_ms,notes\n"
            "novai-a,chat,x,pass,,proxy,chat,1,\n"
            "novai-a-fast,chat-fast,x,pass,,proxy,chat,1,\n"
            "novai-b,embeddings,x,pass,,proxy,emb,1,\n", encoding="utf-8")
        assert chat_groups_from_matrix(p) == ["novai-a", "novai-a-fast"]

    def test_inventario_exclui_nao_chat(self):
        data = [{"id": "glm-5"}, {"id": "text-embedding-v4"}, {"id": "flux-schnell"},
                {"id": "cosyvoice2-tts"}, {"id": "glm-4.6v"}]
        assert chat_models_from_inventory(data) == ["glm-4.6v", "glm-5"]

    def test_matriz_real_tem_grupos(self):
        groups = chat_groups_from_matrix()
        assert len(groups) >= 100
        assert "novai-glm-4.7-flash" in groups


# --------------------------------------------------------------------------- row/csv/report


class FakeResp:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload


class Boom(Exception):
    pass


def _sender_for(resps):
    calls = iter(resps)

    def sender(path, *, json_body=None, stream=False, method="POST", **kw):
        r = next(calls)
        if isinstance(r, Exception):
            raise r
        return r
    return sender


class TestScanModel:
    def test_fluxo_feliz(self):
        ns = FakeResp(_resp(tool_calls=[_tc()], finish="tool_calls"))
        raw = _sse([_delta_event(tool_calls=[
            {"index": 0, "function": {"arguments": "{}"}}]),
            _delta_event(finish="tool_calls")])
        st = FakeResp({}, text=raw)
        sink: dict = {}
        row = scan_model(_sender_for([ns, st]), "m1", stream_raw_sink=sink)
        assert row.ns_code == NS_CONFORME
        assert row.st_code == ST_SO_TOOLS
        assert "raw" in sink
        assert not row.irregular

    def test_transport_exception_registrado(self):
        row = scan_model(_sender_for([Boom("down"), Boom("down")]), "m1")
        assert row.ns_code == NS_ERRO and row.st_code == ST_ERRO
        assert "Boom" in row.ns_ev and "transport" in row.ns_ev
        assert row.irregular

    def test_irregular_flag_propriedade(self):
        r = ScanRow(target="proxy", model="m", ns_code=NS_CONFORME,
                    st_code=ST_FALA_ANTES)
        assert r.irregular
        r2 = ScanRow(target="proxy", model="m", ns_code=NS_CONFORME,
                     st_code=ST_SO_TOOLS)
        assert not r2.irregular

    def test_record_recebe_duas_evidencias_crus(self):
        ns = FakeResp(_resp(tool_calls=[_tc()], finish="tool_calls"),
                      text='{"ok":1}')
        raw = _sse([_delta_event(tool_calls=[
            {"index": 0, "function": {"arguments": "{}"}}]),
            _delta_event(finish="tool_calls")])
        st = FakeResp({}, text=raw)
        recs: list[dict] = []
        row = scan_model(_sender_for([ns, st]), "m1", record=recs.append)
        assert row.ns_code == NS_CONFORME
        assert [r["kind"] for r in recs] == ["nonstream", "stream"]
        assert recs[0]["raw_text"] == '{"ok":1}'
        assert recs[0]["status_code"] == 200
        assert recs[1]["raw_text"] == raw  # SSE integral, sem truncar
        assert all(r["model"] == "m1" for r in recs)

    def test_record_omitido_em_falha_de_transport(self):
        recs: list[dict] = []
        row = scan_model(_sender_for([Boom("down"), Boom("down")]), "m1",
                         record=recs.append)
        assert row.ns_code == NS_ERRO
        assert recs == []


class TestJsonlDumper:
    def test_escreve_linhas_jsonl_append(self, tmp_path: Path):
        import json as _json
        import eval.novai_tool_scan as ts
        p = tmp_path / "d.jsonl"
        rec = ts.jsonl_dumper(p)
        rec({"model": "a", "kind": "nonstream", "raw_text": "x"})
        rec({"model": "b", "kind": "stream", "raw_text": "y\n\n"})
        rec.handle.close()
        lines = p.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert _json.loads(lines[1])["raw_text"] == "y\n\n"
        # append: reabrir mantém as anteriores
        rec2 = ts.jsonl_dumper(p)
        rec2({"model": "c", "kind": "nonstream", "raw_text": "z"})
        rec2.handle.close()
        assert len(p.read_text(encoding="utf-8").splitlines()) == 3

    def test_run_scan_com_record_factory(self, monkeypatch, tmp_path: Path):
        import eval.novai_tool_scan as ts
        mcsv = tmp_path / "m.csv"
        mcsv.write_text(
            "group,modality,upstream_id,status,evidence,target,test_id,"
            "latency_ms,notes\n"
            "novai-a,chat,x,pass,,proxy,chat,1,\n", encoding="utf-8")
        monkeypatch.setattr(ts, "MATRIX_CSV", mcsv)
        ns = FakeResp(_resp(tool_calls=[_tc()], finish="tool_calls"),
                      text='{"choices":[]}')
        raw = _sse([_delta_event(tool_calls=[
            {"index": 0, "function": {"arguments": "{}"}}]),
            _delta_event(finish="tool_calls")])
        st = FakeResp({}, text=raw)
        calls = iter([ns, st])

        def sender(path, *, json_body=None, stream=False, method="POST", **kw):
            return next(calls)

        out = tmp_path / "logs" / "dump.jsonl"
        made: list = []

        def factory(t: str):
            rec = ts.jsonl_dumper(out)
            made.append(rec)
            return rec

        rows = ts.run_scan(["proxy"], sleep=0, limit=1,
                           sender_factory=lambda t: sender,
                           record_factory=factory,
                           progress=lambda s: None)
        for rec in made:
            rec.handle.close()
        assert len(rows) == 1
        import json as _json
        lines = [_json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
        assert [l["kind"] for l in lines] == ["nonstream", "stream"]
        assert lines[1]["raw_text"] == raw


class TestSaidas:
    def _rows(self):
        return [ScanRow("proxy", "m-ok", NS_CONFORME, "e", ST_SO_TOOLS, "e2"),
                ScanRow("gateway", "m-irr", NS_IRREGULAR, "fala", ST_FALA_ANTES,
                        "fala=4ch args=chunk_unico/ok finish=['tool_calls']")]

    def test_csv_roundtrip(self, tmp_path: Path):
        p = tmp_path / "s.csv"
        rows_to_csv(self._rows(), p)
        text = p.read_text(encoding="utf-8")
        assert "target,model,ns_code" in text
        assert "m-irr" in text and "sim" in text and "nao" in text

    def test_relatorio_markdown(self, tmp_path: Path):
        out = tmp_path / "r.md"
        md = build_report(self._rows(), out_path=out)
        assert "# S119" in md
        assert "⚠️ fala antes" in md
        assert "Irregularidades encontradas: **1 linhas**" in md
        assert out.exists()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
