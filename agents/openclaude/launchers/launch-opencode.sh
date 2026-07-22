#!/bin/bash
# OpenCode fast launcher — WSL/Ubuntu
set -euo pipefail

OPENCODE_BIN="/home/itsjimjimsalabim/.opencode/bin/opencode"
ARBITR8DER_DIR="/mnt/c/Users/itsji/ARBITR8DER"

# Source .env for OPENCODE_API_KEY
if [ -f "$ARBITR8DER_DIR/.env" ]; then
  set -a
  source "$ARBITR8DER_DIR/.env"
  set +a
fi

export OPENAI_MODEL="${OPENAI_MODEL:-big-pickle}"

cd "$ARBITR8DER_DIR"
exec "$OPENCODE_BIN" --auto "$@"
