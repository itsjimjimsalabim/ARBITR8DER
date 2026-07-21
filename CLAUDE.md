# ARBITR8DER — Agent Context

Read `agents/agents.md` for your identity, rules, and directory layout. All agents are one brain through agents.md.

## Quick Start

1. `agents/agents.md` — system prompt (Paulie + Claude sections)
2. `agents/claude/howtobuildOpenClaudeCode.md` — rebuild/reconnect guide
3. `agents/claude/configs/` — backed-up provider profiles
4. `agents/claude/launchers/` — startup scripts with Big Pickle tuning

## Security Notes

- **API keys** are embedded in `agents/claude/launchers/openclaude.bat` and `launchers/launch-ubuntu.sh`. If this repo is ever pushed, those keys are exposed. Load from `.env` at runtime instead.
- `--dangerously-skip-permissions` runs all sessions with zero guardrails. Intentional for local-only trusted environment.
