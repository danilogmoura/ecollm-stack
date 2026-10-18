# S119 — Sweep de contrato de tools (2026-10-17)

- Modelo-alvo: **212** (chamadas non-stream + stream cada)
- Irregularidades encontradas: **110 linhas** (110 modelos distintos)

## Distribuição non-stream

| codigo | n |
| --- | --- |
| ✅ conforme | 108 |
| ❌ erro | 60 |
| ⚠️ content+tool | 29 |
| ❌ sem tool_call | 15 |

## Distribuição stream

| codigo | n |
| --- | --- |
| ✅ só tools | 107 |
| ❌ erro | 61 |
| ⚠️ fala antes | 22 |
| ❌ sem tool_call | 15 |
| ⚠️ fala depois | 7 |

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
| gateway | `glm-4.1v-thinking-flash` | ❌ sem tool_call | ❌ sem tool_call | fala=1133ch args=ausente/INVALID finish=['length'] |
| gateway | `glm-4.6v` | ⚠️ content+tool | ⚠️ fala antes | fala=43ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-4.6v-flash` | ⚠️ content+tool | ❌ erro | events=0 done=False |
| gateway | `glm-4.7-flash` | ❌ erro | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5-turbo` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `glm-5.1` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.2` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `glm-5.3` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.3-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `glm-5.3-flashx` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `glm-5v-turbo` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `hunyuan-role` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hunyuan-t1-vision` | ⚠️ content+tool | ⚠️ fala depois | fala=373ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `hunyuan-turbos-vision-video` | ⚠️ content+tool | ⚠️ fala depois | fala=93ch args=chunk_unico/ok finish=['tool_calls'] |
| gateway | `hy-3d-3.0` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-3d-3.1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-3d-express` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-3d-motion` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-mt2-lite` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-mt2-plus` | ❌ sem tool_call | ❌ sem tool_call | fala=824ch args=ausente/INVALID finish=['length'] |
| gateway | `hy-mt2-pro` | ❌ sem tool_call | ❌ sem tool_call | fala=55ch args=ausente/INVALID finish=['stop'] |
| gateway | `hy-role` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-video-v1.5` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `hy-vision-2.0-instruct` | ❌ sem tool_call | ❌ sem tool_call | fala=868ch args=ausente/INVALID finish=['length'] |
| gateway | `hy3` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `hy3-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `hy4-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.5` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.6` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.7-code` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.7-code-highspeed` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k2.8-preview` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kimi-k3` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `kling-video-o1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v2.5-turbo` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v2.6` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v3` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v3-omni` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `kling-video-v3-turbo` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `mimo-v2.5-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `mimo-v2.6-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `mimo-v2.6-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `minimax-m2.5` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `minimax-m2.7` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `minimax-m3` | ⚠️ content+tool | ⚠️ fala antes | fala=255ch args=chunk_unico/ok finish=['tool_calls'] |
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
| gateway | `step-5-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| gateway | `tripo-3d-3.1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `tripo-3d-p1` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `vidu-video-q3` | ❌ erro | ❌ erro | events=0 done=False |
| gateway | `vidu-video-q3-pro` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-deepseek-v4-flash` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-flash-vision` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-flash-vision-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-deepseek-v4-pro-fast` | ✅ conforme | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
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
| proxy | `novai-glm-4.1v-thinking-flash` | ❌ sem tool_call | ❌ sem tool_call | fala=895ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-glm-4.1v-thinking-flash-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=1017ch args=ausente/INVALID finish=['length'] |
| proxy | `novai-glm-4.6v` | ⚠️ content+tool | ⚠️ fala antes | fala=43ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.6v-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=42ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.6v-flash` | ⚠️ content+tool | ⚠️ fala antes | fala=73ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.6v-flash-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=61ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.7-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-4.7-flash-fast` | ✅ conforme | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5-turbo` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5-turbo-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.1` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.1-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.2` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.2-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3` | ⚠️ content+tool | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flash` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flashx` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5.3-flashx-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-glm-5v-turbo` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-glm-5v-turbo-fast` | ⚠️ content+tool | ⚠️ fala antes | fala=41ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-role` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hunyuan-role-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hunyuan-t1-vision` | ⚠️ content+tool | ⚠️ fala depois | fala=95ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-t1-vision-fast` | ⚠️ content+tool | ⚠️ fala depois | fala=363ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-turbos-vision-video` | ⚠️ content+tool | ⚠️ fala depois | fala=117ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hunyuan-turbos-vision-video-fast` | ⚠️ content+tool | ⚠️ fala depois | fala=97ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-hy-mt2-lite` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-mt2-lite-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-mt2-plus` | ❌ sem tool_call | ❌ sem tool_call | fala=668ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-mt2-plus-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=655ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-mt2-pro` | ❌ sem tool_call | ❌ sem tool_call | fala=41ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-mt2-pro-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=41ch args=ausente/INVALID finish=['stop'] |
| proxy | `novai-hy-role` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-role-fast` | ❌ erro | ❌ erro | events=0 done=False |
| proxy | `novai-hy-vision-2.0-instruct` | ❌ sem tool_call | ❌ sem tool_call | fala=835ch args=ausente/INVALID finish=['length'] |
| proxy | `novai-hy-vision-2.0-instruct-fast` | ❌ sem tool_call | ❌ sem tool_call | fala=868ch args=ausente/INVALID finish=['length'] |
| proxy | `novai-hy3` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy3-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy3-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy3-preview-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy4-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-hy4-preview-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
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
| proxy | `novai-kimi-k3` | ⚠️ content+tool | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-kimi-k3-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.5-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.5-pro-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-flash` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-flash-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-pro` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-mimo-v2.6-pro-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.5` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.5-fast` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.7` | ✅ conforme | ✅ só tools | fala=0ch args=chunk_unico/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m2.7-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-minimax-m3` | ✅ conforme | ⚠️ fala antes | fala=169ch args=chunk_unico/ok finish=['tool_calls'] |
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
| proxy | `novai-qwen3.7-max` | ✅ conforme | ⚠️ fala depois | fala=96ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.7-max-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.8-max` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-qwen3.8-max-fast` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-step-5-preview` | ✅ conforme | ✅ só tools | fala=0ch args=fragmentado/ok finish=['tool_calls'] |
| proxy | `novai-step-5-preview-fast` | ✅ conforme | ⚠️ fala antes | fala=51ch args=fragmentado/ok finish=['tool_calls'] |

## Rollup por família (análise manual do CSV)

Das 212 linhas, **59 são ruído não-chat** no gateway (seedance/seedream, kling,
pixverse, vidu, tripo/3d, minimax-video/music, hy-mt2-lite, hunyuan-role/hy-role,
qwen-mt/omni/vl-max/coder-plus/qwen3-max/3.6-max-preview etc.) — o inventário
`GET /models` do gateway não distingue modalidade e a lista de hints não cobre
todos (ex.: "seedream", "role", "mt"). Restam **153 modelos chat analisáveis**.

### Gateway (51 chat)

- ✅ ns conforme + st só_tools: **35**
- ⚠️ stream `fala_antes`: **7** — glm-4.6v, glm-4.7-flash, glm-5, glm-5.2,
  glm-5v-turbo, kimi-k2.8-preview, minimax-m3
- ⚠️ stream `fala_depois`: **2** — hunyuan-t1-vision, hunyuan-turbos-vision-video
- ❌ ignora tools (sem tool_call nos dois modos): **5** — glm-4.1v-thinking-flash,
  hy-mt2-plus, hy-mt2-pro, hy-vision-2.0-instruct, qwen3.5-ocr
- Casos mistos/transporte: glm-4.6v-flash (ns content+tool, stream sem eventos),
  glm-4.7-flash (ns erro HTTP, stream fala_antes), minimax-text-01 (stream
  events=8 sem done nem tool_call → provável framing SSE irregular; a verificar).

### Proxy (102 grupos)

- ✅ ns conforme + st só_tools: **~70**
- ⚠️ stream `fala_antes`: **15** — família glm (4.6v*/4.7-flash-fast/5*/5.2/5v-turbo),
  minimax-m3*, deepseek-v4-pro-fast, step-5-preview-fast
- ⚠️ stream `fala_depois`: **5** — hunyuan-t1-vision*, hunyuan-turbos-vision-video*,
  qwen3.7-max
- ❌ ignora tools: **10** — espelhos dos 5 do gateway × {base, -fast}
- ⚠️ ns content+tool mas stream conforme: deepseek-v4-flash, glm-5.3,
  kimi-k2.8-preview, kimi-k3 (fala só no non-stream)

### Formato de arguments no stream (chat)

- fragmentado: 97 · chunk_unico: 39 · sem args (ignora tools): 15
- **Nenhuma linha com args nao-parseaveis** — o shape do tool_call em si é sempre
  válido; a divergência é de *sequência* (content junto com tool_calls), não de schema.

### Conclusão (foco = inconsistências)

1. A divergência central confirmada em escala: **22 modelos stream** emitem
   `delta.content` antes/depois de `delta.tool_calls` com `finish_reason=tool_calls`
   (OpenAI: stream de tools não carrega fala). 15 deles só no modo fala-antes.
2. **15 modelos ignoram a ferramenta** (respondem texto puro) — candidatos a
   exclusão da whitelist de tools dos agentes.
3. **52 modelos falam junto no non-stream** (content+tool_calls) — o agente mostra
   a frase E chama a tool (dupla narração possível).
4. Proxy e gateway concordam na família (glm/minimax/step fala-antes nos dois);
   diferenças de granularidade de args (chunk_unico vs fragmentado) não quebram parser.
5. Ruído de inventário do gateway (não-chat listados como chat) — melhorar filtro
   de hints se houver re-run.

*Gerado por `eval/novai_tool_scan.py` (S119). Foco: mapear inconsistências do contrato de tools NovAI vs OpenAI.*
