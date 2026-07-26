# Scattered Files Manifest — ARBITR8DER System Audit

> Generated: 2026-07-21
> Auditor: Agent Claude
> Purpose: Track every AI tool config/file outside the canonical ARBITR8DER repo.
> When you find new scattered files, ADD them here with timestamp and action taken.

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| Claude/OpenClaude configs | 6 | Consolidated to `agents/openclaude/configs/` |
| Launchers/shortcuts | 7 | Consolidated to `agents/openclaude/launchers/` |
| Claude Desktop (MSIX) | 2 | App-managed, backed up |
| OpenCode data | 3 | Reference only (591MB DB) |
| Deprecated dirs | 3 | Read-only reference |
| Prompt/session files | 2 | Consolidated to `agents/openclaude/session-history/` |
| **Total scattered** | **23** | |

---

## Detailed Inventory

### 1. Claude/OpenClaude Configs (Consolidated)

| # | Original Location | Contents | Action |
|---|-------------------|----------|--------|
| 1 | `C:\Users\itsji\.openclaude.json` | Project config (openclaudedotdev provider, gpt-5.2-codex model) | Backed up to `configs/.openclaude.json` |
| 2 | `C:\Users\itsji\.openclaude\settings.local.json` | Permissions (Bash, Read, Write, Edit, Glob, Grep allowed) | Backed up to `configs/settings.local.json` |
| 3 | `C:\Users\itsji\.openclaude\.openclaude-profile.json` | Ollama provider, llama3.1:8b model, localhost:11434 | Backed up to `configs/.openclaude-profile.json` |
| 4 | `C:\Users\itsji\openclaude\.openclaude\settings.local.json` | Dev permissions (same as #2) | Backed up to `configs/` |
| 5 | `C:\Users\itsji\openclaude\.openclaude\.openclaude-profile.json` | Dev Ollama profile (same as #3) | Backed up to `configs/` |
| 6 | `C:\Users\itsji\openclaude\.env` | **SECRET** ANTHROPIC_API_KEY, KALSHI_API_KEY, KALSHI_EMAIL | NOT copied. Reference only. |

### 2. Launchers and Shortcuts

| # | Original Location | Contents | Action |
|---|-------------------|----------|--------|
| 7 | `C:\Users\itsji\openclaude\openclaude.bat` | Windows launcher: sets OPENCODE=1, bypasses permissions | Copied to `launchers/` |
| 8 | `C:\Users\itsji\openclaude\launch-ubuntu.sh` | Ubuntu/WSL launcher: opens xterm with Claude | Copied to `launchers/` |
| 9 | `C:\Users\itsji\OneDrive\Desktop\OpenClaude.lnk` | Windows desktop shortcut pointing to Claude.exe | Copied to `launchers/` |
| 20 | `C:\Users\itsji\OneDrive\Desktop\OpenCode at Home.lnk` | Desktop shortcut for OpenCode | Copied to `launchers/` |
| 21 | `C:\Users\itsji\OneDrive\Desktop\Start Codex Full Access.lnk` | Desktop shortcut for Codex full access | Copied to `launchers/` |
| 22 | `C:\Users\itsji\OneDrive\Desktop\agents - Shortcut.lnk` | Desktop shortcut to agents directory | Copied to `launchers/` |
| 23 | `C:\Users\itsji\OneDrive\Desktop\ARBITR8DER - Shortcut.lnk` | Desktop shortcut to ARBITR8DER repo | Copied to `launchers/` |

### 3. Claude Desktop (MSIX Package)

| # | Location | Contents | Action |
|---|----------|----------|--------|
| 10 | `AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json` | MCP servers: filesystem, brave-search, memory, fetch, sequential-thinking | Backed up to `configs/claude_desktop_config.json` |
| 11 | `AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\config.json` | Desktop settings: v1.0.56, dark theme, 1200x800 | Backed up to `configs/claude_desktop_settings.json` |
| 12 | `AppData\Local\Packages\Claude_pzs8sxrjxfjjc` (MSIX root) | Full Claude Desktop app install | App-managed. Do not touch. |

### 4. OpenCode Data

| # | Location | Contents | Action |
|---|----------|----------|--------|
| 13 | `C:\Users\itsji\.config\opencode\opencode.jsonc` | Provider: Claude Code, model: gpt-5.2-codex | Backed up to `configs/opencode.jsonc` |
| 14 | `C:\Users\itsji\.local\share\opencode\opencode.db` | **591MB** session database with all chat history | Reference only. Too large to copy. |
| 15 | `C:\Users\itsji\.local\share\opencode` | OpenCode data directory | Reference only. |
| 16 | `C:\Users\itsji\.local\state\opencode` | OpenCode state directory | Reference only. |

### 5. Deprecated Directories (Reference Only)

| # | Location | Contents | Action |
|---|----------|----------|--------|
| 17 | `C:\Users\itsji\old_ARBITR8DER\` | Old project folder with prompt_clock.py and other files | Deprecated. Do not write here. |
| 18 | `C:\Users\itsji\agents\` | Old agent directories | Deprecated per AWAKENING.md |
| 19 | `C:\Users\itsji\old_agents\` | Old agent directories | Deprecated per AWAKENING.md |

---

## Session History (Preserved)

| File | Contents |
|------|----------|
| `session-history/opencode-session-notes.md` | First real debugging session 2026-07-17 12:45 |
| `session-history/opencode-fixes-and-learnings.md` | All fixes from that session |

---

## How to Audit

When a new AI agent starts, run this check:

```bash
# Find any new Claude/OpenClaude/OpenCode files outside ARBITR8DER
find /mnt/c/Users/itsji -maxdepth 3 \
  \( -iname "*claude*" -o -iname "*openclaude*" -o -iname "*opencode*" \) \
  -not -path "*/ARBITR8DER/*" \
  -not -path "*/AppData/Local/Packages/*" \
  -not -path "*/openclaude/*" \
  -not -path "*/.local/*" \
  -not -path "*/.config/*" \
  -not -path "*/.openclaude*" \
  2>/dev/null
```

If new files appear, add them to this manifest and consolidate to
`agents/openclaude/` or the appropriate agent directory.

---

## Workflow: Audit Any AI Tools

1. Run the find command above
2. Compare results against this manifest
3. Any NEW file not listed = needs investigation
4. If it's a config: back up to `agents/openclaude/configs/`
5. If it's a launcher: back up to `agents/openclaude/launchers/`
6. If it's a session/prompt: back up to `agents/openclaude/session-history/` or `prompts/`
7. If it's sensitive (.env, keys): note location but NEVER copy contents
8. Update this manifest with the new entry
9. Report findings to operator
