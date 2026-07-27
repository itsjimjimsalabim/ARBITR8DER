# NVIDIA NIM Model Menu — Claude Code (OpenClaude)

> Use this menu to switch Claude Code between **OpenCode Zen (big-pickle)** and
> any **NVIDIA NIM** model, on Windows or Ubuntu/WSL.
>
> Switching requires editing **ONE file** (`C:\Users\itsji\.openclaude\.env`)
> because both launchers source it. You must change three env vars:
> `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`.

## How to Switch

Edit `/mnt/c/Users/itsji/.openclaude/.env`:

**To use OpenCode Zen (current default):**
```
OPENAI_API_KEY=<redacted OpenCode Zen key>
OPENAI_BASE_URL=https://opencode.ai/zen/v1
OPENAI_MODEL=big-pickle
```

**To use any NVIDIA NIM model:**
```
OPENAI_API_KEY=<redacted NVIDIA NIM key>
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
OPENAI_MODEL=<pick from table below>
```
`CLAUDE_CODE_USE_OPENAI=1` stays the same for both — it forces the OpenAI-compatible
API path, which both OpenCode Zen and NVIDIA NIM support.

## Full NVIDIA NIM Model List

| Model ID | Display Name | Context | Output | Reasoning |
|----------|-------------|---------|--------|-----------|
| `nvidia/llama-3.1-nemotron-ultra-253b-v1` | Nemotron Ultra 253B | 128K | 8K | yes |
| `nvidia/llama-3.3-nemotron-super-49b-v1.5` | Nemotron Super 49B v1.5 | 131K | 131K | no |
| `nvidia/nemotron-3-ultra-550b-a55b` | Nemotron 3 Ultra 550B | 128K | 128K | no |
| `nvidia/nemotron-3-super-120b-a12b` | Nemotron 3 Super 120B | 262K | 262K | no |
| `nvidia/nvidia-nemotron-nano-9b-v2` | Nemotron Nano 9B v2 | 131K | 131K | no |
| `nvidia/nemotron-nano-12b-v2-vl` | Nemotron Nano 12B VL | 128K | 128K | no |
| `deepseek-ai/deepseek-v4-pro` | DeepSeek V4 Pro | 1M | 384K | yes |
| `deepseek-ai/deepseek-v4-flash` | DeepSeek V4 Flash | 1M | 384K | yes |
| `qwen/qwen3-coder-480b-a35b-instruct` | Qwen3 Coder 480B | 262K | 65K | no |
| `qwen/qwen3.5-122b-a10b` | Qwen3.5 122B | 262K | 65K | no |
| `qwen/qwen3-next-80b-a3b-thinking` | Qwen3 Next 80B Thinking | 131K | 32K | yes |
| `minimaxai/minimax-m2.7` | MiniMax M2.7 | 204K | 131K | no |
| `z-ai/glm-5.2` | GLM 5.2 | 610K | 131K | no |
| `z-ai/glm5.1` | GLM 5.1 | 200K | 131K | no |
| `moonshotai/kimi-k2-thinking` | Kimi K2 Thinking | 262K | 262K | yes |
| `moonshotai/kimi-k2-instruct` | Kimi K2 Instruct | 262K | 262K | no |
| `meta/llama-3.1-405b-instruct` | Llama 3.1 405B | 128K | 4K | no |
| `meta/llama-3.3-70b-instruct` | Llama 3.3 70B | 128K | 4K | no |
| `openai/gpt-oss-120b` | GPT-OSS 120B | 131K | 32K | no |
| `mistralai/mistral-nemotron` | Mistral Nemotron | 128K | 8K | no |

## Switching Back

To return to OpenCode Zen, edit `.env` back to:
```
OPENAI_API_KEY=<redacted OpenCode Zen key>
OPENAI_BASE_URL=https://opencode.ai/zen/v1
OPENAI_MODEL=big-pickle
```
Then restart Claude (`claude` in terminal).

## Rate Limits (NVIDIA Free Tier)

- 1,000 credits (free tier)
- 40 requests per minute
- Key: `<redacted NVIDIA NIM key>`
