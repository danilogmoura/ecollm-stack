"""Pacote `ingest` — pipeline RAG (loader → chunker → embed → store → search).

S65: carrega o `.env` da raiz UMA vez, no import do pacote. Antes, cada entrypoint
(cli, embed, store, recall, rag_server) tinha de LEMBRAR de chamar
`embed.load_dotenv()` — e falhou 2× (74b0457 no CLI; S63 no eval). Centralizar aqui
elimina a classe de bug: qualquer `import ingest.*` já traz o `.env` para o ambiente.

A chamada é idempotente (`embed.load_dotenv` NÃO sobrescreve o que já está em
`os.environ`), então é seguro rodar mesmo que um entrypoint também chame. O import
é lazy (dentro da função) para evitar ciclo: `ingest.embed` importa `ingest.profiles`,
que por sua vez é importado por outros submódulos.
"""

from __future__ import annotations


def _load_env_once() -> None:
    """Carrega o `.env` da raiz no ambiente do processo (idempotente)."""
    try:
        from . import embed as _embed
        _embed.load_dotenv()
    except Exception:  # noqa: BLE001 — ambiente mínimo (ex.: container sem .env)
        pass


_load_env_once()
