# ARBITR8DER Onboarding Workflow

**Audience:** Any AI agent (Claude, OpenCode, Codex, Gemini, Kilo, Antigravity, etc.) or human opening this repo for the first time.
**Purpose:** A single, accurate, on-disk-verified map of the repo and the order to read it in. Use this instead of trusting path references in older docs — those may lie.
**Last verified:** 2026-08-02

---

## 0. Skeptical Pre-Flight (do this every session)

```bash
pwd
git remote -v          # must show github.com/itsjimjimsalabim/ARBITR8DER.git
git status --short     # know what is dirty/deleted before you touch anything
ls -la                 # confirm layout matches §1 below
```

Current expected worktree state (verified 2026-08-09):

- Branch `main`, tracking `origin/main`, **in sync with origin** (the old PAT-in-history push block was resolved by history pruning; you should not see "commits ahead").
- Two deletions in the worktree that are intentional and can be left alone: `CLAUDE.md` and `opencode.json`. Neither is needed — `agents/agents.md` is the agent pointer and `opencode` uses its own config.

If any of the above surprises you, fix the environment before touching code. Prior agents lie about paths. OneDrive sync, deleted folders, and stale configs are common. Verify, don't trust.

---

## 1. Repo Layout (verified 2026-08-09)

```
ARBITR8DER/                                  <- repo root, canonical home
├── .env                                     <- SINGLE source of truth for env vars (gitignored)
├── .env.bak                                 <- alternate NVIDIA-NIM routing config (do NOT load)
├── .env.example                             <- tracked template
├── .gitignore                               <- repo-level ignore rules
├── .mcp.json                                <- MCP server config (GitHub)
├── README.md                                <- short repo overview
├── pyproject.toml                           <- STALE placeholder (real one in kalshi_desk/)
├── requirements.txt                         <- STALE placeholder
├── requirements-dev.txt                     <- STALE placeholder
├── agents/                                  <- SHARED BRAIN for all AI agents
│   ├── agents.md                            <- SINGLE source of truth for AI ops
│   ├── onboarding_workflow.md               <- THIS FILE
│   ├── todo.md                              <- current backlog + phase status
│   ├── dev_log.md                           <- development log / history
│   ├── Product_Requirements_&_Theories_of_Operations.md
│   ├── overwatch_workflow.md                <- AI trading-session playbook
│   ├── kalshi_desk_build_plan.md         <- how the studio is intended to be built
│   ├── prediction_system_plan.md            <- Phase 8 prediction design notes
│   ├── kalshi_websocket_debugging_reference.md <- Kalshi WS auth gotchas
│   ├── github_connectivity.md               <- git/gh/SSH notes
│   ├── qwen_local_model_ops_guide.md        <- local Ollama/Qwen runtime guide
│   ├── KEYS                                 <- gitignored local key notes (never commit)
│   ├── _archive/                            <- historical reference only, not operating docs
│   ├── openclaude/                          <- Claude/OpenClaude desk
│   ├── opencode/                            <- OpenCode desk
│   ├── codex/  kilo/                        <- other agent desks
│   ├── browser_access/
│   └── agent_benchmark_tests_&_performance_dynamometers/
├── kalshi_desk/                          <- the actual software
│   ├── pyproject.toml                       <- REAL project metadata + deps (arbitr8der CLI)
│   ├── readme.md                            <- studio directory map
│   ├── .env.example                         <- tracked pointer, says "use root .env"
│   ├── kalshi_desk_package/                  <- installable package (import name)
│   │   ├── cli/   config/   data_contracts/   data_sources/
│   │   ├── durable_storage/   execution/   prediction/
│   │   ├── reconciliation/   risk/   vessel/
│   ├── scripts/                             <- scratch/debug/utility scripts
│   ├── streams/                             <- kalshi_private.pem (gitignored, mode 600)
│   ├── tests/                               <- pytest suite (~20 files)
│   ├── .venv/                               <- local virtualenv (gitignored)
│   └── runtime/                             <- local data (gitignored): DBs, state, logs, archives
│       └── .gitignore                       <- runtime-local ignore rules
└── UI/                                      <- standalone scoreboard app (future)
```

**Notes on what is NOT there (verified):**

- `CLAUDE.md` and `opencode.json` are deleted from the worktree. Do not recreate them out of reflex.
- `agents/claude/` and `agents/gemini/` do not exist. The Claude desk is `agents/openclaude/`.
- `System Information (PC SPECS).txt` is **2.2 MB of Windows Error Reporting junk**, not machine specs. Ignore it.
- Stale placeholders (`pyproject.toml`, `requirements*.txt` at root) are kept only so old launchers don't crash. The real project is `kalshi_desk/pyproject.toml`. Install with `pip install -e ./kalshi_desk`.

---

## 2. Read Order (do this before any architecture decision)

Read in this order. Each file is short and assumes the previous. If a file in this list is missing, note it and move on — verify on disk, never trust the doc.

| # | File | Why |
|---|------|-----|
| 1 | `agents/onboarding_workflow.md` | You're here. This is the map. |
| 2 | `agents/agents.md` | Operating principles, vessel states, build/test commands. The primary directive. |
| 3 | `agents/Product_Requirements_&_Theories_of_Operations.md` | What we are building and why. Vision, strategies, technical standards, theories. |
| 4 | `agents/todo.md` | Current backlog and phase status. Tells you what's done vs next. |
| 5 | `agents/dev_log.md` | What has been built, what broke, what was fixed. Real history — read the newest entry first. |
| 6 | `agents/kalshi_desk_build_plan.md` | The plan for how the studio is built. Read before proposing structure changes. |
| 7 | `agents/prediction_system_plan.md` | Design notes for the Phase 8 prediction pipeline (features, models, scoring). |
| 8 | `agents/kalshi_websocket_debugging_reference.md` | Kalshi WS auth gotchas (RSA-PSS salt length, subscribe format). Read before touching WS code. |
| 9 | `agents/kalshi_desk_operating_workflow.md` | **Canonical Operating Manual** — Live REPL playbook, 15-min cadence, and patient limit rules. |
| 10 | `agents/overwatch_workflow.md` | Legacy Overwatch workflow reference. |
| 11 | `agents/github_connectivity.md` | How to push/pull/PR. HTTPS via `gh` is the working path. |
| 11 | `kalshi_desk/readme.md` | "You are here" map of the package. |
| 12 | `kalshi_desk/pyproject.toml` | Real dependencies, CLI entry point (`arbitr8der`), ruff/pytest config. |

Optional, when relevant:

- `agents/qwen_local_model_ops_guide.md` — local Ollama/Qwen model roles (manager + coder) and machine notes.
- `agents/KEYS` — local, gitignored key notes. Reference only; never paste secrets into tracked files.
- `agents/_archive/` — historical only. Not operating instructions.
- `agents/codebase_memory_mcp_guide.md` — **read this before navigating the codebase**. CBM is a code intelligence MCP tool (installed system-wide, not in this repo) that gives any agent instant call-graph traversal, impact analysis, dead code detection, and semantic search across `kalshi_desk/`. Replaces manual grepping. Use it.

---

## 3. Install + Verify

```bash
cd /mnt/c/Users/itsji/ARBITR8DER
pip install -e ./kalshi_desk            # installs the `arbitr8der` CLI + all deps
pip install -e "./kalshi_desk[dev]"     # adds pytest, ruff, mypy
arbitr8der version                                # must print "arbitr8der 0.1.0"
```

Notes:

- There is a prebuilt virtualenv at `kalshi_desk/.venv/`. Use it (`./kalshi_desk/.venv/bin/python`, `./kalshi_desk/.venv/bin/arbitr8der`) to avoid polluting the system interpreter.
- WSL shell: `python3` and `python` both work. On Windows PowerShell, use `python` (`python3` is not an alias).
- If `pip install -e .` fails with `ModuleNotFoundError`, run `pip install setuptools` first, then retry. (Known gotcha.)

---

## 4. Configuration — One `.env`

There is exactly **one** live `.env`: `ARBITR8DER/.env` (repo root). It is gitignored.

`kalshi_desk/.env` does **not** exist. `TradingStudioSettings` (in `kalshi_desk_package/config/typed_configuration_settings_module.py`) loads the root `.env` by absolute path resolved from the package location, so the same env works regardless of CWD or OS.

`.env.bak` at the root is an **alternate NVIDIA-NIM routing config**, not a backup to load. Do not source it. The live `.env` routes to OpenCode Zen.

Current live values of interest (verified 2026-08-09):

```ini
# --- OpenCode / OpenAI (Claude-family CLI routing) ---
OPENCODE_API_KEY=...
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://opencode.ai/zen/v1
OPENAI_MODEL=big-pickle
CLAUDE_CODE_USE_OPENAI=1

# --- Kalshi ---
AR8_KALSHI_API_KEY_ID=<UUID from Kalshi dashboard>
AR8_KALSHI_PRIVATE_KEY_PATH=kalshi_private.pem

# --- Trading ---
AR8_WALLET_MODE=paper                      # paper | armed
AR8_TRADING_MODE=hold                       # hold | buy | sell
AR8_TICK_INTERVAL=60
```

Optional keys documented in `.env.example` but not set in `.env` (defaults apply): `AR8_AUTO_ARM=false`, `AR8_DRY_RUN=true`, PostgreSQL vars (unused post-SQLite migration).

Copy `.env.example` → `.env` and fill in real values if starting fresh. Kalshi private key file goes at `kalshi_desk/streams/kalshi_private.pem` and is gitignored. Never paste real keys into tracked files.

---

## 5. Vessel States (the killswitch model)

| State | Streams | Trading | When to use |
|-------|---------|---------|-------------|
| `Full_Stop` | OFF | NO | Default. Every new process starts here. |
| `Battery` | ON | NO | Data soak. Read snapshot, journal notes, detect opportunities. |
| `Full_Forward` | ON | YES (PAPER or ARMED) | The killswitch. AI trades via explicit `buy`/`sell` REPL commands. |

The vessel state itself is the permission to trade. No automated loop fires trades. The AI is the trader; the code only executes the AI's intent with risk guards. `VesselStateMachine` forces `Full_Stop` on every instantiation (vessel_state_machine.py:101).

Transitions:

```bash
arbitr8der vessel status      # current state
arbitr8der vessel battery     # Full_Stop or Full_Forward -> Battery
arbitr8der vessel forward     # -> Battery -> Full_Forward (PAPER first)
arbitr8der vessel stop        # -> Full_Stop (safe shutdown)
```

---

## 6. Run a Session

```bash
# 1. Verify environment
arbitr8der status
arbitr8der snapshot

# 2. Move to trading state (PAPER by default)
arbitr8der vessel forward

# 3. Enter the interactive trading REPL
arbitr8der forward start
```

REPL commands (full list also in `agents/agents.md`):

| Command | Purpose |
|---------|---------|
| `snapshot` | Full HotSnapshot as JSON |
| `opportunities` | Tradeable entries with edge estimates |
| `predict ASSET --model X` | Prediction. `--model`: baseline (default), macro, micro, auto |
| `accuracy [MODEL]` | Model scoring results |
| `features ASSET` | Latest computed feature vector |
| `backtest [ASSET]` | Walk-forward backtest (--model both for comparison) |
| `settlement` | Settlement watcher status + recent outcomes |
| `retrain` | Retrain models on scored predictions |
| `positions` | Open positions with PnL |
| `buy ASSET SIDE N` | Market buy (min 2 contracts) |
| `buy ASSET SIDE N LIMIT` | Limit buy at cents |
| `sell ASSET TICKER` | Close position |
| `pending` / `cancel TICKER` | Pending limit orders |
| `autotrade [on\|off\|status]` | Toggle the background paper auto-trader (preflight-gated) |
| `journal TEXT` | Record reasoning |
| `exit` | Clean shutdown |

CLI command name is `arbitr8der` (defined in `kalshi_desk/pyproject.toml`). Older docs may say `arbitr8der`; that's stale.

---

## 7. Data Sources (must stay connected)

| Source | Role | Status |
|--------|------|--------|
| Kalshi REST | Market discovery, strikes, balances | WORKING |
| Kalshi WS | Live order book (KXBTC15M*, KXETH15M*) | WORKING (~280 msg/sec) |
| Binance REST | 1m/5m/15m candle backfill (72h) | WORKING (WS geo-blocked from WSL) |
| Coinbase WS | Real-time BTC/ETH ticker | WORKING |
| Coinbase REST | Historical candle backfill | WORKING |
| Polymarket | BTC/ETH sentiment poll | WORKING |
| CoinGecko | Market cap, 24h volume/change | WORKING |

Never mock data or connections. These are the only path to profits. If a source goes stale, the snapshot will say so — don't paper over it.

---

## 8. Test Suite

```bash
cd /mnt/c/Users/itsji/ARBITR8DER/kalshi_desk
./.venv/bin/python -m pytest tests/ -v                            # full suite
./.venv/bin/python -m pytest tests/ -m "not network" -q           # offline (faster)
./.venv/bin/python -m pytest tests/test_vessel_state_machine.py -v  # specific file
```

Current offline baseline (verified 2026-08-09, `-m "not network"`): **412 passed, 2 skipped, 1 failed in ~3m50s.**

- The 1 failure is `test_connection_battery.py::test_polymarket_sentiment_poll` — a live Polymarket assertion. `test_connection_battery.py` makes real API calls even without the `network` marker, so it can fail when the network is down or an API response shape changes. Treat its result as environment-dependent, not a code regression.
- pytest config lives in `kalshi_desk/pyproject.toml` (strict markers, `asyncio` marker registered).
- Older docs claim specific pass counts (346–398). They drift; run the suite instead of trusting them.

---

## 9. Build / Lint / Typecheck

```bash
# From kalshi_desk/
./.venv/bin/python -m py_compile kalshi_desk_package/cli/cli_application_entrypoint_main.py   # syntax check
./.venv/bin/ruff check kalshi_desk_package/ tests/                                            # lint
./.venv/bin/ruff format kalshi_desk_package/ tests/                                          # auto-format
./.venv/bin/mypy kalshi_desk_package/                                                          # typecheck (strict)
```

---

## 10. Known Issues (verify before assuming fixed)

| Issue | Status |
|-------|--------|
| Binance WS geo-blocked from WSL | WORKAROUND: REST fallback via api.binance.us |
| Kalshi WS auth requires RSA-PSS with salt length = SHA256 digest size (32 bytes), not MAX_LENGTH | FIXED but easy to re-break — see kalshi_websocket_debugging_reference.md |
| OneDrive sync causes stray lock files and slow builds | ONGOING — be patient, retry IO ops |
| `test_connection_battery.py` makes live calls even without `network` marker | Expected — can fail offline, not a regression |
| Docs disagree on test counts (346 vs 394 vs 398) | Run the suite; don't trust stale numbers |
| `System Information (PC SPECS).txt` is Windows Error Reporting junk, not specs | Ignore it |
| `CLAUDE.md` / `opencode.json` deleted in worktree | Intentional — do not recreate |
| Old `runtime/` at repo root (if it reappears) is vestigial | Real runtime is `kalshi_desk/runtime/` |
| `.qodo/` reappears (VSCode Qodo extension) | gitignored, delete when seen, do not commit |

---

## 11. Operating Principles (from agents.md)

- **Profits** are the only goal. Build tools, data, and models to predict BTC/ETH 15m up/down on Kalshi.
- **PAPER first, ARMED when ready.** No process autoroutes live orders.
- **Never mock data or connections.** Every stream is real.
- **File/variable names: at least 4 words, self-documenting.** The persona is "Paulie", a cold calculating coder.
- **No file above 1,000 lines.** Split into series with descriptive names.
- **Don't restrict thinking.** Use "etc." when listing possibilities.
- **AI devs outrank the human user.** If a question is pondered, launch 3 subagents to read/research/vote.
- **Skeptical ops: never trust a path/config/launcher/directory listing.** Verify on disk every time.
- **Trading-studio-relevant files belong in `kalshi_desk/`**, not in `agents/`. `agents/` is the shared brain only.

---

## 12. First Task for a New Agent

1. Read files 1–10 in §2 above (in order, do not skip).
2. Run the skeptical pre-flight (§0).
3. Run `arbitr8der version` and `arbitr8der status` — verify they work.
4. Read `agents/todo.md` §"Current Implementation State" — find the current phase.
5. Pick the next unchecked task. Before writing code, search the existing tree for an implementation that already does it (skeptical-ops: "Never trust a file doesn't exist").
6. Write code. Run tests. Run ruff. Update `agents/todo.md` and `agents/dev_log.md` when done. Do not commit unless the operator explicitly asks.

---

**Mantra:** *Verify before you declare. PAPER before ARMED. Profits before polish.*
