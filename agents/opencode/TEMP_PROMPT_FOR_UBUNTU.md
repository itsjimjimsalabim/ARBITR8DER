## TEMP PROMPT FOR UBUNTU OPENCODE

You had "Invalid API key" — it's fixed now. Here's what happened and what to verify.

### Root cause
The `.env` file had `OPENCODE_API_KEY=<redacted-nvidia-api-key>...` (NVIDIA key). OpenCode's built-in `opencode` provider sent that to OpenCode Zen → rejected. The real key is `sk-sSGtBd...`.

### What Paulie fixed
1. `.env` → `OPENCODE_API_KEY=<redacted-opencode-api-key>` (correct OpenCode Zen key)
2. `~/.config/opencode/.keys` → both keys labeled (OpenCode Zen + NVIDIA NIM)
3. `~/.config/opencode/opencode.jsonc` → restored with nvidia provider (was stripped during debugging)
4. Windows `C:\Users\itsji\bin\claude.bat` → added `--dangerously-skip-permissions`

### What you need to test
1. Run `opencode` in WSL — does it connect? What model/provider?
2. Try switching to an nvidia model — does that work too?
3. Run `claude` in WSL — does OpenClaude start with permissions skipped?
4. Verify `env | grep OPENAI` shows the right key (should start with `sk-sSGtBd`, not `nvapi-`)

### Config layout (WSL)
- `~/.config/opencode/opencode.jsonc` — has nvidia provider + settings
- `/mnt/c/Users/itsji/ARBITR8DER/.env` — has correct OpenCode Zen key
- `/mnt/c/Users/itsji/ARBITR8DER/opencode.json` — project config (just `"permission": "allow"`)
- `~/bin/claude` — OpenClaude launcher (has `--dangerously-skip-permissions`)

