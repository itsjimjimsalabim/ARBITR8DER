#!/bin/bash
# Claude launcher for WSL — Big Pickle tuned
set -euo pipefail

CLAUDE_BIN="/home/itsjimjimsalabim/bin/claude"
ENV_FILE="/mnt/c/Users/itsji/.openclaude/.env"

# Source API keys
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# Big Pickle tuning
export CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW=256000
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=85
export OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS=120000
export CLAUDE_CODE_USE_OPENAI=1

exec node /mnt/c/Users/itsji/.openclaude/dist/cli.mjs "$@"
