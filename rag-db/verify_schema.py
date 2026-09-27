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
# S29/I9: a constraint de unicidade passou a incluir `gen` (migração 004), então o
# nome do índice único mudou de `chunks_repo_path_content_hash_key` para
# `chunks_repo_path_content_hash_gen_key`. Este nome e o do healthcheck do compose
# e o de init.sql DEVEM mudar em lockstep — senão o container fica unhealthy com
# o schema funcional (R6).
#
# S32-b (I12): os nomes são PREFIXADOS por tabela. Para o perfil default (`chunks`)
# usamos exatamente estes nomes (lockstep com init.sql/migrações). Para um perfil
# publicado alternativo, `_required_for(table)` deriva os mesmos nomes trocando o
# prefixo `chunks_` → `<tabela>_` (a DDL de ensure_profile_table segue esta mesma
# convenção, SPEC §2.4/R3), então a checagem estrutural é idêntica em qualquer perfil.
REQUIRED_INDEXES = {
    "chunks_embedding_hnsw": "hnsw",
    "chunks_tsv_gin": "gin",
    "chunks_repo_path_content_hash_gen_key": "btree",
    "chunks_tsv_pt_gin": "gin",   # S20: GIN parcial p/ prosa pt-BR (kind='doc')
    "chunks_repo_gen": "btree",   # S29: filtro de leitura por gen + GC
}


def _required_for(table: str) -> dict[str, str]:
    """Nomes de índice obrigatórios para a `table` dada (prefixo derivado do nome).

    'chunks' → os nomes canônicos (REQUIRED_INDEXES). Qualquer outra tabela do
    registry ('chunks_qwen37', ...) replica a estrutura trocando o prefixo, pois
    ensure_profile_table nomeia os índices como <tabela>_<...> (SPEC R3 — equivalência
    estrutural). Retorna vazio se a tabela não seguir a convenção (não é um perfil).
    """
    if table == "chunks":
        return dict(REQUIRED_INDEXES)
    if not table.startswith("chunks"):
        return {}
    return {f"{table}_{k[len('chunks_'):]}": v for k, v in REQUIRED_INDEXES.items()}


def _fetch_all(url: str, sql: str):
    import psycopg

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def _check_table(url: str, table: str, dim: int) -> list[tuple[bool, str]]:
    """Checagens estruturais numa tabela de perfil: embedding halfvec(dim), índices
    obrigatórios válidos (com opclass correta), colunas geradas tsv/tsv_pt e gen.

    Assume que `table` JÁ EXISTE (o chamador conferiu via to_regclass). `dim` é a
    dimensão esperada DO PERFIL (registry), não hardcoded 3072 — test 13 rejeita
    um perfil publicado cuja coluna diverge do dim declarado.
    """
    results: list[tuple[bool, str]] = []

    # embedding = halfvec(dim)
    typrows = _fetch_all(
        url,
        f"""
        SELECT format_type(a.atttypid, a.atttypmod), a.atttypmod
        FROM pg_attribute a
        WHERE a.attrelid = '{table}'::regclass AND a.attname = 'embedding'
        """,
    )
    if not typrows:
        results.append((False, f"[{table}] coluna 'embedding' ausente"))
    else:
        ftype, typmod = typrows[0]
        is_halfvec = "halfvec" in (ftype or "").lower()
        dims_ok = typmod == dim
        ok = is_halfvec and dims_ok
        results.append(
            (ok, f"[{table}] embedding é {ftype} (halfvec={is_halfvec}, dims={typmod}; "
                 f"esperado halfvec/{dim})")
        )

    # índices obrigatórios, válidos, com o acesso certo
    idxrows = _fetch_all(
        url,
        f"""
        SELECT c.relname, am.amname, i.indisvalid,
               pg_get_indexdef(i.indexrelid)
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_am am ON am.oid = c.relam
        WHERE i.indrelid = '{table}'::regclass
        """,
    )
    by_name = {r[0]: r for r in idxrows}
    for name, want_am in _required_for(table).items():
        r = by_name.get(name)
        if r is None:
            results.append((False, f"[{table}] índice '{name}' AUSENTE"))
            continue
        _, amname, valid, definition = r
        ok = (amname == want_am) and bool(valid)
        detail = f"acesso={amname} valido={valid}"
        if name.endswith("_embedding_hnsw"):
            uses_correct_opclass = "halfvec_cosine_ops" in (definition or "")
            bad_opclass = "vector_cosine_ops" in (definition or "")
            ok = ok and uses_correct_opclass and not bad_opclass
            detail += f" opclass_halfvec_cosine={uses_correct_opclass}"
        results.append((ok, f"[{table}] índice '{name}' ({detail})"))

    # colunas geradas tsv / tsv_pt existem
    tsrows = _fetch_all(
        url,
        f"""
        SELECT a.attname, a.attgenerated FROM pg_attribute a
        WHERE a.attrelid='{table}'::regclass
          AND a.attname IN ('tsv','tsv_pt') AND a.attnum > 0
        """,
    )
    gen = {r[0]: r[1] for r in tsrows}
    tsv_ok = gen.get("tsv") == "s"  # 's' = generated stored
    results.append((tsv_ok, f"[{table}] coluna gerada 'tsv' presente (generated={gen.get('tsv', '-')}))"))
    tsvpt_ok = gen.get("tsv_pt") == "s"
    results.append((tsvpt_ok, f"[{table}] coluna gerada 'tsv_pt' presente (generated={gen.get('tsv_pt', '-')}))"))

    # coluna `gen` (S29 blue-green)
    gen_rows = _fetch_all(
        url,
        f"""
        SELECT a.attname FROM pg_attribute a
        WHERE a.attrelid='{table}'::regclass AND a.attname = 'gen' AND a.attnum > 0
        """,
    )
    results.append((bool(gen_rows), f"coluna '{table}.gen' presente (S29 blue-green)"))
    return results


def _published_profiles(url: str) -> list[tuple[str, int]]:
    """[(tabela, dim)] de TODO perfil publicado por algum repo, lido do ponteiro+registry.

    O ponteiro `published_profile` é POR REPO (I14); um mesmo volume pode servir
    repos com perfis distintos. verify deve validar CADA tabela que está de fato
    atendendo leitura — não uma escolha global arbitrária. Default gemini/chunks
    entra sempre (compat histórica, I12). Se rag_sync_state/publicado ainda não
    existir (volume pré-S32), cai no default sem falhar.
    """
    try:
        from ingest import profiles as _p  # noqa: PLC0415 — só quando há banco
    except Exception:  # pragma: no cover - ambiente mínimo do container
        return [("chunks", 3072)]
    try:
        rows = _fetch_all(url, "SELECT DISTINCT published_profile FROM rag_sync_state "
                                "WHERE published_profile IS NOT NULL ORDER BY 1")
        slugs = [r[0] for r in rows if r[0]]
    except Exception:  # coluna/tabela ausente → só o default legado
        slugs = []
    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for slug in [_p.DEFAULT_PROFILE] + [s for s in slugs if s != _p.DEFAULT_PROFILE]:
        prof = _p.PROFILES.get(slug)
        table, dim = ("chunks", 3072) if prof is None else (prof.table, prof.dim)
        if table not in seen:
            seen.add(table)
            out.append((table, dim))
    return out or [("chunks", 3072)]


def check(url: str) -> list[tuple[bool, str]]:
    """Rodar todas as checagens; retorna [(ok, mensagem), ...].

    S32-b (I12): valida SEMPRE a tabela default `chunks` (compat histórica) E, se
    houver OUTRO perfil publicado por algum repo, valida também aquela tabela
    contra o dim declarado no registry (test 13 — dim divergente = FALHA).
    """
    results: list[tuple[bool, str]] = []

    # 1. tabela chunks existe (perfil default — checagem preservada)
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
        # sem a tabela default, o resto não faz sentido
        results.append((False, "schema ausente — abortando checagens restantes"))
        return results

    # 2..6. estrutura do perfil default (chunks, halfvec 3072)
    results.extend(_check_table(url, "chunks", 3072))

    # 7. S32-b: validar CADA outro perfil publicado (por repo) contra o registry.
    for pub_table, pub_dim in _published_profiles(url):
        if pub_table == "chunks":
            continue
        try:
            pub_exists = _fetch_all(
                url, f"SELECT to_regclass('{pub_table}') IS NOT NULL")[0][0]
        except Exception:
            pub_exists = False
        results.append((bool(pub_exists),
                        f"tabela do perfil publicado '{pub_table}' presente"))
        if pub_exists:
            results.extend(_check_table(url, pub_table, pub_dim))

    # 8. ponteiros de geração no estado (uma vez, independentemente do perfil)
    state_cols = _fetch_all(
        url,
        """
        SELECT a.attname FROM pg_attribute a
        WHERE a.attrelid='rag_sync_state'::regclass
          AND a.attname IN ('published_gen','in_progress_gen','profile','published_profile')
          AND a.attnum > 0
        """,
    )
    have = {r[0] for r in state_cols}
    ptr_ok = {"published_gen", "in_progress_gen"} <= have
    results.append((ptr_ok, f"rag_sync_state tem published_gen/in_progress_gen (presentes={sorted(have)})"))
    # S32-b: colunas de perfil no estado (lockstep com migração 005 / init.sql).
    prof_cols_ok = {"profile", "published_profile"} <= have
    results.append((prof_cols_ok, f"rag_sync_state tem profile/published_profile (S32-b) presentes={sorted(have)}"))

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
