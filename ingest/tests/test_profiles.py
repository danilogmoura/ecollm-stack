"""Testes unitarios de S32-a — registry de perfis + plumbing gate/prefixo/dim.

Sem rede/DB/cota (SPEC-S32-PERFIS-EMBEDDING.md §6, testes 1–7). Cobrem:
  1. resolve() por slug (dim/gate/prefixo/tabela) + slug invalido levanta.
  2. active_profile(): RAG_PROFILE > publicado > default gemini.
  3. config_for_profile: base/model/key/dim por perfil; prefix_policy=none => texto cru.
  4. ensure_profile_table emite DDL com halfvec(<dim>) e halfvec_cosine_ops — ADIADO
     p/ S32-b (sem DDL nesta fase); aqui cobrimos apenas que o registry expoe a
     tabela/dim corretas (fonte do DDL futuro).
  5. validacao de identificador (R1): caractere invalido / slug fora do registry recusa.
  6. gate por perfil: gemini na faixa 0,30–0,37; qwen37/bgem3 = 0,50.
  7. cli: --profile propaga; roteamento; use sem sync => SystemExit nao-zero (S32-b).

Perfil default `gemini` deve reproduzir o comportamento historico EXATAMENTE.
"""

from __future__ import annotations

import pytest

from ingest import embed, profiles, search


# ---------------------------------------------------------------------------
# teste 1 — registry: resolve() por slug + slug invalido levanta
# ---------------------------------------------------------------------------

def test_resolve_gemini_campos_esperados():
    p = profiles.resolve("gemini")
    assert p.table == "chunks"
    assert p.model == "rag-embeddings"
    assert p.dim == 3072
    assert p.prefix_policy == "gemini"
    assert p.gate == pytest.approx(0.34)


def test_resolve_qwen37_campos_esperados():
    p = profiles.resolve("qwen37")
    assert p.table == "chunks_qwen37"
    assert p.model == "rag-embeddings-qwen37"
    assert p.dim == 1024
    assert p.prefix_policy == "none"
    assert p.gate == pytest.approx(0.50)


def test_resolve_bgem3_campos_esperados():
    p = profiles.resolve("bgem3")
    assert p.table == "chunks_bgem3"
    assert p.model == "rag-embeddings-bgem3"
    assert p.dim == 1024
    assert p.prefix_policy == "none"
    assert p.batch_size == 16 and p.sleep_s == 0.0


def test_resolve_slug_inexistente_levanta():
    with pytest.raises(profiles.InvalidProfile):
        profiles.resolve("nao_existe")


# ---------------------------------------------------------------------------
# teste 2 — active_profile(): precedence RAG_PROFILE > publicado > default
# ---------------------------------------------------------------------------

def test_active_profile_default_e_bgem3_local(monkeypatch):
    # Sem RAG_PROFILE no env E sem repo/conn (sem ponteiro publicado consultável),
    # o registry defaulte para o perfil LOCAL bgem3 (Ollama, $0). Decisão 2026-09-27.
    monkeypatch.delenv("RAG_PROFILE", raising=False)
    assert profiles.active_profile().slug == "bgem3"


def test_active_profile_respeita_rag_profile_env(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "qwen37")
    assert profiles.active_profile().slug == "qwen37"


def test_active_profile_env_vazio_usa_publicado(monkeypatch):
    # RAG_PROFILE="" (setado mas vazio) NAO deve sobrescrever o publicado/default.
    monkeypatch.setenv("RAG_PROFILE", "")
    assert profiles.active_profile().slug == profiles.published_profile()


def test_active_profile_slug_invalido_no_env_levanta(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "BAD SLUG!")
    with pytest.raises(profiles.InvalidProfile):
        profiles.active_profile()


# ---------------------------------------------------------------------------
# teste 3 — config_for_profile + prefix_policy=none => texto inalterado
# ---------------------------------------------------------------------------

def test_config_for_profile_por_perfil(monkeypatch):
    monkeypatch.delenv("RAG_EMBED_MODEL", raising=False)
    monkeypatch.delenv("RAG_EMBED_DIM", raising=False)
    cfg = embed.config_for_profile(profiles.resolve("qwen37"))
    assert cfg["model"] == "rag-embeddings-qwen37"
    assert cfg["dim"] == 1024
    assert cfg["prefix_policy"] == "none"
    assert cfg["batch_size"] == 16


def test_config_ignora_env_legado_todos_perfis(monkeypatch):
    # Corte total (pos-S36): os antigos overrides RAG_EMBED_MODEL/RAG_EMBED_DIM do
    # .env NAO tem mais efeito em NENHUM perfil. A fonte canonica de model/dim e o
    # registry (invariante 7: nunca misturar espaços; um alias Gemini 3072 num perfil
    # 1024 corromperia o indice). Mesmo injetando valores legados no ambiente, cada
    # perfil devolve seu proprio modelo+dim.
    monkeypatch.setenv("RAG_EMBED_MODEL", "rag-embeddings")
    monkeypatch.setenv("RAG_EMBED_DIM", "3072")
    cfg = embed.config_for_profile(profiles.resolve("qwen37"))
    assert cfg["model"] == "rag-embeddings-qwen37"
    assert cfg["dim"] == 1024
    cfg_b = embed.config_for_profile(profiles.resolve("bgem3"))
    assert cfg_b["model"] == "rag-embeddings-bgem3"
    assert cfg_b["dim"] == 1024
    # ate o perfil historico ('gemini') agora ignora o env: seu model/dim vem do
    # registry (que ja e rag-embeddings/3072), nao do override.
    cfg_g = embed.config_for_profile(profiles.resolve("gemini"))
    assert cfg_g["model"] == "rag-embeddings"
    assert cfg_g["dim"] == 3072


def test_config_from_env_wrapper_do_perfil_ativo(monkeypatch):
    monkeypatch.delenv("RAG_EMBED_MODEL", raising=False)
    monkeypatch.delenv("RAG_EMBED_DIM", raising=False)
    monkeypatch.setenv("RAG_PROFILE", "bgem3")
    cfg = embed.config_from_env()
    assert cfg["model"] == "rag-embeddings-bgem3"
    assert cfg["dim"] == 1024
    assert cfg["profile_slug"] == "bgem3"


def test_prefix_none_devolve_texto_cru():
    # politica "none": nenhum prefixo, nem p/ query nem p/ doc — texto cru.
    assert embed.apply_prefix("oi", "query", policy="none") == "oi"
    assert embed.apply_prefix("oi", "doc", policy="none") == "oi"
    assert embed.apply_prefix("oi", "code", policy="none") == "oi"


def test_prefix_gemini_preserva_comportamento_historico():
    assert embed.apply_prefix("oi", "query", policy="gemini") == embed.TASK_PREFIX_QUERY + "oi"
    assert embed.apply_prefix("oi", "doc", policy="gemini") == embed.TASK_PREFIX_DOC + "oi"


def test_apply_prefix_default_segue_perfil_ativo(monkeypatch):
    monkeypatch.setenv("RAG_PROFILE", "qwen37")  # prefix_policy=none
    assert embed.apply_prefix("oi", "query") == "oi"
    monkeypatch.setenv("RAG_PROFILE", "gemini")
    assert embed.apply_prefix("oi", "query") == embed.TASK_PREFIX_QUERY + "oi"


def test_embed_documents_com_politica_none_nao_prefixa():
    seen: list[list[str]] = []

    def capture(texts, cfg, session):
        seen.append(list(texts))
        return [[0.5] * cfg["dim"] for _ in texts]

    cfg = {"base_url": "http://x/v1", "model": "m", "api_key": "", "dim": 3,
           "prefix_policy": "none"}
    embed.embed_documents([("alpha", "code"), ("beta", "query")],
                          cfg=cfg, sleep=lambda s: None, post=capture)
    assert seen[0] == ["alpha", "beta"]  # cru, sem TASK_PREFIX


# ---------------------------------------------------------------------------
# teste 4 — registry expoe tabela+dim (fonte do DDL de S32-b)
# ---------------------------------------------------------------------------

def test_registry_fornece_tabela_e_dim_para_ddl():
    # O DDL (ensure_profile_table) chega em S32-b; aqui garantimos que a fonte
    # unica (registry) ja expoe os parametros que o DDL vai parametrizar.
    for slug in ("gemini", "qwen37", "bgem3"):
        p = profiles.resolve(slug)
        assert isinstance(p.table, str) and p.table
        assert p.dim > 0


# ---------------------------------------------------------------------------
# teste 5 — validacao de identificador (R1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "Chunks; DROP TABLE", "UPPER", "_leading", "a", "com espaco",
    "tab\there", "x" * 40, "9digit", "ponto.in", "tra-o",
])
def test_slug_invalido_recusado(bad):
    with pytest.raises(profiles.InvalidProfile):
        profiles.validate_slug(bad)


def test_slug_valido_aceito():
    for ok in ("gemini", "qwen37", "bgem3", "a1", "my_profile_2"):
        assert profiles.validate_slug(ok) == ok


def test_profile_construido_com_slug_invalido_levanta():
    # defesa em profundidade: ate um Profile() direto com slug proibido falha no __post_init__.
    with pytest.raises(profiles.InvalidProfile):
        profiles.Profile(slug="BAD", table="t", model="m", dim=8,
                         prefix_policy="none", gate=0.5, batch_size=8, sleep_s=0.0)


# ---------------------------------------------------------------------------
# teste 5b — anti-colisao de nome: tabela de perfil nunca pode ser residuo legado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reserved", sorted(profiles.RESERVED_TABLES))
def test_tabela_reservada_recusada_pelo_registry(reserved):
    # Um perfil novo cujo `table` colida com uma das 8 tabelas órfãs históricas
    # (sem coluna gen) deve falhar na construção — elimina ambiguidade de nome.
    with pytest.raises(profiles.InvalidProfile):
        profiles.Profile(slug="novo_perfil", table=reserved, model="m", dim=8,
                         prefix_policy="none", gate=0.5, batch_size=8, sleep_s=0.0)


def test_nome_de_tabela_valido_fora_das_reservadas_e_aceito():
    # Sanidade: o guard não é amplo demais — um nome novo legítimo passa.
    p = profiles.Profile(slug="novo_perfil", table="chunks_novo_perfil", model="m",
                         dim=8, prefix_policy="none", gate=0.5, batch_size=8, sleep_s=0.0)
    assert p.table == "chunks_novo_perfil"


def test_perfis_do_registry_nao_usam_tabela_reservada():
    # O registry vigente jamais aponta para um nome reservado (chunks/chunks_qwen37/
    # chunks_bgem3 ficam; os residuos chunks_gemini/... nao).
    for slug, prof in profiles.PROFILES.items():
        assert prof.table not in profiles.RESERVED_TABLES, slug


# ---------------------------------------------------------------------------
# teste 6 — gate por perfil (substitui o assert fixo antigo)
# ---------------------------------------------------------------------------

def test_gate_gemini_na_faixa_calibrada():
    assert 0.30 < profiles.resolve("gemini").gate < 0.37


def test_gate_perfis_novos_ponto_de_partida():
    # ⚠️ 0,50 e ponto de partida do A/B (corpus 558), NAO valor travado — sweep e
    # aceite da fase c. Aqui so travamos que cada perfil tem gate PROPRIA distinta.
    assert profiles.resolve("qwen37").gate == pytest.approx(0.50)
    assert profiles.resolve("bgem3").gate == pytest.approx(0.50)
    assert profiles.resolve("gemini").gate != profiles.resolve("qwen37").gate


def test_max_top1_dist_alias_do_perfil_default():
    # retro-compat: search.MAX_TOP1_DIST continua sendo o gate do perfil default.
    assert search.MAX_TOP1_DIST == profiles.resolve("gemini").gate


def test_max_gate_for_profile_resolve_por_slug_e_ativo(monkeypatch):
    assert search.max_gate_for_profile("qwen37") == pytest.approx(0.50)
    monkeypatch.setenv("RAG_PROFILE", "gemini")
    assert search.max_gate_for_profile() == pytest.approx(0.34)


def test_search_sentinela_perfil_gate_filtra_pelo_perfil(monkeypatch):
    # PERFIL_GATE deve resolver o gate do perfil ativo e aplicar o corte.
    monkeypatch.setenv("RAG_PROFILE", "gemini")  # gate 0,34
    far = 0.37  # acima de 0,34 => cortado
    conn = _FakeConn([_drow(1, "a.py", far)], [])
    hits = search.search("q", repo="r", conn=conn, qvec=[0.0],
                         max_top1_dist=search.PERFIL_GATE)
    assert hits == []


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConn:
    """Conn minima p/ search(): despacha por SQL (denso/lexico/pt/published_gen)."""

    def __init__(self, vec_rows, lex_rows, pt_rows=None):
        self.vec_rows = vec_rows
        self.lex_rows = lex_rows
        self.pt_rows = pt_rows if pt_rows is not None else []

    def execute(self, sql, params=None):
        if "published_gen" in sql:
            return _FakeCursor([(0,)])
        if "<=>" in sql:
            return _FakeCursor(self.vec_rows)
        if "tsv_pt" in sql:
            return _FakeCursor(self.pt_rows)
        return _FakeCursor(self.lex_rows)

    def close(self):
        pass


def _drow(i, path, dist, kind="code"):
    # colunas na ordem de _COLS + dist: id, repo, path, lang, kind, symbol, content, content_hash, dist
    return (f"id{i}", "r", path, "py", kind, "sym", "conteudo", f"h{i}", dist)


# ---------------------------------------------------------------------------
# teste 7 — cli: --profile propaga (roteamento) + validacao cedo
# ---------------------------------------------------------------------------

def test_cli_profile_propaga_para_busca(monkeypatch):
    from ingest import cli
    import os

    # _set_profile_env muta os.environ de fato. setenv via monkeypatch ANTES de
    # chamar cmd_rag registra o valor prévio p/ restaurar no teardown — sem isso a
    # mutação vaza p/ testes seguintes no mesmo processo (ordem alfabética expõe).
    monkeypatch.setenv("RAG_PROFILE", os.environ.get("RAG_PROFILE", ""))

    seen = {}

    def _capture(*a, **k):
        seen.update(k)
        return []

    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    monkeypatch.setattr(cli.search, "staleness_warning", lambda *a, **k: None)
    monkeypatch.setattr(cli.search, "search", _capture)
    args = _ns(query="oi", repo=".", k=8, kind=None, path=None, ask=False,
               no_snippet=True, profile="qwen37")
    rc = cli.cmd_rag(args)
    assert rc == 0
    assert seen.get("max_top1_dist") == search.PERFIL_GATE
    assert os.environ.get("RAG_PROFILE") == "qwen37"


def test_cli_profile_invalido_recusa(monkeypatch):
    from ingest import cli

    monkeypatch.setattr(cli.ingest_mod, "repo_name", lambda p: "r")
    monkeypatch.setattr(cli.search, "staleness_warning", lambda *a, **k: None)
    args = _ns(query="oi", repo=".", k=8, kind=None, path=None, ask=False,
               no_snippet=True, profile="NAO-EXISTE")
    with pytest.raises(profiles.InvalidProfile):
        cli.cmd_rag(args)


def _ns(**kw):
    import types
    return types.SimpleNamespace(**kw)
