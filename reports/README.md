# `reports/` — relatórios e logs de diagnóstico (versionado)

Diretório **versionado** desde **S106 (2026-10-16)**: relatórios e logs do
trilho de testes **NovAI** são **públicos** e sobem para o remoto. Exceção
explícita (gitignored, ficam locais): os 4 artefatos de **telemetria
operacional** em `reports/logs/` — `mcp-stderr.log`, `h4-mcp-stderr.log`,
`rag-sync.log` e `c6-cost-history.json` — porque contêm queries reais de RAG e
histórico de custo da conta. É o destino de **tudo que é diagnóstico de
operação**: os relatórios narrativos `.md` ficam na raiz deste diretório e os
**logs de execução** ficam em `reports/logs/`.

🔒 **Antes de commitar:** qualquer saída de geração de imagem traz **URLs
pré-assinadas** (AccessKeyId + Signature, expiração ~7 dias). `eval/novai_enrich.py`
redige a query de qualquer URL pré-assinada (`Signature=`/`UCloudPublicKey`/
`X-Amz-Signature`/`OSSAccessKeyId`/**Tencent COS `q-ak=AKID…`/`q-signature`**) ao
persistir `--out`. Se um artefato antigo
ainda tiver URL assinada, redija com
`python -c "import re;p='reports/novai-enriched.json';s=open(p).read();open(p,'w').write(re.sub(r'(\?(?:[^&\"\\\\ ]*&)?)(UCloudPublicKey|Signature|Expires|OSSAccessKeyId|X-Amz-Signature|Credential|Date|SignedHeaders|Algorithm|Security-Token|token)=[^&\"\\\\ ]*', r'\1\2=[REDACTED]', s))"`.

Motivo (S101): antes, o único `.log` de operação morava em `.planning/` —
diretório de **governança** (backlog/estado/planos, também gitignored). Misturar
log de runtime com governança suja o diretório de decisão e faz cada `git
status` do planejamento parecer alterado. Separação adotada: `.planning/` =
decisão; `reports/` = observação.

## Estrutura

```text
reports/                              ← VERSIONADO (S106): sobe para o remoto
├── README.md                         ← este arquivo (política)
├── 2026-10-15-litellm-stack-e-catalogo-novai.md   ← relatórios .md datados (públicos)
├── 2026-10-14-novai-sse-streaming.md
├── novai-*.json / novai-test-matrix.csv            ← dados NovAI (públicos, URLs redigidas)
└── logs/
    ├── 2026-10-16-thinking-sense-retry2.log       ← logs de sweep NovAI (PÚBLICOS)
    ├── 2026-10-16-novai-enrich.log                ←   (image-sweep, thinking-sense,
    ├── ...                                          novai-model-api, chat-sample…)
    ├── rag-sync.log               ← LOCAL (gitignored): sync do índice RAG
    ├── mcp-stderr.log             ← LOCAL (gitignored): stderr MCP (queries de RAG)
    ├── h4-mcp-stderr.log          ← LOCAL (gitignored): legado H4 (congelado)
    └── c6-cost-history.json       ← LOCAL (gitignored): série temporal de custo
```

- **Raiz `reports/`** → relatórios narrativos, nomeados
  `AAAA-MM-DD-<tema>.md`. Data = dia em que o diagnóstico foi escrito. **Públicos.**
- **`reports/logs/`** → arquivos `.log` de operação + snapshots `.json`. Logs do
  trilho **NovAI** são públicos; os **4 operacionais** listados acima ficam locais
  (gitignored). **Um lugar só para log**: nenhum produtor escreve `.log` fora daqui
  (nem em `.planning/`).

## Produtores (quem escreve onde)

| Produtor | Arquivo | Como |
| --- | --- | --- |
| `.git/hooks/post-commit` (instalado de `rag-db/post-commit.sample`) | `logs/rag-sync.log` | hook rotaciona o próprio log antes de gravar |
| `.vscode/mcp.json` | `logs/mcp-stderr.log` | `... rag_server.py 2>> reports/logs/mcp-stderr.log` |
| `.roo/mcp.json` | `logs/mcp-stderr.log` | idem (mesmo padrão do VS Code) |
| `eval/mcp_report.py` | lê `logs/mcp-stderr.log` | `DEFAULT_LOG` aponta para cá |
| `rag-db/sync_if_stale.sh` | `logs/c6-cost-history.json` | snapshot de custo (dado, não log) |
| `rag-db/rotate_log.sh` | `logs/*.log` | rotação manual sob demanda |

⚠️ `reports/` é **versionado** (S106), mas os 4 logs operacionais são
gitignored ⇒ num clone limpo eles não existem. Todo produtor que escreve aqui
precisa de `mkdir -p reports/logs` antes (o hook e os `mcp.json` já fazem isso
explicitamente).

## Política de retenção e rotação

Não há retenção infinita: os dois logs vivos são **rotacionados antes de
crescer**, pelo próprio produtor.

- **`rag-sync.log`** — teto **1000 linhas**; ao exceder, o hook gera
  `rag-sync.log.1` (uma geração) e recomeça o log. `rag-sync.log.1` é
  sobrescrito na rotação seguinte (não acumula gerações).
- **`mcp-stderr.log`** — teto **500 linhas**; mesma mecânica (`mcp-stderr.log.1`).
  O MCP é reiniciado pelo editor com frequência e hoje escreve pouco; o teto
  existe para o caso de stack trace repetido.
- **`h4-mcp-stderr.log`** — **congelado**. Legado do experimento H4, não é mais
  escrito por nenhum produtor (`.roo/mcp.json` apontava para ele por engano até
  a S101). Mantido só como evidência histórica; pode ser apagado sem impacto.
- **`c6-cost-history.json`** — **sem rotação automática**; é série temporal
  (cada `sync_if_stale.sh` faz *append* de um ponto). Se crescer demais, o
  próprio script precisa ser ajustado — não é log, apagar perde a série.
- **Rotação manual**: `rag-db/rotate_log.sh` para forçar quando necessário.

Limpeza segura: apagar `*.log` e `*.log.1` a qualquer momento (são diagnóstico,
não estado). **Não** apagar `c6-cost-history.json` sem querer.

## Escopo NovAI (regra canônica)

**Todo** artefato de diagnóstico do gateway NovAI vive aqui em `reports/`:
relatórios narrativos, bugs (ex.: framing SSE), problemas de conexão/latência,
429/timeout, resultados de sweeps ao vivo e o CSV-matriz de teste. Nada de
diagnóstico NovAI fora deste diretório (nem em `.planning/`, nem na raiz do
repo, nem em `docs/`).

- Relatórios `.md` datados: `AAAA-MM-DD-<tema>.md` na raiz de `reports/`.
- Dados brutos / matriz: `reports/novai-test-matrix.csv` (fonte de verdade por
  grupo/modalidade; **público** desde S106).
- Logs de execução de sweep: `reports/logs/`.
- O relatório consolidado final da S102 também é escrito aqui (só após o gatilho
  "terminamos" do usuário).

## Histórico

- **S101 (2026-10-15)**: criado `reports/logs/`; migrados os 3 `.log` de
  `.planning/` (`rag-sync.log`, `mcp-stderr.log`, `h4-mcp-stderr.log`) + o
  snapshot `c6-cost-history.json`; produtores repontados
  (`post-commit.sample`, `.vscode/mcp.json`, `.roo/mcp.json`,
  `eval/mcp_report.py`, `sync_if_stale.sh`, `mcp.example.json`); testes
  (`test_post_commit.py`, `test_sync_if_stale.py`) atualizados para o novo
  caminho. `.planning/` fica sem `.log`.
- **S106 (2026-10-16)**: `reports/` deixa de ser gitignored e passa a ser
  **versionado** — relatórios, dados e logs do trilho **NovAI** tornam-se
  públicos (decisão do usuário). Os 4 artefatos de **telemetria operacional**
  (`mcp-stderr.log`, `h4-mcp-stderr.log`, `rag-sync.log`, `c6-cost-history.json`)
  são movidos para ignore explícito (contêm queries reais de RAG e histórico de
  custo da conta). Redigidas as 4 URLs pré-assinadas (UCloud/Volcano/Aliyun, com
  AccessKeyId+Signature válidos até 17–23/10) em `novai-enriched.json`; política
  de redação documentada no topo deste arquivo. `.gitignore`: removida a linha
  `/reports/`, adicionados os 4 caminhos locais.
