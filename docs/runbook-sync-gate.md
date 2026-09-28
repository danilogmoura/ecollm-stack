# Runbook — `sync` e `gate` (manutenção do índice RAG)

> Guia operacional dos dois rituais que mantêm a busca RAG correta: **sync** (índice = código) e **gate** (qualidade sem regressão). Criado 2026-09-28.

## Por que existem

A busca RAG **não lê seus arquivos diretamente**. Ela consulta um **índice** (tabelas no Postgres, uma por perfil de embedding) onde cada trecho virou um *chunk* com vetor. Disso derivam dois riscos independentes:

| Risco | Sintoma | Ritual que resolve |
| --- | --- | --- |
| Índice desatualizado vs. código | buscas retornam `stale=True`, informação velha | **sync** |
| Qualidade da recuperação regride (ao mexer em search/chunker/embed/perfil) | busca "funciona" mas acha os trechos errados | **gate** |

```
código no disco --[sync]--> índice (chunks+vetores) --> buscas
                                                     ^
                                              [gate] mede se ainda acha certo
```

---

## 1. `sync` — atualizar o índice

Relê o repositório, recalcula chunks, re-embedda e grava na tabela do **perfil ativo**.

### Comando canônico

```bash
RAG_PROFILE=qwen37 .venv/bin/python -m ingest.cli sync
```

Saída típica (exemplo real de 2026-09-28):

```
chunks=746  inseridos=9  removidos=737  ... gitleaks=0
```

Leitura: removeu os chunks do estado anterior e inseriu os novos, fechando em 746. É o que conserta `stale=True`.

### Variantes úteis

- **Simular sem gravar** (ver impacto antes de aplicar):

  ```bash
  .venv/bin/python -m ingest.cli sync --dry-run
  ```

- **Estado por perfil** (tabela existe? tem chunks? HEAD publicado?):

  ```bash
  RAG_PROFILE=qwen37 .venv/bin/python -m ingest.cli profile status
  ```

- **Publicar/alternar perfil** (ato explícito, fail-closed):

  ```bash
  .venv/bin/python -m ingest.cli profile list
  .venv/bin/python -m ingest.cli profile use bgem3      # recusa se índice vazio/stale
  .venv/bin/python -m ingest.cli profile switch qwen37  # sync do alvo se preciso + publica
  ```

### Quando rodar

| Situação | Sync? |
| --- | --- |
| Editou/commitou arquivos do corpus | **Sim**, senão fica `stale=True` |
| Só rodou testes / leu código | Não |
| Trocou de perfil de embedding | Sim, para aquele perfil |

### Interpretação

- `gitleaks>0` → **pare**: um segredo entrou no corpus; não publique.
- Busca ainda com `stale=True` após editar → rode sync (o `head_sha` publicado divergia do HEAD).

---

## 2. `gate` — travar regressão de qualidade

Teste numérico: roda perguntas curadas (`eval/dataset.jsonl`) contra o índice real e mede **recall@8** (fração das perguntas cujo alvo certo aparece nos 8 primeiros resultados). Se cair abaixo do piso, **reprova com exit code 1**.

### Números travados (ler de `eval/recall.py`, podem mudar)

```python
BASELINE_RECALL_AT_8 = 0.933   # qualidade atual medida
MARGEM_REGRESSAO     = 0.033   # tolerância à flutuação natural de embeddings
GATE_K               = 8       # janela avaliada
# piso efetivo = 0.933 - 0.033 = 0.900
```

Regra: **recall@8 ≥ 0,900 → passa**; abaixo → falha.

### Comando canônico

```bash
export RAG_PROFILE=qwen37
.venv/bin/python -m eval.recall --gate
```

Saída conceitual:

```
recall@8 = 0.933   piso = 0.900   → PASSED ✅   (exit 0)
```

Se a mudança tivesse derrubado para 0,85:

```
recall@8 = 0.850   piso = 0.900   → FALHOU ❌   (exit 1)
```

### ⚠️ O falso-falha (pegadinha nº 1)

Sem exportar `RAG_PROFILE`, o gate usa o perfil default (`gemini`), cuja escala/distância é outra, e **reprova mesmo com índice saudável**. Sempre prefixe `RAG_PROFILE=qwen37`.

### Diagnóstico sem reprovar

```bash
.venv/bin/python -m eval.recall --k 1,3,5,8,10
```

Mostra a curva de recall em vários pontos (útil para ver "acho o alvo, mas só em rank 5"). Gera relatório em `.planning/relatorio-avaliacao-<YYYYMMDD>.md`.

### Formato das perguntas do dataset

Cada linha de `eval/dataset.jsonl` é uma pergunta + o alvo esperado:

```json
{"id": "q01", "question": "Qual modelo gera os embeddings da stack e com quantas dimensões?", "expect_paths": ["README.md"], "expect_kinds": ["doc"], "note": "..."}
{"id": "q06", "question": "Qual é o modelo de fallback local quando o chat do RAG falha?", "expect_paths": ["litellm/config.yaml", "README.md"], "expect_kinds": ["config"], "note": "rag-chat -> qwen3:4b-instruct-2507"}
```

- `expect_paths` / `expect_symbols` / `expect_kinds`: definem o chunk "certo".
- Eixos extras (S23): `source="external"` (expor overfitting), `should_refuse=true` (pergunta fora-do-assunto que deve retornar nada), `expect_targets` (cobertura multi-alvo).

---

## 3. Ritual combinado pós-mudança no pipeline

Depois de alterar `ingest/`, `search`, `chunker`, `embed` ou commitar mudança de corpus:

```bash
export RAG_PROFILE=qwen37
# 1. rebuilda o índice
.venv/bin/python -m ingest.cli sync
# 2. confirma alinhamento com o HEAD
.venv/bin/python -m ingest.cli profile status   # head_sha == git HEAD, STALE? False
# 3. confima que a qualidade não caiu
.venv/bin/python -m eval.recall --gate          # PASSED (recall@8 ≥ 0,900)
# 4. só então commitar / fechar a tarefa
```

## 4. Checklist rápido

- [ ] `RAG_PROFILE=qwen37` exportado antes de gate/sync?
- [ ] Sync reportou `gitleaks=0`?
- [ ] `profile status` mostra `STALE? False`?
- [ ] Gate `PASSED` (exit 0)?
- [ ] Nenhum `.planning/`, `.env`, `.roo/` staged no commit?

## 5. Modo Roo dedicado

Estes rituais estão encapsulados no modo customizado **Gate & Sync** (`.roo/.roomodes`, slug `gate`), que restringe o agente a leitura + comandos + MCP (sem edição de código) e injeta as regras de `.roo/rules-gate/`. Use-o ao apenas manter o índice, sem risco de edições acidentais.
