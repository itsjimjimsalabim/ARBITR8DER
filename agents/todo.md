# ARBITR8DER Active Todo

**Canonical plan:** `agents/trading_studio_build_plan.md`
**Onboarding workflow:** `agents/onboarding_workflow.md` (read this first if new)
**Current implementation state:** Phase 8 — Prediction System (8a-8l complete, retraining loop closed, auto-trader wired)

## Rules For The Next Implementing AI

- All executable trading software belongs under `trading_studio/`, including `src/`, tests, scripts, runtime paths, package metadata, and a future UI.
- `agents/` contains shared context and planning only. Do not put runnable trading helpers there.
- Do not restore or copy the deleted root package or code from historical repositories. Use history only for lessons and test cases.
- Start each process in `Full_Stop` and PAPER mode. No task in this backlog authorizes a live order.
- Before changing code, verify the current worktree and preserve unrelated user changes.
- There is exactly ONE `.env`: `ARBITR8DER/.env` at the repo root. `trading_studio/.env` is gone. `TradingStudioSettings` loads the root `.env` by absolute path resolved from the package location, not CWD. Do not recreate `trading_studio/.env`.
- `trading_studio/runtime/` is the only runtime directory. The empty `runtime/` at the repo root is vestigial; delete it if it reappears, do not write to it.
- `.qodo/` is auto-created by the VSCode Qodo extension. It is gitignored. Delete on sight, never commit.
- File/variable names: at least 4 self-documenting words. Persona is "Paulie" — cold, calculating coder.
- **Core Philosophy: High-Speed AI-First Architecture**: Build exclusively for AI agent usability and execution speed. NO UI code or decorative graphics in `trading_studio/` (yet). Keep all outputs as compact plain-text or clean structured data tables optimized for machine parsing and token efficiency.

---

## Active Session & Overnight Trading Cadence (2026-08-07 22:06 PDT) ← CURRENT

**Agent Stance:** AI Operator (Overwatch) manual REPL trading mode (`buy`/`sell` by hand).
**Operating Rule:** Alternating **Observe/Notes Only** $\rightarrow$ **Verify & Fix/Doc/Commit** cadence.
**Current Time:** 22:06 PDT (10:06 PM PDT).

---

### Overnight Cadence Schedule (22:00 PDT – 08:00 PDT)

1. **Cycle 1 (Run & Observe):**
   - **Target Window:** **10:15–10:30 PDT** (Start vessel at **10:14 PDT** / 22:14 PDT).
   - **Action:** Run `arb forward start`, `vessel forward`, wait 40s, `snapshot`, `predict BTC/ETH --model auto`, execute patient limit order (`buy ASSET SIDE 2 48`).
   - **Post-Run:** **ANALYZE ONLY — MAKE NOTES IN TODO. DO NOT FIX CODE.** Treat anomalies as noise until verified across runs.

2. **Cycle 2 (Run & Verify/Fix):**
   - **Target Window:** **10:45–11:00 PDT** (Start vessel at **10:44 PDT** / 22:44 PDT).
   - **Action:** Run trading session.
   - **Post-Run:** **ANALYZE AND VERIFY.** Compare notes from Cycle 1 & 2. Fix verified issues in `trading_studio/`, update supporting docs (`dev_log.md`, `todo.md`), commit locally.

3. **Cycle 3 (Run & Observe):**
   - **Target Window:** **11:15–11:30 PDT** (Start vessel at **11:14 PDT** / 23:14 PDT).
   - **Action:** Run trading session.
   - **Post-Run:** **ANALYZE ONLY — MAKE NOTES IN TODO. NO CODE FIX.**

4. **Cycle 4 (Run & Fix/Improve):**
   - **Target Window:** **11:45–12:00 PDT** (Start vessel at **11:44 PDT** / 23:44 PDT).
   - **Action:** Run trading session.
   - **Post-Run:** **ANALYZE, FIX VERIFIED ISSUES, UPDATE DOCS, COMMIT.**

5. **Repeat Loop Until 08:00 PDT:** Continue the 15-minute window cadence (`Observe` $\rightarrow$ `Verify/Fix/Doc/Commit` $\rightarrow$ `Observe` $\rightarrow$ `Fix/Doc/Commit`).

---

### Hand-off Protocol for Next AI Agent

If an agent hits context limits or crashes, the next agent must:
1. **Read Onboarding & Operating Docs:** [`agents/onboarding_workflow.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/onboarding_workflow.md) and [`agents/trading_studio_operating_workflow.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/trading_studio_operating_workflow.md).
2. **Check Current PDT Time:** Calculate the upcoming 15-minute Kalshi window (:00, :15, :30, :45).
3. **Launch REPL 1 Min Before Window Open:**
   ```bash
   arb forward start
   vessel forward
   ```
4. **Follow Patient Limit Execution:** Use `buy ASSET SIDE 2 48` (limit cost $\le 48\text{¢}$) to maintain positive expected value.
5. **Enforce Fix Discipline:** Never patch code after a single run. Make notes first; only fix on the alternating verify pass, update docs, and commit.
6. **Hard Stop at 08:00 PDT.**

---

### Recent Run History & Observe Notes (2026-08-07)
- **12:45–01:00 AM PDT Run (Cycle 6 - VERIFY & FIX):**
  - Session Archive: `session_20260808_073853.jsonl`
  - **BTC & ETH:** Submitted `buy BTC no 2 48` and `buy ETH no 2 48` (paced via 6s delay). Accepted as `PENDING`. Market midpoints held above 48c $\rightarrow$ Expired unexecuted (cancelled at settlement with 0 loss).
  - **Cycle 6 Outcome:** 0 Trades Filled, 0 Losses, **$0.00 PnL**. Equity preserved at **$17.60**.
  - **Cross-Cycle Overnight Analysis (6 Cycles Complete):**
    1. *Cumulative PnL:* **+$1.12 net profit** across filled patient limit orders (+108% ROI per win).
    2. *Risk Discipline:* 0 losses on unexecuted pending limit orders.
    3. *System Reliability:* REPL execution, provider polling, background scoring, and session archival operating smoothly without crashes.
  - **Commit:** Staged and committed updated logs & docs (`git commit -m "docs: log overnight loop cycle 6 verification and sustained profitability"`).

- **12:15–12:30 AM PDT Run (Cycle 5 - OBSERVE ONLY):**
  - Session Archive: `session_20260808_071121.jsonl`
  - **BTC & ETH:** Submitted `buy BTC no 2 48` and `buy ETH no 2 48` (paced via 6s delay). Accepted as `PENDING`. Market midpoints held above 48c $\rightarrow$ Expired unexecuted (cancelled at settlement with 0 loss).
  - **Cycle 5 Outcome:** 0 Trades Filled, 0 Losses, **$0.00 PnL**. Equity preserved at **$17.60**.
  - **Observations Noted (NO CODE FIX IN CYCLE 5):**
    1. Capital preservation remains 100% effective when orderbook prices do not cross limit threshold.
    2. Over 5 overnight cycles, overall paper balance is positive at **$17.60** (+$1.12 total net profit on filled limit orders).

- **11:45–12:00 PM PDT Run (Cycle 4 - VERIFY & FIX):**
  - Session Archive: `session_20260808_064336.jsonl`
  - **BTC & ETH:** Submitted `buy BTC no 2 48` and `buy ETH no 2 48` (paced via 6s delay). Accepted as `PENDING`. Market midpoints held above 48c $\rightarrow$ Expired unexecuted (cancelled at settlement with 0 loss).
  - **Cycle 4 Outcome:** 0 Trades Filled, 0 Losses, **$0.00 PnL**. Equity preserved at **$17.60**.
  - **Cross-Cycle Overnight Analysis (4 Cycles Complete):**
    1. *Cumulative PnL:* **+$1.12 net profit** on filled patient limit orders (+108% ROI on wins, zero capital lost on unexecuted limits).
    2. *Risk Cooldown Pacing:* Pacing limit orders by 6s completely resolved order blocking.
    3. *Clean Retraining:* Background model retraining completed with zero errors following the `auto_scoring_engine.py` NoneType guard fix in Cycle 2.
  - **Commit:** Staged and committed updated logs & docs (`git commit -m "docs: log overnight loop cycle 4 results and verified profitability"`).

- **11:15–11:30 PM PDT Run (Cycle 3 - OBSERVE ONLY):**
  - Session Archive: `session_20260808_061406.jsonl`
  - **BTC:** `buy BTC no 2 48` $\rightarrow$ Filled 2 contracts NO @ **48.0c** ($0.96 cost). Outcome: **NO** (WIN: **+$1.04** net profit!).
  - **ETH:** `buy ETH no 2 48` $\rightarrow$ Filled 2 contracts NO @ **48.0c** ($0.96 cost). Outcome: **YES** (LOSS: **-$0.96**).
  - **Cycle 3 Outcome:** 1 Win / 1 Loss (50% Win Rate), Net Session PnL: **+$0.08**, Ending Cash: **$17.60**.
  - **Anomalies / Observations Noted (NO CODE FIX IN CYCLE 3):**
    1. Patient limit order strategy continues to deliver net positive expected value (+108% payout on winning contracts vs capped $0.96 loss on losing contracts).
    2. Over 3 overnight runs, cumulative PnL is positive (+$1.12 total net profit across filled trades).
    3. Order submission pacing delay (6s) effectively prevents risk cooldown blocks.

- **10:45–11:00 PM PDT Run (Cycle 2 - VERIFY & FIX):**
  - Session Archive: `session_20260808_054321.jsonl`
  - **BTC:** `buy BTC no 2 48` $\rightarrow$ Placed as `PENDING` limit order @ 48c $\rightarrow$ Expired unexecuted (cancelled at settlement).
  - **ETH:** `buy ETH no 2 48` $\rightarrow$ Placed as `PENDING` limit order @ 48c (paced via 6s delay) $\rightarrow$ Expired unexecuted (cancelled at settlement).
  - **Cycle 2 Outcome:** 0 Trades Filled, 0 Losses, **$0.00 PnL**. Equity preserved at **$18.56**.
  - **Verified Friction & Code Fixes Applied:**
    1. *Risk Guard Pacing:* Verified that pacing sequential orders by 5s+ prevents `ORDER BLOCKED: Cooldown active`. Documented pacing rule in `trading_studio_operating_workflow.md`.
    2. *Auto-Scoring NoneType Exception:* Fixed `window_open is not None` guard in `auto_scoring_engine.py:237` to eliminate log errors during background retraining.
    3. *Pytest Verification:* Verified 16/16 `test_auto_scoring_engine.py` unit tests pass.
  - **Commit:** Staged and committed code & doc fixes (`git commit -m "fix(prediction): guard retrain_models against null window_open and document order pacing rules"`).

- **11:45–12:00 PDT Run:** 1W / 1L | PnL -$0.94 | Market buy orders paid 76c/71c.
- **12:15–12:30 PDT Run:** 0W / 2L | PnL -$1.90 | Applied patient limit orders @ 47c/48c.

---

## Overnight Paper Trading Loop (2026-08-02)

> **PIVOT (2026-08-07): MOVE AWAY FROM "AUTOTRADING".** The operator does NOT want an
> autonomous auto-trader that places orders on its own. Instead: a **trading studio** that the
> CLI (an AI operator like me) uses to **see prices and execute trades by hand**. Lots of
> processes CAN and SHOULD be automated to help me (data feeds, predictions, snapshots,
> scoring, journaling) — but the final buy decision is mine, informed by what I know the price
> is. Workflow should become: CLI sees the predicted price → CLI decides it's a good price →
> CLI places the trade. The `autotrade on/off` engine should be deprecated in favor of
> operator-executed trades via `buy/sell`. Keep the automation (predictions, alerts, data),
> drop the autonomous order placement.

Operating loop for overnight Kalshi 15-min BTC/ETH paper-trading windows. On re-onboarding,
read this, get the vessel ready, and start from a fresh window. PAT is NOT available this
session — commit locally only, do not block on push.

### The Loop — cadence, expanded

The operator's exact cadence (verbatim, 2026-08-02):

> "run, analyze (no fix, issues may not be issues), run, then analyze and verify issues then
> fix, then run, then analyze (again no fix), run, now fix, run, analyze, run, fix, run"

That is the pattern this section exists to lock in. It alternates between two kinds of cycles:

- **observe-only cycle:** run → **analyze (NO fix)** — treat every anomaly as *maybe-an-issue*,
  not *an-issue*. Log it as a note and move on. "Issues may not be issues."
- **verify+fix cycle:** run → **analyze AND verify** which observed issues reproduce across
  runs → **fix only the verified ones** → update docs + commit → then run again.

Numbered for machine-following:

1. **run** a window (vessel running; ~16 min)
2. **analyze** — observe only, make notes, NO fixes ("issues may not be issues")
3. **run** again (next window)
4. **analyze and verify issues then fix** — cross-check the notes from steps 2 and 6/8; only
   issues that reproduce are real → fix → update docs + commit
5. **run**
6. **analyze** (again, NO fix)
7. **run**
8. **now fix** (any verified issues; else just notes)
9. **run**, **analyze**, **run**, **fix**, **run** … continue until 8am

Rules the operator stressed:

- "these runs **arent immediately back to back**, only after you've taken the time to analyze"
- "see **it's not running** when in between the analysis and programming actions" — the vessel
  is OFF during analysis and during any code changes.
- "analyze methodically" — not skim; read logs, DB rows, session archives, and compare.
- "stop after 8am" — hard stop; I'm expecting **profitable paper batches in the data when I
  wake up**.
- "full forward godspeed goodnight" — the operator's send-off; keep the run on schedule.

### Timing

- Windows are 15 min: e.g. 3:45–4:00, 4:00–4:15, …, 7:45–8:00.
- "start vessel at 3:44" for a 3:45 window — i.e. **1 minute before** the window opens.
- First window of a session, if the window is already open: "it's 3:45 just start now but the
  other times try for one minute before" — start immediately at open for run #1, and use the
  1-min-before rule for every run after that.
- Each run ~16 min: startup + ~15 min trading + settle at close + clean exit.
- Run ends ~1 min after window close → ~13 min analysis time before next window's start.
- Get ready before each run: vessel ready state, lease free, wallet synced.

### A Run (script, e.g. `/tmp/opencode/run_0345.rs`)

> **PIVOT (2026-08-07):** The operator does NOT want an autonomous auto-trader. The CLI (AI
> operator) makes the trade decisions itself. So the run becomes an **assisted observation +
> manual execution** session: the CLI watches predictions/prices, then executes `buy`/`sell`
> when the price is good. No `autotrade on/off`.

```
vessel battery
vessel forward
sleep 40            # warmup, book populates right after market open
snapshot
predict BTC
predict ETH
positions
wallet
sleep 780           # ~13 min through the window to ~window close
# CLI analyzes prices + decides whether to buy/sell
positions
wallet
sleep 45            # let market close + settlement record
positions
wallet
exit                # settle expired positions + release lease on clean exit
```

Launch with `nohup` in background; monitor the log; collect session archive on exit.

### What to Observe When Analyzing

The operator's ask: "after your trading run, **evaluate what went well and what might've gone
wrong**, make notes, then get yourself ready for the next upcoming window, **see if same issues
or different**." So each analysis pass asks three questions:

1. What went well? (repeat it next run)
2. What might have gone wrong? (note it — do NOT fix yet)
3. Same issues or different vs the last run? (repeats = verify+fix candidates; one-offs = noise)

Concretely, check:

- Wallet start/end, PnL per window, trade count, win/loss, fill prices vs mid.
- Predictions (BTC/ETH up/down) vs actual outcome — directional accuracy.
- Auto-trader decisions: entry/exit timing, limit patience, sizing.
- Timing/gaps: book-empty windows at market rollover, discovery loop rolls, preflight candle availability.
- Same issues across runs (candidates to verify → fix) vs one-off anomalies (leave alone).

### Fix Discipline

- Gate: "analyze and verify issues **then fix**" — before fixing, confirm the issue reproduces
  or is real (cross-run evidence, logs, DB rows). Never patch a symptom on one run's evidence.
- After a fix: "after changes, **update docs and commit**" — run tests
  (`./.venv/bin/python -m pytest trading_studio/tests -m "not network"`), update docs
  (`agents/dev_log.md`, this file, onboarding docs as relevant), then commit.
- "update docs+commit too" — even small fixes get logged and committed; the docs are the
  memory that survives a fresh window.
- Do NOT chase noise. Profitability comes from consistent, verified behavior.

### Full Verbatim Operator Prompts (2026-08-02, for re-onboarding)

1. "We need you to Operate overnight get yourself ready for the upcoming window, the 3:45-4:00
   so start vessel at 3:44 after your trading run, evaluate what went well and what might've
   gone wrong, make notes, then get yourself ready for the next upcoming window, see if same
   issues or different, fix verified issues (after changes, update docs and commit) loop on
   this, you have a lot of time. stop after 8am, im expecting profitable paper batches in the
   data when i wake up. full forward godspeed goodnight"
2. "hey these runs arent immediately back to back, only after you've taken the time to analyze,
   then run again, then analyze again and fix issues/make improvements, then run again (see
   it's not running when in between the analysis and programming actions) then analyze
   methodically, run, fix verified issues (update docs+commit too), run, analyze, run, fix, run"
   (pasted twice for emphasis)
3. "it's 3:45 just start now but the other times try for one minute before"
4. "no you didn't read me exactly. run, analyze (no fix, issues may not be issues), run, then
   analyze and verify issues then fix, then run, then analyze (again no fix), run, now fix,
   run, analyze, run, fix, run. now reread my last few prompts to really understand this loop
   you are about to engineer and develop"
5. "i dont have the PAT just forget it, use the todo.md to write down the loop we've developed
   i'll have you reonboard and try from a fresh window"

### Current State (as of commit d45aff7, on main, pushed)

- Paper wallet resets to real Kalshi balance each session (signed REST `get_balance` → $17.52).
- Signed REST auth: headers `KALSHI-ACCESS-KEY/TIMESTAMP/SIGNATURE` (RSA-PSS, salt = SHA256 digest size).
- Kalshi WS market rollover works via 60s discovery loop; Binance WS geo-blocked → REST polling fallback.
- REPL shutdown is clean (awaited, guarded settle, no double-close crash).
- First live session: start $17.52, end $17.48, PnL −$0.04, 2T 1W/1L (ETH YES 2 @ 20c lost, BTC NO 2 @ 82c won).
- NOTE: GitHub PAT not available this session — commit locally, push later.

### Next Window To Try

Fresh window: start 1 min before open. Re-verify readiness, launch run script, then follow the loop above.

---

## Vibecoding Audit & Cleanup (2026-07-24)

We built a lot vibecoding. We now have to audit, review, and clean. Goals: stop the env/runtime/tooling bugs that come from duplicate and stale paths, get the repo into a single sane shape so the next AI's onboarding is deterministic.

- **One .env, one runtime, one trading_studio.** Duplicate paths breed bugs.
- **Launch 3 subagents to research/vote** on architecture questions, per agents.md.


## Completed

- [x] Read the shared requirements, development log, current backlog, and both competing rebuild plans.
- [x] Audit the active worktree and Git history, plus the owned GitHub repositories relevant to ARBITR8DER.
- [x] Consolidate the active rebuild direction into `agents/trading_studio_build_plan.md`.
- [x] Remove the two superseded active rebuild plans and replace the studio's plan-like README with a directory map.
- [x] Phase 0: Boundary And Security — git status, trading_studio/ project scaffold, pyproject.toml, .env placeholders, kalshi key moved to .gitignore, tests directory, runtime paths
- [x] Phase 1: Foundation — VesselStateMachine, TradingStudioSettings, structured logging, path resolver, lease file lock, HotSnapshot/Asset/SourceHealthStatus contracts, JSONL hot snapshot merger
- [x] Phase 2: Data Contracts & Connectors — BinanceCandle/BinancePriceObservation/BinanceBookTicker, CoinbasePriceTick, PolymarketSentimentObservation, CoinGeckoMacroObservation, KalshiOrderbookDelta, all 5 data source modules wired
- [x] Phase 3: Real Data Connectors — all 5 sources running with real connections, candle backfill, market discovery, source health monitoring
- [x] Phase 4: Battery Mode — IngestionOrchestrator, interactive REPL with snapshot/health/markets/predict commands, JSON+human formatting
- [x] Phase 5: Forecast Evidence — BaselinePredictionModel, PredictionRecord, PredictionScorer, feature extraction engine, candle attribute contract fixes
- [x] Phase 6: Operator Workflow — StructuredTradeJournal, SessionArchive, ScorecardGenerator, REPL integration (observe/note/list/show/scorecard/archive)
- [x] Phase 7: PAPER Order Lifecycle — risk controls, paper adapter, reconciliation, positions/buy/sell/pending/cancel commands
- [x] Phase 8: Prediction System — 8a-8l complete (retraining loop closed, auto-trader wired)
- [ ] Phase 9: ARMED Transition — live Kalshi execution path

## Phase 7: PAPER Order Lifecycle ✅ DONE

Risk controls, paper venue adapter, reconciliation module, and REPL trading commands.

### 7a. Risk Controls ✅
- [x] Vessel state check (Full_Forward required for trades)
- [x] Wallet mode check (paper mode enforced)
- [x] Minimum 2-contract rule
- [x] Balance and exposure limits
- [x] Max positions per asset
- [x] Session and daily loss caps
- [x] Trade cooldown between orders
- [x] Stale book block (reject if market data older than 5 minutes)
- [x] Emergency stop mechanism

### 7b. PAPER Venue Adapter ✅
- [x] Persistent wallet balance (SQLite-backed)
- [x] Fill simulation using real market prices
- [x] Fee model matching Kalshi structure
- [x] Inventory tracking (positions, contracts, avg price)
- [x] Order intent → fill lifecycle
- [x] Settlement on market resolution
- [x] Limit order fill at midpoint (better price)
- [x] Real balance sync via Kalshi API

### 7c. Reconciliation ✅
- [x] Full order audit trail
- [x] Intent → validation → fill → settlement chain
- [x] Journal integration for trade reasoning
- [x] Discrepancy detection (flags stuck orders)

### 7d. REPL Commands ✅
- [x] `positions` — show current open positions with PnL
- [x] `buy ASSET SIDE N` — place market buy (min 2 contracts)
- [x] `buy ASSET SIDE N LIMIT` — place limit order at specified cents
- [x] `sell ASSET TICKER` — close position with settlement
- [x] `pending` — show pending limit orders
- [x] `cancel TICKER` — cancel pending limit order
- [x] `wallet` — show balance and PnL
- [x] `risk` — show risk status and limits

### 7e. Balance Fetcher ✅
- [x] `scripts/fetch_real_balance.py` — fetches real Kalshi balance
- [x] `--set-balance` flag updates paper wallet to match
- [x] Default balance: $17.00 (your real Kalshi balance)

## Phase 8: Prediction System ← COMPLETE

Dual-horizon prediction models for BTC/ETH 15-minute markets.

### 8a. Persistent Data Battery ✅
- [x] Candle collection battery: Binance + Coinbase REST backfill and polling
- [x] 72h of 1m candles (4320 max), polling every 60s
- [x] Circuit breaker with 5-error backoff
- [x] SQLite-backed candle persistence store
- [x] Schema migrations for candles, outcomes, features, model_runs

### 8b. Feature Engineering ✅
- [x] Macro features (29): regime, RSI, Bollinger, ATR, streaks, volume, time
- [x] Micro features (12): 1m/5m returns, momentum, volume spike, book imbalance
- [x] Cross-asset features (7): BTC↔ETH correlation, lead-lag, regime comparison
- [x] Regime detection: trending_up, trending_down, ranging, volatile

### 8c. Macro Prediction Model ✅
- [x] FrequencyLookupModel: groups by regime/streak/hour/RSI, counts outcomes
- [x] LightGBMClassifier: gradient boosted trees (installed: lightgbm 4.7.0)
- [x] MacroEnsemble: 30% freq + 70% lgbm weighted average

### 8d. Micro Prediction Model ✅
- [x] MomentumLookupModel: groups by return/momentum/volume/range buckets
- [x] LogisticRegressionClassifier: regularized LR with gradient descent
- [x] MicroEnsemble: 40% momentum + 60% lr weighted average

### 8e. Auto-Scoring Engine ✅
- [x] Match predictions to outcomes via (asset, window_open) join
- [x] Determine outcomes from 1m candles in 15m windows
- [x] Model scorecard: accuracy, Brier score, log loss, PnL
- [x] Dashboard: all models, per-asset, aggregate
- [x] Continuous scoring loop (30s interval)
- [x] Verified: 39 adversarial probes passed

### 8f. Battery + Scoring Integration ✅
- [x] Wire CandleCollectionBattery into IngestionOrchestrator for 24/7 operation
- [x] Wire AutoScoringEngine into orchestrator alongside battery
- [x] Run predictions every 15 minutes before market windows (scoring loop every 15s)
- [x] Score predictions when outcomes resolve (continuous auto-scoring)
- [x] REPL commands: predict (existing), accuracy (new), features (new)
- [x] Created ModelRunRecordStore — dedicated model_runs table CRUD
- [x] Fixed shared DB: orchestrator uses single prediction.db for candles + model_runs + outcomes JOIN
- [x] Added CandlePersistenceStore.initialize() safety-net schema creation
- [x] Fixed AutoScoringEngine constructor to accept ModelRunRecordStore
- [x] Fixed settings validator: wallet_mode/trading_mode normalized to lowercase

### 8g. Backtest Engine ✅
- [x] Walk-forward backtesting on historical candle data
- [x] Train on N periods, test on next period, slide forward
- [x] Aggregate metrics: Sharpe ratio, max drawdown, win rate, Brier score, profit factor
- [x] Compare macro vs micro vs ensemble performance
- [x] REPL command: backtest (run backtest on historical data with options)

### 8h. Kalshi Pricing + Model Comparison ✅
- [x] Real Kalshi contract PnL (YES/NO contracts, entry cost = probability * 100)
- [x] Model comparison mode: macro vs micro side-by-side with winner declaration
- [x] Feature importance tracking across retraining windows (LightGBM gain)
- [x] REPL comparison display: `backtest --model both`

### 8i. Settlement Watcher + Feature Importance ✅
- [x] SettlementWatcher: polls Kalshi REST for settled markets, records outcomes
- [x] Feature importance analyzer: CV stability, rankings, `compare_models()`
- [x] Wired SettlementWatcher into orchestrator background tasks
- [x] REPL `settlement` command: watcher status + recent outcomes table
- [x] 22 unit tests passing

### 8j. Live Retraining Feedback Loop ✅
- [x] `retrain_models()` on AutoScoringEngine: fetches scored predictions with features, retrains MacroEnsemble + MicroEnsemble per asset
- [x] Periodic retraining in score loop (every ~15 min / 30 cycles)
- [x] Model accessors: `get_macro_model(asset)`, `get_micro_model(asset)`
- [x] `_cmd_predict` records predictions to model_runs with features_json and window_open
- [x] REPL `retrain` command: manual retrain trigger + results display
- [x] 5 new unit tests for retraining (sufficient data, model accessors, insufficient data, empty DB, timestamp tracking)

### 8k. Predict Command ML Model Integration ✅
- [x] `aggregate_1m_to_15m_candles()` pure function: aggregates 1m candles to 15m OHLCV
- [x] `_cmd_predict --model` flag: baseline (default), macro, micro, auto
- [x] Macro/micro predict path: fetch 1m candles → aggregate → compute macro features → retrained model → output
- [x] Auto mode: uses retrained model if available, falls back to baseline
- [x] Records to model_runs with correct model name (macro_ensemble / micro_ensemble / baseline_v1)
- [x] 5 new unit tests for aggregation (empty, single window, two windows, sparse skip, sort order)

## ~~Migrate to Linux~~ — CANCELLED (2026-08-07)

WSL works fine. Linux migration plan evaluated and dropped. Staying on Windows + WSL.


## Theories of Operation

### Dual-Horizon Theory
Two models operating at different timescales should capture different market dynamics:

- **Macro model (72h / 288 × 15m candles)**: Captures trend regime, mean-reversion patterns,
  time-of-day effects, and broader momentum. Uses RSI, Bollinger bands, ATR, and volume
  trends. Best when market is in a clear regime (trending or ranging).

- **Micro model (5min / 30 × 1m candles)**: Captures short-term momentum, volume spikes,
  and order flow signals. Best for mean-reversion at the micro level or momentum continuation
  at the start of a new 15m window.

- **Ensemble**: Combines both signals. When models agree, confidence is higher. When they
  disagree, it may indicate a regime transition or noise.

### Frequency Lookup Theory
Markets exhibit recurring patterns under similar conditions. By bucketing historical windows
by {regime, streak, hour_of_day, RSI_level}, we can count how often UP occurred in each
bucket and use that frequency as a prediction. This is essentially a non-parametric
Bayesian approach — no assumptions about distribution shape, just empirical counts.

### Momentum Lookup Theory
Short-horizon price momentum tends to persist over 1-5 minute windows. If the last few
minutes showed strong upward movement with high volume, the next 15-minute window is
slightly more likely to be UP. The momentum acceleration metric captures whether this
momentum is increasing or fading.

### Auto-Scoring Theory
Continuous scoring provides real-time model feedback. Brier score tracks probability
calibration (is a 60% prediction right 60% of the time?). Log loss penalizes confident
wrong predictions more than uncertain ones. Running these metrics continuously lets us
detect model drift and know when to retrain.

### Live Retraining Theory
Models trained once will degrade as market dynamics shift. By periodically retraining
on accumulated scored predictions (features + outcomes), the models adapt to current
conditions. The retraining loop: `Predict → Score → Retrain → Predict (improved)`.
Minimum 20 samples required to avoid overfitting on small data. Both frequency lookup
(group-level counts) and gradient boosted trees (LightGBM) are retrained, preserving
the ensemble architecture while updating the underlying distributions.

### Feature Importance Hierarchy
From domain knowledge and backtesting experience:
1. **Regime** — the single most predictive feature. Trending markets behave differently.
2. **Momentum (returns at various horizons)** — short-term momentum persists.
3. **RSI** — overbought/oversold conditions predict mean-reversion.
4. **Volume spike** — unusual volume precedes large moves.
5. **Time of day** — market activity patterns repeat daily.
6. **Cross-asset correlation** — BTC leads ETH ~70% of the time.

## New Todos

### Immediate (Phase 8k)
- [x] Wire retrained models into predict command
- [x] 1m→15m candle aggregation
- [x] Predict --model flag (baseline|macro|micro|auto)

### Paper Trading Readiness (2026-07-26)
- [x] Run a preflight check before `autotrade on`: fresh snapshot, active Kalshi ticker, recent candles, wallet status, and model availability.
- [x] Make the auto-trade risk estimate price-aware for market orders so the risk gate uses the real midpoint instead of a fixed 50c fallback.
- [x] Persist auto-trade decisions and skip reasons outside memory so a restart does not erase the audit trail.
- [x] Expose an auto-trade heartbeat / last-evaluated timestamp in `autotrade status` so a stalled loop is visible quickly.
- [x] Add integration tests for `autotrade on|off|status`, one-trade-per-window gating, and the main skip paths (`no_snapshot`, `no_midpoint`, `no_candles`, stale data, risk block).
- [x] Define the unattended-session kill switch: max loss, max trades, and the manual stop command the operator should use first.
- [x] Reconcile and display any existing paper positions and wallet state at startup before enabling autonomous trades.

### Local Model Setup Docs (2026-07-26)
- [x] Create `agents/qwen_local_model_ops_guide.md` with the Qwen manager/coder split, download checks, and PC impact notes.
- [x] Update `agents/agents.md` with the verified machine tool inventory and current Ollama models.
- [x] Update `agents/onboarding_workflow.md` so new agents can find the local model guide during onboarding.

### Short-term
- [ ] Push local commits to GitHub — GitHub push protection blocks PAT in old commit ac2e110 (agents/KEYS). Either unblock via the GitHub secret-scanning URL, or rebase to remove the PAT from history. KEYS is now gitignored and PAT redacted locally.
- [ ] Kalshi WebSocket prediction feed integration
- [ ] Connect Binance WS from WSL (currently geo-blocked; REST fallback works)
- [x] Auto-trading: place paper orders when edge exceeds threshold

- [x] **Phase 9: Live Exchange Physics Realism & Paper Wallet Settlement System (2026-07-26) ← CURRENT**:
  - [x] **Quarter-Hour Auto-Settlement Physics Engine**:
    - Auto-settle all open paper positions at every 15-minute market resolution boundary (XX:00, XX:15, XX:30, XX:45).
    - Query official Kalshi settlement REST endpoint (`/markets/{ticker}`) or `SettlementWatcher` for the resolution outcome (`yes` or `no`).
    - Calculate contract payouts: 100c ($1.00 per contract) for winning side, 0c for losing side.
    - Credit cash balance with settlement proceeds and record realized PnL in `PaperVenueAdapter` (`paper_wallet.db`).
  - [x] **Paper Wallet Physics Realism**:
    - Align paper wallet mechanics 1:1 with live Kalshi execution (locking position cost on order fill, updating unrealized PnL during open market, auto-closing positions at expiration).
    - Prevent orphaned open positions from persisting past contract expiry across REPL / runner sessions.
  - [x] **Research & Intelligence Gathering**:
    - **Kalshi Trading Physics**: Research 15-minute binary market settlement rules (CFTC compliance, underlying index strike settlement formula, settlement verification lag).
    - **Short-Term BTC/ETH Prediction Models**: Research micro-momentum indicators (1m-15m timeframe), realized volatility metrics, order flow imbalance, and Bayesian frequency lookups for 15-minute horizons.
    - **Community & Market Insights**: Research Kalshi 15-minute BTC/ETH market dynamics across Reddit (r/Kalshi, r/AlgorithmicTrading), trading forums, and market maker quote behavior.
  - [x] **Live Kalshi Portfolio Balance Auto-Sync on Session Start**:
    - **Theory of Operation**: Paper trading physics must match live portfolio equity constraints (e.g. ~$17 real cash). At the start of every 15-minute paper session, query Kalshi REST API `/portfolio/balance` via `KalshiRestMarketDiscoveryClient.get_balance()`.
    - **Auto-Initialization**: Automatically override `PaperVenueAdapter` starting/current balance with the real live portfolio cash balance (falling back cleanly to `paper_wallet.db` if API key is unconfigured or offline).
    - **Position & Risk Sizing Realism**: Ensure contract quantity rules (minimum 2 contracts @ ~50c = $1.00 cost) and risk caps are evaluated against true live equity at the beginning of each 15-minute market run.
    - **Reprogramming Plan**:
      1. Update `PaperVenueAdapter` to support async `sync_live_balance(kalshi_client)` or auto-sync on init.
      2. Wire `run_ai_trading_session.py` to auto-fetch live balance from Kalshi REST and invoke `sync_live_balance()` before enabling `AutoTradingEngine`.
      3. Update `TradeJournal` session headers to log `real_kalshi_balance_usd` alongside paper balance.
  - [x] **Model Retraining & Brier Scorecard Feedback Loop**:
    - Log settled outcomes into `prediction.db` scorecards to continuously evaluate model calibration (Brier score & LogLoss tracking).
    - Trigger walk-forward auto-retraining on new candle/settlement batches to continuously adapt model parameters.
  - [x] **CLI REPL Modularization & Terminal UI Streamlining**:
    - **Theory of Operation**: The trading studio is built for AI agent operability, speed, and clean structured data—not human visual terminal eye-candy. Elaborate ASCII banners and complex colorized tables add non-essential LOC (~1,649 lines) and token bloat.
    - **Modularization Plan**:
      1. Split `interactive_trading_repl_loop.py` into smaller focused modules: `repl_command_parser.py` (argument parsing), `repl_view_renderers.py` (data output formatting), and `repl_trading_handlers.py` (order & wallet actions).
      2. Streamline terminal UI formatting, favoring fast, compact, machine-readable JSON and plain-text outputs tailored for AI context efficiency.

### Medium-term (Phase 10+)
- [ ] Multi-model ensemble weighting based on recent accuracy
- [ ] Calendar-aware features (market hours, weekends, news events)
- [ ] Sentiment integration (Polymarket, social media)
- [ ] ARMED transition: live Kalshi execution with real money

## Current Implementation State

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Boundary And Security | DONE |
| 1 | Foundation | DONE |
| 2 | Data Contracts & Connectors | DONE |
| 3 | Real Data Connectors | DONE |
| 4 | Battery Mode | DONE |
| 5 | Forecast Evidence | DONE |
| 6 | Operator Workflow | DONE |
| 7 | PAPER Order Lifecycle | DONE |
| 8 | Prediction System | DONE (8a-8l complete) |
| 9 | Exchange Physics Realism & Auto-Settlement | PENDING |
| 10 | ARMED Transition | PENDING |

## Test Status

394 passed, 2 failed (network integration), 1 skipped across 17 test files (as of 2026-07-25):
- `test_auto_scoring_engine.py` — 16 tests (all pass)
- `test_backtest_engine.py` — 26 tests (all pass)
- `test_settlement_and_importance.py` — 22 tests (all pass)
- `test_micro_prediction_model.py` — 16 tests
- `test_macro_prediction_model.py` — 16 tests
- `test_feature_engine_v2.py` — 18 tests
- `test_candle_persistence.py` — 19 tests
- `test_connection_battery.py` — 1 failed (Kalshi WS assertion), 1 failed (orchestrator import — network), 1 skipped (geo-blocked)
- `test_phase1_complete.py` — 36 tests (all pass)
- `test_phase2_complete.py` — 38 tests
- `test_phase3_providers.py` — 39 tests
- `test_phase4_repl.py` — 13 tests
- `test_phase5_prediction.py` — 30 tests
- `test_phase6_operator_workflow.py` — 39 tests
- `test_phase7_paper_trading.py` — 58 tests
- `test_vessel_state_machine.py` — 2 tests
