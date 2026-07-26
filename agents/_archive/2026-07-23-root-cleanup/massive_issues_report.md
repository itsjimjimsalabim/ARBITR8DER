# Massive Issues Report — ARBITR8DER System
**Generated:** 2026-07-21
**Severity:** Critical / High / Medium / Low
**Status:** Open / Fixed / Won't Fix

---

## CRITICAL — Immediate Attention

### 1. ARBITR8DER .env has no API keys for Kalshi
- **Status:** Open
- **File:** `C:\Users\itsji\ARBITR8DER\.env`
- **Current:** Only contains `AR8_WALLET_MODE=PAPER`
- **Missing:** Kalshi API key, Binance API key/secret, Coinbase credentials
- **Impact:** Cannot connect to any exchange. Trading is impossible.
- **Fix:** Add keys to `.env`. User says they have Kalshi keys.

### 2. Ollama has no models downloaded
- **Status:** Open
- **Location:** WSL `localhost:11434`
- **Impact:** Local LLM fallback is non-functional
- **Fix:** `ollama pull llama3.1:8b` or similar

### 3. No Python on Windows
- **Status:** Open
- **Impact:** Can't run ARBITR8DER from Windows side, pipx unavailable
- **Fix:** `winget install Python.Python.3.12`

---

## HIGH — Blocking Workflow

### 4. agents.md references dead paths
- **Status:** Fixed (skeptical traits added 2026-07-21)
- **File:** `agents/agents.md`
- **Old references:** `openclaude/` source dir (deleted), `C:\Users\itsji\openclaude\` (deleted)
- **Impact:** Agents following old docs would fail
- **Fix:** Paths need updating to `.openclaude` (next pass)

### 5. agents/claude/launchers/openclaude.bat is dead
- **Status:** Open
- **File:** `agents/claude/launchers/openclaude.bat`
- **Points to:** `C:\Users\itsji\openclaude\bin\openclaude.mjs` (deleted)
- **Impact:** Windows launch via this path fails
- **Fix:** Delete file or update to point to `~/.openclaude/dist/cli.mjs`

### 6. WSL .bashrc PATH may not load on new shells
- **Status:** Fixed (added `~/bin` to PATH 2026-07-21)
- **File:** `~/.bashrc`
- **Impact:** `claude` command might not be found in new WSL terminals until `source ~/.bashrc`
- **Fix:** Already added. Verify with `wsl -e bash -ic "which claude"`

### 7. OpenCode WSL config has hardcoded NVIDIA API key
- **Status:** Open
- **File:** `~/.config/opencode/opencode.jsonc`
- **Key:** `<redacted-nvidia-api-key>`
- **Impact:** API key in plaintext config. If repo is public, key is exposed.
- **Fix:** Move to `.env` or use environment variable injection

### 8. OpenClaude settings.local.json has hardcoded API key
- **Status:** Open
- **File:** `~/.openclaude/settings.local.json`
- **Key:** `<redacted-opencode-api-key>`
- **Impact:** Same as above — plaintext key exposure
- **Fix:** Move to environment variable

---

## MEDIUM — Quality of Life

### 9. Desktop shortcuts all dead
- **Status:** Open
- **Location:** `C:\Users\itsji\OneDrive\Desktop\`
- **Shortcuts:** OpenCode, Claude, Codex, agents
- **All point to:** Deleted paths in `C:\Users\itsji\openclaude\`
- **Impact:** User clicks shortcuts, nothing happens
- **Fix:** Recreate shortcuts pointing to correct paths

### 10. Deprecated directories still exist
- **Status:** Open
- **Locations:** `C:\Users\itsji\old_agents`, `C:\Users\itsji\old_ARBITR8DER`, `C:\Users\itsji\agents` (root)
- **Impact:** Confusion about which is the real project
- **Fix:** Delete after confirming no unique files

### 11. agents/claude/launchers/ is empty
- **Status:** Open
- **Location:** `agents/claude/launchers/`
- **Impact:** agents.md says launchers are there, but they're in `agents/openclaude/launchers/`
- **Fix:** Move launchers or update docs

### 12. .openclaude/.config.json has stale project paths
- **Status:** Fixed (updated 2026-07-21)
- **File:** `~/.openclaude/.config.json`
- **Old:** `C:\Users\itsji\openclaude` and `C:/Users/itsji/openclaude`
- **New:** `C:\Users\itsji\.openclaude`
- **Impact:** Minor — session tracking may reference old paths

### 13. WSL has redundant ~/.bun directory (481MB)
- **Status:** Open
- **Location:** `~/.bun` (standalone) vs `~/.nvm/versions/node/v24.18.0/bin/bun` (nvm global)
- **Impact:** Wasted disk space
- **Fix:** `rm -rf ~/.bun` (bun still available via nvm)

### 14. No dev tools in WSL (ruff, jq, ripgrep, htop, etc.)
- **Status:** Open
- **Impact:** No linting, no fast search, no process monitoring
- **Fix:** `sudo apt install ripgrep fd-find fzf bat htop tree jq && pip install ruff`

---

## LOW — Cleanup

### 15. agents.md OpenCode launch references OneDrive Desktop
- **Status:** Open
- **Line:** 137-138
- **Old:** `C:\Users\itsji\OneDrive\Desktop\OpenCode at Home.lnk`
- **Impact:** OneDrive is deleted, shortcuts are orphaned
- **Fix:** Update to point to correct launch method

### 16. agents.md Session Chats path is wrong
- **Status:** Open
- **Line:** 155
- **Old:** `~/.openclaude/projects/C--Users-itsji-openclaude/*.jsonl`
- **Actual:** Sessions are in `~/.openclaude/projects/` (multiple subdirs)
- **Impact:** Misleading docs
- **Fix:** Update path reference

### 17. agents.md references two repos that don't exist as described
- **Status:** Open
- **Line:** 239-241
- **Old:** "C:\Users\itsji\openclaude\` — OpenClaude CLI source"
- **Actual:** Source is now at `C:\Users\itsji\.openclaude\`
- **Impact:** Confusing docs
- **Fix:** Update path

### 18. PC_CLEANUP.ps1 on Desktop is a live script
- **Status:** Open
- **Location:** `C:\Users\itsji\Desktop\PC_CLEANUP.ps1`
- **Impact:** Could be accidentally run. Contains OneDrive kill logic.
- **Fix:** Move to `scripts/` or delete

### 19. agents.md says "Two repos on same machine cause confusion"
- **Status:** Open
- **Impact:** Still true — ARBITR8DER and openclaude are separate
- **Fix:** Keep separate, just ensure paths in docs are correct

### 20. No .gitconfig set globally
- **Status:** Open
- **Impact:** Git operations may prompt for name/email
- **Fix:** `git config --global user.name "..." && git config --global user.email "..."`

---

## FIXED — 2026-07-21 Session

| # | Issue | Fix |
|---|-------|-----|
| 1 | OpenClaude source dir deleted | Recloned to `.openclaude`, built v0.25.0 |
| 2 | `claude` command broken | Created `~/bin/claude` wrapper in WSL |
| 3 | `~/bin` not in PATH | Added to `.bashrc` |
| 4 | Dead `alias oc=` in .bashrc | Removed |
| 5 | `.config.json` wrong path | Updated to `.openclaude` |
| 6 | No skeptical traits in agents.md | Added Paulie's Skeptical Operating Principles |

---

## Summary

| Severity | Count | Fixed |
|----------|-------|-------|
| Critical | 3 | 0 |
| High | 5 | 2 |
| Medium | 6 | 1 |
| Low | 6 | 0 |
| **Total** | **20** | **3** |

---

## End of Report

