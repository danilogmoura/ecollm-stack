# NovAI smoke — resultados

| grupo | alvo | modalidade | teste | status | latência | evidência |
| --- | --- | --- | --- | --- | --- | --- |
| novai-glm-4.7-flash | proxy | chat | chat | pass | 55984 ms | reasoning_chars=555 reasoning_tokens=152 |
| novai-glm-4.7-flash-fast | proxy | chat | chat | skipped | 52662 ms | skip: upstream não suporta thinking OFF |
| novai-doubao-seed-2.0-pro | proxy | chat | chat | pass | 3122 ms | reasoning_chars=144 reasoning_tokens=43 |
| novai-doubao-seed-2.0-pro-fast | proxy | chat | chat | pass | 1800 ms | no-reasoning OK len(content)=2 |
| novai-deepseek-v4.1-flash | proxy | chat | chat | pass | 2296 ms | reasoning_chars=36 reasoning_tokens=9 |
| novai-deepseek-v4.1-flash-fast | proxy | chat | chat | pass | 2724 ms | no-reasoning OK len(content)=2 |
| novai-deepseek-v4-pro | proxy | chat | chat | pass | 1402 ms | reasoning_chars=101 reasoning_tokens=26 |
| novai-deepseek-v4-pro-fast | proxy | chat | chat | pass | 1241 ms | no-reasoning OK len(content)=2 |
| novai-deepseek-v4-flash | proxy | chat | chat | pass | 1348 ms | reasoning_chars=36 reasoning_tokens=9 |
| novai-deepseek-v4-flash-fast | proxy | chat | chat | pass | 2045 ms | no-reasoning OK len(content)=2 |
| novai-deepseek-v4-flash-vision | proxy | chat | chat | pass | 2310 ms | reasoning_chars=93 reasoning_tokens=24 |
| novai-deepseek-v4-flash-vision-fast | proxy | chat | chat | pass | 2458 ms | no-reasoning OK len(content)=2 |
| novai-qwen3.8-max | proxy | chat | chat | pass | 2620 ms | reasoning_chars=112 reasoning_tokens=28 |
| novai-qwen3.8-max-fast | proxy | chat | chat | pass | 1752 ms | no-reasoning OK len(content)=2 |
| novai-qwen3.7-max | proxy | chat | chat | pass | 2403 ms | reasoning_chars=347 reasoning_tokens=97 |
| novai-qwen3.7-max-fast | proxy | chat | chat | pass | 1602 ms | no-reasoning OK len(content)=2 |
| novai-qwen3.6-max-preview | proxy | chat | chat | fail | 647 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3.6-max-preview-fast | proxy | chat | chat | fail | 650 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-max | proxy | chat | chat | fail | 666 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-max-fast | proxy | chat | chat | fail | 662 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-coder-plus | proxy | chat | chat | fail | 645 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-coder-plus-fast | proxy | chat | chat | fail | 1206 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen-vl-max | proxy | chat | chat | fail | 667 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen-vl-max-fast | proxy | chat | chat | fail | 978 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-vl-plus | proxy | chat | chat | skipped | 1338 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen3-vl-plus-fast | proxy | chat | chat | pass | 1231 ms | no-reasoning OK len(content)=2 |
| novai-qwen3.5-ocr | proxy | chat | chat | skipped | 1276 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen3.5-ocr-fast | proxy | chat | chat | pass | 704 ms | no-reasoning OK len(content)=2 |
| novai-qwen-vl-ocr | proxy | chat | chat | skipped | 1281 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen-vl-ocr-fast | proxy | chat | chat | pass | 671 ms | no-reasoning OK len(content)=2 |
| novai-qwen-mt-plus | proxy | chat | chat | skipped | 698 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen-mt-plus-fast | proxy | chat | chat | pass | 706 ms | no-reasoning OK len(content)=2 |
| novai-qwen-plus | proxy | chat | chat | skipped | 1921 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen-plus-fast | proxy | chat | chat | pass | 853 ms | no-reasoning OK len(content)=2 |
| novai-qwen3-coder-flash | proxy | chat | chat | skipped | 758 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen3-coder-flash-fast | proxy | chat | chat | pass | 784 ms | no-reasoning OK len(content)=2 |
| novai-qwen3-vl-flash | proxy | chat | chat | fail | 620 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-vl-flash-fast | proxy | chat | chat | fail | 637 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba Cloud] Model not exist.\n\nLiteLLM |
| novai-qwen3-omni-flash | proxy | chat | chat | skipped | 711 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-qwen3-omni-flash-fast | proxy | chat | chat | pass | 716 ms | no-reasoning OK len(content)=2 |
| novai-qwen-omni-turbo | proxy | chat | chat | fail | 653 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba (通义千问)] Model not exist.\n\nLiteLL |
| novai-qwen-omni-turbo-fast | proxy | chat | chat | fail | 647 ms | HTTP 404: {"error":{"message":"litellm.NotFoundError: NotFoundError: OpenAIException - [Alibaba (通义千问)] Model not exist.\n\nLiteLL |
| novai-doubao-seed-2.1-pro | proxy | chat | chat | pass | 2726 ms | reasoning_chars=25 reasoning_tokens=31 |
| novai-doubao-seed-2.1-pro-fast | proxy | chat | chat | pass | 1517 ms | no-reasoning OK len(content)=2 |
| novai-doubao-seed-2.0-code | proxy | chat | chat | pass | 5356 ms | reasoning_chars=63 reasoning_tokens=20 |
| novai-doubao-seed-2.0-code-fast | proxy | chat | chat | pass | 1984 ms | no-reasoning OK len(content)=2 |
| novai-doubao-seed-2.1-turbo | proxy | chat | chat | pass | 1978 ms | reasoning_chars=38 reasoning_tokens=18 |
| novai-doubao-seed-2.1-turbo-fast | proxy | chat | chat | pass | 1932 ms | no-reasoning OK len(content)=2 |
| novai-doubao-seed-2.0-lite | proxy | chat | chat | pass | 3144 ms | reasoning_chars=53 reasoning_tokens=32 |
| novai-doubao-seed-2.0-lite-fast | proxy | chat | chat | pass | 1444 ms | no-reasoning OK len(content)=2 |
| novai-minimax-m3 | proxy | chat | chat | pass | 2043 ms | reasoning_chars=67 reasoning_tokens=15 |
| novai-minimax-m3-fast | proxy | chat | chat | pass | 2162 ms | no-reasoning OK len(content)=2 |
| novai-minimax-m2.7 | proxy | chat | chat | pass | 1649 ms | reasoning_chars=90 reasoning_tokens=0 |
| novai-minimax-m2.7-fast | proxy | chat | chat | fail | 1987 ms | reasoning_chars=150 reasoning_tokens=0 |
| novai-minimax-m2.5 | proxy | chat | chat | pass | 1729 ms | reasoning_chars=131 reasoning_tokens=34 |
| novai-minimax-m2.5-fast | proxy | chat | chat | fail | 1667 ms | reasoning_chars=90 reasoning_tokens=23 |
| novai-minimax-text-01 | proxy | chat | chat | skipped | 1507 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-minimax-text-01-fast | proxy | chat | chat | pass | 960 ms | no-reasoning OK len(content)=2 |
| novai-kimi-k3 | proxy | chat | chat | pass | 5593 ms | reasoning_chars=286 reasoning_tokens=71 |
| novai-kimi-k3-fast | proxy | chat | chat | skipped | 28079 ms | skip: upstream não suporta thinking OFF |
| novai-kimi-k2.8-preview | proxy | chat | chat | pass | 1950 ms | reasoning_chars=146 reasoning_tokens=34 |
| novai-kimi-k2.8-preview-fast | proxy | chat | chat | fail | 1567 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [Moonshot (Kimi)] The request is invalid: the request wa |
| novai-kimi-k2.7-code | proxy | chat | chat | pass | 4078 ms | reasoning_chars=125 reasoning_tokens=32 |
| novai-kimi-k2.7-code-fast | proxy | chat | chat | fail | 1484 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [Moonshot (Kimi)] The request is invalid: the request wa |
| novai-kimi-k2.7-code-highspeed | proxy | chat | chat | pass | 1557 ms | reasoning_chars=99 reasoning_tokens=26 |
| novai-kimi-k2.7-code-highspeed-fast | proxy | chat | chat | fail | 1055 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [Moonshot (Kimi)] The request is invalid: the request wa |
| novai-kimi-k2.6 | proxy | chat | chat | pass | 2139 ms | reasoning_chars=209 reasoning_tokens=63 |
| novai-kimi-k2.6-fast | proxy | chat | chat | fail | 1174 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [Moonshot (Kimi)] The request is invalid: the request wa |
| novai-kimi-k2.5 | proxy | chat | chat | pass | 2168 ms | reasoning_chars=154 reasoning_tokens=47 |
| novai-kimi-k2.5-fast | proxy | chat | chat | fail | 1285 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [Moonshot (Kimi)] The request is invalid: the request wa |
| novai-step-5-preview | proxy | chat | chat | pass | 2266 ms | reasoning_chars=227 reasoning_tokens=0 |
| novai-step-5-preview-fast | proxy | chat | chat | fail | 2376 ms | reasoning_chars=130 reasoning_tokens=0 |
| novai-hy4-preview | proxy | chat | chat | pass | 3225 ms | reasoning_chars=173 reasoning_tokens=45 |
| novai-hy4-preview-fast | proxy | chat | chat | pass | 1889 ms | no-reasoning OK len(content)=2 |
| novai-hy3 | proxy | chat | chat | pass | 1888 ms | reasoning_chars=43 reasoning_tokens=12 |
| novai-hy3-fast | proxy | chat | chat | pass | 1478 ms | no-reasoning OK len(content)=2 |
| novai-hunyuan-t1-vision | proxy | chat | chat | skipped | 1690 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hunyuan-t1-vision-fast | proxy | chat | chat | pass | 1743 ms | no-reasoning OK len(content)=2 |
| novai-hy-vision-2.0-instruct | proxy | chat | chat | skipped | 1351 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hy-vision-2.0-instruct-fast | proxy | chat | chat | pass | 1484 ms | no-reasoning OK len(content)=2 |
| novai-hunyuan-turbos-vision-video | proxy | chat | chat | skipped | 1912 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hunyuan-turbos-vision-video-fast | proxy | chat | chat | pass | 1819 ms | no-reasoning OK len(content)=2 |
| novai-hy-mt2-pro | proxy | chat | chat | skipped | 1427 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hy-mt2-pro-fast | proxy | chat | chat | pass | 1223 ms | no-reasoning OK len(content)=2 |
| novai-hy-mt2-plus | proxy | chat | chat | skipped | 1121 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hy-mt2-plus-fast | proxy | chat | chat | pass | 1235 ms | no-reasoning OK len(content)=2 |
| novai-hunyuan-role | proxy | chat | chat | skipped | 1093 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hunyuan-role-fast | proxy | chat | chat | pass | 1003 ms | no-reasoning OK len(content)=2 |
| novai-hy-role | proxy | chat | chat | skipped | 1255 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hy-role-fast | proxy | chat | chat | pass | 1197 ms | no-reasoning OK len(content)=2 |
| novai-hy3-preview | proxy | chat | chat | skipped | 1841 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hy3-preview-fast | proxy | chat | chat | pass | 1773 ms | no-reasoning OK len(content)=2 |
| novai-hy-mt2-lite | proxy | chat | chat | skipped | 1099 ms | skip: modelo não-reasoning (sem par de thinking) |
| novai-hy-mt2-lite-fast | proxy | chat | chat | pass | 981 ms | no-reasoning OK len(content)=2 |
| novai-mimo-v2.5-pro | proxy | chat | chat | pass | 10278 ms | reasoning_chars=53 reasoning_tokens=14 |
| novai-mimo-v2.5-pro-fast | proxy | chat | chat | pass | 1539 ms | no-reasoning OK len(content)=2 |
| novai-mimo-v2.6-pro | proxy | chat | chat | pass | 4701 ms | reasoning_chars=33 reasoning_tokens=10 |
| novai-mimo-v2.6-pro-fast | proxy | chat | chat | pass | 2148 ms | no-reasoning OK len(content)=2 |
| novai-mimo-v2.6-flash | proxy | chat | chat | pass | 3120 ms | reasoning_chars=37 reasoning_tokens=11 |
| novai-mimo-v2.6-flash-fast | proxy | chat | chat | pass | 3623 ms | no-reasoning OK len(content)=2 |
| novai-glm-5.3 | proxy | chat | chat | pass | 2870 ms | reasoning_chars=337 reasoning_tokens=78 |
| novai-glm-5.3-fast | proxy | chat | chat | fail | 617 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [ZhiPu (智谱)] 该模型始终思考，不支持关闭思考；请使用 low、high 或 max。\n\nLite |
| novai-glm-5.2 | proxy | chat | chat | pass | 3959 ms | reasoning_chars=361 reasoning_tokens=107 |
| novai-glm-5.2-fast | proxy | chat | chat | skipped | 1571 ms | skip: upstream não suporta thinking OFF |
| novai-glm-5.1 | proxy | chat | chat | pass | 4971 ms | reasoning_chars=423 reasoning_tokens=120 |
| novai-glm-5.1-fast | proxy | chat | chat | skipped | 4017 ms | skip: upstream não suporta thinking OFF |
| novai-glm-5 | proxy | chat | chat | pass | 2565 ms | reasoning_chars=388 reasoning_tokens=118 |
| novai-glm-5-fast | proxy | chat | chat | skipped | 1498 ms | skip: upstream não suporta thinking OFF |
| novai-glm-5v-turbo | proxy | chat | chat | pass | 2080 ms | reasoning_chars=246 reasoning_tokens=60 |
| novai-glm-5v-turbo-fast | proxy | chat | chat | skipped | 1280 ms | skip: upstream não suporta thinking OFF |
| novai-glm-4.6v | proxy | chat | chat | pass | 2008 ms | reasoning_chars=263 reasoning_tokens=57 |
| novai-glm-4.6v-fast | proxy | chat | chat | skipped | 647 ms | skip: upstream não suporta thinking OFF |
| novai-glm-5.3-flash | proxy | chat | chat | pass | 2064 ms | reasoning_chars=431 reasoning_tokens=89 |
| novai-glm-5.3-flash-fast | proxy | chat | chat | fail | 536 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [ZhiPu (智谱)] 该模型始终思考，不支持关闭思考；请使用 low、high 或 max。\n\nLite |
| novai-glm-5-turbo | proxy | chat | chat | pass | 2741 ms | reasoning_chars=270 reasoning_tokens=63 |
| novai-glm-5-turbo-fast | proxy | chat | chat | fail | 1017 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [ZhiPu (智谱)] The request is invalid: the request was rej |
| novai-glm-4.6v-flash | proxy | chat | chat | pass | 1257 ms | reasoning_chars=107 reasoning_tokens=53 |
| novai-glm-4.6v-flash-fast | proxy | chat | chat | fail | 7476 ms | HTTP 429: {"error":{"message":"litellm.RateLimitError: RateLimitError: OpenAIException - [ZhiPu (智谱)] 该模型当前访问量过大，请您稍后再试\n\nLiteLLM |
| novai-glm-4.1v-thinking-flash | proxy | chat | chat | pass | 1203 ms | reasoning_chars=112 reasoning_tokens=0 |
| novai-glm-4.1v-thinking-flash-fast | proxy | chat | chat | skipped | 1309 ms | skip: upstream não suporta thinking OFF |
| novai-glm-5.3-flashx | proxy | chat | chat | pass | 2584 ms | reasoning_chars=338 reasoning_tokens=73 |
| novai-glm-5.3-flashx-fast | proxy | chat | chat | fail | 981 ms | HTTP 400: {"error":{"message":"litellm.BadRequestError: OpenAIException - [ZhiPu (智谱)] The request is invalid: the request was rej |
