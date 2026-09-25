"""Testes unitarios do servidor MCP rag_search (FASE 5) — sem DB/rede.

O nucleo (`run_search`) e testado com um `search` falso injetado; o handler da
tool e testado via `server.call_tool` (API oficial do MCPServer), validando que
a ferramenta esta registrada e devolve JSON no contrato do plano.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from ingest.search import Hit

# O diretorio do servidor chama-se `mcp` (nome travado no plano), que COLIDE com o
# pacote instalado do SDK `mcp`. Para importar nosso modulo sem quebrar os imports
# internos dele (`from mcp.server...` -> precisa ser o SDK), carregamos o arquivo
# por caminho sob um nome privado, SEM injeta-lo em sys.modules["mcp"].
_SERVER_PATH = Path(__file__).resolve().parents[1] / "rag_server.py"
_spec = importlib.util.spec_from_file_location("rag_server_under_test", _SERVER_PATH)
rag_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rag_server)


def _hit(path="ingest/search.py", symbol="search", kind="code", score=0.0321, content="def search(): ..."):
    return Hit(
        id="11111111-1111-1111-1111-111111111111", repo="ecollm-stack", path=path,
        lang="python", kind=kind, symbol=symbol, content=content, score=score,
        vec_rank=1, lex_rank=None,
    )


class FakeSearch:
    """Registra os kwargs recebidos e devolve hits fixos."""

    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def __call__(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.hits


# ---------------------------------------------------------------------------
# hit_to_dict — forma do payload prometida pelo contrato da tool
# ---------------------------------------------------------------------------

def test_hit_to_dict_campos_e_source():
    d = rag_server.hit_to_dict(_hit())
    assert set(d) == {"path", "symbol", "kind", "score", "source", "content"}
    assert d["path"] == "ingest/search.py"
    assert d["symbol"] == "search"
    assert d["kind"] == "code"
    assert d["source"] == "ingest/search.py::search [code]"
    assert d["score"] == pytest.approx(0.0321, abs=1e-6)


def test_hit_to_dict_score_arredondado():
    d = rag_server.hit_to_dict(_hit(score=0.0321456789))
    assert d["score"] == round(0.0321456789, 6)


# ---------------------------------------------------------------------------
# run_search — clamp de k, defaults, propagacao de filtros, erros
# ---------------------------------------------------------------------------

def test_run_search_retorna_lista_serializada(monkeypatch):
    fake = FakeSearch([_hit(), _hit(path="README.md", symbol=None, kind="doc")])
    monkeypatch.setattr(rag_server, "search", fake)
    out = rag_server.run_search("como funciona a busca", k=2, repo="r")
    assert isinstance(out, list) and len(out) == 2
    assert out[1]["source"] == "README.md [doc]"  # symbol None -> sem ::symbol


def test_run_search_final_k_recebe_k_apos_clamp(monkeypatch):
    fake = FakeSearch([])
    monkeypatch.setattr(rag_server, "search", fake)
    monkeypatch.setenv("RAG_REPO", "meu-repo")
    rag_server.run_search("x", k=999)
    _, kw = fake.calls[0]
    assert kw["final_k"] == rag_server.MAX_K
    assert kw["repo"] == "meu-repo"  # default vem de RAG_REPO


def test_run_search_clamp_k_minimo(monkeypatch):
    fake = FakeSearch([])
    monkeypatch.setattr(rag_server, "search", fake)
    rag_server.run_search("x", k=0, repo="r")
    assert fake.calls[0][1]["final_k"] == 1


def test_run_search_propaga_kind_e_path_prefix(monkeypatch):
    fake = FakeSearch([])
    monkeypatch.setattr(rag_server, "search", fake)
    rag_server.run_search("x", k=5, repo="r", kind="code", path_prefix="ingest/")
    _, kw = fake.calls[0]
    assert kw["kind"] == "code"
    assert kw["path_prefix"] == "ingest/"


def test_run_search_query_vazia_levanta(monkeypatch):
    monkeypatch.setattr(rag_server, "search", FakeSearch([]))
    with pytest.raises(ValueError):
        rag_server.run_search("   ", k=3)


# ---------------------------------------------------------------------------
# S22 — log estruturado de observabilidade (query, k, latência, n resultados)
# ---------------------------------------------------------------------------

def _capture_stderr(monkeypatch):
    """Instala um coletor no lugar de sys.stderr.write do módulo sob teste."""
    lines: list[str] = []
    monkeypatch.setattr(rag_server.sys.stderr, "write", lambda s: lines.append(s))
    return lines


def test_log_estruturado_campos_obrigatorios(monkeypatch):
    lines = _capture_stderr(monkeypatch)
    fake = FakeSearch([_hit(), _hit()])
    monkeypatch.setattr(rag_server, "search", fake)
    rag_server.run_search("gitleaks gate", k=4, repo="r")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event"] == "rag_search"
    assert rec["query"] == "gitleaks gate"
    assert rec["k"] == 4
    assert rec["n_results"] == 2
    assert isinstance(rec["latency_ms"], (int, float)) and rec["latency_ms"] >= 0
    assert rec["status"] == "ok"
    assert rec["slo_ms"] == rag_server.SLO_LATENCY_MS
    assert rec["slo_breach"] is (rec["latency_ms"] > rag_server.SLO_LATENCY_MS)


def test_log_registra_erro_e_propaga(monkeypatch):
    lines = _capture_stderr(monkeypatch)

    def boom(query, **kwargs):
        raise RuntimeError("db fora do ar")

    monkeypatch.setattr(rag_server, "search", boom)
    with pytest.raises(RuntimeError):
        rag_server.run_search("x", k=3, repo="r")
    rec = json.loads(lines[0])
    assert rec["status"].startswith("error:")
    assert rec["n_results"] == 0


def test_log_nao_vaza_para_stdout(monkeypatch):
    # o canal MCP (stdout) deve permanecer limpo; só stderr recebe o log
    out_lines: list[str] = []
    monkeypatch.setattr(rag_server.sys.stdout, "write", lambda s: out_lines.append(s))
    _capture_stderr(monkeypatch)
    monkeypatch.setattr(rag_server, "search", FakeSearch([_hit()]))
    rag_server.run_search("oi", k=1, repo="r")
    assert out_lines == []


def test_log_trunca_query_longa(monkeypatch):
    lines = _capture_stderr(monkeypatch)
    monkeypatch.setattr(rag_server, "search", FakeSearch([]))
    rag_server.run_search("q" * 500, k=2, repo="r")
    rec = json.loads(lines[0])
    assert len(rec["query"]) <= 200


# ---------------------------------------------------------------------------
# registro + invocacao da tool pela API oficial do MCPServer
# (sem pytest-asyncio: dirigimos o event loop com asyncio.run nos proprios testes)
# ---------------------------------------------------------------------------

def test_tool_registrada_com_descricao():
    tools = asyncio.run(rag_server.server.list_tools())
    names = {t.name for t in tools}
    assert "rag_search" in names
    tool = next(t for t in tools if t.name == "rag_search")
    assert "busca semantica" in tool.description.lower()
    schema = tool.input_schema
    assert "query" in schema["properties"]
    assert "k" in schema["properties"]


def test_call_tool_devolve_json_results(monkeypatch):
    fake = FakeSearch([_hit()])
    monkeypatch.setattr(rag_server, "search", fake)
    res = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "oi", "k": 3}))
    assert res.is_error is False
    payload = json.loads(res.content[0].text)
    assert payload["results"][0]["path"] == "ingest/search.py"


def test_call_tool_erro_vira_payload_sem_crash(monkeypatch):
    def boom(query, **kwargs):
        raise RuntimeError("db fora do ar")
    monkeypatch.setattr(rag_server, "search", boom)
    res = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "x"}))
    payload = json.loads(res.content[0].text)
    assert payload["results"] == []
    assert "db fora do ar" in payload["error"]


# ---------------------------------------------------------------------------
# S14 — envelope traz aviso de desatualizacao (campo extra retrocompativeis)
# ---------------------------------------------------------------------------

def test_envelope_sem_stale_quando_fresco(monkeypatch):
    fake = FakeSearch([_hit()])
    monkeypatch.setattr(rag_server, "search", fake)
    monkeypatch.setattr(rag_server, "staleness_note", lambda repo=None: None)
    res = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "oi"}))
    payload = json.loads(res.content[0].text)
    assert "stale" not in payload and "notice" not in payload
    assert payload["results"][0]["path"] == "ingest/search.py"


def test_envelope_com_stale_quando_desatualizado(monkeypatch):
    fake = FakeSearch([_hit()])
    monkeypatch.setattr(rag_server, "search", fake)
    monkeypatch.setattr(
        rag_server, "staleness_note",
        lambda repo=None: "[aviso] indice pode estar desatualizado — HEAD mudou")
    res = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "oi"}))
    payload = json.loads(res.content[0].text)
    assert payload["stale"] is True
    assert "HEAD mudou" in payload["notice"]
    # contrato base preservado mesmo com o campo extra
    assert payload["results"][0]["path"] == "ingest/search.py"


def test_staleness_note_nunca_levanta(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db fora")
    monkeypatch.setattr("ingest.search.staleness_warning", boom)
    # deve retornar None (ou string), jamais propagar exceção
    out = rag_server.staleness_note()
    assert out is None or isinstance(out, str)
