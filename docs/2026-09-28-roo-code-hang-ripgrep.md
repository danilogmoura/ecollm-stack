# Roo Code trava em "API Request…" para sempre — causa raiz: `ripgrep` ausente

- **Data:** 2026-09-28
- **Ambiente:** WSL2 · code-server (VS Code Remote) · Linux x64
- **Cliente:** Roo Code `3.54.0` (`rooveterinaryinc.roo-cline-3.54.0`)
- **Backend:** LiteLLM proxy `:4000` (config [`../litellm/config.yaml`](../litellm/config.yaml)) + MCP `rag_search` ([`../mcpsrv/rag_server.py`](../mcpsrv/rag_server.py))
- **Status:** ✅ **Resolvido e verificado** (usuário confirmou; log sem erros, task avança até `followup`)
- **Impacto no código do repo:** **nenhum** — working tree permaneceu limpo. O fix é de *ambiente* (binário ausente), não da aplicação.

---

## 1. Sintoma

Ao enviar qualquer tarefa no Roo Code, a interface congelava indefinidamente no botão
**"API Request…"**. A requisição **nunca chegava a ser processada** pelo cliente, apesar de:

- O LiteLLM estar **100% saudável**: `GET :4000/health/liveliness` → `"I'm alive!"`, e um
  `curl` reproduzindo o **payload EXATO** que o Roo manda (streaming SSE + `tools:[rag_search]`)
  respondia perfeitamente (`finish_reason` correto + `[DONE]`).
- O servidor MCP responder ao handshake `initialize` + `tools/list` com JSON-RPC válido.

Detalhe decisivo: o travamento era **idêntico com QUALQUER modelo**
(`qwen3.8-flash`, `qwen3.8-flash-fast`, `deepseek-flash`). Isso já apontava para um
**bloqueador pré-API do cliente**, não para o modelo, o streaming ou o proxy.

No lado do LiteLLM apareciam `CancelledError` + `stream_closed` — ou seja, **o Roo cancelou
o stream antes de consumi-lo**. Era *consequência*, não causa.

---

## 2. Diagnóstico (como se chegou à causa)

Ordem de eliminação, do backend para o cliente:

1. **Servidor/MCP saudáveis?** → Sim (handshake OK, `TOOLS=['rag_search']`).
2. **Endpoint responde ao payload real do Roo?** → Sim: `curl` com o corpo exato capturado
   (via `LITELLM_LOG=DEBUG`, depois revertido para `INFO` — ⚠️ DEBUG vaza corpo inteiro,
   incluindo credenciais e prompts) retornou resposta perfeita.
3. **É o `thinking ON` / `reasoning_content` vazio?** → Não. Red herring.
4. **É o perfil de API por modo (`ModeApiConfig`: UI mostrava `-fast`, request enviava `flash`)?**
   → Não. Também red herring.
5. **Log PRÓPRIO do Roo** em
   `~/.vscode-server/data/logs/<sessão>/exthost*/output_logging_*/1-Roo-Code.log`
   → continha **7× `ripgrep not found`**. ← **Aqui estava a causa.**

> **Lição durável:** quando um agente de código trava em "API Request…" com *qualquer*
> modelo e o proxy está saudável, suspeite de uma **checagem pré-API do cliente**
> (ripgrep/git), não do streaming/modelo/proxy. Isolou-se com `curl` do payload exato +
> leitura do log do próprio cliente (não só do backend).

---

## 3. Causa raiz

Antes de disparar a requisição HTTP, o Roo Code executa uma verificação de repositório git
aninhado (`getNestedGitRepository`) que **depende do binário `ripgrep` (`rg`)**. Quando o `rg`
não é encontrado, ele lança um erro e **aborta silenciosamente o fluxo** — daí o hang eterno
no "API Request…".

Trecho real extraído do bundle `dist/extension.js` da extensão:

```js
// …replacePath:e, limit:r=500}){
let a = await fne(mne.env.appRoot);
if (!a) throw new Error(`ripgrep not found: ${a}`);
return new Promise((o, s) => { let n = MCr.spawn(a, t), /* … */ });
```

E a função `fne` que resolve o caminho do binário, testando uma lista fixa de locais
**relativos a `appRoot`** (ela **NÃO usa o `PATH`**):

```js
return await e("node_modules/@vscode/ripgrep/bin/")
    || await e("node_modules/vscode-ripgrep/bin")
    || await e("node_modules.asar.unpacked/vscode-ripgrep/bin/")
    || await e("node_modules.asar.unpacked/@vscode/ripgrep/bin/");
// nome do binário: "rg" (linux/macOS) | "rg.exe" (Windows)
```

**Consequência prática:** instalar o `rg` no `PATH` (ex.: `~/.local/bin`) **não resolve**,
porque o Roo procura exclusivamente dentro de `<appRoot>/node_modules/...`. Foi exatamente o
que aconteceu na primeira tentativa de correção.

---

## 4. Solução aplicada

Colocar o binário `rg` no **primeiro caminho hardcoded** que o Roo testa, relativo ao `appRoot`.

### Valores reais deste ambiente

| Item | Valor |
| ---- | ----- |
| `appRoot` | `/home/demo/.vscode-server/bin/04c0d99f4fb0d8afe6ce4f0c58e31e183ac3e4b1` |
| Extensão Roo | `~/.vscode-server/extensions/rooveterinaryinc.roo-cline-3.54.0` |
| Origem do binário | `<appRoot>/node_modules/@vscode/ripgrep-universal/bin/linux-x64/rg` |
| Destino do fix | `<appRoot>/node_modules/@vscode/ripgrep/bin/rg` |
| Versão | `ripgrep 15.0.0 (rev 3a612f88b8)` · `features:+pcre2` · 5.728.032 bytes |

### Comando do fix (reprodutível)

```bash
APPROOT=$(ls -d ~/.vscode-server/bin/*/ | head -1)
SRC="$APPROOT/node_modules/@vscode/ripgrep-universal/bin/linux-x64/rg"
DST_DIR="$APPROOT/node_modules/@vscode/ripgrep/bin"
mkdir -p "$DST_DIR"
cp "$SRC" "$DST_DIR/rg"
chmod +x "$DST_DIR/rg"
"$DST_DIR/rg" --version   # -> ripgrep 15.0.0 (rev 3a612f88b8)
```

> Se o diretório `@vscode/ripgrep-universal` não existir no seu `appRoot`, baixe um `rg`
> estático Linux x64 (v≥14) e coloque-o no mesmo destino. O essencial é: **um executável
> chamado `rg` em `<appRoot>/node_modules/@vscode/ripgrep/bin/rg`**.

### Por que funciona sem reiniciar

O fix é baseado em **disco** (o arquivo passa a existir no caminho testado), então vale
imediatamente. Diferente de um fix por `PATH`: em **WSL**, o *"Developer: Reload Window"*
**não mata o processo `vscode-server`** (ele sobrevive), logo mudanças de `PATH` não pegariam
sem matar o server ou fechar a janela.

---

## 5. Verificação

Após aplicar o fix:

- Log Roo mais recente: **0 ocorrências** de `ripgrep not found`.
- Task mais nova (`ui_messages.json`): sequência `text → api_req_started → text →
  api_req_started → followup` — ou seja, o Roo passou a **responder normalmente** e sugerir
  follow-ups (antes parava em `api_req_started` com `tokensIn/tokensOut = 0`).
- Usuário confirmou funcionamento ("Aléluia!").

### Como diagnosticar no futuro (runbook rápido)

```bash
# 1) Os requests estão chegando ao LiteLLM?
docker compose logs --since=5m litellm | grep "POST /v1/chat"

# 2) O Roo ainda reclama de ripgrep?
L=$(ls -t ~/.vscode-server/data/logs/*/exthost*/output_logging_*/1-Roo-Code.log | head -1)
grep -c "ripgrep not found" "$L"

# 3) A task travou pré-consumo? (api_req_started sem finished + tokens 0)
#    ~/.vscode-server/data/User/globalStorage/rooveterinaryinc.roo-cline/tasks/*/ui_messages.json
```

---

## 6. Red herrings (sintomas que NÃO eram a causa)

- **`thinking ON` / `reasoning_content` vazio:** os modelos `qwen3.8-*` emitem raciocínio, mas
  isso não bloqueava o fluxo.
- **`ModeApiConfig` (perfil de API por modo):** a UI mostrava `-fast` enquanto o request ia com
  `flash`; real, mas irrelevante para o hang.
- **Streaming/parser/proxy:** o backend esteve saudável o tempo todo.

---

## 7. Manutenção / caveats

- ⚠️ **O `rg` instalado vive dentro do diretório de hash do `vscode-server`
  (`~/.vscode-server/bin/<hash>/`).** Quando o VS Code/code-server **atualizar**, ele cria um
  novo diretório de hash e o fix **é perdido**. Se o Roo voltar a travar após um update,
  **refazer a seção 4** apontando para o novo `appRoot`.
- 🧹 Resíduo inofensivo: `~/.local/bin/rg` (da 1ª tentativa via `PATH`). Não é usado pelo Roo;
  pode permanecer ou ser removido.
- 🔒 Nunca ativar `LITELLM_LOG=DEBUG` de forma permanente: vaza corpo inteiro das requisições
  (credenciais + prompts). Usar sob demanda e reverter para `INFO`.

---

## 8. Arquivos relacionados neste repositório

| Arquivo | Papel |
| ------- | ----- |
| [`../litellm/config.yaml`](../litellm/config.yaml) | Definição dos modelos roteados pelo proxy (inclui variantes `-fast` com `enable_thinking:false`). |
| [`../mcpsrv/rag_server.py`](../mcpsrv/rag_server.py) | Servidor MCP `rag_search` consumido pelo Roo/Copilot. |
| [`../.env.example`](../.env.example) | Template de variáveis (`LITELLM_MASTER_KEY`, `RAG_PROFILE`, etc.). |
| [`../README.md`](../README.md) | Visão geral da stack e comandos. |

> Nota: este incidente **não gerou mudança de código** no repositório — o bug era de ambiente
> (binário `rg` ausente). Esta pasta `docs/` existe justamente para capturar diagnósticos
> operacionais assim, separados do planejamento local (`.planning/`, que é gitignored).
