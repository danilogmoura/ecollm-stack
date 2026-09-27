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
    python -m mcpsrv.rag_server
Registros de cliente (exemplo) em mcpsrv/mcp.example.json.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Garante que o pacote `ingest` seja importavel quando o servidor e lancado por
# caminho absoluto (ex.: mcp.json do Roo aponta ".../mcpsrv/rag_server.py"), nao
# por `-m` a partir da raiz. Insere o repo root no sys.path antes de importar.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


# --- H3 (SPEC-H-HEADROOM-SEGURO): transformações PURAS na EMISSÃO -----------------
# Contrato de pureza (§2): sem relógio/random/locale/I-O/estado entre chamadas.
# Mesma entrada => mesmos bytes de saída, sempre (preserva prompt-cache C5 §6).
# Risco de cache = ZERO: age só no tool-result (Zona C, nasce agora), NUNCA toca
# instructions/description da tool (Zona A) nem a ordenação final (invariante 1).

# Cap de PROTEÇÃO (backstop), não de poda. Acima de TODO o corpus publicado hoje
# (max content observado = 2.089 B, H1), logo NO-OP no índice atual; só ativa se um
# ingest futuro publicar um outlier grande. Ajustável DENTRO da janela de Zona A
# (SPEC-H §6) se o corpus crescer. Code points, não bytes (não depende de locale).
CONTENT_CAP_CHARS = 4000

# Marcador FIXO appended quando trunc ativa. Só {n} varia (determinístico). Nunca
# contém relógio/UUID/locale. SPEC-H §3.1.
TRUNC_MARKER_FMT = "…[truncado {n} chars — consulte {loc}]"


def compact_content(content: str, loc: str, cap: int = CONTENT_CAP_CHARS) -> str:
    """Pura: teto de ``cap`` code points em ``content``, cortando na ÚLTIMA quebra de
    linha que caiba dentro de ``cap`` (preserva legibilidade; nunca corta no meio de
    uma linha de código). Se não houver '\\n' aproveitável dentro do teto, corta no
    char exato ``cap`` (fallback determinístico). Acrescenta marcador fixo.

    Retorna ``content`` inalterado (SEM marcador) quando ``len(content) <= cap`` —
    é o caso de TODO o corpus atual (no-op hoje, SPEC-H §3.2).
    """
    if len(content) <= cap:
        return content
    # Maior índice i <= cap tal que content[i] == '\n' (guarda o '\n'); senão i = cap.
    window = content[: cap + 1]
    nl = window.rfind("\n")
    i = nl if nl != -1 else cap
    retained = content[:i]
    n = len(content) - len(retained.rstrip("\n"))
    return retained.rstrip("\n") + "\n" + TRUNC_MARKER_FMT.format(n=n, loc=loc)


def dedupe_intra(out: list[dict]) -> list[dict]:
    """Pura: mantém a PRIMEIRA ocorrência de cada chunk, na ordem original. Identidade
    = (path, symbol, kind) + prefixo de content. No-op hoje (a fusão RRF de
    ingest.search já não repete chunk na mesma query); adotado como anti-regressão:
    se um dia a fusão mudar e produzir duplicata, a emissão remove a repetida
    mantendo a de maior score (a 1ª, pois RRF ordena por score) e a ORDEM intacta.
    Não reordena: só remove ocorrências repetidas posteriores (SPEC-H §5.1)."""
    seen: set[tuple] = set()
    result: list[dict] = []
    for hit in out:
        key = (hit.get("path"), hit.get("symbol"), hit.get("kind"),
               (hit.get("content") or "")[:200])
        if key in seen:
            continue
        seen.add(key)
        result.append(hit)
    return result


def hit_to_dict(h) -> dict:
    """Serializa um Hit da forma que o contrato da tool promete.

    Ordem dos campos CONGELADA (path, symbol, kind, score, source, content) — Python
    >=3.7 preserva ordem de inserção e json.dumps respeita (SPEC-H §2). Aplica o
    trunc puro (H3) ao content; não reordena nem muda contagem/score.
    """
    source = h.source()
    return {
        "path": h.path,
        "symbol": h.symbol,
        "kind": h.kind,
        "score": round(float(h.score), 6),
        "source": source,
        "content": compact_content(h.content, source),
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
    # S32-c (I8): qual ESPAÇO vetorial atendeu a consulta. Diagnóstico de "por que
    # os resultados mudaram?" — o perfil ativo (RAG_PROFILE > publicado > default)
    # decide tabela+dim+gate; só vai no log stderr, NUNCA no envelope p/ o agente
    # (preserva o contrato estável e o prompt-cache §4b-5).
    try:
        from ingest import profiles as _profiles  # noqa: PLC0415
        profile_used = _profiles.active_profile().slug
    except Exception:  # noqa: BLE001 — diagnóstico melhor-esforço, nunca derruba a tool
        profile_used = None
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
        out = dedupe_intra([hit_to_dict(h) for h in hits])
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
            "profile": profile_used,
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
        "presentes neste projeto; NAO a chame para edicao comum nem re-consulte o "
        "mesmo fato na mesma sessao. O backend devolve SEMPRE o top-k em ordem "
        "deterministica (score desc + desempate path/symbol/id) e NAO filtra por "
        "relevancia: quem decide 'NAO SEI' e o agente, lendo o score (RRF puro; "
        "~0,015-0,017 = nao relacionado). Preserve a ordem retornada ao citar "
        "chunks (reordenar zera o prompt-cache)."
    ),
)


@server.tool(
    name="rag_search",
    description=(
        "Busca semantica no indice do repositório. Usar quando a resposta depende "
        "de código, documentação ou decisões do projeto (retorna chunks com fonte: "
        "path, symbol, kind, score e conteúdo). Scores são RRF puro (~0,015-0,017 = "
        "não relacionado): aplique você o corte 'NÃO SEI'. Use k pequeno e filtre "
        "com kind/path_prefix para afunilar."
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
        return json.dumps({"error": str(exc), "results": []}, ensure_ascii=False,
                          separators=(",", ":"))
    payload: dict = {"results": results}
    # S14: se o indice pode estar desatualizado, sinaliza no envelope (sem quebrar
    # o contrato {results:[...]} — campo extra e retrocompativel).
    note = staleness_note()
    if note:
        payload["stale"] = True
        payload["notice"] = note
    # H3 (SPEC-H §4): envelope minificado — remove espaços após ',' e ':' (~2,5% do
    # envelope). Determinístico, transparente a json.loads; não muda semântica nem ordem.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
