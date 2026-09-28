"""Registry de perfis de embedding (S32) — fonte unica de slug -> espaco vetorial.

Trocar de embedder hoje exigia editar ~10 pontos espalhados (.env, codigo, DDL,
testes). Este modulo concentra a descricao de cada **perfil** em um lugar: o nome
da tabela, a dimensao, o alias LiteLLM, a politica de task-prefix, o gate de
distancia e o tamanho de batch. Um perfil = um **espaco vetorial** inteiro; nunca
ha mistura de dois espacos numa coluna (invariante 7 do `10-STATE.md` §4 — "sem
fallback de embeddings por design"). Trocar de perfil e um ato EXPLICITO de
publicacao, nao uma queda automatica entre espacos.

Design (SPEC-S32-PERFIS-EMBEDDING.md §2):
  - `resolve(slug)`   -> Profile (levanta KeyError p/ slug desconhecido).
  - `active_profile()`-> RAG_PROFILE > publicado > default `bgem3` (local).
  - Slug validado por regex ANTES de qualquer interpolacao em SQL (R1 — a tabela
    so vem deste registry, jamais de input solto do usuario).

S32-a entregou o registry + plumbing de gate/prefixo/dim (SEM DDL). S32-b adicionou
o **ponteiro de perfil publicado** (`rag_sync_state.published_profile`, lido por
`published_profile(repo, conn)`) e a criação sob demanda de tabela por perfil
(`store.ensure_profile_table`). O default global é `bgem3` (local/Ollama, $0); o
perfil legado `gemini` (tabela `chunks`, dim 3072) segue íntegro e continua sendo
quem honra os overrides `RAG_EMBED_*`. Um perfil não-publicado só é usado via
override explícito (`RAG_PROFILE` ou `--profile`) ou publicação (`profile switch`),
nunca por fallback automático (invariante 7).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Defaults globais de conexao (override por env) — preservados de embed.py
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:4000/v1"
# Default quando NADA especifica (sem RAG_PROFILE no env E sem ponteiro publicado).
# bgem3 = espaço vetorial LOCAL (Ollama bge-m3, $0/offline). Precedência completa:
# RAG_PROFILE (env) > published_profile (banco) > DEFAULT_PROFILE (aqui).
DEFAULT_PROFILE = "bgem3"

# R1: identificador de perfil validado antes de virar nome de tabela em SQL.
# ^[a-z][a-z0-9_]{1,31}$ — minusculo, digito/underscore no resto, 2..32 chars.
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

# Nomes de tabela RESERVADOS — jamais usaveis por um perfil novo. Sao os residuos
# dos experimentos A/B de sessoes passadas (tabelas criadas em runtime, SEM coluna
# `gen`, fora do registry). O banco fisico foi limpo (DROP 2026-09-27), mas o risco
# persiste no espaco de nomes: se alguem registrar um perfil cujo `table` colida com
# um desses, `ensure_profile_table` veria `to_regclass` nao-nulo (uma tabela legada
# ainda presente, ex.: apos restaurar volume antigo) e PULARIA a criacao — entao
# leitura/GC (`WHERE gen < ...`) quebrariam em "column gen does not exist". Travar
# aqui (fonte unica) elimina a ambiguidade de nome de forma duravel e versionada.
RESERVED_TABLES: frozenset[str] = frozenset({
    "chunks_gemini", "chunks_qwen", "chunks_nomic",
    "chunks_nop_bgem3", "chunks_nop_nomic", "chunks_nop_qwapi",
    "chunks_nop_qwen", "chunks_nop_v4",
})


class InvalidProfile(ValueError):
    """Slug de perfil invalido (formato), desconhecido, ou tabela reservada."""


@dataclass(frozen=True)
class Profile:
    """Um espaco vetorial completo: tabela + modelo + dim + prefixo + gate + batch."""

    slug: str
    table: str            # nome da tabela (SO este registry e fonte — R1)
    model: str            # alias LiteLLM (ex.: rag-embeddings)
    dim: int              # dimensao do vetor (assertada contra o upstream no build)
    prefix_policy: str    # {"gemini", "none"} — none = texto cru (sem instruction)
    gate: float           # limiar MAX_TOP1_DIST proprio do espaco (⚠️ a calibrar)
    batch_size: int       # itens por request ao upstream
    sleep_s: float        # pausa entre batches (respeitar rate-limit do provedor)

    def __post_init__(self) -> None:
        # Defesa em profundidade (R1): um Profile so pode existir com slug/table
        # validos. Se alguem construir um direto com caractere proibido, falha aqui
        # — antes de qualquer SQL.
        if not SLUG_RE.match(self.slug):
            raise InvalidProfile(f"slug invalido: {self.slug!r}")
        # Anti-colisao de nome: a tabela de um perfil nunca pode ser um dos residuos
        # legados (sem `gen`). Ver nota em RESERVED_TABLES.
        if self.table in RESERVED_TABLES:
            raise InvalidProfile(
                f"nome de tabela reservado (residuo legado, sem coluna gen): "
                f"{self.table!r}"
            )


# ---------------------------------------------------------------------------
# Registry (fonte unica) — SPEC §2.2
# ---------------------------------------------------------------------------

# ⚠️ Gates dos perfis novos NAO estao calibradas: 0,50 vem do A/B em corpus de 558
# chunks; o indice real tem 411. Sweep + registro em 10-STATE §3 sao aceite da fase
# c — tratar como ponto de partida, nao valor travado. Licao paga (BUG S21/R4):
# gate herdada de outro espaco sabotou o bge-m3 em -28 pp.
PROFILES: dict[str, Profile] = {
    "gemini": Profile(
        slug="gemini",
        table="chunks",                 # nome legado preservado (intocado)
        model="rag-embeddings",         # -> gemini/gemini-embedding-2
        dim=3072,
        prefix_policy="gemini",
        gate=0.34,                      # calibrada no corpus atual (S21)
        batch_size=8,
        sleep_s=1.5,
    ),
    "qwen37": Profile(
        slug="qwen37",
        table="chunks_qwen37",
        model="rag-embeddings-qwen37",  # -> openai/qwen3.7-text-embedding
        dim=1024,
        prefix_policy="none",
        gate=0.50,                      # ⚠️ a recalibrar (fase c)
        batch_size=16,                  # upstream qwen3.7 aceita <= 20 itens
        sleep_s=0.3,
    ),
    "bgem3": Profile(
        slug="bgem3",
        table="chunks_bgem3",
        model="rag-embeddings-bgem3",   # -> openai/bge-m3 (Ollama local)
        dim=1024,
        prefix_policy="none",
        gate=0.50,                      # ⚠️ a recalibrar (fase c)
        batch_size=16,
        sleep_s=0.0,                    # offline, sem rate-limit externo
    ),
}


def validate_slug(slug: str) -> str:
    """Retorna `slug` se casar SLUG_RE; senao levanta InvalidProfile (R1).

    Chamado SEMPRE antes de usar o slug para derivar/interpor nome de tabela.
    """
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise InvalidProfile(f"slug invalido: {slug!r} (esperado {SLUG_RE.pattern})")
    return slug


def resolve(slug: str) -> Profile:
    """Perfil pelo slug. Valida formato (R1) e existencia no registry.

    Levanta InvalidProfile p/ slug malformado OU desconhecido — nunca cai num
    default silencioso (um typo nao deve embedar no espaco errado).
    """
    validate_slug(slug)
    try:
        return PROFILES[slug]
    except KeyError as exc:
        raise InvalidProfile(f"perfil desconhecido: {slug!r}") from exc


def published_profile(repo: str | None = None, conn=None) -> str:
    """Slug do perfil publicado. Default `DEFAULT_PROFILE` quando nao ha ponteiro consultavel.

    S32-a retornava sempre o default (stub — nao havia coluna). S32-b (I6/I8):
    quando `repo` E uma conexao sao fornecidos, le o ponteiro `published_profile`
    de rag_sync_state (via store, import lazy p/ evitar ciclo no topo). Sem esses
    argumentos (ex.: busca sem repo, teste unitario, CLI antes de abrir conn),
    devolve o default — comportamento historico, nunca falha por falta de banco.
    """
    if repo is None or conn is None:
        return DEFAULT_PROFILE
    from . import store as _store  # lazy — profiles é importado por store no topo
    try:
        return _store.get_published_profile(conn, repo)
    except Exception:  # noqa: BLE001 — sem tabela/coluna (volume pré-S32) → default
        return DEFAULT_PROFILE


def active_profile(repo: str | None = None, conn=None) -> Profile:
    """Perfil em uso: RAG_PROFILE (env) > publicado > default `bgem3`.

    A precedence fica explicita aqui (SPEC teste 2). RAG_PROFILE sobrescreve o
    publicado (util p/ A/B e eval); na ausencia dele usamos o publicado; e na
    ausencia de ponteiro consultavel caimos no DEFAULT_PROFILE (`bgem3`, local).
    Nota: published_profile hoje aponta bgem3 (publicado via `profile switch`);
    sem env nem ponteiro, o default do registry decide. Em S32-b, passando
    `repo`+`conn` o "publicado" vem do ponteiro no banco; omitindo, default.
    """
    slug = os.environ.get("RAG_PROFILE")
    if slug is None or slug == "":
        slug = published_profile(repo, conn)
    return resolve(slug)
