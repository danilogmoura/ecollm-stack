# S103 — Fase J: vídeo/3D assíncrono (T24)

**Data:** 2026-10-17 · **Escopo:** resolver o gap S100 de vídeo/3D — task id +
polling → artefato acessível **ou** motivo documentado.
**Alvo:** gateway NovAI (`aiapi-pro.com`). **Custo:** alto (autorizado pelo usuário
para usar modelo pago neste teste).

## 1. Resultado

| Endpoint | Modelo | Resultado |
| --- | --- | --- |
| `/v1/video/generations` | `minimax-video-h3` | ✅ **SUCCEEDED** — artefato mp4 em 14–18 polls |
| `/v1/three_d/generations` | `hy-3d-3.1` | ✅ **SUCCEEDED** — artefato 3D em 15 polls |
| `/v1/video/generations` | `cogvideox-flash` (grátis) | ❌ instável — `RemoteDisconnected` / HTTP 520 |
| `/v1/video/generations` | `minimax-video-v2.3-fast` | ❌ `status=FAILED` no upstream |

**Gap S100 resolvido:** vídeo e 3D **são roteáveis** pelo gateway, com contrato
assíncrono `POST → id → GET /{id} → status terminal → URL`.

## 2. Contrato descoberto

```
POST /v1/video/generations      {"model": "...", "prompt": "..."}
  → 200 {"id": "...", "request_id": "vidgen-...", "status": "queued",
         "model": "...", "resolution": "720p", "duration": 5}

GET  /v1/video/generations/{id}
  → 200 {"id": "...", "task_status": "PROCESSING" | "SUCCEEDED" | "FAILED",
         "upstream_status": "...", "video_url": "https://..." | null,
         "url": "https://..." | null, "video_result": []}
```

3D usa o mesmo shape em `/v1/three_d/generations` (rota `/v1/3d/generations`
devolve **405**).

## 3. Achados

### J1 — campo `n` derruba a conexão (classe H, NOSSO bug) — **corrigido**

`{"model": ..., "prompt": ..., "n": 1}` → `RemoteDisconnected`. Sem `n` → 200.
Isolado por A/B direto no gateway. O body do runner não envia mais `n`.

### J2 — polling era POST, não GET (classe H, NOSSO bug) — **corrigido**

`make_sender` só fazia `POST`; o poll devolvia **405 Method Not Allowed**.
`make_sender` ganhou `method="GET"` e o runner usa `GET <path>/<id>`.

### J3 — `cogvideox-flash` (grátis) é instável (upstream)

`RemoteDisconnected` e HTTP 520 (Cloudflare) intermitentes. Não é bug nosso: o
mesmo body via `curl` alterna entre 200 e conexão derrubada. **Não serve como
representante** do endpoint.

### J4 — `minimax-video-v2.3-fast` falha no upstream

Task criada, `status=FAILED`, `upstream_status="Fail"`, `video_url=null`, sem
motivo detalhado na resposta. Modelo pago quebrado.

### J5 — 3D é mais lento que vídeo

`hy-3d-3.1` estourou 20 polls × 6 s (2 min) ainda em `PROCESSING`; concluiu em
**15 polls × 10 s** com orçamento de 60. O CLI usa orçamento maior para 3D.

## 4. Implementação

### Funções puras (`eval/novai_test.py`)

| Função | Papel |
| --- | --- |
| `extract_task_id(payload)` | aceita `id`/`task_id`/`taskId`; `None` se ausente |
| `extract_task_status(payload)` | normaliza `task_status`/`status`/`state` em maiúsculas |
| `extract_artifact_url(payload)` | varre `url`/`video_url`/`output`/`result`/`data` e listas; **só http(s)** |
| `verdict_video_task(payload, *, polls)` | fail-closed: sucesso **exige** URL de artefato |

### Runner

`run_video_task(sender, group, *, kind, prompt, path, max_polls, interval_s, sleep)`

- **Polling limitado por design** — `max_polls` é orçamento, não loop infinito.
  Estourar = fail com evidência explícita (`orçamento de polls esgotado (N)`).
- `sleep` injetável ⇒ testes rodam sem esperar.
- `path` parametriza vídeo (`/video/generations`) vs 3D (`/three_d/generations`).

### CLI

- `--video MODEL` — task de vídeo.
- `--3d MODEL` — task 3D (orçamento 60 × 10 s).

## 5. Verificação

- Suíte completa: **795 passed** (+19 testes da Fase J).
- Live: vídeo ✅ e 3D ✅, ambos reprodutíveis (vídeo confirmado em 2 rodadas).

## 6. Arquivos tocados

- `eval/novai_test.py` — 4 funções puras, `run_video_task`, `make_sender` com GET,
  flags `--video`/`--3d`.
- `eval/tests/test_novai_test.py` — +19 testes (extractors, veredito, polling,
  orçamento esgotado, falha precoce).
