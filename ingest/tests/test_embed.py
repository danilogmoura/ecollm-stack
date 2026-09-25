"""Testes da FASE 2 — embed.py (sem rede: post injetado)."""

from __future__ import annotations

import pytest

from ingest import embed


CFG = {"base_url": "http://x/v1", "model": "rag-embeddings", "api_key": "", "dim": 4}


def _fake_post(dim=4):
    """Um post fake que devolve um vetor deterministico por texto (soma dos chars)."""
    calls = {"n": 0, "batches": []}

    def post(texts, cfg, session):
        calls["n"] += 1
        calls["batches"].append(list(texts))
        out = []
        for t in texts:
            seed = sum(ord(c) for c in t) % 97 / 100.0
            out.append([seed + i * 0.01 for i in range(cfg["dim"])])
        return out

    return post, calls


def test_prefix_doc_e_query():
    assert embed.apply_prefix("oi", "code") == embed.TASK_PREFIX_DOC + "oi"
    assert embed.apply_prefix("oi", "doc") == embed.TASK_PREFIX_DOC + "oi"
    assert embed.apply_prefix("oi", "config") == embed.TASK_PREFIX_DOC + "oi"
    assert embed.apply_prefix("oi", "query") == embed.TASK_PREFIX_QUERY + "oi"


def test_batching_preserva_ordem_e_tamanho():
    post, calls = _fake_post()
    texts = [f"texto-{i}" for i in range(75)]
    vecs = embed.embed_texts(texts, cfg=CFG, batch_size=32, sleep=lambda s: None, post=post)
    assert len(vecs) == 75
    # 3 batches: 32 + 32 + 11
    assert [len(b) for b in calls["batches"]] == [32, 32, 11]
    # ordem: cada vetor corresponde ao seed do respectivo texto
    for i, v in enumerate(vecs):
        seed = sum(ord(c) for c in texts[i]) % 97 / 100.0
        assert v[0] == pytest.approx(seed)


def test_retry_backoff_exponencial():
    attempts = {"n": 0}

    def flaky(texts, cfg, session):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise embed.EmbedError("boom transitório")
        return [[0.1] * CFG["dim"] for _ in texts]

    delays: list[float] = []
    vecs = embed.embed_texts(["a"], cfg=CFG, max_retries=3,
                             sleep=delays.append, post=flaky)
    assert len(vecs) == 1
    assert attempts["n"] == 3
    # backoff exponencial: 1.5, 3.0
    assert delays == [pytest.approx(1.5), pytest.approx(3.0)]


def test_falha_definitiva_apos_esgotar_retries():
    def always_fail(texts, cfg, session):
        raise embed.EmbedError("upstream morto")

    with pytest.raises(embed.EmbedError):
        embed.embed_texts(["a", "b"], cfg=CFG, max_retries=3,
                          sleep=lambda s: None, post=always_fail)


def test_post_batch_valida_dimensao_incorreta(monkeypatch):
    """_post_batch (caminho HTTP real) deve rejeitar vetor com dim errada."""
    class Resp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}  # dim 2 != 4

    class Session:
        def post(self, *a, **k):
            return Resp()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(embed.requests, "Session", lambda: Session())
    with pytest.raises(embed.EmbedError):
        embed.embed_texts(["a"], cfg=CFG, sleep=lambda s: None)


def test_embed_documents_aplica_prefixo_antes_do_embed():
    seen: list[list[str]] = []

    def capture(texts, cfg, session):
        seen.append(list(texts))
        return [[0.5] * cfg["dim"] for _ in texts]

    pairs = [("conteudo code", "code"), ("uma pergunta", "query")]
    out = embed.embed_documents(pairs, cfg=CFG, sleep=lambda s: None, post=capture)
    assert len(out) == 2
    flat = seen[0]
    assert flat[0].startswith(embed.TASK_PREFIX_DOC)
    assert flat[1].startswith(embed.TASK_PREFIX_QUERY)


def test_vector_to_halfvec_text_formato():
    txt = embed.vector_to_halfvec_text([0.0, 1.5, -2.25])
    assert txt.startswith("[") and txt.endswith("]")
    parts = txt[1:-1].split(",")
    assert len(parts) == 3
    assert float(parts[1]) == pytest.approx(1.5)
