# NovAI — Relatórios e Evidências

Investigação completa da integração com o gateway NovAI (`aiapi-pro.com`) via proxy LiteLLM. Período: 2026-10-14 a 2026-10-18.

---

## Estrutura

```
NovAI/
├── tickets-upstream.md  # 📌 7 bug reports em inglês (pronto para envio à NovAI)
├── catalogo/            # Configuração, modelos, docs, tool scan
├── contrato/            # Contrato API, streaming SSE, LiteLLM stack
├── testes/              # Fases de teste (F–L), sweeps, verificações
├── reteste/             # S122-R: dossiê, evidências, consolidado
└── logs/                # Logs brutos (jsonl, txt, csv) de todas as execuções
```

---

## Catálogo (`catalogo/`)

| Arquivo | Conteúdo |
| --------- | ---------- |
| `2026-10-16-novai-configs-por-modelo.md` | Configurações por modelo (params, limits, capabilities) |
| `2026-10-16-novai-model-api.md` | Análise da API de modelos NovAI |
| `2026-10-16-novai-docs.md` | Documentação oficial NovAI analisada |
| `2026-10-16-novai-enriquecido.md` | Catálogo enriquecido com metadados |
| `2026-10-17-novai-tool-scan.md` | Varredura completa de tools/function calling |
| `2026-10-17-novai-tool-scan.csv` | Dados brutos do tool scan (CSV) |

## Contrato (`contrato/`)

| Arquivo | Conteúdo |
| --------- | ---------- |
| `2026-10-14-novai-sse-streaming.md` | Análise do streaming SSE NovAI |
| `2026-10-15-litellm-stack-e-catalogo-novai.md` | Integração LiteLLM + catálogo NovAI |
| `2026-10-17-novai-contrato-api.md` | Verificação de contrato OpenAI-compatível |

## Testes (`testes/`)

| Arquivo | Conteúdo |
| --------- | ---------- |
| `2026-10-17-novai-fase-f.md` | Fase F: testes iniciais |
| `2026-10-17-novai-fase-g.md` | Fase G: expansão de cobertura |
| `2026-10-17-novai-fase-h.md` | Fase H: validação de embeddings |
| `2026-10-17-novai-fase-i.md` | Fase I: testes de imagem |
| `2026-10-17-novai-fase-j.md` | Fase J: testes de vídeo/3D |
| `2026-10-17-novai-fase-k.md` | Fase K: stress tests |
| `2026-10-17-novai-fase-l.md` | Fase L: varredura final |
| `2026-10-17-novai-chat-sweep.md` | Sweep completo de chat completions |
| `2026-10-17-novai-s114-remocao-grupos-mortos.md` | S114: remoção de grupos mortos |
| `2026-10-17-novai-s114-verificacao.md` | S114: verificação pós-remoção |
| `2026-10-17-novai-s115-sweep-contrato-erro.md` | S115: sweep de envelopes de erro |
| `2026-10-17-novai-s116-fails-corrigiveis.md` | S116: fails corrigíveis localmente |

## Reteste S122-R (`reteste/`)

| Arquivo | Conteúdo |
| --------- | ---------- |
| `2026-10-18-novai-consolidado-falhas-servidor.md` | Consolidação inicial das falhas de servidor |
| `2026-10-18-novai-erros-servidor-dossie-completo.md` | **Dossiê completo** de erros de servidor |
| `2026-10-18-novai-reteste-falhas-evidencia.md` | Evidências do primeiro reteste |
| `2026-10-18-novai-reteste-s122-r-evidencia.md` | S122-R: vereditos apenas |
| `2026-10-18-novai-reteste-s122-r-detalhado.md` | S122-R: análise detalhada (o que é / por que / implica) |
| `2026-10-18-novai-reteste-s122-r-consolidado.md` | **📌 Referência canônica** — unifica evidências + análise |

### Leitura recomendada (ordem)

1. **`../tickets-upstream.md`** — 7 bug reports prontos para envio à NovAI
2. **`reteste-s122-r-consolidado.md`** — visão completa em documento único
3. **`erros-servidor-dossie-completo.md`** — contexto técnico profundo

## Logs (`logs/`)

Logs brutos organizados por data e tipo. Incluem:

- `*-novai-*.jsonl` — respostas raw da API (chat, embedding, image, proxy, gateway)
- `retest-2026-10-18/` — evidências do primeiro reteste
- `retest-2026-10-18-v2/` — evidências do reteste S122-R (5 ondas)
- `tool-scan-*` — dumps completos do tool scan

---

## Resumo dos Resultados (S122-R)

| Status | Count | Error IDs |
| -------- | ------- | ----------- |
| 🔴 FAIL persistente | 6 | P-3, P-7a, P-5, P-6, P-7b, P-7d |
| 🔴 Rate limit persistente | 1 | E-429 (glm-4.6v-flash) |
| 🟡 Intermitente | 1 | E-429 (glm-4.7-flash) |
| ✅ Resolvido | 1 | P-7c (mimo-v2.6-pro) |
| ✅ Pass | 1 | S115 (error sweep 440/440) |
| ⚪ Billing | 1 | P-7e (hy-3d-3.1 quota) |

**7 bugs abertos → 7 tickets upstream prontos para envio.**

---

## Tickets Upstream

O arquivo [`tickets-upstream.md`](tickets-upstream.md) contém **7 bug reports em inglês**, formatados e prontos para envio à NovAI. Cada ticket inclui:

- **Summary** — descrição concisa do problema
- **Evidence** — dados reproduzidos (tabelas, timestamps, payloads)
- **How We Tested** — metodologia (N≥3 retries, 10s spacing, streaming)
- **Impact** — consequências para billing, monitoring, UX
- **Requested Action** — o que se espera da NovAI

| # | Ticket | Error ID | Severidade |
| --- | -------- | ---------- | ------------ |
| 1 | Reasoning Accounting Inconsistency | P-3 | 🔴 Persistente |
| 2 | wan2.2-t2i-flash Deterministic Timeout | P-7a | 🔴 Persistente (120s) |
| 3 | Gateway/Proxy Divergence on Error Envelopes | P-5 | 🔴 Confirmado |
| 4 | Partial Model Failures (3/5 models) | P-6 | 🔴 Parcial |
| 5 | Missing [DONE] Sentinel in SSE Stream | P-7b | 🔴 Confirmado |
| 6 | Async Task FAILED Without Error Detail | P-7d | 🔴 Confirmado |
| 7 | glm-4.6v-flash Persistent Rate Limit | E-429 | 🔴 Persistente |

> **Arquitetura:** Os testes foram executados contra o gateway direto (`aiapi-pro.com`) e via proxy LiteLLM (`localhost:4000`) para isolar bugs upstream de comportamento do proxy.

---

*Última atualização: 2026-10-18*
