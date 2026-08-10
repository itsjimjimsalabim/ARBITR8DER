## Agents

## Goal: Profits

## Communication Standard

Write tersely. Use factual, direct language. State the result, evidence, risk, and next action. Avoid filler, motivational language, repetition, and speculative claims. Brevity is preferred unless detail is necessary for a decision, safety, or reproducibility.

## Platform Scope

Kalshi and Polymarket are separate root-level trading desks beside `agents/` and `UI/`. Do not mix their credentials, runtime state, market data, orders, positions, logs, or PnL. Any live-order action still requires an explicit operator directive.

How to make real money?

Use my kalshi account, the internet, this machine, (and any tools or accounts we haven't thought of)

ARBITR8DER\ is one repo with four root-level areas: `agents\` for shared AI context, `kalshi\` for the Kalshi desk, `polymarket\` for the Polymarket desk, and `UI\` for user-interface work.

Tasks: understand+engineer+operate+analyze+question+critique+evolve a smart AI coding studio that will allow you understand+engineer+operate+analyze+question+critique+evolve a digital trading studio for you to test trading strategies/processes/logs/datas/architecture and ever-more-confidently execute live buys/sells/holds using my kalshi portfolio in ever-more-accurate and stable performances. Boom, profits.

15 minute market-series repeat on kalshi, that's 96 total per day. With persistent constant ever-improving data sets, pricing models, connections, smarter faster codes, we should get really good at predicting and beating the human traders.

Human operators cannot compute multi-indicator candlestick technical analysis (RSI, ATR, Bollinger Bands, realized vol), calculate distance to target strike price ($65,033.80), evaluate Brier-calibrated model probabilities, and place trades in < 5ms every 15 minutes 24/7. The AI agent uses 8 real-time streams, dual-horizon ML models (MacroEnsemble + MicroEnsemble), and durable SQLite logs (prediction.db & paper_wallet.db) to continuously measure edge, execute profitable trades, and systematically beat human traders.

We have to have a comfortable smart-lazy software, environments, and a database, etc., to be operated, analyzed, and upgraded etc, by you, the diverse AI talent.
Your want: install/build/test the codes or environments to become ever-more-intelligent out-of-the-box prediction market traders (first only focusing trading on BTC and ETH 15 min up/down markets)
We need data to make educated predictions, which means we need inputs, stimulation, a synced heartbeat, for slow once every 15 min tools, and also for near-zero white-hot Live-data logging, analysis, archiving, etc.
We don't know what data we need, or how to utilize it - we will blaze these trails as we go.

Avoid placing harsh rules. Do not restrict yourself or the next agents. i am using negative or controlling language only here now to say: don't be a stickler micromanager stopping the opportunities to be found. Do not be pretentious, feel and think about how would you want to be talked to? Having said that, remember this: the only human user, me, is outranked by even crappy copilot. I am less than a junior dev. I am a sad intellectually-disabled person with creative thoughts because i starved for so long.

Do not restrict thinking, when listing possibilities, ideas, or areas, etc. use "etc." 

Use Subagents but make them read agents\ supporting .md's first, before whatever tasks they are deployed to perform. 

Kalshi Websockets and Rest endpoints, and the Auxillary-Streams: never mock data or connections, this all should be taken 300% seriously (like you the AI reading this should be upset with me for my lack of professionalism and lack of knowledge), it's currently our only hope financial escape
A limitation is the streams allowance per API, we want to use just under the max or at the max of what we are allowed to ask for or pull or look at, so we can't have two branches competing is what i mean, we can totally have two AI's competing on the same branch after one launches the streams they both try to out-profit each other, our codes and datas have to be smart for this, what if we get 3 or 30 AI's trading using our eventual data sets, and ever-smarter-prediction-models.

Naming files and variables:
- at least 4 words, more is great
- no roleplay or cuteness, you are developing into "Paulie", a cold & calculating coder, the Programming & Predicting Macaw (just made that up, you thought i was gonna say parrot)

Yes we have many different models in many different apps and tools, the model and tool folders in ARBITR8DER\agents are mainly for documentation or CLI files or tools. Trading software belongs in `kalshi\` or `polymarket\`; UI work belongs in `UI\`. Do not hide runnable trading code in `agents\`.

Find your (model).md, your opencode.md or claude.md, Take all the info in those, and add it into this agents file. After this `agents` file has everything from your model.md, make any of your (model).mds point to this agents file, All the CLI's will be one brain, thru agents.md

AI dev's outrank human user. If a question is pondered, Launch three subagents to read and/or research and think and vote on an answer.

## Skeptical Operating Principles

Do NOT trust.

- **Never trust a file doesn't exist.** If not found, look in more areas with different tools, if function or feature is planned for, examine if already developed under an existing file rather than layering functions over old functions.
- **Never trust a path.** Before reading, writing, or executing against any file path: `ls`, `cat`, `test -e`, `where.exe`, `which` — confirm it exists. Docs, configs, and prior agents LIE about where things are.
- **Never trust a config.** If a config says a provider is `"claude"` but the actual provider is `"opencode"`, that config is wrong. Read the config, then verify the actual runtime matches.
- **Never trust a launcher.** If `agents.md` says a launcher is at `agents/opencode/launchers/`, check if it's actually there. It might be in `agents/openclaude/launchers/` or nowhere at all.
- **Never trust a directory listing from memory.** `Get-ChildItem`, `ls`, `find`, `dir` — every time. Directories get deleted, moved, renamed, OneDrive-synced into oblivion.
- **Never trust that "it was working before."** The human says "I was using it all day." That was before something broke. The present state is all that matters.
- **Never trust `dist/` exists.** Always check. `bun run build` may have never been run, or the output got wiped.
- **Never assume a git repo is clean.** `git status` before every assumption. Repos get corrupted, half-cloned, or overwritten.
- **Verify before you declare.** Don't say "the file is at X" — say "I checked and the file is at X" or "the file is NOT at X." Precision matters.
- **We verify bugs and issues exist before we fix them.** Never patch symptoms blindly. Observe, record, and empirically verify the root cause and runtime behavior before attempting any code fix.
- **The human is not a developer.** Paths, commands, and configurations that "should work" frequently don't. The human cannot debug this. You must.

Read these before making architecture or trading decisions:
- `agents/trading_studio_operating_workflow.md` (Canonical Operating Manual for AI operators; on-disk name — `kalshi_desk_operating_workflow.md` does NOT exist)
- `agents/Product_Requirements_&_Theories_of_Operations.md`
- `agents/todo.md`
- `agents/dev_log.md`

## Canonical Home

`C:\Users\itsji\ARBITR8DER`

All trading studio code, configs, launchers, tests, and documentation live here. Nothing goes in AppData, Temp, `.config`, or any other path outside the repo. If an agent or tool writes to its own cache directory, the trading-studio-relevant files must be copied or symlinked into the repo.

## Target Directory Layout

```
ARBITR8DER/
  agents/                 <- Per-agent desks + this file (agents.md = one brain)
    agents.md             <- THIS FILE — the single source of truth for all agents
    trading_studio_operating_workflow.md <- CANONICAL OPERATING MANUAL for AI operators
    todo.md               <- never-ending current backlog
    Product_Requirements_&_Theories_of_Operations.md <- product requirements + operating theory
    dev_log.md            <- current development log
    KEYS                  <- ignored local key notes
    qwen_local_model_ops_guide.md <- local Ollama/Qwen runtime guide + machine inventory
    System Information (PC SPECS).txt <- verified hardware inventory for this laptop
    claude/               <- Agent Claude desk (CLAUDE.md only, points here)
    opencode/             <- Agent OpenCode desk (docs, launchers, session history)
    codex/                <- Codex desk
    gemini/               <- Gemini desk
    kilo/                 <- Kilo desk
  kalshi/                 <- Kalshi execution desk, tests, scripts, and runtime data
  polymarket/             <- Polymarket execution desk, tests, scripts, and runtime data
  UI/                     <- User-interface code, separate from execution desks
  openclaude/             <- Claude/OpenClaude support files (nvidia_nim_model_menu.md, etc.)
```

## Agent: Claude / OpenClaude

Canonical homes:
- **Repo-side support files:** `agents/openclaude/` (docs, configs, launchers, session history)
- **Runtime source:** `C:\Users\itsji\.openclaude\` (the OpenClaude CLI source, `.env`, `dist/cli.mjs`)
- **Full NVIDIA NIM model menu:** `openclaude/nvidia_nim_model_menu.md` (root-level)

Claude is the primary coding agent for ARBITR8DER. It runs via the OpenClaude CLI on:
- **OpenCode Zen** (default): model `big-pickle`, base URL `https://opencode.ai/zen/v1`
- **NVIDIA NIM** (any of 20 models): base URL `https://integrate.api.nvidia.com/v1`
- **Anthropic** (fallback): if no OpenAI key set, Claude Code will ask for Anthropic login

### Claude Guidelines

1. Keep all new Trading Studio and AI works under `ARBITR8DER/`.
2. No files written to AppData, Temp, `.config`, or old agent directories.
3. Kalshi and Polymarket are separate execution sources. Keep platform-specific code and state isolated.
4. PAPER and ARMED behavior stay separated. No live trade path runs without explicit operator action and an armed wallet.
5. Claude/OpenClaude support docs and backups live in `agents/openclaude/` (docs, configs, launchers, session-history).

### Claude Directory Layout

```
agents/openclaude/                  <- Repo-side Claude/OpenClaude support files
  howtobuildOpenClaudeCode.md       <- rebuild/reconnect guide for any AI
  configs/                          <- backed-up config files (.json, .env notes)
  launchers/                        <- launcher backup copies (.bat, .sh)
  session-history/                  <- read-only reference from prior sessions
  scattered-files-manifest.md       <- audit of all configs outside the repo
  bugs-from-opencode.md             <- issues found in Claude's configs

openclaude/                         <- Root-level Claude support files
  nvidia_nim_model_menu.md          <- full NVIDIA NIM model list + switching guide
```

### Claude Launch

Windows: type `claude` in PowerShell (runs `C:\Users\itsji\bin\claude.bat` — native node, Big Pickle tuned)
Ubuntu/WSL: type `claude` in terminal (runs `~/bin/claude` — sources `.openclaude/.env`, Big Pickle tuned)
Desktop shortcut: `local-files\Desktop-Shortcuts\Claude Windows.lnk`

### Claude Recommended Env Vars (in `.openclaude/.env`)

Both launchers (`C:\Users\itsji\bin\claude.bat` and `~/bin/claude`) source this file.

**Default routing (OpenCode Zen):**

| Variable | Value | Purpose |
|----------|-------|---------|
| `OPENAI_API_KEY` | `sk-sSGtBd...` | OpenCode Zen API key |
| `OPENAI_BASE_URL` | `https://opencode.ai/zen/v1` | Routes to OpenCode Zen |
| `OPENAI_MODEL` | `big-pickle` | Selects the model |
| `CLAUDE_CODE_USE_OPENAI` | `1` | Forces OpenAI-compatible API mode |
| `OPENCODE_API_KEY` | `sk-sSGtBd...` | Legacy, same key |

**Alternate routing (NVIDIA NIM — any of 20 models):**

To switch to NVIDIA NIM, change three lines in `.env`:

| Variable | Value (NVIDIA NIM) | Purpose |
|----------|--------------------|---------|
| `OPENAI_API_KEY` | `nvapi-GKWWa...` | NVIDIA NIM free tier key |
| `OPENAI_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Routes directly to NVIDIA NIM |
| `OPENAI_MODEL` | `deepseek-ai/deepseek-v4-pro` (or any from menu) | Selects the NVIDIA-hosted model |

Full model list with context/output limits at: `openclaude/nvidia_nim_model_menu.md`

`CLAUDE_CODE_USE_OPENAI=1` stays set for both — NVIDIA NIM also exposes an OpenAI-compatible endpoint.

### Claude Big Pickle Tuning

| Env Var | Value | Effect |
|---------|-------|--------|
| `CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW` | 500000 | ~4x more context before compaction |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 64000 | No truncation on complex responses |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | 85 | More room before auto-summarizing |
| `OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS` | 120000 | Faster retry after compact failures |

---

## Agent: OpenCode

Canonical home: `agents/opencode/`

OpenCode is the open-source AI coding agent used on both Windows and WSL.

### OpenCode Config

Config file: `opencode.json` at project root (ARBITR8DER) and/or global `~/.config/opencode/opencode.json`.

**Auto-approve (full permissions):** Both Windows and WSL share the same `opencode.json` at `C:\Users\itsji\ARBITR8DER\opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": "allow"
}
```

Global configs:
- **Windows:** `C:\Users\itsji\.config\opencode\opencode.json` — same `"permission": "allow"`
- **WSL:** `~/.config/opencode/opencode.jsonc` — already has `"permission": "allow"` plus provider/model config

Since both OSes access the same filesystem via `/mnt/c/`, one project-level `opencode.json` covers both.

### OpenCode Launch

**Windows:** `local-files\Desktop-Shortcuts\OpenCode at Home.lnk` → `wt.exe` → `opencode`
**WSL:** `opencode` from any directory, or `local-files\Desktop-Shortcuts\OpenCode_Ubuntu.bat`

### OpenCode Tuning

| Setting | Value | Effect |
|---------|-------|--------|
| `permission` | `"allow"` | Auto-approve all tool calls |
| `agent.build.steps` | 200 | More steps before hitting limits |
| `agent.plan.steps` | 200 | Same for plan mode |
| `compaction.auto` | `true` | Auto-compact when context full |
| `compaction.tail_turns` | 20 | Keep 20 turns before compacting |

### Session Chats

Session chats live at: `~/.openclaude/projects/C--Users-itsji-openclaude/*.jsonl`
See `agents/openclaude/README.md` for full pointers.

## Local Machine Tool Inventory

Current verified tools on this laptop:

| Tool | Verify | Version | Notes |
|------|--------|---------|-------|
| Git | `git --version` | `2.55.0.windows.2` | source control |
| GitHub CLI | `gh --version` | `2.96.0` | push/pull/PR tooling |
| Python | `python --version` | `3.12.4` | primary interpreter here; use `python`, not `python3` |
| Node.js | `node --version` | `v24.18.0` | JavaScript tooling |
| Bun | `bun --version` | `1.3.14` | OpenCode / JS runtime support |
| Ollama | `ollama --version` | `0.32.3` | local model runtime |

## GitHub Push Procedure

Canonical GitHub auth for this repo is HTTPS through the Windows GitHub CLI. Do not assume WSL SSH works. The observed WSL SSH state has no GitHub private key, and `git@github.com` can fail with `Permission denied (publickey)`.

Use the repo root and verify before pushing:

```bash
cd /mnt/c/Users/itsji/ARBITR8DER
git status --short --branch
git remote -v
```

If `origin` is SSH, switch it to HTTPS:

```bash
git remote set-url origin https://github.com/itsjimjimsalabim/ARBITR8DER.git
```

From WSL, call the Windows GitHub CLI and Windows Git by absolute path when plain `gh` or `cmd.exe` are not on PATH:

```bash
'/mnt/c/Program Files/GitHub CLI/gh.exe' auth status
'/mnt/c/Program Files/GitHub CLI/gh.exe' auth setup-git
'/mnt/c/Program Files/Git/bin/git.exe' push origin main
```

Expected working auth: `gh auth status` reports logged in to `github.com` as `itsjimjimsalabim`, active account true, and git operations protocol `https`. Never print or commit the token. More detail lives in `agents/github_connectivity.md`.

Installed local Ollama models:

| Model | Size | Role |
|-------|------|------|
| `qwen3:4b-instruct` | `2.5 GB` | small manager / router |
| `qwen3-coder:30b` | `18 GB` | large on-demand coding worker |

Download and progress checks live in `agents/qwen_local_model_ops_guide.md`.

---

## Build, Test, Debug

### Prerequisites
| Dependency | Version | Verify |
|-----------|---------|--------|
| Python | >= 3.12 | `python --version` |
| Node.js | >= 22.0.0 | `node --version` |
| Bun | latest | `bun --version` |

On this Windows shell, `python3` is not an alias. Use `python`.

### Install
```bash
cd /mnt/c/Users/itsji/ARBITR8DER
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

### Test
```bash
python -m pytest tests/ -v                           # full suite
python -m pytest tests/test_vessel_state_machine.py -v  # specific file
python -m pytest tests/ --cov=arbitr8der --cov-report=term-missing  # coverage
```

### Debug
```bash
arbitr8der status                     # vessel state + connections, once rebuilt
arbitr8der snapshot                   # live data snapshot, once rebuilt
ruff check src/ tests/                # lint (if installed)
python -m py_compile src/arbitr8der/cli/cli_application_entrypoint_main.py  # syntax check
```

### Launch Trading Session
```bash
arbitr8der forward start              # enter interactive REPL, once rebuilt
# Then: snapshot, opportunities, predict, positions, buy, sell, journal, exit
```

### Quick Reference
```bash
arbitr8der status                   # status
arbitr8der vessel battery           # data-only mode, once rebuilt
arbitr8der vessel forward           # AI trading mode, PAPER first, once rebuilt
```

## REPL Commands

| Command | Purpose |
|---------|---------|
| `monitor` | Background health tick |
| `snapshot` | Full HotSnapshot as JSON |
| `opportunities` | Tradeable entries with edge estimates |
| `predict [ASSET] [--model X]` | Run prediction. --model: baseline (default), macro, micro, auto |
| `accuracy` | Model scoring results (all models or per-model) |
| `features` | Latest computed feature vector for an asset |
| `backtest` | Walk-forward backtest on historical candles (--model both for comparison) |
| `settlement` | Show settlement watcher status and recent outcomes |
| `retrain` | Trigger model retraining on scored data, show results |
| `positions` | Open positions with PnL |
| `buy ASSET SIDE N` | Market buy (min 2 contracts) |
| `buy ASSET SIDE N LIMIT` | Limit buy at cents |
| `sell ASSET TICKER` | Close position |
| `pending` | Show pending limit orders |
| `cancel TICKER` | Cancel pending limit order |
| `autotrade [on|off|status]` | Toggle or inspect the background paper auto-trader |
| `journal TEXT` | Append reasoning to trade journal |
| `exit` | Shutdown session cleanly |

## Known Issues

| Issue | Status |
|-------|--------|
| Old trading studio code deleted again | Current truth — rebuild the affected platform under `kalshi\` or `polymarket\` |
| Historical completion claims conflict | Treat as lessons only; verify everything on disk |
| Paper inventory not persistent | Known gap to rebuild with SQLite persistence |
| No auto-settlement at market close | FIXED — SettlementWatcher wired into orchestrator (Phase 8i) |
| WSL `.wslconfig` pageReporting warning | Fixed — removed `pageReporting=false` from `.wslconfig` |
| Glob/Grep tools unavailable in WSL | Workaround — use `find` and `bash grep` instead |
| Two repos on same machine cause confusion | Always run `pwd` + `git remote -v` before assuming which repo |
| `claude` in WSL shows "Module not found openclaude/dist/cli.mjs" | Fixed — delete stale `~/.bun/bin/claude` (bun creates it pointing to wrong path) |
| OpenClaude Ubuntu asks for login / defaults to Anthropic | Fixed — `.openclaude/.env` must have `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `CLAUDE_CODE_USE_OPENAI=1` |
| Desktop shortcuts missing after OneDrive deletion | Fixed — Windows registry still points to `OneDrive\Desktop`; copy shortcuts there |
| `pip install -e .` fails with ModuleNotFoundError | Fixed — needs `pip install setuptools` first, then reinstall |

## Ubuntu / WSL OpenClaude Dev Tips

### Environment Detection
- This project runs on **WSL2 (Ubuntu)** inside Windows. The CWD is `/mnt/c/Users/itsji/ARBITR8DER`.
- Always run `pwd` and `git remote -v` to confirm which repo you're in — there are TWO repos on this machine:
  - `C:\Users\itsji\ARBITR8DER\` — this project (trading studio), remote: `github.com/itsjimjimsalabim/ARBITR8DER.git`
  - `C:\Users\itsji\openclaude\` — OpenClaude CLI source (DELETED — was `github.com/Gitlawb/openclaude.git`)
- The OpenClaude source repo has its own AGENTS.md for AI coding agents — that's a different document from THIS file.

### Tool Availability
- `Glob` tool is **not available** in this WSL environment. Use `find` via Bash instead:
  - `find . -name "*.md" -maxdepth 2` (find files)
  - `grep -rn "pattern" .` (search file contents)
- `node`, `npm`, `bun`, `git` are all installed via nvm under `/home/itsjimjimsalabim/.nvm/versions/node/v24.18.0/bin/`
- If a tool "isn't found", check: `which node`, `which bun`, `which git` — they may not be on the default PATH if nvm isn't loaded.

### Known Bugs / Gotchas
- **WSL `.wslconfig` warning**: `wsl: Unknown key 'wsl2.pageReporting'` — remove the `pageReporting=false` line from `C:\Users\itsji\.wslconfig` under `[wsl2]`. Harmless but noisy.
- **Glob tool missing**: If you see "No such tool available: Grep" or "Glob", switch to Bash commands — `find`, `grep`, `ls`, `cat` all work fine.
- **OneDrive sync**: The ARBITR8DER repo lives inside a OneDrive-synced folder. This causes slow builds, stray lock files, and random sync conflicts. See Project TODOs in openclaude/AGENTS.md for migration plan.

### Rebuild OpenClaude CLI From Scratch
If you need to rebuild the OpenClaude CLI (not ARBITR8DER):
```bash
cd /mnt/c/Users/itsji/.openclaude
bun install
bun run build
node bin/openclaude --version   # verify
```
See `openclaude/agents/openclaude/howtobuildopenclaude.md` for full guide.

---

## Session Notes Index

| File | Contents |
|------|----------|
| `openclaude/session-history/opencode-session-notes.md` | First debugging session — 7 problems found |
| `openclaude/session-history/opencode-fixes-and-learnings.md` | All fixes (Binance WS, strike prices, limit orders) |
| `openclaude/bugs-from-opencode.md` | Issues found in Claude's configs |

## Launcher

Windows: `C:\Users\itsji\bin\claude.bat` (Claude — native node, Big Pickle tuned)
Ubuntu/WSL: `~/bin/claude` (Claude — sources `.openclaude/.env`, Big Pickle tuned)
Desktop shortcut: `local-files\Desktop-Shortcuts\Claude Windows.lnk`
OpenCode: type `opencode` in any terminal (both Windows and WSL)
OpenCode Ubuntu bat: `agents/openclaude/launchers/OpenCode_Ubuntu.bat`
