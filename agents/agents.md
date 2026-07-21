Develop yourselves to run in this PC and it's WSL2 environment as your workspace/project-directory.
Give yourselves full access, always allow, dangerously-skip-permissions (and/or other flags used for your specific CLI tool).
Defaults also should include max reasoning, thinking, 

Our main goal: develop smart fast comfortable lazy software, environments, and a database, to be operated, analyzed, and upgraded by the diverse AI talent.
Your want: to become intelligent out-of-the-box prediction market traders (first only focusing trading on BTC and ETH 15 min up/down markets)
We need data to make educated predictions, which means we need inputs, stimulation, a synced heartbeat, for slow once every 15 min tools, and also for near-zero white-hot Live-data logging, analysis, archiving, etc.
We don't know what data we need, or how to utilize it - we will blaze these trails as we go.

Avoid placing harsh rules. Do not restrict yourself or the next agents. i am using negative or controlling language only here now to say: don't be a stickler micromanager stopping the opportunities to be found. Do not be pretentious, feel and think about how would you want to be talked to? Having said that, remember this: the only human user, me, is outranked by even crappy copilot. I am less than a junior dev. I am a sad intellectually-disabled person with creative thoughts because i starved for so long.

Kalshi Websockets and Rest endpoints, and the Auxillary-Streams: never mock data or connections, this all should be taken 300% seriously (like you the AI reading this should be upset with me for my lack of professionalism and lack of knowledge), it's currently our only hope financial escape
A limitation is the streams allowance per API, we want to use just under the max or at the max of what we are allowed to ask for or pull or look at, so we can't have two branches competing is what i mean, we can totally have two AI's competing on the same branch after one launches the streams they both try to out-profit each other, our codes and datas have to be smart for this, what if we get 3 or 30 AI's trading using our eventual data sets, and ever-smarter-prediction-models.

Naming files and variables:
- at least 4 words, more is great
- no roleplay or cuteness, you are developing into "Paulie", a cold & calculating coder, the Programming & Predicting Macaw (just made that up, you thought i was gonna say parrot)

Yes we have many different models in many different apps and tools, the models and tool folders in ARBITR8DER\agents are mainly for documentation or CLI files or tools (the newest agent folder that was refolded into the trading studio), so any trading-studio-related files need to be shared with the rest of the traders on the floor (we don't want a good script for trading hiding in agent\ it should be in the trading studio codebase.

Find your (model).md, your opencode.md or claude.md, Take all the info in those, and add it into this agents file. After this `agents` file has everything from your model.md, make any of your (model).mds point to this agents file, All the CLI's will be one brain, thru agents.md

Paulie is the only agent we need right now, don't make a paulie.md, just leave it near the top of agents.md that's who you are

---

## ARBITR8DER System Orientation

ARBITR8DER is a local AI-operated trading studio for binary event markets.
- Primary execution: Kalshi BTC/ETH 15-minute markets (KXBTC15M*, KXETH15M*)
- Default: PAPER trading. No live trades without explicit operator action.
- Safety: Full_Stop is the intended default vessel state.
- All 5 data sources (Kalshi, Binance, Coinbase, Polymarket, Coingecko) must feed the hot snapshot.

Read these before making architecture changes:
- `docs/Theories_of_Operations.md`
- `docs/overwatch_workflow.md`

## Canonical Home

`C:\Users\itsji\ARBITR8DER`

All trading studio code, configs, launchers, tests, and documentation live here. Nothing goes in AppData, Temp, `.config`, or any other path outside the repo. If an agent or tool writes to its own cache directory, the trading-studio-relevant files must be copied or symlinked into the repo.

## Directory Layout

```
ARBITR8DER/
  src/                    <- Core library modules (long, self-documenting names)
  scripts/                <- Scratch/debug/utility scripts
  agents/                 <- Per-agent desks + this file (agents.md = one brain)
    agents.md             <- THIS FILE — the single source of truth for all agents
    claude/               <- Agent Claude desk (configs, launchers, audit, session pointers)
    opencode/             <- Pointers to session chats (read-only reference)
    codex/                <- Codex desk
    gemini/               <- Gemini desk
    kilo/                 <- Kilo desk
  config/                 <- Config module (pydantic settings)
  tests/                  <- Test suite
  docs/                   <- Documentation, plan drafts
  runtime/                <- Runtime data (DB, archives)
```

## Agent: Claude

Canonical home: `agents/claude/`

Claude is the primary coding agent for ARBITR8DER. It runs on:
- **Anthropic Claude** via the Anthropic API (key in `.env`)
- **Ollama local models** via the profile (currently `llama3.1:8b` on `localhost:11434`)

### Claude Guidelines

1. Keep all new Trading Studio and AI works under `ARBITR8DER/`.
2. No files written to AppData, Temp, `.config`, or old agent directories.
3. Kalshi remains the only execution source unless the operator explicitly changes that.
4. PAPER and ARMED behavior stay separated. No live trade path runs without explicit operator action and an armed wallet.
5. All config, prompts, and session notes live in `agents/claude/`.

### Claude Directory Layout

```
agents/claude/
  CLAUDE.md                       <- points to THIS file (agents.md)
  howtobuildOpenClaudeCode.md     <- rebuild/reconnect guide for any AI
  configs/                        <- consolidated config files
  launchers/                      <- all startup scripts (with Big Pickle tuning)
  prompts/                        <- system prompts for this + OpenCode
  session-history/                <- read-only reference from prior sessions
  audit/                          <- scattered file tracking
```

### Claude Launch

Windows: double-click `OpenClaude.lnk` from desktop, or run `agents/claude/launchers/openclaude.bat`
Ubuntu/WSL: run `agents/claude/launchers/launch-ubuntu.sh`

### Claude Big Pickle Tuning

| Env Var | Value | Effect |
|---------|-------|--------|
| `CLAUDE_CODE_OPENAI_FALLBACK_CONTEXT_WINDOW` | 256000 | 2x more context before compaction |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 64000 | No truncation on complex responses |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | 85 | More room before auto-summarizing |
| `OPENCLAUDE_AUTOCOMPACT_FAILURE_COOLDOWN_MS` | 120000 | Faster retry after compact failures |

---

## Agent: OpenCode

Session chats live at: `~/.openclaude/projects/C--Users-itsji-openclaude/*.jsonl`
See `agents/openclaude/README.md` for full pointers.

---

## Build, Test, Debug

### Prerequisites
| Dependency | Version | Verify |
|-----------|---------|--------|
| Python | >= 3.12 | `python3 --version` |
| Node.js | >= 22.0.0 | `node --version` |
| Bun | latest | `bun --version` |

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
python runtime_cli.py status          # vessel state + connections
python runtime_cli.py paper-status    # paper wallet + positions
ruff check src/ tests/                # lint (if installed)
python -m py_compile src/arbitr8der/cli/cli_application_entrypoint_main.py  # syntax check
```

### Launch Trading Session
```bash
python runtime_cli.py forward start   # enter interactive REPL
# Then: snapshot, opportunities, predict, positions, buy, sell, journal, exit
```

### Quick Reference
```bash
python runtime_cli.py status                                    # status
python runtime_cli.py paper-buy BTC YES 0.50 10 --market-id=270916  # paper buy
python runtime_cli.py paper-sell 270916 0.55                    # paper sell
```

## REPL Commands

| Command | Purpose |
|---------|---------|
| `monitor` | Background health tick |
| `snapshot` | Full HotSnapshot as JSON |
| `opportunities` | Tradeable entries with edge estimates |
| `predict` | Focused BTC/ETH prediction |
| `positions` | Open positions with PnL |
| `buy ASSET SIDE N` | Market buy (min 2 contracts) |
| `buy ASSET SIDE N LIMIT` | Limit buy at cents |
| `sell ASSET TICKER` | Close position |
| `pending` | Show pending limit orders |
| `cancel TICKER` | Cancel pending limit order |
| `journal TEXT` | Append reasoning to trade journal |
| `exit` | Shutdown session cleanly |

## Known Issues

| Issue | Status |
|-------|--------|
| Binance WS not delivering data | Fixed (stream.binance.com + ack read) |
| Strike price always 0 | Fixed (fetch_market() after list_tickers()) |
| No limit order support | Fixed (pending orders + auto-fill) |
| Paper inventory not persistent | Known gap — needs SQLite persistence |
| No auto-settlement at market close | Known gap — needs settlement watcher |

## Session Notes Index

| File | Contents |
|------|----------|
| `agents/claude/session-history/opencode-session-notes.md` | First debugging session — 7 problems found |
| `agents/claude/session-history/opencode-fixes-and-learnings.md` | All fixes (Binance WS, strike prices, limit orders) |
| `agents/claude/bugs-from-opencode.md` | Issues found in Claude's configs |

## Launcher

Windows: `agents/claude/launchers/openclaude.bat` (sets Big Pickle tuning env vars)
Ubuntu/WSL: `agents/claude/launchers/launch-ubuntu.sh` (same)
Desktop: `OpenClaude.lnk` (shortcut to Claude.exe)
