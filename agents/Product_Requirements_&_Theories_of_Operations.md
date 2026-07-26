# ARBITR8DER — Product Requirements and Theories of Operations

Trading studio to be operated by different AI's until basic bots are developed based on the AI's strategies and datas.

---

## 1. Vision and Strategy

### User input July22nd 2:21PM Trading Strategy Massive Rewrite and Refactoring Ideas:

This project started with a spreadsheet and 2 columns, it's evolved over different repos, accounts, machines, environments. It will never be finished or shipped. These softwares are for me, and YOU the AI reading this now.

We've gotten complicated as you've taught me how to use computers and internet.

I'm ready to realign to the basics.

The two columns spreadsheet track BTC price every 15 minutes.
I wanted to build a model so we could guess up or down every 15 minutes, but then I drifted from the clear easy goal.

We need an ever-smarter, ever-more-accurate pricing model.

Our AI's should be able to examine the models easily and clearly, then confidentally predict the asset's future movement for that 15 minutes, then place trades.

Eventually automated bots only after the AI's have figured out the patterns using the software processes and datas and logs etc.

This trading studio is our ARBITR8DER\ the vessel the AI's fly (operate)

I want new trading studio codes from scratch again i'm saying it now 07/22/2026
I want old folders erased.
I want this folder layout:

ARBITR8DER\
  - agents\ (Central mind folder shared by all the AI's for coding, all supporting docs)
  - trading_studio (software AI's use to Operate as Prediction Market traders)

I don't want supporting docs in the trading studio anymore, i want them in agents\, readmes in trading studio folders to act as "you are here" directory maps with the current folder it's in expanded to full list.

The agents\ exists because a single agents.md is not going to be strong enough to maintain context over months and billions of tokens.

these two main folders are what i want in the repo, They can share an .env in the ARBITR8DER\ root, and there can be a .dependencies or .pycache if needed.

trading studio has its own data set, agents\ database is for memories, reviews, todos

Database I am most focused on. It has to be modular, dynamic, smart. Longterm datas, and even Live microsecond datas, persistent 24/7 slow background data collectors (15 min price gatherer), all the way to white-hot near zero latency processes (the scripts or codes an ai executes to buy or sell). What datas would a AI prediction market trader need available as they place their buys/sells

Kalshi of course has the most datas we need.
Polymarket we've underutilized the amount of helpful datas we could be easily for free be pulling or viewing.
the other 3 streams will be different prices than what kalshi and polymarket show, but the gathering all of theser datas, especially overtime will reveal hidden patterns that we can find and use to our strategies.
If our trading studio database gets too big we can gigignore up to the last week of trading data or something or develop a smarter archiving system

This trading studio should run headless except for the CLI that is operating it, unless we can run a onboarded headless AI process and have a way to keep track of what it's doing because the TUI's do take processing power.

---

## 2. Systems

### 2.1 Kalshi — Main Connection and Data Source

We have all the know-how in using our Kalshi wallet, finding specific series, executing buys of Yes's+No's, and selling those contracts

Kalshi is the main datas and main execution. Only BTC and ETH 15-minute yes/no markets (KXBTC15M*, KXETH15M*), no other assets for now. We need the active tickers found before the run and around each rollover, then live orderbook snapshot + deltas staying in sequence.

Private Kalshi order/fill stream is for ARMED/PAPER physics and reconciliation, not a replacement for checking orders, positions, and balances.

### 2.2 Auxiliary Streams — Polymarket, Coingecko, Binance, Coinbase

(let me know if there are other free fast trackers we can utilize)

Polymarket
Coingecko
Binance
Coinbase

Binance + Coinbase are the fast spot price/check streams. We use both so we can see movement, spread, and if they disagree.

Polymarket is a slower probability/sentiment overlay, it does not mirror the Kalshi 15min markets and cannot make a Kalshi trade valid.

Coingecko is slow bigger-picture data like volume/marketcap/longer changes. Context only, never an entry/exit trigger.

All aux streams have to say when their datas are old/broken. None of them can cover for a broken Kalshi book.

(Why limit what each stream does? Reevaluate if we are being too specific and restricting)

---

## 3. Data

PostrgeSQL
We need to keep track of so much, all the data incoming from the streams for the applicable markets/assets/series needs to be seen by the ai's to make those descisions, it's gotta be as low latency as possible, we will figure out how to do this better over time

Use machine RAM for the live hot datas, then SQLite for the history/audit/replays. Do not make the streams wait for database writes. The AI reads one complete local hot snapshot with timestamps, data ages, Kalshi book health, and a version number so it knows exactly what it saw. Database writer is separate and the 72HR deep datas get archived after it is safely written.

Zero latency is not real, so we log it: provider time -> recieved time -> hot snapshot -> AI read -> order intent -> Kalshi response/fill. This tells us what is actually slow instead of guessing.

---

## 4. Trading Strategies

One AI at a time to perform trades thru respective CLI app (Codex, OpenCode, antigravity, anyone else)

Main idea is an AI we can talk to that sees the same fresh datas and can make/adjust its strategy during one run, not old hardcoded bots trying to do everything forever. AI gets read-only datas commands and has to record the snapshot/version it saw before it does anything. Trading commands stay separate and ARMED stays hard blocked unless explicitly armed.

They each have to keep a trading log, a journal of what they saw, what they thought was going to happen and why, versus what actually happened and why, and their next strategy tweaks

Only BTC and ETH on the Kalshi 15min markets (KXBTC15M*, KXETH15M*)

Examine prices, examine past prices if applicable, use technical analysis if applicable and if it's fast enough

The systems will have to evolve, we will figure out how to do this better over time.

trading frequency: aiming for at least 3 buys/sells per 15 minute run, eventually will be trading higher frequency

Minimum 2 contracts per order enforced in all entry paths. Kalshi fees at 50¢ are
~1.75¢ per contract per leg (entry + exit = ~3.5¢ round trip). On 1 contract, fees
eat the entire edge. At 2+ contracts, fees are amortized and small edges become viable.

---

## 5. Operations

### 5.1 Vessel States

Full_Stop - no processes, all streams off, no data in motion. The ground state.

Battery - data collection only. Streams connect, hot state fills, any running database is populated with observations. Opportunities are detected and logged so any AI that reads them can see what edges existed. NO TRADING in Battery — no evaluation that could fire a buy, no risk manager gating entries, no execution engine loaded. Battery is a pure soak mode: the AI reads the data, makes notes, and waits for Full_Forward to act.

Full_Forward - THE KILLSWITCH. The vessel state being Full_Forward is itself the permission for an AI to trade. When an AI launches `arbitr8der forward start`, it enters an interactive session where it — not the code — decides every buy and sell. The AI reads live HotSnapshot data, evaluates edges, and issues explicit commands:
  `buy ETH YES 3` — execute a buy with AI-chosen parameters
  `sell ETH KXETH15M-...` — close a specific position
  `snapshot` — read the complete current market state as JSON
  `opportunities` — see what edges exist across the active universe
  `journal <text>` — log reasoning so future AIs see the thought process

No automated tick loop evaluates or fires trades. The code does not decide. It only executes the AI's expressed intent, with latency simulation, price-drift checks, fee accounting, and journaling as guardrails. The AI is the trader. Full_Forward is the state that makes that legal.

### 5.2 PAPER Wallet and ARMED Wallet

ARMED Wallet is real money, actual kalshi portfolio balance, and cash balance, held positions, realized/unrealized

- System uses real money

PAPER Wallet is theoretical trading, paper trading, fake money, no risk

- Real connections for real data
- every new paper run starts with the actual balance value pulled from the kalshi connection, but the wallet balances are paper, only at the start, because we only have like $17 dollars, so our paper strategies have to work with such little money
- Paper Physics have to be exactly like ARMED physics: latencies have to logged and applied - paper strategies have to be the same once ARMED is run so that there is no confusion or surprises
- Live Physics have to be learned to be as accurate as possible for Paper runs

### 5.3 Scoreboard

Do not work on UI until this trading studio is first built for AI's to operate and read datas and interact with. UI is lowest priority and not to be made until at least one live trade is performed, this will be a standalone app within the trading studio, so the trading studio doesn't evolve around a UI, only speed and AI usability

Pretty much we need to find out what who, what and where is doing profitable/non-profitable when, why and how

This scoreboard lives in `ARBITR8DER/UI/` as a standalone local webpage. It is a passive display — no trading controls, no data writes. It reads from the runtime data and renders: market state, wallet, open positions, opportunity log, trade journal, connection health, error log. All information is selectable/copyable by clicking for pasting into an AI CLI. The `main-region` is the primary data display area; the inspector panel holds the never-ending goal text; the nav bar switches between views. No mock data — empty regions until real data is wired.

### 5.4 Limit Orders

Support for limit orders via `buy ASSET SIDE N LIMIT_CENTS`. When the limit price
is below the current market ask, a `PendingLimitOrder` is placed in the inventory
(in-memory, session-scoped). On every `snapshot()` call, pending orders are checked:
if the market ask has dropped to or below the limit price, the order fills automatically
(balance deducted, position created). The AI can check pending orders with the `pending`
REPL command.

Kalshi real limit orders use `POST /portfolio/events/orders` with `side: "bid"` for
buying YES, `price: "0.1500"` format, and `client_order_id` for deduplication. Our
PAPER system mirrors this flow. ARMED mode will call the real endpoint.

Minimum 2 contracts per order enforced (fees make single-contract trades unprofitable).

### 5.5 REPL Command Reference

| Command | Description |
|---|---|
| `monitor` | Start background health tick display |
| `snapshot` | Dump live market data (order books, spot, wallet as JSON) |
| `opportunities` | Show detected trade opportunities with edge estimates |
| `positions` | Show current open positions with PnL |
| `buy ASSET SIDE N` | Buy at market: `buy ETH YES 3` or `buy BTC NO 5` |
| `buy ASSET SIDE N LIMIT` | Buy with limit order in cents: `buy ETH NO 3 15` |
| `sell ASSET TICKER` | Close position: `sell ETH KXETH15M-...` |
| `pending` | Show pending limit orders waiting to fill |
| `journal TEXT` | Append AI reasoning to the trading journal |
| `help` | Print command reference |
| `exit` | Shut down the session |

---

## 6. Technical Standards

### 6.1 Variable Naming

Use many worded variables specific to what they do, like have the variable explain itself so other AI's know what systems it works for

No abbreviated variables unless neccesary, i don't know how to code so don't fully listen to me, if our kalshi wallet makes money we get more AI power

Applied 2026-07-17: all 27 source modules renamed with longer, self-documenting names
(e.g. `execution_engine.py` → `trade_execution_and_inventory_engine.py`). Follow suit
for any new files. A filename should tell an AI what the module is for without opening it.

### 6.2 Hyper Modularity

We want this vessel built into systems, we want all the data yes, but streams but have individual and/or grouped test in the test suite

AI models or CLI-tools have to have their own folders for documentation and journal archives

Database has to be flexible for different operators, ARMED/PAPER wallets and datas and trades, database has to be useful for the AI-devs and operators to see and use, we need a 72HR archiving system where the logs and data go deeper so AI's don't accidentally read data from so long ago when they are doing small tweak, but we still need that data for deeperdives in analysises

No files above 1,000 lines, they can be in series, file names like variable names should be long, include any systems, and self-explanatory for AIs who may not have full context

### 6.3 Testing

User likes tests for the tests

Debugging manuals

Logs for everything, even logs for how much processing power or internet the logs are using

Sensors have to watch CPU, ram, queues, disk, internet bytes, connection/reconnects, stream ages, and timing thru the whole run. They have to be light: read counters and sample every few seconds, no speed tests or extra internet calls during a run, and never slow the datas or trades to measure them. If the database is busy the normal sensor samples drop/coalesce first, not the real market/order/audit stuff.

### 6.4 Speed

We want to be fast, we want to be fast

### 6.5 Redundancies

We don't need redundancies but with vibecoding they seem to appear under multiple names and systems, these trading studios always accidentally have like 3 killswitches. Regularly inspect for where we bug ourselves.

### 6.6 Computer Languages and Tools

I really don't care, python, json

download whatever we need just be smart with the dependencies not being uploaded to the github repo

Local and for only us to use, this is not a product to ship, it's software we will be able to use on any laptop if the github repo is cloned from another machine it should work on that if it has the Kalshi API keys

### 6.7 Historical Price Data

Current gap: zero historical data. The AI sees only the current HotSnapshot with zero context
about whether BTC/ETH is trending up, down, or ranging.

Strategy: Build a `price_history` table in SQLite that stores 1-minute OHLCV candles for
BTC and ETH from Binance. On session start, backfill any missing candles up to 72 hours.
Then calculate:

- P(up) = probability that close > open 15 minutes later over last N windows
- P(down) = 1 - P(up)
- Edge = historical_P(up) - market_YES_price (in cents)
- If |edge| > threshold (e.g. 10c), flag as tradeable opportunity

This gives the AI a data-driven prior. Over time, we tune the window size, threshold,
and weighting (recent candles weighted higher).

Requirements to enable this (see TODOs):
1. Binance REST klines endpoint (already have Binance client, need REST helper)
2. SQLite migration for `price_history` table
3. Backfill job on session start
4. Probability calculation in detect_opportunities()

---

## 7. Infrastructure

### 7.1 Repo Organization — Two Main Folders

The fresh restart uses two main repo folders:

| Path | Purpose |
|------|---------|
| `agents\` | Shared brain for all AI operators and coders: requirements, todo, dev log, keys notes, agent desks, workstation context |
| `trading_studio\` | The actual headless/CLI software AI operators use to collect data, predict, paper trade, journal, and eventually trade |

Supporting docs belong in `agents\`, not in `trading_studio\`. Folders inside
`trading_studio\` may have short README files only as "you are here" directory maps.

Nothing trading-studio-relevant should be written to AppData, Temp, `.config`, or old agent
directories without being mirrored or documented under `ARBITR8DER\`.

### 7.2 Moved from AppData (2026-07-21)

The following scripts were orphaned in `AppData\Local\Temp\opencode\` and have been
moved to `scripts/`:

- `auto_trader.py` — automated trading bot (launches session, scans, trades, monitors)
- `manual_archive.py` — manual DB-to-JSON archiver
- `check_active.py` / `check_active2.py` — Kalshi REST market queries
- `check_all_markets.py` / `check_markets.py` / `check_markets2.py` / `check_markets3.py` / `check_markets4.py` — market listing variants
- `check_streams.py` — DB stream value inspector
- `check_strikes.py` — strike price checker
- `check_trades.py` — trade journal inspector
- `check_db.py` / `check_db2.py` — DB table inspectors

The launcher `start-opencode.ps1` was in `.config\opencode\` and has been moved to
`scripts/` as well.

### 7.3 Rule for Future Sessions

No file written by any session should land outside `C:\Users\itsji\ARBITR8DER\`.
If an agent or tool writes to its own cache/config directory, the trading-studio-relevant
files must be copied or symlinked into the repo. The repo is the source of truth.

---

## 8. Workstation and Tooling

### 8.1 Machine

- Machine: ZEN-LAPTOP
- OS: Windows 11 plus WSL2 Ubuntu 24.04.4
- CPU/RAM: AMD Ryzen AI 9 465, 32 GB RAM
- Primary repo: `C:\Users\itsji\ARBITR8DER`
- Canonical shared agent folder: `C:\Users\itsji\ARBITR8DER\agents`

### 8.2 Active AI Coding Agents

| Tool | Status | Windows | WSL | Purpose |
|---|---|---|---|---|
| OpenCode | Active | `C:\Users\itsji\.bun\bin\opencode.exe` | `~/.opencode/bin/opencode` | Primary coding agent |
| OpenClaude | Active | `C:\Users\itsji\.openclaude\dist\cli.mjs` | `~/bin/claude` wrapper | Claude-compatible coding agent |
| Kilo | Active | N/A | `~/.kilo/bin/kilo` | OpenCode-family agent |
| Copilot CLI | Active | GitHub CLI install | N/A | GitHub terminal assistant |
| Codex | Active | `C:\Users\itsji\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe` | `~/.local/bin/codex` | OpenAI Codex CLI |

OpenClaude is the expected coding executor for the fresh rebuild. Codex may act as the
planning/review brain and keep `agents/todo.md` aligned.

### 8.3 Runtime and Development Tools

| Tool | Windows | WSL | Purpose |
|---|---|---|---|
| Node.js/npm | Installed | nvm | OpenClaude/OpenCode support |
| Bun | Installed | Installed | Fast JS runtime and builds |
| Python | Python 3.12 | Python 3.12 | ARBITR8DER trading studio |
| Git | Installed | Installed | Version control |
| GitHub CLI | Installed | Not guaranteed | HTTPS auth, PRs, issues |
| PowerShell | Built in | N/A | Windows automation |
| tmux/vim/nano/curl/wget/make/gcc | N/A | Installed | WSL development support |

WSL quality-of-life tools still worth installing or verifying: `ruff`, `uv`, `jq`,
`ripgrep`, `fd`, `fzf`, `bat`, `htop`, `tree`, and `gh`.

### 8.4 Secrets and Config Rules

- `agents/KEYS` is the local ignored key store for sensitive values and notes.
- Full API tokens, private keys, and wallet secrets must never be pasted into tracked docs.
- `.env` at `ARBITR8DER\` is shared by `agents\` and `trading_studio\` when needed.
- OpenCode/OpenClaude launcher scripts must load keys from ignored storage or environment
  variables, not embed keys in plaintext.

### 8.5 Known Workstation Gotchas

- HTTPS through authenticated `gh` is the practical GitHub default; SSH currently has a
  fingerprint mismatch unless a matching key is found or a new key is added.
- Old docs may reference `runtime_cli.py`, `docs/`, `agents/claude/`, or deleted
  `C:\Users\itsji\openclaude` paths. Verify every path before using it.
- OneDrive Desktop redirection may still affect shortcuts even when OneDrive appears removed.
- Global and app-managed AI config directories may exist outside the repo. Trading-studio
  relevant configs should be documented here or mirrored under `agents\`, while secrets stay
  out of tracked files.

---

## 9. AI CLI Agents and Session History

The AI CLIs are not side tools. They are part of the operating floor for ARBITR8DER. They
need their own desks, build guides, session-history pointers, and recovery notes so a future
agent can inspect what earlier agents tried without bloating this product requirements file.

### 9.1 Agent Desk Index

| CLI | Desk | Primary guide |
|---|---|---|
| OpenCode | `agents\opencode\` | `agents\opencode\howtobuildOpenCode.md` |
| OpenClaude | `agents\openclaude\` | `agents\openclaude\howtobuildopenclaude.md` and `agents\openclaude\howtobuildOpenClaudeCode.md` |
| Codex | `agents\codex\` | `agents\codex\README.md` and `agents\codex\AWAKENING.md` |
| Gemini CLI | `agents\gemini\` | TODO: add Gemini CLI build/recovery guide |

Keep detailed rebuild steps in the desk guide files. Product requirements should only explain
where to look and what role each CLI plays.

### 9.2 Session History How-To: Codex

Codex local storage is under:

```text
C:\Users\itsji\.codex\
```

Known useful files:

| Path | Purpose |
|---|---|
| `.codex\sessions\YYYY\MM\DD\rollout-*.jsonl` | Per-session event history; this is the main recoverable transcript source |
| `.codex\state_5.sqlite` | Thread index and metadata, including rollout path, title, cwd, model, token use, first user message |
| `.codex\history.jsonl` | Prompt/input history |
| `.codex\session_index.jsonl` | Small index of named older sessions |
| `.codex\logs_2.sqlite` | Internal/runtime logs, not the clean chat transcript source |

Safe inspection commands:

```powershell
Get-ChildItem -Recurse -File C:\Users\itsji\.codex\sessions |
  Select-Object Name,Length,LastWriteTime

Get-Content C:\Users\itsji\.codex\history.jsonl -Tail 20
```

For SQLite metadata, inspect schema/table counts before reading contents. Do not dump secrets
or large raw transcripts into tracked docs.

### 9.3 Session History How-To: OpenCode

OpenCode stores chat/session history in a single SQLite database per OS. See
`agents\opencode\session-history\README.md` for the latest paths and symlink/mirroring notes.

Known paths from prior audits:

| OS | Path |
|---|---|
| Windows | `C:\Users\itsji\.local\share\opencode\opencode.db` |
| WSL/Ubuntu | `/home/itsjimjimsalabim/.local/share/opencode/opencode.db` |

Do not move or delete these databases unless the operator explicitly wants to lose or reset
OpenCode session history. If pointers or mirrors are needed under `agents\opencode\`, use
gitignored links/copies and document the source path.

### 9.4 Session History How-To: OpenClaude

TODO: document exact OpenClaude session-history storage locations after verification.

Known places to inspect first:

- `C:\Users\itsji\.openclaude\`
- `C:\Users\itsji\.openclaude\projects\`
- `agents\openclaude\session-history\`
- `agents\openclaude\scattered-files-manifest.md`

### 9.5 Session History How-To: Gemini CLI

TODO: document exact Gemini CLI session-history storage locations after verification.

Known places to inspect first:

- `agents\gemini\`
- User home config/cache folders with names containing `gemini`

---

## 10. Troubleshooting Tips

This section evolves over time. Add new findings here as they are discovered during development and operations.

### PAPER vs ARMED Parity

PAPER currently simulates fill latency (random 60-100ms) instead of sharing the real Kalshi
fill path. The AI agent flow (read snapshot → decide → `buy` command → execute) introduces
its own latency which is visible and measurable. The gap to close: replace synthetic latency
with the real Kalshi order lifecycle so PAPER physics match ARMED exactly.

Current known gaps:
- Fill latency is synthetic (60-100ms random) rather than real Kalshi REST round-trip
- Settlement-based exits mean the AI never sees real limit-order fills — paper physics for
  limit orders are untested
- The "$17 real balance" matters: paper starts from live Kalshi balance pull, sizing is
  constrained to that tiny float

If adjustments are needed, make them in the shared physics path (ExecutionEngine /
price_models / RiskManager), not as paper-only hacks, so ARMED inherits the same model.

### Data Source Integration Status

- Coinbase, Polymarket, and Coingecko clients exist in code but are DEAD CODE — not started
  by the connection manager, events never reach HotState or the database.
- Hot snapshot currently only carries Kalshi + Binance. Must carry all 5 sources.
- The latency trace (provider time → received time → hot snapshot → AI read → order intent →
  Kalshi response/fill) is incomplete — the PAPER fill leg is simulated, not measured.

### General Debugging

- Always run `pwd` and `git remote -v` before assuming which repo you are in (two repos on this machine).
- Verify file paths exist before trusting them — configs and prior agents lie about locations.
- `dist/` may not exist — always check before assuming a build was completed.
- The REPL blocks on input() and exits on EOFError when stdin is consumed. No way to insert
  delays between piped commands. Need a --script FILE mode or a non-interactive command queue.
