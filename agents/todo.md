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

---

## Vibecoding Audit & Cleanup (2026-07-24) ← CURRENT

We built a lot vibecoding. We now have to audit, review, and clean. Goals: stop the env/runtime/tooling bugs that come from duplicate and stale paths, get the repo into a single sane shape so the next AI's onboarding is deterministic.

### Done today
- [x] Audit on-disk state to verify every path (found: stale `agents/agents.md` Directory Layout, stale `overwatch_workflow.md`/`github_connectivity.md` pointers, two `.env` files, two `runtime/` dirs, `.qodo/` junk directory, `trading_studio/.venv/` polluting path lookups)
- [x] Write `agents/onboarding_workflow.md` — fresh, accurate, on-disk-verified read order and layout. Supersedes the archived 2026-07-21 version.
- [x] Restore `agents/overwatch_workflow.md` and `agents/github_connectivity.md` from `agents/_archive/2026-07-23-root-cleanup/` so all doc references resolve
- [x] Consolidate `.env`: removed `trading_studio/.env`; single source of truth is `ARBITR8DER/.env` at repo root
- [x] `trading_studio/.env.example` reduced to a pointer comment that directs operators to `ARBITR8DER/.env`
- [x] `TradingStudioSettings` (`typed_configuration_settings_module.py`) now resolves `.env` by absolute path from package location, not CWD
- [x] Remove `.qodo/` directory; gitignore it
- [x] Remove vestigial empty `runtime/` at repo root; gitignore it so it never comes back
- [x] Update root `.gitignore` to cover: root `runtime/`, `.qodo/`, VSCode-like extension junk
- [x] Fix `agents/agents.md` Directory Layout (was listing `src/`, `scripts/`, `config/`, `tests/`, `runtime/` at the repo root — they live under `trading_studio/`)
- [x] Fix `README.md` and `CLAUDE.md` references (overwatch_workflow / github_connectivity now resolve)
- [x] `arb version` + `arb status` smoke test after rewiring
- [x] Append today's dev_log.md entry

### Audit backlog (next agent picks these up)
- [ ] Sweep every file in `agents/` for stale path references (openclaude/opencode/codex/gemini/kilo desks)
- [ ] Audit `agents/opencode/prompts_windows.md` and `prompts_ubuntu.md` — known to contain old `docs/onboarding_workflow.md` and `C:\Users\...\ARBITR8DER\overwatch_workflow.md` paths
- [ ] Audit `agents/codex/AWAKENING.md` — references `docs/overwatch_workflow.md`
- [ ] Audit root stale placeholders (`pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.env.example`) — decide: delete vs keep with pointer comment (current: kept as pointers)
- [ ] Sweep `trading_studio/arbitr8der_package/` for any hardcoded `.env` paths other than the settings module
- [ ] Move `agents/openclaude/launchers/.mcp.json` and `agents/openclaude/launchers/.venv/` — launchers/ should be launcher scripts only, not tooling state
- [ ] Audit `trading_studio/scripts/` content for stale or duplicate utilities
- [ ] Audit `trading_studio/runtime/.gitignore` vs root `.gitignore` — ensure no contradictions
- [ ] Consider: should `trading_studio/runtime/` move to `ARBITR8DER/runtime/` so multiple agents/studios can share? Out of scope for now, log as future question.

### Process discipline going forward
- **Never trust a path from docs.** Verify on disk with `ls`, `cat`, `test -e`.
- **Never trust "it was working before."** Present state is all that matters.
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

## Phase 8: Prediction System ← CURRENT

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

### Short-term
- [ ] Push local commits to GitHub — GitHub push protection blocks PAT in old commit ac2e110 (agents/KEYS). Either unblock via the GitHub secret-scanning URL, or rebase to remove the PAT from history. KEYS is now gitignored and PAT redacted locally.
- [ ] Kalshi WebSocket prediction feed integration
- [ ] Connect Binance WS from WSL (currently geo-blocked; REST fallback works)
- [x] Auto-trading: place paper orders when edge exceeds threshold

### Medium-term (Phase 9+)
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
| 8 | Prediction System | IN PROGRESS (8a-8i done, 8j next) |
| 9 | ARMED Transition | PENDING |

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
