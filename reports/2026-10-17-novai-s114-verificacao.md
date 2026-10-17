# S114 — Checklist de verificação pós-testes

**Data:** 2026-10-17
**Commit:** `d1accf9` (== `origin/master`)
**Relatório principal:** `reports/2026-10-17-novai-s114-remocao-grupos-mortos.md`

Este arquivo é o **roteiro de conferência** para rodar depois que os testes
atuais terminarem. Cada item tem o comando exato e o resultado esperado.

---

## 1. Estado do repositório

```bash
git log --oneline -1
git status -sb
```

**Esperado:** `d1accf9` no topo, `## master...origin/master` sem divergência,
working tree limpo (exceto `.planning/`, que é gitignored).

---

## 2. Catálogo — contagens travadas

```bash
.venv/bin/python -c "
import yaml
d = yaml.safe_load(open('litellm/config.yaml'))
names = [m['model_name'] for m in d['model_list']]
novai = [n for n in names if n.startswith('novai-')]
print('total model_list:', len(names))
print('novai ids:', len(novai))
"
```

**Esperado:** `total model_list: 152` · `novai ids: 139`

---

## 3. Os 16 grupos mortos não existem mais

```bash
.venv/bin/python -c "
import yaml
d = yaml.safe_load(open('litellm/config.yaml'))
names = {m['model_name'] for m in d['model_list']}
dead = ['novai-qwen3.6-max-preview','novai-qwen3.6-max-preview-fast',
        'novai-qwen3-max','novai-qwen3-max-fast',
        'novai-qwen3-coder-plus','novai-qwen3-coder-plus-fast',
        'novai-qwen-vl-max','novai-qwen-vl-max-fast',
        'novai-qwen3-vl-flash','novai-qwen3-vl-flash-fast',
        'novai-qwen-omni-turbo','novai-qwen-omni-turbo-fast',
        'novai-image-qwen-image','novai-image-qwen-image-plus',
        'novai-tts-qwen-tts-latest','novai-tts-qwen-tts']
print('ainda no config:', sorted(names & set(dead)))
"
```

**Esperado:** `ainda no config: []`

---

## 4. Pares ON/OFF de chat íntegros

```bash
.venv/bin/python -c "
import yaml
d = yaml.safe_load(open('litellm/config.yaml'))
names = [m['model_name'] for m in d['model_list'] if m['model_name'].startswith('novai-')]
chat = [n for n in names if not any(n.startswith(p) for p in
        ('novai-embed-','novai-image-','novai-tts-','novai-asr-'))]
base = [n for n in chat if not n.endswith('-fast')]
print('base', len(base), 'chat', len(chat))
print('base sem par:', [n for n in base if n + '-fast' not in chat])
print('fast sem base:', [n for n in chat if n.endswith('-fast') and n[:-5] not in base])
"
```

**Esperado:** `base 55 chat 110` · `base sem par: []` · `fast sem base: []`

---

## 5. Suíte de testes

```bash
RAG_PROFILE=qwen37 .venv/bin/python -m pytest
```

**Esperado:** `833 passed`

---

## 6. Invariante 7 — nenhum `novai-*` em `rag-chat`/`fallbacks`

```bash
.venv/bin/python -c "
import yaml
d = yaml.safe_load(open('litellm/config.yaml'))
rc = [m['model_name'] for m in d['model_list'] if m['model_name'] == 'rag-chat']
fb = d.get('router_settings', {}).get('fallbacks') or d.get('litellm_settings', {}).get('fallbacks')
print('rag-chat:', rc)
print('fallbacks:', fb)
"
```

**Esperado:**
```
rag-chat: ['rag-chat']
fallbacks: [{'rag-chat': ['qwen3:4b-instruct-2507']}]
```

---

## 7. Proxy ao vivo — `/v1/models`

```bash
set -a && . ./.env && set +a
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  http://localhost:4000/v1/models | .venv/bin/python -c "
import json, sys
ids = [m['id'] for m in json.load(sys.stdin)['data']]
print('total ids:', len(ids))
print('novai ids:', len([i for i in ids if i.startswith('novai-')]))
"
```

**Esperado:** `total ids: 152` · `novai ids: 139`

> Se o proxy não estiver de pé: `docker compose up -d litellm` e aguardar ~12 s.

---

## 8. Matriz de testes

```bash
.venv/bin/python -c "
import csv, collections
rows = list(csv.DictReader(open('reports/novai-test-matrix.csv')))
print('linhas:', len(rows))
print(dict(collections.Counter(r['status'] for r in rows)))
"
```

**Esperado:**
```
linhas: 157
{'pass': 101, 'skipped': 26, 'removed': 16, 'fail': 14}
```

---

## 9. Os 14 fails são todos de upstream

```bash
.venv/bin/python -c "
import csv
rows = list(csv.DictReader(open('reports/novai-test-matrix.csv')))
for r in rows:
    if r['status'] == 'fail':
        print(r['modality'], '|', r['group'], '|', r['evidence'][:80])
"
```

**Esperado — 14 linhas, todas de uma destas 3 classes:**

| Classe | Qtd | Assinatura na evidência |
| --- | --- | --- |
| B — Kimi/ZhiPu sem modo off | 9 | `HTTP 400` + `Moonshot (Kimi)` / `ZhiPu (智谱)` |
| D — contabilidade de reasoning | 3 | `reasoning_chars=N reasoning_tokens=0` |
| G — rede / resposta vazia | 2 | `RemoteDisconnected` / `sem text` |

**Se aparecer qualquer outro tipo de falha, é regressão nossa — investigar.**

---

## 10. Sweep de chat (opcional, ~2-3 min, custo zero)

```bash
RAG_PROFILE=qwen37 .venv/bin/python -m eval.novai_test --family chat --live --sleep 1.1
```

**Esperado:** 110 grupos rodados, nenhum `404 Model not exist` de Alibaba Cloud
para os 16 removidos (eles não são mais chamados).

> O jsonl `reports/logs/2026-10-17-novai-chat.jsonl` **acumula** execuções.
> Para ler o resultado da última, agrupe por `group` e pegue a última ocorrência.

---

## Resumo do que deve estar verdadeiro

| Fato | Valor |
| --- | --- |
| Entradas em `model_list` | 152 |
| Ids NovAI | 139 |
| Chat upstreams × ON/OFF | 55 × 2 = 110 |
| Grupos mortos no config | 0 |
| `pytest` | 833 passed |
| Invariante 7 | intacto |
| Matriz | 101 pass / 26 skip / 16 removed / 14 fail |
| Fails acionáveis por nós | **0** |
