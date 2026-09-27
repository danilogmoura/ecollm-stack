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
  - `active_profile()`-> RAG_PROFILE > publicado > default `gemini`.
  - Slug validado por regex ANTES de qualquer interpolacao em SQL (R1 — a tabela
    so vem deste registry, jamais de input solto do usuario).

S32-a entrega apenas o registry + plumbing de gate/prefixo/dim (SEM DDL). O
ponteiro de perfil publicado (`rag_embed_profile`) chega em S32-b; ate la,
`active_profile()` le do ambiente com default `gemini`, entao o comportamento e
IDENTICO ao atual (perfil default preserva tabela `chunks`, dim 3072, prefixo
Gemini e gate 0,34).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Defaults globais de conexao (override por env) — preservados de embed.py
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:4000/v1"
DEFAULT_PROFILE = "gemini"

# R1: identificador de perfil validado antes de virar nome de tabela em SQL.
# ^[a-z][a-z0-9_]{1,31}$ — minusculo, digito/underscore no resto, 2..32 chars.
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class InvalidProfile(ValueError):
    """Slug de perfil invalido (formato) ou desconhecido (fora do registry)."""


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


def published_profile() -> str:
    """Slug do perfil publicado. Em S32-a ainda nao ha ponteiro no banco (S32-b);
    retorna o default. Mantido como funcao separada p/ o override de `active_profile`
    ficar legivel e testavel.
    """
    return DEFAULT_PROFILE


def active_profile() -> Profile:
    """Perfil em uso: RAG_PROFILE (env) > publicado > default `gemini`.

    A precedence fica explicita aqui (SPEC teste 2). RAG_PROFILE sobrescreve o
    publicado (util p/ A/B e eval); na ausencia dele usamos o publicado; e o
    publicado defaulte para `gemini` (comportamento historico).
    """
    slug = os.environ.get("RAG_PROFILE")
    if slug is None or slug == "":
        slug = published_profile()
    return resolve(slug)
