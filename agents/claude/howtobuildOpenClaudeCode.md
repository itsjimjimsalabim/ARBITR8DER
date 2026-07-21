# howtobuildOpenClaudeCode — Rebuild and Reconnect Guide

> This document tells any AI (Claude, OpenCode, Codex, Gemini, Kilo, or a fresh
> install) exactly how to rebuild and reconnect the OpenClaude CLI agent on this
> machine. This is the single source of truth for recovery.

---

## 1. System Layout

### Canonical Repo
```
C:\Users\itsji\ARBITR8DER                   <- main workspace
C:\Users\itsji\ARBITR8DER\agents\claude\    <- THIS agent's home
C:\Users\itsji\openclaude\                  <- OpenClaude source code
```

---

## 2. Prerequisites — Install These First

These are required before anything else works. None of these get moved
or consolidated — they stay in their default installation locations.

| # | Dependency | Version | Install | Verify |
|---|-----------|---------|---------|--------|
| 1 | **Node.js** | >= 22.0.0 | `nvm install 22` or nodejs.org | `node --version` |
| 2 | **Bun** | latest | `curl -fsSL https://bun.sh/install \| bash` or `npm i -g bun` | `bun --version` |
| 3 | **Ollama** | latest | ollama.ai | `ollama --version` |
| 4 | **nvm** | latest | `curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh \| bash` | `nvm --version` |
| 5 | **Git** | any | `apt install git` or git-scm.com | `git --version` |

### Post-install: Start Ollama
```bash
ollama serve                  # start if not running
ollama pull llama3.1:8b       # pull the local model
```

---

## 3. Wire Up OpenClaude CLI with OpenAI Model Selections

This is how the launcher connects to OpenAI-compatible providers and sets
the model. The `.bat` and `.sh` launchers do this automatically.

### 3.1 The Launch Chain

```
openclaude.bat (Windows) / launch-ubuntu.sh (WSL)
  → sets OPENCODE_API_KEY=<your-api-key>
  → sets OPENAI_MODEL=big-pickle
  → runs: node bin/openclaude --provider opencode --bare --dangerously-skip-permissions
```

### 3.2 Environment Variables

| Variable | Purpose | Where Set |
|----------|---------|-----------|
| `OPENCODE_API_KEY` | API key for the OpenAI-compatible provider | Launcher (.bat / .sh) |
| `OPENAI_MODEL` | Model name to use (e.g., `big-pickle`, `gpt-5.2-codex`) | Launcher (.bat / .sh) |
| `OPENCODE=1` | Signals we're running inside ARBITR8DER context | Launcher (.bat / .sh) |

### 3.3 Provider Flags

| Flag | Effect |
|------|--------|
| `--provider opencode` | Routes through the OpenAI-compatible bridge |
| `--bare` | Minimal UI, no decoration |
| `--dangerously-skip-permissions` | Skips permission prompts (trusted environment only) |

### 3.4 Start Scripts (from source)

```bash
# Development mode with profile
bun run dev:profile          # auto-detects best local model
bun run dev:fast             # low latency preset
bun run dev:code             # better coding quality preset

# Initialize a profile manually
bun run profile:init -- --provider ollama --model llama3.1:8b
bun run profile:init -- --provider ollama --goal coding
```

### 3.5 Health Check

```bash
bun run doctor:runtime       # human-readable checks
bun run doctor:runtime:json  # JSON for automation
bun run doctor:report        # persist to reports/doctor-runtime.json
```

### 3.6 Rebuild from Source

```bash
cd C:\Users\itsji\openclaude   # or /mnt/c/Users/itsji/openclaude in WSL
git status                     # confirm repo is clean
bun install                    # install dependencies
bun run build                  # compile the CLI
node bin/openclaude --version  # verify it runs
```

If building from a fresh clone:
```bash
git clone <repo-url> openclaude
cd openclaude
bun install
bun run build
```

---

---

## 4. Big Pickle Tuning — Custom Parameters

### What Was Already Tweaked

| Parameter | Default | Our Value | File | Why |
|-----------|---------|-----------|------|-----|
| `DEFAULT_REPL_MAX_TURNS` | 50 | **9,999** | `src/screens/replMaxTurns.ts` | Unlimited REPL turns for long sessions |

### Full Parameter Table — Defaults vs Recommended for Big Pickle

| Parameter | Default | Recommended | Env Var Override | Source File |
|-----------|---------|-------------|-----------------|-------------|
| **Context & Output** | | | | |
| `MODEL_CONTEXT_WINDOW_DEFAULT` | 200,000 | 200,000 | `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | `src/utils/context.ts` |
| `OPENAI_FALLBACK_CONTEXT_WINDOW` | 128,000 | **256,000** | `CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW` | `src/utils/context.ts` |
| `MAX_OUTPUT_TOKENS_DEFAULT` | 32,000 | **64,000** | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `src/utils/context.ts` |
| `CAPPED_DEFAULT_MAX_TOKENS` | 8,000 | **16,000** | _(code only)_ | `src/utils/context.ts` |
| `ESCALATED_MAX_TOKENS` | 64,000 | 64,000 | _(code only)_ | `src/utils/context.ts` |
| `COMPACT_MAX_OUTPUT_TOKENS` | 20,000 | 20,000 | _(code only)_ | `src/utils/context.ts` |
| **Auto-Compact** | | | | |
| `AUTOCOMPACT_BUFFER_TOKENS` | 30,000 | **45,000** | _(code only)_ | `src/services/compact/autoCompact.ts` |
| `AUTOCOMPACT_FLOOR_BUFFER_TOKENS` | 13,000 | 13,000 | _(code only)_ | `src/services/compact/autoCompact.ts` |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | _(off)_ | **85** | `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | `src/services/compact/autoCompact.ts` |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | _(off)_ | _(off)_ | `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | `src/services/compact/autoCompact.ts` |
| **Warning & Blocking** | | | | |
| `WARNING_THRESHOLD_BUFFER_TOKENS` | 20,000 | 20,000 | _(code only)_ | `src/services/compact/autoCompact.ts` |
| `ERROR_THRESHOLD_BUFFER_TOKENS` | 20,000 | 20,000 | _(code only)_ | `src/services/compact/autoCompact.ts` |
| `MANUAL_COMPACT_BUFFER_TOKENS` | 3,000 | 3,000 | `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` | `src/services/compact/autoCompact.ts` |
| **Circuit Breaker** | | | | |
| `AUTOCOMPACT_FAILURE_COOLDOWN_MS` | 300,000 (5min) | **120,000 (2min)** | `OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS` | `src/services/compact/autoCompact.ts` |
| `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES` | 3 | 3 | _(code only)_ | `src/services/compact/autoCompact.ts` |
| **Turns & Goals** | | | | |
| `DEFAULT_REPL_MAX_TURNS` | 50 | **9,999** ✅ done | _(code only)_ | `src/screens/replMaxTurns.ts` |
| `DEFAULT_GOAL_MAX_TURNS` | 50 | 50 | _(code only)_ | `src/services/goal/state.ts` |
| `DEFAULT_OPTIONS.maxTurns` (multiTurn) | 10 | 10 | _(code only)_ | `src/utils/multiTurnContext.ts` |
| **Session Memory** | | | | |
| `POST_COMPACT_TOKEN_BUDGET` | 50,000 | 50,000 | _(code only)_ | `src/services/compact/compact.ts` |

### Recommended Launch Environment for Big Pickle

Set these in `openclaude.bat` / `launch-ubuntu.sh`:

```bash
# Context & Output — push higher for Big Pickle
export CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW=256000
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000

# Auto-compact fires at 85% of context instead of ~84%
# Gives Big Pickle more room before summarizing
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=85

# Faster recovery from compact failures (2min instead of 5min)
export OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS=120000
```

### Why These Values

| Tweak | Reasoning |
|-------|-----------|
| **Fallback context 256K** | Big Pickle is OpenAI-compatible; 128K is conservative. 256K matches gpt-5.2-codex's actual capacity and delays compaction. |
| **Max output 64K** | Default 32K truncates large code blocks. 64K lets Big Pickle finish complex responses without retry escalation. |
| **Capped default 16K** | The 8K cap over-reserves for p99 output of ~5K. 16K gives more room before the escalation retry. |
| **Auto-compact at 85%** | The default ~84% threshold fires compaction early. 85% lets you use more context before the summary. Rare compaction in OpenCode confirms Big Pickle handles full context well. |
| **Cooldown 2min** | 5min is too long if compact genuinely fails — you're stuck waiting. 2min retries faster. |
| **REPL turns 9999** | ✅ Already done. Unlimited interactive turns. |

### What NOT to Touch

| Parameter | Why Leave It |
|-----------|-------------|
| `AUTOCOMPACT_FLOOR_BUFFER_TOKENS` (13K) | Safety net for small-context models. Changing breaks fallback logic. |
| `WARNING/ERROR_THRESHOLD_BUFFER_TOKENS` (20K each) | UI warning thresholds — cosmetic, not functional. |
| `POST_COMPACT_TOKEN_BUDGET` (50K) | Already generous for summary generation. |
| `DEFAULT_GOAL_MAX_TURNS` (50) | Goals are automated — 50 turns is plenty for task completion. |
| `DISABLE_COMPACT` / `DISABLE_AUTO_COMPACT` | Never disable compact entirely — you'll hit blocking limits and crash. |



## 5. Token Limits and Context Window (What the 32K Was)

When the session hit "32K tokens," this is what was happening:

| Setting | Value | File |
|---------|-------|------|
| **MAX_OUTPUT_TOKENS_DEFAULT** | **32,000** | `src/utils/context.ts` |
| MAX_OUTPUT_TOKENS_UPPER_LIMIT | 64,000 | `src/utils/context.ts` |
| CAPPED_DEFAULT_MAX_TOKENS | 8,000 | `src/utils/context.ts` |
| MODEL_CONTEXT_WINDOW_DEFAULT | 200,000 | `src/utils/context.ts` |
| DEFAULT_REPL_MAX_TURNS | 9,999 | `src/screens/replMaxTurns.ts` |
| DEFAULT_GOAL_MAX_TURNS | 50 | `src/services/goal/state.ts` |
| POST_COMPACT_TOKEN_BUDGET | 50,000 | `src/services/compact/compact.ts` |

### What Happened
- The **32K** was the **default max output tokens per response**, not the context window.
- The context window is **200K tokens** (or 128K for OpenAI fallback models).
- Auto-compact triggers when context gets too full (~84% of effective context window).
- After compaction, a summary replaces old messages, freeing space.
- The REPL allows **9,999 turns** (tweaked from default 50).
- Goals (automated multi-turn tasks) get **50 turns** by default.

### How to Get More Output
- The cap automatically escalates from 32K -> 64K on retry when the model wants more.
- With `CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000` set, Big Pickle gets full 64K from the start.
- For compaction summaries, the cap is 20K output tokens (hardcoded).


## 6. Default Installations — LEAVE IN PLACE

These are managed by their respective apps. **Do not move or consolidate.**
This section documents where they live so any agent can find them.

| Path | Contents | Owner | Action |
|------|----------|-------|--------|
| `AppData\Local\Packages\Claude_pzs8sxrjxfjjc\...` | Claude Desktop MSIX install | Claude App | **Leave alone** |
| `%APPDATA%\Claude\claude_desktop_config.json` | Claude Desktop MCP servers | Claude App | Reference only |
| `%APPDATA%\Claude\config.json` | Claude Desktop app settings | Claude App | Reference only |
| `~/.config/opencode/opencode.jsonc` | OpenCode provider config | OpenCode | Reference only |
| `~/.local/share/opencode/opencode.db` | OpenCode 591MB session database | OpenCode | Reference only |
| `~/.local/state/opencode` | OpenCode state directory | OpenCode | Reference only |

---

## 7. Custom Files — Consolidated to agents/claude/

These are **our** files. They live in the canonical ARBITR8DER repo and
are backed up from scattered locations across the system.

| Original Location | Contents | Backed Up To |
|-------------------|----------|-------------|
| `C:\Users\itsji\.openclaude.json` | Project config | `configs/.openclaude.json` |
| `C:\Users\itsji\.openclaude/settings.local.json` | Permission defaults | `configs/settings.local.json` |
| `C:\Users\itsji\.openclaude\.openclaude-profile.json` | Ollama provider profile | `configs/.openclaude-profile.json` |
| `C:\Users\itsji\openclaude\.env` | **SECRET** API keys (never copy) | Reference only |
| `C:\Users\itsji\OneDrive\Desktop\OpenClaude.lnk` | Desktop shortcut | `launchers/OpenClaude.lnk` |
| `C:\Users\itsji\OneDrive\Desktop\OpenCode at Home.lnk` | Desktop shortcut | `launchers/` |
| `C:\Users\itsji\OneDrive\Desktop\Start Codex Full Access.lnk` | Desktop shortcut | `launchers/` |
| `C:\Users\itsji\OneDrive\Desktop\agents - Shortcut.lnk` | Desktop shortcut | `launchers/` |
| `C:\Users\itsji\OneDrive\Desktop\ARBITR8DER - Shortcut.lnk` | Desktop shortcut | `launchers/` |

### Launcher Files (canonical copies)
| File | Platform | Purpose |
|------|----------|---------|
| `launchers/openclaude.bat` | Windows | Sets API key + model, launches with bypass perms |
| `launchers/launch-ubuntu.sh` | WSL/Linux | Same as .bat but for Ubuntu/xterm |
| `launchers/OpenClaude.lnk` | Windows | Desktop shortcut to Claude.exe |

---

## 8. Deprecated Directories — Read-Only Reference

| Path | Contents | Status |
|------|----------|--------|
| `C:\Users\itsji\old_ARBITR8DER\` | Old project with prompt_clock.py | Deprecated. Do not write. |
| `C:\Users\itsji\agents\` | Old agent directories | Deprecated per AWAKENING.md |
| `C:\Users\itsji\old_agents\` | Old agent directories | Deprecated per AWAKENING.md |

---

## 9. Session History (Preserved)

| File | Contents |
|------|----------|
| `session-history/opencode-session-notes.md` | First debugging session 2026-07-17 12:45 |
| `session-history/opencode-fixes-and-learnings.md` | All fixes from that session |

---

## 10. Reconnection Checklist

| Step | Command | Expected |
|------|---------|----------|
| 1 | `node --version` | v22+ |
| 2 | `bun --version` | Latest |
| 3 | `ollama --version` | Latest |
| 4 | `ollama serve` | Server running |
| 5 | `ollama list` | llama3.1:8b present |
| 6 | `bun run doctor:runtime` | All checks pass |
| 7 | `bun run dev:profile` | OpenClaude starts |

---

## 11. First Agent Workflow

When a fresh agent starts in ARBITR8DER:

1. Read `CLAUDE.md` for identity and hard rules
2. Read this file (`howtobuildOpenClaudeCode.md`) for recovery
3. Check `configs/` for backed-up provider profiles
4. Check `launchers/` for startup scripts
5. Run `bun run doctor:runtime` to validate environment
6. Start with `bun run dev:profile` or the appropriate launcher
7. Verify: `node bin/openclaude --version`
