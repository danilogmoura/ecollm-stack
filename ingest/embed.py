"""Embedder da FASE 2 — texto -> vetor via LiteLLM (rag-embeddings).

Regras travadas no plano (.planning/PLANO-RAG.md §1, §3 FASE 2):
  - Embedder SÓ Google: grupo `rag-embeddings` = gemini-embedding-2, 3072d.
    Trocar embedder = re-embedar TUDO; por isso NAO ha fallback aqui (um vetor
    de outro espaco corromperia o indice unico).
  - Task-prefix ASSIMETRICO aplicado AQUI, no texto ANTES do embed:
      docs/config -> "task: code retrieval | doc: <conteudo>"
      queries     -> "task: code retrieval | query: <conteudo>"
    O chunk guarda texto PURO (content_hash e do puro); o prefixo so existe na
    hora de embedar. Validado no demo /tmp/rag_demo.py e na memoria do repo.
  - Batches de 32 textos (limite pratico Gemini), retry 3x com backoff
    exponencial, timeout 60s por request.
  - Cache Redis do proxy (escopo deliberado = so aembedding) faz re-ingest ser
    barato: mesmo texto -> mesmo vetor -> hit. Batch/retry/dedupe NAO afetam o
    cache (vetor e funcao deterministica do texto embedado — plano 4b-5).

Sem framework de RAG: stdlib + requests. Config lida do ambiente (.env no repo
root carregado por ingest/cli; ver _load_env).
"""

from __future__ import annotations

import base64
import os
import struct
import time
from typing import Callable, Sequence

import requests

# ---------------------------------------------------------------------------
# Defaults de configuracao (override por env)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:4000/v1"
DEFAULT_MODEL = "rag-embeddings"
DEFAULT_DIM = 3072
BATCH_SIZE = 32          # limite pratico Gemini (plano §3 FASE 2)
MAX_RETRIES = 3          # tentativas por batch
BACKOFF_BASE = 1.5       # segundos; dobra a cada retry (exponencial)
TIMEOUT_S = 60           # timeout por request HTTP

TASK_PREFIX_DOC = "task: code retrieval | doc: "
TASK_PREFIX_QUERY = "task: code retrieval | query: "


class EmbedError(RuntimeError):
    """Falha definitiva ao obter embeddings (apos esgotar retries)."""


def load_dotenv(path: str | os.PathLike | None = None) -> None:
    """Carrega KEY=VALUE de um .env no processo (sem sobrescrever o que ja existe).

    Minimo, sem dependencia externa: ignora comentarios e linhas vazias, aceita
    aspas opcionais no valor. Ja exportado no ambiente > valor do arquivo.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def config_from_env() -> dict:
    """Parametros de conexao do embedder a partir do ambiente (com defaults)."""
    load_dotenv()
    return {
        "base_url": os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.environ.get("RAG_EMBED_MODEL", DEFAULT_MODEL),
        "api_key": os.environ.get("LITELLM_MASTER_KEY", ""),
        "dim": int(os.environ.get("RAG_EMBED_DIM", DEFAULT_DIM)),
    }


# ---------------------------------------------------------------------------
# task-prefix assimetrico
# ---------------------------------------------------------------------------

def apply_prefix(text: str, kind: str) -> str:
    """Aplica o prefixo de tarefa conforme o tipo do chunk.

    code|doc|config usam o rotulo "doc:" (lado documento da busca assimetrica);
    apenas uma QUERY de busca usa "query:". Tudo que sai daqui e embedado como
    documento. A ordem (prefixo antes do texto) e o que casa com o validado no
    demo — nao mexer sem re-validar recall.
    """
    if kind == "query":
        return TASK_PREFIX_QUERY + text
    return TASK_PREFIX_DOC + text


# ---------------------------------------------------------------------------
# serializacao halfvec (compatível com pgvector)
# ---------------------------------------------------------------------------

def vector_to_halfvec_text(vec: Sequence[float]) -> str:
    """Vetor float -> literal text do pgvector `halfvec`.

    meio mais compacto e sem perda relevante p/ ranking (erro fp16 ~1e-3 <<
    ruido do proprio embedder — BUG-001). O formato aceito pelo cast
    `?::halfvec(3072)` e identico ao de `vector`: "[f1,f2,...]".
    """
    dims = len(vec)
    parts = [f"{float(x):.6g}" for x in vec]
    return "[" + ",".join(parts) + "]"


def halfvec_bytes(vec: Sequence[float]) -> bytes:
    """Vetor -> bytes wire-format halfvec (BTree/binary), para quem preferir."""
    head = struct.pack(">HH", len(vec), 1)  # n_dims, n_unused
    body = b"".join(struct.pack(">e", float(x)) for x in vec)
    return head + body


# ---------------------------------------------------------------------------
# cliente de embeddings
# ---------------------------------------------------------------------------

def _post_batch(texts: Sequence[str], cfg: dict, session: requests.Session) -> list[list[float]]:
    """Um POST /v1/embeddings com um lote de textos; retorna os vetores na ordem."""
    url = f"{cfg['base_url']}/embeddings"
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    payload = {"model": cfg["model"], "input": list(texts)}
    resp = session.post(url, json=payload, headers=headers, timeout=TIMEOUT_S)
    if resp.status_code != 200:
        raise EmbedError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    items = sorted(data["data"], key=lambda d: d.get("index", 0))
    vecs = [it["embedding"] for it in items]
    if len(vecs) != len(texts):
        raise EmbedError(f"resposta com {len(vecs)} vetores p/ {len(texts)} textos")
    for v in vecs:
        if len(v) != cfg["dim"]:
            raise EmbedError(f"dimensao inesperada: {len(v)} != {cfg['dim']}")
    return vecs


def embed_texts(
    texts: Sequence[str],
    *,
    cfg: dict | None = None,
    batch_size: int = BATCH_SIZE,
    max_retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
    post: Callable[[Sequence[str], dict, requests.Session], list[list[float]]] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Embeda uma lista de textos em lotes, com retry/backoff exponencial.

    Ordem preservada: out[i] corresponde a texts[i]. Falha definitiva apos
    `max_retries` levantando EmbedError (o orquestrador decide abortar).
    `post` e injetavel p/ testes (mock sem rede).
    """
    if cfg is None:
        cfg = config_from_env()
    _post = post or _post_batch
    out: list[list[float]] = []
    total = len(texts)
    with requests.Session() as session:
        for start in range(0, total, batch_size):
            batch = list(texts[start:start + batch_size])
            attempt = 0
            while True:
                try:
                    vecs = _post(batch, cfg, session)
                    out.extend(vecs)
                    break
                except (EmbedError, requests.RequestException) as exc:
                    attempt += 1
                    if attempt >= max_retries:
                        raise EmbedError(
                            f"batch @{start} falhou apos {max_retries} tentativas: {exc}"
                        ) from exc
                    delay = BACKOFF_BASE * (2 ** (attempt - 1))
                    sleep(delay)
            if on_progress:
                on_progress(len(out), total)
    return out


def embed_documents(
    chunks_textos: Sequence[tuple[str, str]],
    **kwargs,
) -> list[list[float]]:
    """Conveniencia: [(texto, kind)] -> aplica prefixo -> embeda.

    Aplica apply_prefix sobre cada texto conforme o kind ANTES de embedar, mas
    NUNCA altera o texto original (content_hash e do puro — decisao do plano).
    """
    prefixed = [apply_prefix(t, k) for t, k in chunks_textos]
    return embed_texts(prefixed, **kwargs)
