# Migrações de schema do índice RAG (S18 · T-OPS-3)

`rag-db/init.sql` só roda na **primeira** criação do volume e o entrypoint do
Postgres não garante `ON_ERROR_STOP` (ver S11). Para **evoluir** o schema depois
do bootstrap usamos este diretório.

## Como funciona

- Um arquivo por mudança: `NNN_descricao.sql`, com `NNN` inteiro de 3 dígitos,
  crescente e **sem lacunas** (`001`, `002`, …). O runner valida a sequência.
- Cada migração deve ser **idempotente** (`IF NOT EXISTS` / `IF EXISTS` /
  `ON CONFLICT`). Assim ela roda tanto num volume novo (onde `init.sql` já criou
  tudo → vira no-op) quanto num volume antigo.
- O runner (`rag-db/run_migrations.py`) registra cada `NNN` aplicado na tabela
  `schema_migrations` e pula o que já foi aplicado — re-rodar é sempre seguro.
- Cada migração roda em **transação própria**: se falhar, faz rollback daquela e
  para; nunca deixa metade aplicada nem marca como concluída.

## Regra de ouro

> **Nunca edite uma migração já aplicada.** Correção vira uma migração nova
> (`N+1`). `init.sql` continua sendo o retrato do estado inicial p/ volume novo;
> migrações trazem o delta p/ volumes existentes. Ao fim, os dois caminhos
> convergem para o mesmo schema — conferido por `verify_schema.py` (S11).

## Comandos

```bash
python rag-db/run_migrations.py --status     # o que está aplicado x pendente
python rag-db/run_migrations.py --dry-run    # o que seria aplicado
python rag-db/run_migrations.py              # aplica as pendentes
python rag-db/verify_schema.py               # confirma integridade pós-migração
```

Lê `RAG_DB_URL` do `.env` no repo root (override com `--url`).

## Histórico

| NNN | Arquivo | O que faz |
| --- | --- | --- |
| 001 | `001_baseline.sql` | Estado inicial (FASE 0 + S11 + S14), idempotente. No-op num volume recém-bootstrapped. |
| 002 | `002_add_meta.sql` | Coluna `meta jsonb` em `chunks` (metadados futuros sem nova ALTER por campo). |
