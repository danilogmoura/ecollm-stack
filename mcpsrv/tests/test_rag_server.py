"""Testes unitarios do servidor MCP rag_search (FASE 5) — sem DB/rede.

O nucleo (`run_search`) e testado com um `search` falso injetado; o handler da
tool e testado via `server.call_tool` (API oficial do MCPServer), validando que
a ferramenta esta registrada e devolve JSON no contrato do plano.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ingest.search import Hit

# O pacote do servidor chama-se `mcpsrv` (nao `mcp`) para nao colidir com o SDK
# instalado `mcp` — assim o import direto resolve os `from mcp.server...` internos
# sem nenhum workaround (BUG-008 resolvido em S25/T-ENV-4).
import mcpsrv.rag_server as rag_server


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


def test_run_search_final_k_recebe_profundidade_apos_clamp(monkeypatch):
    # S37: final_k enviado ao search() e a PROFUNDIDADE interna
    # max(k, SEARCH_DEPTH), nao o k emitido. Com k=999 -> clamp MAX_K (>= depth).
    fake = FakeSearch([])
    monkeypatch.setattr(rag_server, "search", fake)
    monkeypatch.setenv("RAG_REPO", "meu-repo")
    rag_server.run_search("x", k=999)
    _, kw = fake.calls[0]
    assert kw["final_k"] == rag_server.MAX_K
    assert kw["repo"] == "meu-repo"  # default vem de RAG_REPO


def test_run_search_busca_profundidade_minima_e_emite_k(monkeypatch):
    # S37 coracao: p/ k pequeno, busca SEARCH_DEPTH mas EMITE so k (fatiamento).
    hits = [_hit(path=f"p{i}.py", symbol=f"s{i}") for i in range(12)]
    fake = FakeSearch(hits)
    monkeypatch.setattr(rag_server, "search", fake)
    out = rag_server.run_search("x", k=3, repo="r")
    _, kw = fake.calls[0]
    # profundidade pedida = max(3, SEARCH_DEPTH=8) = 8 (mantem ranking canônico)
    assert kw["final_k"] == rag_server.SEARCH_DEPTH
    # emissao truncada no k pedido
    assert len(out) == 3


def test_run_search_clamp_k_minimo(monkeypatch):
    fake = FakeSearch([])
    monkeypatch.setattr(rag_server, "search", fake)
    rag_server.run_search("x", k=0, repo="r")
    # k e clampado a 1 (emitido), mas a BUSCA vai ate a profundidade minima.
    assert fake.calls[0][1]["final_k"] == rag_server.SEARCH_DEPTH


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
    fake = FakeSearch([_hit(), _hit(path="README.md", symbol=None, kind="doc")])
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


# ---------------------------------------------------------------------------
# S37 (opcao 2) — DEFAULT_K so quando o cliente OMITE k; schema Zona A estavel
# ---------------------------------------------------------------------------

def _call_with_request_ctx(args: dict):
    """Invoca a tool pelo ToolManager com um Context que tem request_context real.

    Simula o despacho MCP de verdade (params.arguments brutos), permitindo ao
    _k_omitido distinguir 'cliente nao mandou k' de 'mandou k=8 explicito'.
    """
    from types import SimpleNamespace
    from mcp.server.mcpserver.context import Context

    class RC:
        def __init__(self, a):
            self.params = SimpleNamespace(arguments=a)

    ctx = Context(request_context=RC(args), mcp_server=rag_server.server)
    return asyncio.run(
        rag_server.server._tool_manager.call_tool(
            "rag_search", args, ctx, convert_result=True
        )
    )


def _many_hits(n=12):
    return [_hit(path=f"p{i}.py", symbol=f"s{i}", score=1.0 / (i + 1)) for i in range(n)]


def test_s37_schema_k_nao_muda_zona_a():
    # Invariante: assinatura permanece literal `k: int = 8`; schema exposto e
    # byte-identico ao historico (default 8, integer) => zero reconstrucao de cache.
    tools = asyncio.run(rag_server.server.list_tools())
    tool = next(t for t in tools if t.name == "rag_search")
    kprop = tool.input_schema["properties"]["k"]
    assert kprop == {"default": 8, "title": "K", "type": "integer"}
    assert "ctx" not in tool.input_schema["properties"]  # Context NAO e exposto


def test_s37_k_omitido_emite_default_k(monkeypatch):
    fake = FakeSearch(_many_hits())
    monkeypatch.setattr(rag_server, "search", fake)
    res = _call_with_request_ctx({"query": "x", "repo": "r"})
    payload = json.loads(res.content[0].text)
    assert len(payload["results"]) == rag_server.DEFAULT_K
    # busca vai ate SEARCH_DEPTH (ranking canônico preservado)
    assert fake.calls[0][1]["final_k"] == max(rag_server.DEFAULT_K, rag_server.SEARCH_DEPTH)


def test_s37_k_exPLICITO_respeitado_mesmo_maior_que_default(monkeypatch):
    # Quem pede k=8 recebe 8 (nao e truncado ao DEFAULT_K); omitir != pedir 8.
    fake = FakeSearch(_many_hits())
    monkeypatch.setattr(rag_server, "search", fake)
    res = _call_with_request_ctx({"query": "x", "repo": "r", "k": 8})
    payload = json.loads(res.content[0].text)
    assert len(payload["results"]) == 8


def test_s37_k_exPLICITO_menor_que_default_respeitado(monkeypatch):
    fake = FakeSearch(_many_hits())
    monkeypatch.setattr(rag_server, "search", fake)
    res = _call_with_request_ctx({"query": "x", "repo": "r", "k": 3})
    payload = json.loads(res.content[0].text)
    assert len(payload["results"]) == 3


def test_s37_default_k_config_via_env(monkeypatch):
    # RAG_DEFAULT_K ajusta a emissao sem tocar codigo (mesmo padrao de RAG_REPO).
    monkeypatch.setattr(rag_server, "DEFAULT_K", 4)
    fake = FakeSearch(_many_hits())
    monkeypatch.setattr(rag_server, "search", fake)
    res = _call_with_request_ctx({"query": "x", "repo": "r"})
    payload = json.loads(res.content[0].text)
    assert len(payload["results"]) == 4


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


# ---------------------------------------------------------------------------
# H3 (SPEC-H-HEADROOM-SEGURO §8) — golden-file tests das transformações PURAS
# na EMISSÃO: trunc de content, envelope minificado, dedupe intra. Todos sem
# DB/rede; nenhum pode exigir mudança de ordem/score/n_results (invariante 1).
# ---------------------------------------------------------------------------

def test_compact_content_fronteira_de_linha():
    """cap no meio de uma linha => corta na ÚLTIMA quebra que caiba, marcador com n."""
    content = "linha1\nlinha2\nlinha3-longa-alem-do-cap\nfim"
    cap = len("linha1\nlinha2\n")  # teto cai logo após a 2ª linha
    out = rag_server.compact_content(content, "x/y.py::f [code]", cap=cap)
    assert out.startswith("linha1\nlinha2")
    assert "linha3-longa" not in out
    assert "…[truncado" in out and "consulte x/y.py::f [code]" in out
    # n = code points removidos (content inteiro menos o retido sem \\n trailing)
    esperado_n = len(content) - len("linha1\nlinha2")
    assert f"truncado {esperado_n} chars" in out


def test_compact_content_sem_corte_quando_cabe():
    """len <= cap => saída IDÊNTICA, sem marcador (é TODO o corpus atual)."""
    content = "def search():\n    return hits\n"
    out = rag_server.compact_content(content, "a.py::b [code]", cap=4000)
    assert out == content
    assert "truncado" not in out


def test_compact_content_linha_unica_longa():
    """sem '\\n' dentro do cap => corte exato em cap + marcador (fallback puro)."""
    content = "x" * 5000  # uma única linha, sem newline
    cap = 100
    out = rag_server.compact_content(content, "big.log [doc]", cap=cap)
    assert out.startswith("x" * 100)
    assert "y" not in out
    assert "…[truncado 4900 chars — consulte big.log [doc]]" in out


def test_compact_content_deterministica():
    """mesma entrada N vezes => bytes idênticos (contrato de pureza §2)."""
    content = ("a" * 3000 + "\n" + "b" * 3000 + "\n" + "c" * 3000)
    results = {rag_server.compact_content(content, "m.py::f [code]", cap=4000)
               for _ in range(20)}
    assert len(results) == 1  # todas as 20 saídas iguais


def test_compact_content_noop_no_corpus_atual():
    """content típico (<= 2.089 B) com cap=4000 => intocado (no-op hoje, §3.2)."""
    content = "z" * 2089
    out = rag_server.compact_content(content, "f.py::g [code]")
    assert out == content


def test_envelope_bytes_identico_entre_execucoes(monkeypatch):
    """rag_search 2x com mesmos hits => res.content[0].text byte-idêntico."""
    fake = FakeSearch([_hit(), _hit(path="README.md", symbol=None, kind="doc")])
    monkeypatch.setattr(rag_server, "search", fake)
    monkeypatch.setattr(rag_server, "staleness_note", lambda repo=None: None)
    a = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "q", "k": 2}))
    b = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "q", "k": 2}))
    assert a.content[0].text == b.content[0].text


def test_envelope_minificado_sem_espacos(monkeypatch):
    """saída contém 'results':[{'path'... sem espaço após ':' e ',' (§4)."""
    fake = FakeSearch([_hit()])
    monkeypatch.setattr(rag_server, "search", fake)
    monkeypatch.setattr(rag_server, "staleness_note", lambda repo=None: None)
    res = asyncio.run(rag_server.server.call_tool("rag_search", {"query": "oi"}))
    text = res.content[0].text
    assert '{"results":[{"path"' in text
    # não há ', ' nem ': ' estruturais (só dentro de strings de content, aqui simples)
    assert '", "' not in text
    json.loads(text)  # continua JSON válido p/ todos os testes existentes


def test_ordem_campos_congelada():
    """list(hit.keys()) == [path,symbol,kind,score,source,content] (§2)."""
    d = rag_server.hit_to_dict(_hit())
    assert list(d.keys()) == ["path", "symbol", "kind", "score", "source", "content"]


def test_dedupe_intra_noop_sem_duplicata():
    """hits únicos => saída igual (anti-regressão, §5.1)."""
    hits = [{"path": "a.py", "symbol": "f", "kind": "code", "content": "aaa"},
            {"path": "b.py", "symbol": "g", "kind": "code", "content": "bbb"}]
    assert rag_server.dedupe_intra(hits) == hits


def test_dedupe_intra_remove_duplicata_preserva_ordem():
    """duplicata => mantém 1ª (maior score), remove 2ª, ORDEM intacta (§5.1)."""
    h = {"path": "a.py", "symbol": "f", "kind": "code", "content": "aaa"}
    dup = [h, {"path": "z.py", "symbol": "q", "kind": "code", "content": "zzz"}, dict(h)]
    out = rag_server.dedupe_intra(dup)
    assert out == [h, {"path": "z.py", "symbol": "q", "kind": "code", "content": "zzz"}]
    assert len(out) == 2


def test_trunc_preserva_contagem_e_ordem(monkeypatch):
    """run_search com trunc ativo => n_results e ordem INALTERADOS, só content muda."""
    long_a = _hit(path="a.py", symbol="fa", score=0.03, content=("L1\n" * 3000)[:6000])
    long_b = _hit(path="b.py", symbol="fb", score=0.02, content=("M1\n" * 3000)[:6000])
    fake = FakeSearch([long_a, long_b])
    monkeypatch.setattr(rag_server, "search", fake)
    # patcha a FUNÇÃO (o default do parâmetro cap congela na def, então mudar só a
    # constante nao bastaria); wrapper chama a função real com cap pequeno => trunc ativo.
    real_compact = rag_server.compact_content
    monkeypatch.setattr(
        rag_server, "compact_content",
        lambda content, loc, cap=100: real_compact(content, loc, 100),
    )
    out = rag_server.run_search("q", k=2, repo="r")
    assert len(out) == 2  # contagem preservada
    assert [o["path"] for o in out] == ["a.py", "b.py"]  # ordem preservada
    assert all("…[truncado" in o["content"] for o in out)  # só content mudou


def test_marcador_contem_source():
    """marcador contém o source() do hit (path#symbol) (§3.1)."""
    content = "q" * 5000
    loc = "mod.py::fun [code]"
    out = rag_server.compact_content(content, loc, cap=100)
    assert loc in out
