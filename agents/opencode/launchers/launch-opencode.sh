#!/bin/bash
# OpenCode_Ubuntu — WSL launcher for the ARBITR8DER trading studio
# Launches OpenCode (big-pickle) via the OpenClaude bridge
#
# Windows equivalent: OneDrive/Desktop/OpenCode_Ubuntu.bat
# This script is the Linux-side companion.

set -euo pipefail

OPENCODE_BIN="/home/itsjimjimsalabim/.opencode/bin/opencode"
ARBITR8DER_DIR="/mnt/c/Users/itsji/ARBITR8DER"
OPENCODE_DIR="$ARBITR8DER_DIR/agents"

export OPENCODE_API_KEY="${OPENCODE_API_KEY:-}"
export OPENAI_MODEL="${OPENAI_MODEL:-big-pickle}"
export CLAUDE_CODE_USE_OPENAI=1

if [ -z "$OPENCODE_API_KEY" ]; then
  echo "ERROR: OPENCODE_API_KEY not set."
  echo "Set it in your shell or in .env"
  exit 1
fi

if [ ! -x "$OPENCODE_BIN" ]; then
  echo "ERROR: opencode binary not found at $OPENCODE_BIN"
  exit 1
fi

cd "$OPENCODE_DIR"
exec "$OPENCODE_BIN" "$@"
