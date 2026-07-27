# ARBITR8DER Onboarding Workflow

**Audience:** Any AI agent (Claude, OpenCode, Codex, Gemini, Kilo, Antigravity, etc.) or human opening this repo for the first time.
**Purpose:** A single, accurate, on-disk-verified map of the repo and the order to read it in. Use this instead of trusting path references in older docs — those may lie.

---

## 0. Skeptical Pre-Flight (do this every session)

```bash
pwd
git remote -v          # must show github.com/itsjimjimsalabim/ARBITR8DER.git
git status --short
ls -la                 # confirm layout matches §1 below
```

If any of those fail or surprise you, fix the environment before touching code. Prior agents lie about paths. OneDrive sync, deleted folders, and stale configs are common. Verify, don't trust.

---

## 1. Repo Layout (verified 2026-07-24)

```
ARBITR8DER/                                  <- repo root, canonical home
├── .env                                     <- SINGLE source of truth for env vars
├── .env.example                             <- tracked placeholder, points to .env
├── .gitignore                               <- repo-level ignore rules
├── .mcp.json                                <- MCP server config (GitHub)
├── CLAUDE.md                                <- startup pointer for Claude-family agents
├── README.md                                <- short repo overview
├── opencode.json                            <- OpenCode project config (permission: allow)
├── pyproject.toml                           <- STALE placeholder (real one in trading_studio/)
├── requirements.txt                         <- STALE placeholder
├── requirements-dev.txt                     <- STALE placeholder
├── agents/                                  <- SHARED BRAIN for all AI agents
│   ├── agents.md                            <- SINGLE source of truth for AI ops
│   ├── onboarding_workflow.md               <- THIS FILE
│   ├── todo.md                              <- current backlog
│   ├── dev_log.md                           <- development log
│   ├── Product_Requirements_&_Theories_of_Operations.md
│   ├── overwatch_workflow.md                <- AI trading-session playbook
│   ├── github_connectivity.md               <- git/gh/SSH notes
│   ├── kalshi_websocket_debugging_reference.md
│   ├── prediction_system_plan.md
│   ├── trading_studio_build_plan.md
│   ├── qwen_local_model_ops_guide.md        <- local Ollama/Qwen runtime guide + machine inventory
│   ├── System Information (PC SPECS).txt    <- verified hardware inventory for this laptop
│   ├── KEYS                                 <- gitignored local key notes
│   ├── _archive/                            <- historical reference only
│   │   └── 2026-07-23-root-cleanup/
│   ├── agent_benchmark_tests_&_performance_dynamometers/
│   ├── browser_access/
│   ├── claude/  codex/  gemini/  kilo/  openclaude/  opencode/  <- per-agent desks
├── trading_studio/                          <- the actual software
│   ├── pyproject.toml                       <- REAL project metadata + deps
│   ├── readme.md                            <- studio directory map
│   ├── .env.example                         <- tracked template, points to root .env
│   ├── arbitr8der_package/                  <- installable package (import name)
│   │   ├── cli/   config/   data_contracts/   data_sources/
│   │   ├── durable_storage/   execution/   prediction/
│   │   ├── reconciliation/   risk/   vessel/
│   ├── scripts/                             <- scratch/debug/utility scripts
│   │   └── fetch_real_balance.py
│   ├── streams/                             <- Kalshi private key (gitignored, NOT committed)
│   │   └── kalshi_private.pem
│   ├── tests/                               <- pytest suite
│   └── runtime/                             <- local data (gitignored): DBs, state, logs, archives
│       └── .gitignore                       <- runtime-local ignore rules
├── UI/                                      <- standalone scoreboard app (future)
└── runtime/                                  <- VESTIGIAL empty root runtime (scheduled for removal)
```

**Stale placeholders** (`pyproject.toml`, `requirements*.txt` at root): kept only so old launchers don't crash. Real project is `trading_studio/pyproject.toml`. Install with `pip install -e ./trading_studio`.

---

## 2. Read Order (do this before any architecture decision)

Read in this exact order. Each file is short and assumes the previous:

| # | File | Why |
|---|------|-----|
| 1 | `agents/agents.md` | Operating principles, vessel states, build/test commands. Treat as primary directive. |
| 2 | `agents/Product_Requirements_&_Theories_of_Operations.md` | What we are building and why. Vision, strategies, technical standards. |
| 3 | `agents/todo.md` | Current backlog and phase status. Tells you what's done vs next. |
| 4 | `agents/dev_log.md` | What has been built, what broke, what was fixed. Real history. |
| 5 | `agents/overwatch_workflow.md` | How to actually run a trading session in the REPL. Commands, timing, journaling. |
| 6 | `agents/github_connectivity.md` | How to push/pull/PR. HTTPS via `gh` is the working path. |
| 7 | `agents/onboarding_workflow.md` | You're here. |
| 8 | `trading_studio/readme.md` | "You are here" map of the package. |
| 9 | `trading_studio/pyproject.toml` | Real dependencies, CLI entry point (`arb`), ruff/pytest config. |

Optional, when relevant:
- `agents/prediction_system_plan.md` — design notes for Phase 8 prediction work.
- `agents/kalshi_websocket_debugging_reference.md` — Kalshi WS auth gotchas.
- `agents/qwen_local_model_ops_guide.md` — local Ollama/Qwen model roles, progress checks, and machine inventory.
- `agents/System Information (PC SPECS).txt` — hardware reference for CPU/RAM/disk sizing and model choice.
- `agents/_archive/2026-07-23-root-cleanup/` — historical only, not operating instructions.

---

## 3. Install + Verify

```bash
cd /mnt/c/Users/itsji/ARBITR8DER
pip install -e ./trading_studio            # installs the `arb` CLI + all deps
pip install -e "./trading_studio[dev]"     # adds pytest, ruff, mypy
arb version                                # must print "arbitr8der 0.1.0"
```

If `pip install -e .` fails with `ModuleNotFoundError`, run `pip install setuptools` first, then retry. (Known gotcha, see agents.md.)

---

## 4. Configuration — One `.env`

There is exactly **one** `.env` file: `ARBITR8DER/.env` (repo root). It is gitignored.

`trading_studio/.env` is **not** used anymore. The `TradingStudioSettings` pydantic model loads the root `.env` by absolute path (resolved from the package location), so the same env works regardless of CWD or OS.

Required keys in `.env`:

```ini
# --- OpenCode / OpenAI (Claude-family CLI routing) ---
OPENCODE_API_KEY=...
OPENAI_API_KEY=...                         # same value as OPENCODE_API_KEY
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

# --- Safety ---
AR8_AUTO_ARM=false
AR8_DRY_RUN=true
```

Copy `.env.example` → `.env` and fill in real values. Kalshi private key file goes at `trading_studio/streams/kalshi_private.pem` and is gitignored. Never paste real keys into tracked files.

---

## 5. Vessel States (the killswitch model)

| State | Streams | Trading | When to use |
|-------|---------|---------|-------------|
| `Full_Stop` | OFF | NO | Default. Every new process starts here. |
| `Battery` | ON | NO | Data soak. Read snapshot, journal notes, detect opportunities. |
| `Full_Forward` | ON | YES (PAPER or ARMED) | The killswitch. AI trades via explicit `buy`/`sell` REPL commands. |

The vessel state itself is the permission to trade. No automated loop fires trades. The AI is the trader; the code only executes the AI's intent with risk guards.

Transitions:
```bash
arb vessel status      # current state
arb vessel battery     # Full_Stop or Full_Forward -> Battery
arb vessel forward     # -> Battery -> Full_Forward (PAPER first)
arb vessel stop        # -> Full_Stop (safe shutdown)
```

---

## 6. Run a Session

```bash
# 1. Verify environment
arb status
arb snapshot

# 2. Move to trading state (PAPER by default)
arb vessel forward

# 3. Enter the interactive trading REPL
arb forward start
# Then in the REPL:
#   snapshot        — full HotSnapshot as JSON
#   opportunities   — tradeable entries with edge estimates
#   predict         — focused BTC/ETH prediction
#   accuracy        — model scoring results (all models or per-model)
#   features        — latest computed feature vector for an asset
#   positions       — open positions with PnL
#   buy BTC YES 3   — market buy, min 2 contracts
#   buy BTC NO 2 15 — limit buy at 15 cents
#   sell BTC KXBTC15M-...  — close a position
#   pending         — show pending limit orders
#   cancel TICKER   — cancel pending limit
#   journal "..."   — record reasoning
#   exit            — clean shutdown
```

CLI command name is `arb` (defined in `trading_studio/pyproject.toml`). Older docs may say `arbitr8der`; that's stale.

---

## 7. Data Sources (must stay connected)

| Source | Role | Status (2026-07-23) |
|--------|------|---------------------|
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
cd /mnt/c/Users/itsji/ARBITR8DER/trading_studio
python -m pytest tests/ -v                            # full suite (346 passed, 2 network-fail, 1 skipped)
python -m pytest tests/test_connection_battery.py -v -s   # live integration (network)
python -m pytest tests/test_vessel_state_machine.py -v     # specific file
```

Tests live in `trading_studio/tests/`. pytest config is in `trading_studio/pyproject.toml`. Tests tagged `network` make real API calls — skip with `-m "not network"` if offline.

---

## 9. Build / Lint / Typecheck

```bash
# From trading_studio/
python -m py_compile arbitr8der_package/cli/cli_application_entrypoint_main.py   # syntax check
ruff check arbitr8der_package/ tests/                                            # lint
ruff format arbitr8der_package/ tests/                                          # auto-format
mypy arbitr8der_package/                                                          # typecheck (strict)
```

---

## 10. Known Issues (verify before assuming fixed)

| Issue | Status |
|-------|--------|
| Binance WS geo-blocked from WSL | WORKAROUND: REST fallback via api.binance.us |
| Kalshi WS auth requires RSA-PSS with salt length = SHA256 digest size (32 bytes), not MAX_LENGTH | FIXED but easy to re-break |
| OneDrive sync causes stray lock files and slow builds | ONGOING — be patient, retry IO ops |
| Two repos on this machine (ARBITR8DER + deleted openclaude) | Always `pwd` + `git remote -v` first |
| `.qodo/` reappears (VSCode Qodo extension) | gitignored, delete when seen, do not commit |
| Old `runtime/` at repo root is vestigial and empty | Real runtime is `trading_studio/runtime/` |

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
- **Trading-studio-relevant files belong in `trading_studio/`**, not in `agents/`. `agents/` is the shared brain only.

---

## 12. First Task for a New Agent

1. Read files 1–8 in §2 above (in order, do not skip).
2. Run the skeptical pre-flight (§0).
3. Run `arb version` and `arb status` — verify they work.
4. Read `agents/todo.md` §"Current Implementation State" — find the current phase.
5. Pick the next unchecked task. Before writing code, search the existing tree for an implementation that already does it (skeptical-ops: "Never trust a file doesn't exist").
6. Write code. Run tests. Run ruff. Update `agents/todo.md` and `agents/dev_log.md` when done. Do not commit unless the operator explicitly asks.

---

**Mantra:** *Verify before you declare. PAPER before ARMED. Profits before polish.*
