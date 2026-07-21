@echo off
title OpenClaude - Big Pickle
cd /d C:\Users\itsji\openclaude
set OPENCODE_API_KEY=sk-sSGtBd1LIdg4UrRTPfVhA0JDStpSpmBBOiZk3uT2YLWsjrUOD8VkuanCjmspocIH
set OPENAI_MODEL=big-pickle
:: Big Pickle Tuning — push output and context higher
set CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW=256000
set CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
set CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=85
set OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS=120000
node bin\openclaude --provider opencode --bare --dangerously-skip-permissions %*
