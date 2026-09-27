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

from . import profiles as _profiles

# ---------------------------------------------------------------------------
# Defaults de configuracao (override por env)
# ---------------------------------------------------------------------------

# DEFAULT_BASE_URL/DEFAULT_MODEL/DEFAULT_DIM/BATCH_SIZE sao o perfil `gemini`
# legado — preservados p/ compat com imports antigos. A fonte canonica agora e o
# registry (ingest/profiles.py); config_for_profile() deriva destes valores.
DEFAULT_BASE_URL = _profiles.DEFAULT_BASE_URL
DEFAULT_MODEL = _profiles.PROFILES["gemini"].model
DEFAULT_DIM = _profiles.PROFILES["gemini"].dim
BATCH_SIZE = 32          # limite pratico historico (plano §3 FASE 2); por perfil via registry
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


def config_for_profile(profile: "_profiles.Profile") -> dict:
    """Parametros de conexao DO PERFIL (base_url/model/key/dim), com override por env.

    base_url/api_key continuam vindo do ambiente (sao globais ao proxy LiteLLM —
    todos os perfis falam OpenAI-compat /embeddings no MESMO proxy).

    model/dim tem o REGISTRY como fonte canonica (S32). RAG_EMBED_MODEL/RAG_EMBED_DIM
    sao overrides LEGADOS que se aplicam SOMENTE ao perfil default (`gemini`) — e
    preservam o comportamento historico do .env p/ esse perfil. Para um perfil nao-
    default, um RAG_EMBED_MODEL antigo (ex.: 'rag-embeddings' do .env) NAO deve
    sobrescrever o modelo do espaco (senão embedaríamos qwen37 no alias Gemini, com
    dim errada). Assim trocar de perfil troca modelo+dim de fato, sem editar .env.
    """
    load_dotenv()
    is_default = profile.slug == _profiles.DEFAULT_PROFILE
    model = profile.model
    dim = profile.dim
    if is_default:
        model = os.environ.get("RAG_EMBED_MODEL", profile.model)
        dim = int(os.environ.get("RAG_EMBED_DIM", profile.dim))
    return {
        "base_url": os.environ.get("LITELLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": model,
        "api_key": os.environ.get("LITELLM_MASTER_KEY", ""),
        "dim": dim,
        # transport por perfil (batch/sleep) — usado por quem embeda em lote.
        "batch_size": profile.batch_size,
        "sleep_s": profile.sleep_s,
        "prefix_policy": profile.prefix_policy,
        "profile_slug": profile.slug,
    }


def config_from_env() -> dict:
    """Config do PERFIL ATIVO (RAG_PROFILE > publicado > gemini). Wrapper de I2.

    Mantem a assinatura antiga (retorna dict com base_url/model/api_key/dim) para
    que todo call site existente (search, cli, ingest, testes) continue funcionando
    sem edicao — agora o dim/model/prefixo dao origem no registry, nao em constantes
    soltas. Com default `gemini` o resultado e identico ao comportamento historico.
    """
    return config_for_profile(_profiles.active_profile())


# ---------------------------------------------------------------------------
# task-prefix assimetrico
# ---------------------------------------------------------------------------

def apply_prefix(text: str, kind: str, policy: str | None = None) -> str:
    """Aplica o prefixo de tarefa conforme o tipo do chunk e a politica do perfil.

    code|doc|config usam o rotulo "doc:" (lado documento da busca assimetrica);
    apenas uma QUERY de busca usa "query:". Tudo que sai daqui e embedado como
    documento. A ordem (prefixo antes do texto) e o que casa com o validado no
    demo — nao mexer sem re-validar recall.

    S32 (I2): `policy` vem do perfil ativo quando omitido. `policy="none"` devolve
    o texto CRU (correto p/ modelos sem instruction-tuning, ex.: bge-m3/qwen3.7) —
    nenhum prefixo e aplicado. `policy="gemini"` preserva o comportamento historico
    (prefixo assimetrico). Assim o task-prefix deixa de ser hardcoded e segue o perfil.
    """
    if policy is None:
        policy = _profiles.active_profile().prefix_policy
    if policy == "none":
        return text
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
    *,
    policy: str | None = None,
    **kwargs,
) -> list[list[float]]:
    """Conveniencia: [(texto, kind)] -> aplica prefixo -> embeda.

    Aplica apply_prefix sobre cada texto conforme o kind ANTES de embedar, mas
    NUNCA altera o texto original (content_hash e do puro — decisao do plano).

    S32: `policy` (gemini|none) controla o task-prefix; quando omitido segue o
    perfil ativo (via apply_prefix). Se `cfg` for passado com `prefix_policy`, ele
    e usado como politica — assim quem embeda por perfil propaga a politica sem
    precisar setar ambiente.
    """
    if policy is None:
        cfg = kwargs.get("cfg")
        if cfg and "prefix_policy" in cfg:
            policy = cfg["prefix_policy"]
    prefixed = [apply_prefix(t, k, policy=policy) for t, k in chunks_textos]
    return embed_texts(prefixed, **kwargs)
