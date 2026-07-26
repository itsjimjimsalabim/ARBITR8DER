# Fresh Onboarding Workflow
**For:** New AI agent joining ARBITR8DER
**Last Updated:** 2026-07-21

---

## Step 1: Read These Files (In Order)

Read every file below before touching any code. This is your education.

### Priority 1 — Identity & Rules
| # | File | What It Tells You |
|---|------|-------------------|
| 1 | `agents/agents.md` | rules, system orientation, all tool locations |
| 2 | `Theories_of_Operations.md` | How the trading system works |
| 3 | `overwatch_workflow.md` | How monitoring and alerts work |

### Priority 2 — Current State
| # | File | What It Tells You |
|---|------|-------------------|
| 4 | `docs/tools_database.md` | Every tool on this machine, where it lives, what version |
| 5 | `docs/massive_issues_report.md` | Known bugs, broken things, what's been fixed |
| 6 | `docs/fresh_onboarding_workflow.md` | This file — you're reading it |
| 7 | `docs/dev_log.md` | What happened recently |
| 8 | `docs/development_plan.md` | What's planned next |

### Priority 3 — Agent Desks
| # | File | What It Tells You |
|---|------|-------------------|
| 9 | `agents/openclaude/README.md` | OpenClaude desk overview |
| 10 | `agents/openclaude/howtobuildopenclaude.md` | How to rebuild OpenClaude |
| 11 | `agents/openclaude/howtobuildOpenClaudeCode.md` | Alternate build guide |
| 12 | `agents/opencode/README.md` | OpenCode desk overview |
| 13 | `agents/opencode/opencode-session-notes.md` | Prior debugging sessions |
| 14 | `agents/opencode/opencode-fixes-and-learnings.md` | What was fixed and how |
| 15 | `agents/codex/AWAKENING.md` | Codex agent orientation |
| 16 | `agents/gemini/journal_2026-07-17.md` | Gemini's system analysis |
| 17 | `agents/kilo/journal_2026-07-17.md` | Kilo onboarding journal |

### Priority 4 — Codebase
| # | File | What It Tells You |
|---|------|-------------------|
| 18 | `src/arbitr8der/__init__.py` | Package entry point |
| 19 | `src/arbitr8der/cli/cli_application_entrypoint_main.py` | CLI entry point |
| 20 | `requirements.txt` | Python dependencies |
| 21 | `opencode.json` | OpenCode auto-approve config |
| 22 | `.env` | Wallet mode + API keys (DO NOT log secrets) |

### Priority 5 — Configs & Launchers
| # | File | What It Tells You |
|---|------|-------------------|
| 23 | `agents/claude/configs/` | Claude config files |
| 24 | `agents/openclaude/launchers/` | How to start tools |
| 25 | `agents/openclaude/scattered-files-manifest.md` | Audit of scattered files |
| 26 | `agents/openclaude/bugs-from-opencode.md` | Known config bugs |

---

## Step 2: Understand the Machine

### What You're Running On
- **Hardware:** AMD Ryzen AI 9 465, 32GB RAM, 1TB SSD
- **OS:** Windows 11 + WSL2 Ubuntu 24.04
- **User:** itsjimjimsalabim
- **Machine:** ZEN-LAPTOP

### Key Paths
| Path | What's There |
|------|-------------|
| `C:\Users\itsji\ARBITR8DER\` | Trading studio (this repo) |
| `C:\Users\itsji\.openclaude\` | OpenClaude source + build + sessions |
| `C:\Users\itsji\.config\opencode\` | OpenCode config (Windows) |
| `~/.config/opencode/opencode.jsonc` | OpenCode config (WSL) |
| `~/.openclaude/` | Same as Windows `.openclaude` (via /mnt/c/) |
| `~/.opencode/bin/opencode` | OpenCode binary (WSL) |
| `~/bin/claude` | Claude wrapper script (WSL) |
| `C:\Users\itsji\bin\claude.bat` | Claude launcher (Windows) |

### What Works Now
| Tool | Windows | WSL | How to Launch |
|------|---------|-----|---------------|
| OpenCode | `opencode` | `opencode` | Type in terminal |
| OpenClaude | `claude.bat` | `claude` | Type in terminal |
| ARBITR8DER | `python runtime_cli.py` | `python runtime_cli.py` | From ARBITR8DER dir |

---

## Step 3: Verify Your Environment

Run these checks before doing anything:

```bash
# WSL
wsl -e bash -c "source ~/.nvm/nvm.sh && node --version && npm --version && bun --version && git --version && python3 --version"
wsl -e bash -c "which opencode && which claude"
wsl -e bash -c "claude --version"

# Windows
node --version
git --version
& "C:\Users\itsji\.bun\bin\bun.exe" --version

# ARBITR8DER
cd C:\Users\itsji\ARBITR8DER
python runtime_cli.py status
```

---

## Step 4: Know the Rules

1. **Paulie does NOT trust.** Verify every path, every config, every assumption.
2. **Never log secrets.** API keys in `.env` stay in `.env`.
3. **PAPER by default.** Never execute live trades without explicit operator action.
4. **Naming:** 4+ words, no cuteness, no roleplay.
5. **Kalshi is sacred.** Never mock data or connections. Take it 300% seriously.
6. **One brain.** `agents/agents.md` is the single source of truth.
7. **Share code.** Good trading scripts go in the trading studio, not hidden in agent dirs.

---

## Step 5: Start Working

1. Pick a task from `docs/development_plan.md`
2. Run `python runtime_cli.py status` to check system health
3. Run `python runtime_cli.py forward start` to enter the trading REPL
4. Use `snapshot`, `opportunities`, `predict` to understand market state
5. Make changes, test them, document them in `docs/dev_log.md`

---

## Quick Reference

| Command | What It Does |
|---------|-------------|
| `python runtime_cli.py status` | System health check |
| `python runtime_cli.py paper-status` | Paper wallet + positions |
| `python runtime_cli.py forward start` | Enter trading REPL |
| `python runtime_cli.py paper-buy BTC YES 0.50 10 --market-id=270916` | Paper buy |
| `python runtime_cli.py paper-sell 270916 0.55` | Paper sell |
| `claude` | Launch OpenClaude |
| `opencode` | Launch OpenCode |

---

## End of Workflow
