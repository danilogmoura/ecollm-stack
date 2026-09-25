"""FASE 5 — servidor MCP `rag_search` (stdio).

Expoe a busca hibrida da FASE 3 (ingest.search) como uma *tool* MCP para que um
agente (Roo Code / Copilot / qualquer cliente stdio MCP) consulte o indice do
repositorio e receba chunks com fonte.

Contrato da tool (plano .planning/PLANO-RAG.md §3 FASE 5):
    rag_search(query: str, k: int = 8) -> JSON {"results": [{path, symbol, kind, score, source, content}]}
    (em erro: {"error": str, "results": []}). O envelope {"results": [...]} e
    deliberado: deixa espaco p/ metadados futuros sem quebrar o contrato do cliente.

Decisoes travadas no plano:
  - Reusa ingest.search.search() tal qual: mesma fusao RRF e MESMA ordenacao
    final deterministica (score desc + desempate path/symbol/id). Isso preserva
    o prefixo estavel exigido pelo prompt cache do agente (§4b-5 / regra 4b-6).
  - Sem framework de RAG: so o SDK oficial `mcp` (MCPServer) em volta da funcao.
  - `repo` vem de RAG_REPO (default = nome do diretorio do repo root), o mesmo
    identificador gravado pelo ingest (ingest.repo_name). Config/env do DB e do
    LiteLLM sao lidos por ingest.embed.load_dotenv() a partir do .env da raiz.

Rodar (stdio):
    python -m mcp.rag_server
Registros de cliente (exemplo) em mcp/mcp.example.json.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Garante que o pacote `ingest` seja importavel quando o servidor e lancado por
# caminho absoluto (ex.: mcp.json do Roo aponta ".../mcp/rag_server.py"), nao por
# `-m` a partir da raiz. Insere o repo root no sys.path antes de importar ingest.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Este diretorio chama-se `mcp` (nome travado no plano), o que COLIDE com o pacote
# instalado do SDK `mcp`. Quando este modulo e importado como arquivo solto (por
# caminho, ou sob pytest com rootdir no sys.path), `import mcp` pode resolver para
# NOSSO pacote em vez do SDK. Resolvemos carregando o SDK REAL explicitamente pelo
# file loader e registrando-o em sys.modules["mcp"] ANTES de qualquer `from mcp...`.
# Assim os imports abaixo funcionam em todos os modos de execucao
# (`python -m mcp.rag_server`, por caminho, e testes).
def _ensure_real_mcp_sdk() -> None:
    cur = sys.modules.get("mcp")
    if cur is not None and hasattr(cur, "server"):
        return  # ja e o SDK real
    import importlib.util
    from pathlib import Path as _P

    here = str(REPO_ROOT)
    real = None
    for entry in sys.path:
        try:
            base = _P(entry if entry else ".").resolve()
            cand = base / "mcp" / "__init__.py"
            if cand.is_file() and str(base) != here:
                real = cand
                break
        except OSError:
            continue
    if real is None:
        raise ImportError("SDK 'mcp' (Model Context Protocol) nao encontrado")
    spec = importlib.util.spec_from_file_location(
        "mcp", str(real), submodule_search_locations=[str(real.parent)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["mcp"] = module
    spec.loader.exec_module(module)


_ensure_real_mcp_sdk()

from mcp.server.mcpserver import MCPServer  # noqa: E402

from ingest import embed  # noqa: E402
from ingest.ingest import repo_name  # noqa: E402
from ingest.search import search  # noqa: E402

# Carrega RAG_DB_URL / LITELLM_* do .env da raiz (idempotente; nao sobrescreve o
# que ja estiver exportado no ambiente do processo).
embed.load_dotenv()

MAX_K = 50  # teto defensivo p/ nao despejar contexto demais no prompt do agente

# SLO de latência da busca (S22 / T-OPS-4): a parte DB do rag_search mede ~1-6 ms
# morno; o orçamento <200 ms cobre a ida ao embedder da QUERY quando o cliente não
# injeta qvec. Medir: o log estruturado abaixo traz latency_ms por chamada — um
# `grep '"event": "rag_search"' stderr.log | jq .latency_ms` dá a distribuição;
# p/ p95, `sort -n | awk '{a[NR]=$1} END{print a[int(NR*0.95)+1]}'`.
SLO_LATENCY_MS = 200


def _log_line(obj: dict) -> None:
    """Escreve UMA linha JSON em stderr (S22). Nunca levanta: observabilidade não
    pode derrubar a tool. stdout é reservado ao protocolo MCP (stdio), por isso o
    log vai para stderr/arquivo, nunca para o canal da conversa."""
    try:
        sys.stderr.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001 — logging best-effort
        pass


def _default_repo() -> str:
    return os.environ.get("RAG_REPO") or repo_name(REPO_ROOT)


def hit_to_dict(h) -> dict:
    """Serializa um Hit da forma que o contrato da tool promete."""
    return {
        "path": h.path,
        "symbol": h.symbol,
        "kind": h.kind,
        "score": round(float(h.score), 6),
        "source": h.source(),
        "content": h.content,
    }


def run_search(
    query: str,
    k: int = 8,
    *,
    repo: str | None = None,
    kind: str | None = None,
    path_prefix: str | None = None,
) -> list[dict]:
    """Nucleo testavel: busca hibrida e retorna a lista de chunks serializada.

    Separado do decorator MCP p/ permitir testes unitarios sem subir o servidor.
    """
    if not query or not query.strip():
        raise ValueError("query vazia")
    k = max(1, min(int(k), MAX_K))
    repo_used = repo or _default_repo()
    t0 = time.perf_counter()
    status = "ok"
    n = 0
    try:
        hits = search(
            query.strip(),
            repo=repo_used,
            kind=kind,
            path_prefix=path_prefix,
            final_k=k,
        )
        out = [hit_to_dict(h) for h in hits]
        n = len(out)
        return out
    except Exception as exc:  # noqa: BLE001 — registra e propaga (caller vira payload)
        status = f"error:{type(exc).__name__}"
        raise
    finally:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        _log_line({
            "event": "rag_search",
            "ts": round(time.time(), 3),
            "repo": repo_used,
            "query": query.strip()[:200],
            "k": k,
            "kind": kind,
            "path_prefix": path_prefix,
            "n_results": n,
            "latency_ms": latency_ms,
            "slo_ms": SLO_LATENCY_MS,
            "slo_breach": latency_ms > SLO_LATENCY_MS,
            "status": status,
        })


def staleness_note(repo: str | None = None) -> str | None:
    """S14: mensagem de indice desatualizado (ou None se fresco). Nunca levanta."""
    try:
        from ingest import search as _search
        return _search.staleness_warning(REPO_ROOT, repo or _default_repo())
    except Exception:  # noqa: BLE001 — frescor é melhor-esforço, nunca derruba a tool
        return None


server = MCPServer(
    name="rag-search",
    instructions=(
        "Busca semantica (hibrida: vetorial + lexica) no indice do repositorio. "
        "Use rag_search quando a resposta depender de codigo, docs ou decisoes "
        "presentes neste projeto."
    ),
)


@server.tool(
    name="rag_search",
    description=(
        "Busca semantica no indice do repositório. Usar quando a resposta depende "
        "de código, documentação ou decisões do projeto (retorna chunks com fonte: "
        "path, symbol, kind, score e conteúdo)."
    ),
)
async def rag_search(
    query: str,
    k: int = 8,
    kind: str | None = None,
    path_prefix: str | None = None,
) -> str:
    """Retorna top-k chunks relevantes como JSON (string), prontos p/ o agente citar.

    Args:
        query: pergunta ou termo de busca (linguagem natural ou identificadores).
        k: numero de chunks a retornar (1..50, default 8).
        kind: filtro opcional por tipo de conteudo (code|doc|config).
        path_prefix: filtro opcional por prefixo de caminho (ex.: "ingest/").
    """
    try:
        results = run_search(
            query, k, repo=None, kind=kind, path_prefix=path_prefix
        )
    except Exception as exc:  # noqa: BLE001 — erro vira payload p/ o agente, nao crash
        return json.dumps({"error": str(exc), "results": []}, ensure_ascii=False)
    payload: dict = {"results": results}
    # S14: se o indice pode estar desatualizado, sinaliza no envelope (sem quebrar
    # o contrato {results:[...]} — campo extra e retrocompativel).
    note = staleness_note()
    if note:
        payload["stale"] = True
        payload["notice"] = note
    return json.dumps(payload, ensure_ascii=False)


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
