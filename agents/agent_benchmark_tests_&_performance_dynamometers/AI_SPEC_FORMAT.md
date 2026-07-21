# AI Specification Format

> Created: 2026-07-21
> Status: SCAFFOLD

Every test result MUST be tagged with a complete AI spec. This document defines the exact format.

---

## Why This Matters

Two runs of "Claude" can produce wildly different results if one used `claude-opus-4-0` with
temperature 0.0 and 200K context, and the other used `claude-sonnet-4` with temperature 0.7
and 128K context. Without exact specs, benchmark data is meaningless.

---

## Spec Format (JSON)

Each AI spec is stored as a JSON file in `configs/ai_specs/` and as a row in the `ai_specs` table.

```json
{
  "spec_id": "big-pickle-default",
  "display_name": "Big Pickle (gpt-5.2-codex) via OpenClaude",

  "provider": {
    "name": "openclaudedotdev",
    "api_base": "https://openclaudedotdev.com/v1",
    "auth_method": "api_key"
  },

  "model": {
    "id": "gpt-5.2-codex",
    "version": "2026-07-15",
    "family": "gpt-5",
    "context_window": 256000,
    "max_output_tokens": 64000
  },

  "cli_tool": {
    "name": "openclaude",
    "version": "0.25.0",
    "source": "local-build",
    "build_date": "2026-07-20"
  },

  "reasoning": {
    "depth": "high",
    "chain_of_thought": true,
    "self_correction": true
  },

  "generation_settings": {
    "temperature": 0.0,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
  },

  "session_config": {
    "repl_max_turns": 9999,
    "auto_compact_pct": 85,
    "compact_cooldown_ms": 120000,
    "dangerously_skip_permissions": true,
    "bare_mode": true
  },

  "env_overrides": {
    "CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW": "256000",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "85",
    "OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS": "120000"
  },

  "notes": "Our primary Big Pickle config for ARBITR8DER trading and coding tasks."
}
```

---

## Required Fields (Every Spec)

| Field | Type | Description |
|-------|------|-------------|
| `spec_id` | string | Unique ID (kebab-case) |
| `display_name` | string | Human-readable name |
| `provider.name` | string | `openai`, `anthropic`, `ollama`, `openclaudedotdev`, etc. |
| `model.id` | string | Exact model identifier |
| `model.version` | string | Model version/date if known |
| `model.context_window` | int | Max context in tokens |
| `model.max_output_tokens` | int | Max output tokens |
| `cli_tool.name` | string | CLI tool used to run the test |
| `cli_tool.version` | string | CLI version |
| `reasoning.depth` | enum | `none`, `low`, `medium`, `high` |
| `generation_settings.temperature` | float | Temperature setting |

## Optional But Recommended

| Field | Type | When to Use |
|-------|------|-------------|
| `session_config.*` | mixed | Any custom session settings that affect output |
| `env_overrides.*` | string | Any env vars set during the run |
| `reasoning.chain_of_thought` | bool | Whether CoT was enabled/visible |
| `reasoning.self_correction` | bool | Whether model can retry within a turn |
| `notes` | string | Anything unusual about this config |

---

## Spec Naming Convention

Format: `{provider}-{model}-{variant}`

Examples:
- `openclaudedotdev-gpt52codex-bigpickle` — our Big Pickle config
- `openclaudedotdev-gpt52codex-default` — same model, no custom tuning
- `anthropic-claudeopus40-default` — Claude Opus 4, vanilla
- `anthropic-claudeopus40-claudecode` — Claude Opus 4 via Claude Code CLI
- `ollama-llama31-8b-default` — local Llama 3.1 8B
- `ollama-llama31-8b-optimized` — local with quantization tweaks

---

## Comparing Specs

The scoreboard supports side-by-side comparison:

| Comparison Type | Use Case |
|----------------|----------|
| **Model vs Model** | `gpt-5.2-codex` vs `claude-opus-4-0` vs `llama3.1:8b` |
| **Config vs Config** | Same model, default vs Big Pickle tuning |
| **CLI vs CLI** | Same model via OpenClaude vs Claude Code vs OpenCode |
| **Reasoning Depth** | Same model at depth=none vs depth=high |
| **Context Window** | Same model at 128K vs 256K (does more context help?) |

---

## Pre-Defined Specs for ARBITR8DER

These are our known configurations. Add new ones as we test more models.

| spec_id | Display Name | Key Differentiator |
|---------|-------------|-------------------|
| `big-pickle-default` | Big Pickle via OpenClaude | Our tuned config (256K ctx, 64K out, 85% compact) |
| `big-pickle-baseline` | Big Pickle Default Settings | Same model, no env overrides |
| `claude-opus4-claudecode` | Claude Opus 4 via Claude Code | Anthropic's native CLI |
| `claude-opus4-openclaude` | Claude Opus 4 via OpenClaude | Same model, our CLI |
| `llama31-8b-ollama` | Llama 3.1 8B via Ollama | Local, no API cost |
