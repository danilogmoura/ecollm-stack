#!/usr/bin/env python3
"""S11 — Verificação pós-boot do schema do índice RAG (T-OPS-1).

O entrypoint oficial do Postgres roda os scripts de
``docker-entrypoint-initdb.d`` SEM ``ON_ERROR_STOP`` garantido, e só executa
``init.sql`` na PRIMEIRA criação do volume. Resultado: um ``statement`` inválido
no meio do init.sql pode deixar o container "up" com schema INCOMPLETO
(tabela sem índice HNSW, ou sem a coluna tsv gerada) — silencioso.

Este script fecha essa lacuna: ele CONFERE o schema real contra as decisões
travadas no plano (.planning/PLANO-RAG.md §3 FASE 0) e sai com código != 0 se
algo estiver errado. Pode ser usado como healthcheck do compose OU rodado à mão
após mexer em init.sql.

Checagens (todas derivadas das regras BUG-001 / BUG-002):
  1. tabela ``chunks`` existe;
  2. coluna ``embedding`` é halfvec com atttypmod == 3072 (NÃO vector — BUG-001);
  3. os índices obrigatórios existem E estão válidos (indisvalid), com o acesso
     correto: hnsw sobre embedding, gin sobre tsv, btree único (repo,path,content_hash);
  4. o operador class do índice vetorial é halfvec_cosine_ops (NÃO vector_* —
     BUG-002: operator class errada = seq scan silencioso, índice vira enfeite);
  5. a coluna gerada ``tsv`` existe (caminho lexical da busca híbrida).

Por que NÃO checamos o EXPLAIN diretamente: com o corpus atual (207 chunks) o
planner escolhe legitimamente seq-scan (mais barato que HNSW em tabelas
pequenas), então um teste de plano daria falso-negativo. A checagem estrutural
(índice hnsw válido + operator class halfvec_cosine_ops) garante que, quando o
corpus crescer, o índice SERÁ usável — que é exatamente o que BUG-002 quebrou.

Uso:
    python rag-db/verify_schema.py                 # lê RAG_DB_URL do .env
    python rag-db/verify_schema.py --url postgresql://rag:rag_secret@localhost:5433/rag

Saída: uma linha por checagem (OK/FALHA) + resumo; exit 0 se tudo OK, 1 caso contrário.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite importar ingest.store tanto por "python rag-db/verify_schema.py"
# (sys.path[0] = rag-db/) quanto pelo healthcheck do container.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from ingest.store import db_url_from_env  # reaproveita load_dotenv + default
except Exception:  # pragma: no cover - ambiente mínimo do container
    def db_url_from_env() -> str:  # type: ignore
        import os
        return os.environ.get("RAG_DB_URL", "postgresql://rag:rag_secret@localhost:5433/rag")


# Índices obrigatórios -> acesso esperado. (nome, amname)
REQUIRED_INDEXES = {
    "chunks_embedding_hnsw": "hnsw",
    "chunks_tsv_gin": "gin",
    "chunks_repo_path_content_hash_key": "btree",
}


def _fetch_all(url: str, sql: str):
    import psycopg

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def check(url: str) -> list[tuple[bool, str]]:
    """Rodar todas as checagens; retorna [(ok, mensagem), ...]."""
    results: list[tuple[bool, str]] = []

    # 1. tabela chunks existe
    try:
        rows = _fetch_all(url, "SELECT 'chunks'::regclass::text")
        exists = bool(rows) and rows[0][0] == "chunks"
    except Exception as exc:  # regclass lança se não existir
        exists = False
        note = f" ({exc.__class__.__name__})"
    else:
        note = ""
    results.append((exists, f"tabela 'chunks' presente{note}"))
    if not exists:
        # sem tabela, o resto não faz sentido
        results.append((False, "schema ausente — abortando checagens restantes"))
        return results

    # 2. embedding = halfvec(3072)
    typrows = _fetch_all(
        url,
        """
        SELECT format_type(a.atttypid, a.atttypmod), a.atttypmod
        FROM pg_attribute a
        WHERE a.attrelid = 'chunks'::regclass AND a.attname = 'embedding'
        """,
    )
    if not typrows:
        results.append((False, "coluna 'embedding' ausente"))
    else:
        ftype, typmod = typrows[0]
        is_halfvec = "halfvec" in (ftype or "").lower()
        dims_ok = typmod == 3072
        ok = is_halfvec and dims_ok
        results.append(
            (ok, f"embedding é {ftype} (halfvec={is_halfvec}, dims={typmod}; "
                 f"esperado halfvec/3072)")
        )

    # 3+4. índices obrigatórios, válidos, com o acesso certo
    idxrows = _fetch_all(
        url,
        """
        SELECT c.relname, am.amname, i.indisvalid,
               pg_get_indexdef(i.indexrelid)
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_am am ON am.oid = c.relam
        WHERE i.indrelid = 'chunks'::regclass
        """,
    )
    by_name = {r[0]: r for r in idxrows}
    for name, want_am in REQUIRED_INDEXES.items():
        r = by_name.get(name)
        if r is None:
            results.append((False, f"índice '{name}' AUSENTE"))
            continue
        _, amname, valid, definition = r
        ok = (amname == want_am) and bool(valid)
        detail = f"acesso={amname} valido={valid}"
        # checagem específica do operador class p/ o índice vetorial (BUG-002)
        if name == "chunks_embedding_hnsw":
            uses_correct_opclass = "halfvec_cosine_ops" in (definition or "")
            bad_opclass = "vector_cosine_ops" in (definition or "")
            ok = ok and uses_correct_opclass and not bad_opclass
            detail += f" opclass_halfvec_cosine={uses_correct_opclass}"
        results.append((ok, f"índice '{name}' ({detail})"))

    # 5. coluna gerada tsv existe
    tsrows = _fetch_all(
        url,
        """
        SELECT a.attgenerated FROM pg_attribute a
        WHERE a.attrelid='chunks'::regclass AND a.attname='tsv'
        """,
    )
    tsv_ok = bool(tsrows) and tsrows[0][0] == "s"  # 's' = generated stored
    results.append((tsv_ok, f"coluna gerada 'tsv' presente (generated="
                            f"{tsrows[0][0] if tsrows else '-'})"))

    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verifica o schema do índice RAG (S11).")
    ap.add_argument("--url", default=None,
                    help="URL do Postgres (default: RAG_DB_URL do .env).")
    args = ap.parse_args(argv)

    url = args.url or db_url_from_env()
    # nunca imprimir a senha
    safe_url = url.split("@")[-1] if "@" in url else url
    print(f"[verify-schema] conferindo schema em {safe_url}")
    try:
        results = check(url)
    except Exception as exc:
        print(f"[verify-schema] FALHA ao conectar/checar: {exc}")
        return 1

    failed = 0
    for ok, msg in results:
        print(f"  [{'OK' if ok else 'FALHA'}] {msg}")
        if not ok:
            failed += 1

    if failed:
        print(f"[verify-schema] {failed} checagem(ns) falharam — schema incompleto.")
        print("  Provável causa: init.sql rodou parcial (volume antigo) ou tem erro.")
        print("  Recuperação: docker compose down -v && docker compose up -d rag-db")
        print("  (atenção: down -v apaga TAMBÉM outros volumes nomeados no mesmo arquivo).")
        return 1
    print("[verify-schema] schema íntegro — todas as checagens passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
