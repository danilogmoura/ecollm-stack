# S119 — Sweep de contrato de tools (2026-10-17)

- Modelo-alvo: **212** (chamadas non-stream + stream cada)
- Irregularidades encontradas: **112 linhas** (112 modelos distintos)

## Distribuição non-stream

| codigo | n |
| --- | --- |
| ✅ conforme | 103 |
| ❌ erro | 63 |
| ⚠️ content+tool | 31 |
| ❌ sem tool_call | 15 |

## Distribuição stream

| codigo | n |
| --- | --- |
| ✅ só tools | 108 |
| ❌ erro | 63 |
| ⚠️ fala antes | 20 |
| ❌ sem tool_call | 15 |
| ⚠️ fala depois | 6 |

## Tabela por modelo

| alvo | modelo | non-stream | stream | evidência stream |
| --- | --- | --- | --- | --- |
| gateway | `deepseek-v4-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `deepseek-v4-flash-vision` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `deepseek-v4-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `deepseek-v4.1-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `doubao-seed-2.0-code` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `doubao-seed-2.0-lite` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `doubao-seed-2.0-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `doubao-seed-2.1-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `doubao-seed-2.1-turbo` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `doubao-seedance-2.0` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `doubao-seedance-2.0-fast` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `doubao-seedance-2.5` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `doubao-seedream-5.0` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `doubao-seedream-5.0-pro` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `glm-4.1v-thinking-flash` | ❌ sem tool_call | ❌ sem tool_call | fala=919ch args=ausente/INVALID finish=['stop'] |
| gateway | `glm-4.6v` | ⚠️ content+tool | ⚠️ fala antes | fala=43ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-4.6v-flash` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `glm-4.7-flash` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `glm-5` | ⚠️ content+tool | ⚠️ fala antes | fala=38ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5-turbo` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `glm-5.1` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.2` | ⚠️ content+tool | ⚠️ fala antes | fala=38ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.3` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.3-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.3-flashx` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `glm-5v-turbo` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `hunyuan-role` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hunyuan-t1-vision` | ⚠️ content+tool | ⚠️ fala depois | fala=96ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `hunyuan-turbos-vision-video` | ⚠️ content+tool | ⚠️ fala depois | fala=96ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `hy-3d-3.0` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-3d-3.1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-3d-express` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-3d-motion` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-mt2-lite` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-mt2-plus` | ❌ sem tool_call | ❌ sem tool_call | fala=518ch args=ausente/INVALID finish=['stop'] |
| gateway | `hy-mt2-pro` | ❌ sem tool_call | ❌ sem tool_call | fala=41ch args=ausente/INVALID finish=['stop'] |
| gateway | `hy-role` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-video-v1.5` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-vision-2.0-instruct` | ❌ sem tool_call | ❌ sem tool_call | fala=597ch args=ausente/INVALID finish=['stop'] |
| gateway | `hy3` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `hy3-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `hy4-preview` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.5` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.6` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.7-code` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.7-code-highspeed` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.8-preview` | ✅ conforme | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k3` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kling-video-o1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v2.5-turbo` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v2.6` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v3` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v3-omni` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v3-turbo` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `mimo-v2.5-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `mimo-v2.6-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `mimo-v2.6-pro` | ❌ erro | ❌ erro | transport: ConnectionError |
| gateway | `minimax-m2.5` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `minimax-m2.7` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `minimax-m3` | ⚠️ content+tool | ⚠️ fala antes | fala=133ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `minimax-music-v2.6` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `minimax-music-v3.0` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `minimax-text-01` | ✅ conforme | ❌ erro | events=8 done=False |
| gateway | `minimax-video-h3` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `minimax-video-h3-max` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `minimax-video-v2.3` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `minimax-video-v2.3-fast` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `pixverse-video-c1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `pixverse-video-v5.6` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `pixverse-video-v6.0` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen-mt-plus` | ❌ erro | ❌ erro | events=1 done=False |
| gateway | `qwen-omni-turbo` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen-plus` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `qwen-vl-max` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen-vl-ocr` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `qwen3-coder-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `qwen3-coder-plus` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen3-max` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen3-omni-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `qwen3-vl-flash` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen3-vl-plus` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `qwen3.5-ocr` | ❌ sem tool_call | ❌ sem tool_call | fala=35ch args=ausente/INVALID finish=['stop'] |
| gateway | `qwen3.6-max-preview` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `qwen3.7-max` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `qwen3.8-max` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `step-5-preview` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `tripo-3d-3.1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `tripo-3d-p1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `vidu-video-q3` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `vidu-video-q3-pro` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-deepseek-v4-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-flash-vision` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-flash-vision-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-pro-fast` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4.1-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4.1-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.0-code` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.0-code-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.0-lite` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.0-lite-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.0-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.0-pro-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.1-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.1-pro-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.1-turbo` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-doubao-seed-2.1-turbo-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.1v-thinking-flash` | ❌ sem tool_call | ❌ sem tool_call | fala=1074ch args=ausente/INVALID finish=['length'] |
| proxy | `novai-glm-4.1v-thinking-flash-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=1020ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-glm-4.6v` | ⚠️ content+tool | ⚠️ fala antes | fala=43ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.6v-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=42ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.6v-flash` | ⚠️ content+tool | ⚠️ fala antes | fala=73ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.6v-flash-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=61ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.7-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.7-flash-fast` | ❌ erro | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5-turbo` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5-turbo-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.1` | ✅ conforme | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.1-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.2` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.2-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flashx` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flashx-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5v-turbo` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5v-turbo-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-role` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hunyuan-role-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hunyuan-t1-vision` | ⚠️ content+tool | ⚠️ fala depois | fala=88ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-t1-vision-fast` | ⚠️ content+tool | ⚠️ fala depois | fala=117ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-turbos-vision-video` | ⚠️ content+tool | ⚠️ fala depois | fala=118ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-turbos-vision-video-fast` | ⚠️ content+tool | ⚠️ fala depois | fala=88ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hy-mt2-lite` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-mt2-lite-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-mt2-plus` | ❌ sem tool_call | ❌ sem tool_call | fala=785ch args=ausente/INVALID finish=['length'] |
| proxy | `novai-hy-mt2-plus-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=818ch args=ausente/INVALID finish=['length'] |
| proxy | `novai-hy-mt2-pro` | ❌ sem tool_call | ❌ sem tool_call | fala=41ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-mt2-pro-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=41ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-role` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-role-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-vision-2.0-instruct` | ❌ sem tool_call | ❌ sem tool_call | fala=585ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-vision-2.0-instruct-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=558ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy3` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy3-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy3-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy3-preview-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy4-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy4-preview-fast` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.5` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.5-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.6` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.6-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.7-code` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.7-code-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.7-code-highspeed` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.7-code-highspeed-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.8-preview` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k2.8-preview-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k3` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k3-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.5-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.5-pro-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-pro-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.5` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.5-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.7` | ⚠️ content+tool | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.7-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m3` | ⚠️ content+tool | ⚠️ fala antes | fala=239ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m3-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-text-01` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-text-01-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-qwen-mt-plus` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen-mt-plus-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen-omni-turbo` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen-omni-turbo-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen-plus` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen-plus-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen-vl-max` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen-vl-max-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen-vl-ocr` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen-vl-ocr-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3-coder-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3-coder-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3-coder-plus` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3-coder-plus-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3-max` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3-max-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3-omni-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-qwen3-omni-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-qwen3-vl-flash` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3-vl-flash-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3-vl-plus` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3-vl-plus-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.5-ocr` | ❌ sem tool_call | ❌ sem tool_call | fala=35ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-qwen3.5-ocr-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=35ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-qwen3.6-max-preview` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3.6-max-preview-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-qwen3.7-max` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.7-max-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.8-max` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.8-max-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-step-5-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-step-5-preview-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |

## Rollup por família (análise manual do CSV)

_Números desta seção referem-se à re-execução S120 (mesma suíte, com dump de
evidência crua ativado); 112/212 linhas irregulares. Diferenças pequenas vs a
primeira corrida (110) são flutuação de verdict em casos limite e erros de
transporte pontuais._

Das 212 linhas, **~68 são ruído não-chat** no gateway (seedance/seedream, kling,
pixverse, vidu, tripo/3d, minimax-video/music, hy-mt2, hunyuan-role/hy-role,
qwen-mt/omni/vl-max/coder-plus/qwen3-max/3.6-max-preview etc.) — o inventário
`GET /models` do gateway não distingue modalidade e a lista de hints não cobre
todos (ex.: "seedream", "role", "mt"). Quase todas dão HTTP erro nos dois modos
(confirma que não são endpoints chat). Restam **~144 modelos chat analisáveis**.

### Gateway (chat)

- ✅ ns conforme + st só_tools: **30**
- ⚠️ stream `fala_antes`: **6** — glm-4.6v, glm-5, glm-5.2, glm-5v-turbo,
  kimi-k2.8-preview, minimax-m3
- ⚠️ stream `fala_depois`: **1** — hunyuan-t1-vision
- ❌ ignora tools (sem tool_call nos dois modos): **2** — glm-4.1v-thinking-flash,
  hy-vision-2.0-instruct
- ⚠️ ns content+tool mas stream só_tools: **3** — hy4-preview, kimi-k3,
  step-5-preview
- Erros de transporte nesta corrida: glm-4.6v-flash, glm-4.7-flash,
  mimo-v2.6-pro, qwen-omni-turbo, qwen3-vl-flash (ambos os modos) e
  minimax-text-01 (ns conforme, stream sem `done`; na 1ª corrida o ns dele foi
  HTTP 500 — instável nos dois alvos/corridas).

### Proxy (96 grupos chat)

- ✅ ns conforme + st só_tools: **67**
- ⚠️ stream `fala_antes`: **14** — família glm (4.6v*/4.6v-flash*/5/5.1/5.2/
  5v-turbo, bases e -fast), kimi-k3, minimax-m3*
- ⚠️ stream `fala_depois`: **2** — hunyuan-t1-vision*
- ❌ ignora tools: **4** — glm-4.1v-thinking-flash*, hy-vision-2.0-instruct*
- ⚠️ ns content+tool mas stream só_tools: **4** — deepseek-v4-pro-fast,
  hy4-preview-fast, kimi-k2.8-preview, minimax-m2.7
- Erros de transporte: qwen-omni-turbo*, qwen3-vl-flash* (ambos os modos);
  novai-glm-4.7-flash-fast deu erro no ns mas `so_tools` no stream.

### Formato de arguments no stream (chat)

- fragmentado: 88 · chunk_unico: 40 · sem args mensurável (erro/ignora tools): 16
- **Nenhuma linha com args nao-parseaveis** — o shape do tool_call em si é sempre
  válido; a divergência é de _sequência_ (content junto com tool_calls), não de
  schema.

### Conclusão (foco = inconsistências)

1. A divergência central confirmada em escala: **23 linhas stream** emitem
   `delta.content` antes/depois de `delta.tool_calls` com `finish_reason=tool_calls`
   (OpenAI: stream de tools não carrega fala). Bases únicas: glm-4.6v(+flash),
   glm-5/5.1/5.2, glm-5v-turbo, hunyuan-t1-vision, kimi-k2.8-preview, kimi-k3,
   minimax-m3.
2. **Ignoram a ferramenta** (texto puro nos dois modos): glm-4.1v-thinking-flash,
   hy-vision-2.0-instruct (+ espelhos -fast no proxy) — candidatos a exclusão da
   whitelist de tools dos agentes.
3. **28 linhas falam junto no non-stream** (content+tool_calls) — o agente mostra
   a frase E chama a tool (dupla narração possível).
4. Proxy e gateway concordam na família (glm/minimax/kimi fala-antes nos dois);
   diferenças de granularidade de args (chunk_unico vs fragmentado) não quebram
   parser.
5. Ruído de inventário do gateway (não-chat listados como chat) — melhorar filtro
   de hints se houver re-run.
6. Instabilidade observada entre corridas (glm-4.7-flash, minimax-text-01,
   glm-4.6v-flash no gateway): ver evidência crua em
   `reports/logs/tool-scan-2026-10-17-{gateway,proxy}.jsonl` (S120).

_Gerado por `eval.novai_tool_scan.py` (S119/S120). Foco: mapear inconsistências do contrato de tools NovAI vs OpenAI._
