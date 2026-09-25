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
