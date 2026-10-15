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
        ("chunks_repo_path_content_hash_gen_key", "btree", True,
         "CREATE UNIQUE INDEX ... USING btree (repo, path, content_hash, gen)"),
        ("chunks_tsv_pt_gin", "gin", True,
         "CREATE INDEX ... USING gin (tsv_pt) WHERE kind = 'doc'"),
        ("chunks_repo_gen", "btree", True,
         "CREATE INDEX ... USING btree (repo, gen)"),
    ],
    "tsv": [("tsv", "s"), ("tsv_pt", "s")],
    # S29: coluna gen em chunks + ponteiros de geração no estado de sync.
    "gen": [("gen",)],
    # S32-b: rag_sync_state ganhou profile/published_profile (PK muda p/ repo,profile).
    "state": [("published_gen",), ("in_progress_gen",), ("profile",),
              ("published_profile",)],
    # S32-b: probe do perfil publicado (default gemini -> tabela chunks já validada).
    "published_profile": [("gemini",)],
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
        # S32-b: probe do perfil publicado (SELECT published_profile ... LIMIT 1).
        if "published_profile from rag_sync_state" in s:
            return table.get("published_profile", [("gemini",)])
        # S29/S32-b: checagem da lista de colunas do estado de sync.
        if "rag_sync_state" in s:
            return table["state"]
        if "attname = 'gen'" in s or "attname='gen'" in s:
            return table["gen"]
        # S69: checagem da coluna meta.
        if "attname = 'meta'" in s or "attname='meta'" in s:
            return table.get("meta", [("meta",)])
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


# ---------------------------------------------------------------------------
# S85 — main() (CLI) + ramos de erro (cobertura do verify_schema)
# ---------------------------------------------------------------------------

def test_main_sucesso_retorna_zero(monkeypatch, capsys):
    monkeypatch.setattr(verify, "check", lambda url: [(True, "ok1"), (True, "ok2")])
    monkeypatch.setattr(verify, "db_url_from_env", lambda: "postgresql://u:p@h/db")
    rc = verify.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "schema íntegro" in out
    assert "h/db" in out          # imprime a URL SEM a senha
    assert "u:p" not in out       # senha NÃO vaza


def test_main_falha_retorna_um(monkeypatch, capsys):
    monkeypatch.setattr(verify, "check", lambda url: [(True, "ok"), (False, "ruim")])
    monkeypatch.setattr(verify, "db_url_from_env", lambda: "postgresql://h/db")
    rc = verify.main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert "1 checagem(ns) falharam" in out
    assert "down -v" in out       # orienta a recuperação


def test_main_conexao_falha_retorna_um(monkeypatch, capsys):
    def boom(url):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(verify, "check", boom)
    monkeypatch.setattr(verify, "db_url_from_env", lambda: "postgresql://h/db")
    rc = verify.main([])
    assert rc == 1
    assert "FALHA ao conectar" in capsys.readouterr().out


def test_main_usa_url_do_arg(monkeypatch):
    seen = {}
    monkeypatch.setattr(verify, "check", lambda url: seen.update(url=url) or [(True, "ok")])
    rc = verify.main(["--url", "postgresql://custom/db"])
    assert rc == 0
    assert seen["url"] == "postgresql://custom/db"


def test_required_for_tabela_nao_chunks():
    """_required_for: tabela de perfil deriva os nomes trocando o prefixo."""
    req = verify._required_for("chunks_qwen37")
    assert "chunks_qwen37_embedding_hnsw" in req
    assert req["chunks_qwen37_embedding_hnsw"] == "hnsw"


def test_required_for_tabela_estranha_retorna_vazio():
    """_required_for: tabela que não começa com 'chunks' → {} (sem checagens)."""
    assert verify._required_for("outra_tabela") == {}


def test_check_detecta_perfil_publicado_ausente(monkeypatch):
    """Ramo: perfil publicado cuja tabela NÃO existe → falha reportada."""
    def fetch(url, sql):
        if "published_profile" in sql:
            return [("qwen37",)]
        if "to_regclass" in sql and "chunks_qwen37" in sql:
            return [(False,)]          # tabela do perfil ausente
        return _fake_fetch(HEALTHY)(url, sql)
    monkeypatch.setattr(verify, "_fetch_all", fetch)
    results = verify.check("u")
    assert any((not ok) and "chunks_qwen37" in m for ok, m in results)
