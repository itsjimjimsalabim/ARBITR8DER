#!/bin/bash
# OpenClaude_Ubuntu launcher — called from the Windows .bat shortcut
export OPENCODE_API_KEY='sk-sSGtBd1LIdg4UrRTPfVhA0JDStpSpmBBOiZk3uT2YLWsjrUOD8VkuanCjmspocIH'
export OPENAI_MODEL='big-pickle'
# Big Pickle Tuning — push output and context higher
export CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW=256000
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=85
export OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS=120000

# Source nvm to get node into PATH
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

cd /mnt/c/Users/itsji/openclaude
exec node bin/openclaude --provider opencode --bare --dangerously-skip-permissions "$@"
