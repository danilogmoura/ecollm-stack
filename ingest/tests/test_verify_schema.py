"""S11 — testes de rag-db/verify_schema.py (T-OPS-1).

O script fala com Postgres real; aqui exercitamos apenas a LÓGICA de decisão
(``check``), injetando um ``_fetch_all`` fake que devolve o que o pg catalog
devolveria num schema íntegro vs um sabotado. Não toca DB nem rede.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# verify_schema.py não é um pacote instalável; carregamos por caminho.
_MOD_PATH = Path(__file__).resolve().parents[2] / "rag-db" / "verify_schema.py"
_spec = importlib.util.spec_from_file_location("verify_schema", _MOD_PATH)
verify = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(verify)


HEALTHY = {
    "regclass": [("chunks",)],
    "embedding": [("halfvec(3072)", 3072)],
    "indexes": [
        ("chunks_embedding_hnsw", "hnsw", True,
         "CREATE INDEX ... USING hnsw (embedding halfvec_cosine_ops)"),
        ("chunks_tsv_gin", "gin", True, "CREATE INDEX ... USING gin (tsv)"),
        ("chunks_repo_path_content_hash_key", "btree", True,
         "CREATE UNIQUE INDEX ... USING btree (repo, path, content_hash)"),
        ("chunks_tsv_pt_gin", "gin", True,
         "CREATE INDEX ... USING gin (tsv_pt) WHERE kind = 'doc'"),
    ],
    "tsv": [("tsv", "s"), ("tsv_pt", "s")],
}


def _fake_fetch(table: dict):
    """Retorna um _fetch_all que escolhe a resposta pela palavra-chave do SQL."""
    def fetch(url: str, sql: str):
        s = sql.lower()
        if "regclass::text" in s:
            return table["regclass"]
        if "format_type" in s:
            return table["embedding"]
        if "pg_get_indexdef" in s:
            return table["indexes"]
        if "attgenerated" in s:
            return table["tsv"]
        raise AssertionError(f"SQL não mapeado no fake: {sql!r}")
    return fetch


def test_check_passa_com_schema_integro(monkeypatch):
    monkeypatch.setattr(verify, "_fetch_all", _fake_fetch(HEALTHY))
    results = verify.check("postgresql://x/y")
    assert all(ok for ok, _ in results), [m for ok, m in results if not ok]


def test_check_detecta_indice_hnsw_ausente(monkeypatch):
    broken = {**HEALTHY,
              "indexes": [r for r in HEALTHY["indexes"]
                          if r[0] != "chunks_embedding_hnsw"]}
    monkeypatch.setattr(verify, "_fetch_all", _fake_fetch(broken))
    results = verify.check("u")
    assert any((not ok) and "chunks_embedding_hnsw" in m for ok, m in results)


def test_check_detecta_operator_class_errada(monkeypatch):
    # BUG-002: índice hnsw criado com vector_cosine_ops numa coluna halfvec.
    bad = [list(r) for r in HEALTHY["indexes"]]
    for r in bad:
        if r[0] == "chunks_embedding_hnsw":
            r[3] = "CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)"
    monkeypatch.setattr(verify, "_fetch_all",
                        _fake_fetch({**HEALTHY, "indexes": [tuple(r) for r in bad]}))
    results = verify.check("u")
    assert any((not ok) and "opclass_halfvec_cosine=False" in m for ok, m in results)


def test_check_detecta_dim_errada(monkeypatch):
    monkeypatch.setattr(verify, "_fetch_all",
                        _fake_fetch({**HEALTHY, "embedding": [("vector(3072)", 3072)]}))
    results = verify.check("u")
    assert any((not ok) and "halfvec=False" in m for ok, m in results)


def test_check_aborta_sem_tabela(monkeypatch):
    def fetch(url, sql):
        raise RuntimeError('relation "chunks" does not exist')
    monkeypatch.setattr(verify, "_fetch_all", fetch)
    results = verify.check("u")
    assert results[0][0] is False
    assert "abortando" in results[-1][1].lower()


def test_s20_detecta_indice_tsv_pt_ausente(monkeypatch):
    """GIN parcial tsv_pt (S20) ausente deve ser reportado como falha."""
    broken = {**HEALTHY,
              "indexes": [r for r in HEALTHY["indexes"]
                          if r[0] != "chunks_tsv_pt_gin"]}
    monkeypatch.setattr(verify, "_fetch_all", _fake_fetch(broken))
    results = verify.check("u")
    assert any((not ok) and "chunks_tsv_pt_gin" in m for ok, m in results)


def test_s20_detecta_coluna_tsv_pt_nao_gerada(monkeypatch):
    """tsv_pt presente mas não GENERATED STORED ('s') → falha."""
    monkeypatch.setattr(verify, "_fetch_all",
                        _fake_fetch({**HEALTHY, "tsv": [("tsv", "s"), ("tsv_pt", "")]}))
    results = verify.check("u")
    assert any((not ok) and "tsv_pt" in m for ok, m in results)
