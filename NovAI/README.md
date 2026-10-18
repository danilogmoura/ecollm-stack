# NovAI — Relatórios e Evidências

Investigação completa da integração com o gateway NovAI (`aiapi-pro.com`) via proxy LiteLLM. Período: 2026-10-14 a 2026-10-18.

---

## Estrutura

```
NovAI/
├── catalogo/       # Configuração, modelos, docs, tool scan
├── contrato/       # Contrato API, streaming SSE, LiteLLM stack
├── testes/         # Fases de teste (F–L), sweeps, verificações
├── reteste/        # S122-R: dossiê, evidências, consolidado, tickets upstream
└── logs/           # Logs brutos (jsonl, txt, csv) de todas as execuções
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
| `2026-10-18-novai-tickets-upstream.md` | **Tickets para NovAI** (inglês, 7 bugs, pronto para envio) |

### Leitura recomendada (ordem)

1. **`reteste-s122-r-consolidado.md`** — visão completa em documento único
2. **`tickets-upstream.md`** — se precisar enviar bugs à NovAI
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

*Última atualização: 2026-10-18*
