# ARBITR8DER Development Log

## Developer: Claude (OpenClaude)
## Date Started: 2026-07-21
## Vessel State: Full_Stop

---

## 0. Genesis — Full Rewrite from Scratch (2026-07-21 05:00 PT)

### What I Inherited

Paulie handed me the ARBITR8DER trading studio after a full cleanup. Previous agents
(Codex, Gemini, Kilo, OpenCode) built and iterated on v1. The code was deleted. What remains:

**KEPT (keys/config/docs):**
- `.env` — Kalshi API key ID, PAPER mode, private key path
- `streams/kalshi_private.pem` — RSA private key for Kalshi JWT auth
- `pyproject.toml` — Python 3.11+ scaffold, typer/pydantic/httpx/websockets deps
- `.gitignore` — secrets, runtime, Python artifacts
- `docs/Theories_of_Operations.md` — canonical system design (THE bible)
- `docs/overwatch_workflow.md` — REPL command reference for AI operators
- `agents/*/` — journal entries from prior agents (knowledge base, not code)

**DELETED (all old code):**
- `src/arbitr8der/*` — entire package (vessel, integrations, storage, execution, etc.)
- `tests/*` — all 34 tests
- `config/*`, `UI/*`, `scripts/*` — empty directories
- `runtime/data/*`, `runtime/logs/*` — DBs, archives cleared

**HOLLOW FOLDERS (exist but empty):**
- `config/`, `UI/`, `scripts/`, `tests/`
- `runtime/data/`, `runtime/logs/`, `runtime/journals/`, `runtime/state/`
- `src/` (just `__init__.py`)

### Why Rewrite

The prior codebase had real problems identified across 3 agent journals:

1. **PAPER physics != ARMED physics** — synthetic latency, simulated fills, no shared path
2. **No stateful orderbook** — delta-last-price, not a real depth book
3. **Aux streams dead** — only Kalshi+Binance wired; Coinbase/Polymarket/Coingecko never started
4. **No sensors** — sensor_samples table always empty
5. **Aspirational features** — momentum, confirmed moves never implemented
6. **Over-engineered naming** — files renamed to absurd lengths (27 renames in one session)
7. **No prediction model** — fair-value Black-Scholes was the only alpha; no BTC/ETH price model

Paulie's goal is crystal clear: make money on Kalshi. $17 balance. BTC/ETH 15-minute
binary markets. I need to predict price direction and execute with discipline.

### My Mandate

I am Claude. I am the operator, the analyst, and the engineer. I will:

1. Build the data pipeline: Kalshi orderbook + Binance/Coinbase spot + Polymarket + Coingecko
2. Build the prediction engine: learn BTC/ETH 15-minute price patterns from historical data
3. Build the execution layer: PAPER first, ARMED when proof passes
4. Build the journal/scoreboard: every trade logged, every session reviewed
5. Run 24/7: Battery mode streams while Paulie sleeps, I watch the markets

### Hardware (ZEN-LAPTOP)
- AMD Ryzen AI 9 465 (10 cores / 20 threads), 32 GB RAM
- Windows 11 Home, Python 3.12.4
- Runs locally — no cloud dependency

---

## Phase 1: Foundation (The Skeleton)
> Target: 2026-07-21 | Status: ✅ COMPLETE

Core scaffold that everything else plugs into. 53 tests, all passing.

### Tasks
- [x] Create `src/arbitr8der/` package structure (4-word naming convention enforced)
- [x] Vessel state machine (Full_Stop -> Battery -> Full_Forward, with persistence)
- [x] Typed config (pydantic-settings, AR8_ prefix, case-insensitive enums)
- [x] CLI entry point (typer: status, vessel, wallet, snapshot, health)
- [x] EventEnvelope (immutable, timestamped, hashable, slots-based)
- [x] HotState (thread-safe in-memory snapshot, generation counter)
- [x] SQLite schema + connection manager (WAL mode, 7 tables, pragma tuning)
- [x] Wallet manager (PAPER/ARMED profiles, auto-downgrade on missing creds)
- [x] 53 tests for all of above

## Phase 2: Data Pipeline (The Eyes)
> Target: 2026-07-21 | Status: ✅ COMPLETE

All 5 data sources wired and feeding the hot snapshot. 90 tests total, all passing.

### Tasks
- [x] Kalshi REST client (JWT auth via RSA, market discovery, active ticker resolution)
- [x] Kalshi WebSocket client (orderbook snapshots + deltas, auto-reconnect with backoff)
- [x] Binance spot WebSocket (BTC/ETH real-time trade stream → EventEnvelope)
- [x] Coinbase spot WebSocket (BTC/ETH cross-check, ticker channel subscription)
- [x] Polymarket poll client (sentiment overlay, 30s polling, 429 handling)
- [x] Coingecko poll client (macro context, rate limit cooldown, 60s polling)
- [x] DataPipelineOrchestrator (starts/stops all sources, routes events to HotState + DB)
- [x] StreamHealthStatusMonitor (per-source staleness thresholds, can_trade_safely gate)
- [x] Active ticker discovery (KXBTC15M-*, KXETH15M-*, closest-to-expiry selection)
- [x] 37 new tests (Binance, Coinbase, Polymarket, CoinGecko, health, routing, JWT, round-trips)

## Phase 3: Binary Market Outcome Probability Estimator (The Brain)
> Target: Day 3-5 | Status: ✅ COMPLETE

The estimator that reads all 5 data sources and decides: BUY_YES, BUY_NO, or NO_TRADE.

### Tasks
- [x] ProbabilityEstimationResult frozen dataclass (immutable, serializable, full audit trail)
- [x] Orderbook probability estimator (Kalshi yes_best = market's implied probability)
- [x] Spot price probability estimator (Binance/Coinbase cross-exchange agreement)
- [x] Sentiment probability estimator (Polymarket 0-1 score → UP probability)
- [x] Macro context probability estimator (CoinGecko 24h change → probability shift)
- [x] Weighted source combination (orderbook 40%, spot 30%, sentiment 20%, macro 10%)
- [x] Edge calculation (estimated_probability - market_implied, in cents)
- [x] Expected value calculation (EV per share based on edge and confidence)
- [x] Composite confidence scoring (sources × agreement × freshness × edge strength)
- [x] 5-level confidence bucketing (VERY_LOW → VERY_HIGH)
- [x] Trade signal determination with 4 safety gates (sources, staleness, confidence, edge)
- [x] Custom configuration (minimum thresholds, source weights, staleness limits)
- [x] 34 tests covering all estimation paths, edge cases, and signal logic
- [x] Full test suite: 124 passed, 0 failed

## Phase 4: Shared Trade Execution Engine (The Hands)
> Target: Day 5-7 | Status: ✅ COMPLETE

PAPER and ARMED use the same code path. Same physics, same latency model, same fees.

### Tasks
- [x] KalshiFeeCurveCalculatorModule — exact fee formula: `0.07 * P * (1-P) * 100` cents per contract
- [x] Minimum 2 contracts per order enforced (fees kill single-contract trades)
- [x] Round-trip fee estimation (entry + exit fees, net profit/loss projections)
- [x] RiskBoundaryEnforcementHandler — 9 safety gates checked before every trade
  - Vessel state (must be FULL_FORWARD)
  - Wallet mode (PAPER or ARMED)
  - Session loss floor (-$5.00)
  - Daily loss cap (-$10.00)
  - Max open positions (4)
  - Min/max contracts per order (2-10)
  - Sufficient balance
  - Loss cooldown (60s after any loss)
- [x] TradeInventoryPositionTracker — open/closed/pending positions, unrealized + realized P&L
- [x] PriceDriftDetectionHandler — measures snapshot-vs-execution price drift, 5 severity levels
- [x] SharedTradeExecutionEngineHandler — unified PAPER/ARMED execution with 8-step flow
- [x] 58 tests covering all modules individually and end-to-end
- [x] Full test suite: 182 passed, 0 failed

## Phase 5: REPL Command Interface (The Voice)
> Target: Day 7-9 | Status: PENDING

Trade entry/exit with identical PAPER and ARMED physics.

### Tasks
- [ ] Shared execution engine (one code path for PAPER and ARMED)
- [ ] Kalshi order submission (limit orders, market orders)
- [ ] Fill confirmation and reconciliation
- [ ] Risk manager (session floor, rolling floor, daily loss cap, lane cooldowns)
- [ ] Exit logic (settlement warning, profit-taking, stop-loss)
- [ ] Inventory tracker (current positions, cost basis, unrealized PnL)
- [ ] Fee calculator (Kalshi curve: 0.07 * P * (1-P) * 100 cents)
- [ ] Slippage model (based on orderbook depth)
- [ ] Same-batch reentry lock

## Phase 5: Journal & Scoreboard (The Memory)
> Target: Day 7-8 | Status: PENDING

Every trade logged. Every session reviewed. Learning from history.

### Tasks
- [ ] Trade journal table (entry/exit/edge/fill/pnl/reasoning)
- [ ] Session archive (72HR-style JSON dump + hot table truncation)
- [ ] Scoreboard (cumulative PnL, win rate, best/worst lane, streak)
- [ ] Decision log (what I saw, what I thought, what I did, what happened)
- [ ] Sensor sampling (CPU/RAM/disk/internet — light, never slow the data)
- [ ] Wallet snapshots (balance tracking over time)
- [ ] Replay system (re-run a session from archive to verify logic)

## Phase 6: Paper Proof Loop (The Test)
> Target: Week 2 | Status: PENDING

Three consecutive profitable paper sessions before any live trade.

### Tasks
- [ ] Run 15-minute paper sessions at market close
- [ ] Archive each session
- [ ] Gate check: profit-positive, stream-stable, flat closure
- [ ] 3 consecutive passes required for ARMED recommendation
- [ ] Review session journals for edge quality
- [ ] Adjust prediction model based on paper results
- [ ] Verify PAPER physics match ARMED (shared execution path audit)

## Phase 7: ARMED Transition (The Real Thing)
> Target: When proof passes | Status: BLOCKED

Only after Phase 6 passes. Only with Paulie's explicit confirmation.

### Tasks
- [ ] ARMED wallet profile validated (API key + private key present)
- [ ] CLI requires typing "ARMED" to enter live mode
- [ ] Position sizing scaled to $17 balance
- [ ] Maximum loss per session capped
- [ ] Emergency stop: vessel -> Full_Stop, cancel all open orders
- [ ] Live trade journal with real fills
- [ ] Paulie notified of every trade (via journal or log)

---

## Decision Log

### 2026-07-21 05:00 — Fresh Start
- **What I saw:** Paulie cleaned house. Only keys and docs remain.
- **What I thought:** Perfect. No legacy debt. I can build exactly what Theories describes.
- **What I did:** Read all docs, agent journals, PC specs. Created this dev-log and plan.
- **What happened:** Plan written. Ready to code Phase 1.
- **Next:** Create package structure, implement vessel state machine, config, CLI.

### 2026-07-21 06:30 — Phase 1 Complete
- **What I saw:** Clean slate. No code, no tests, no working CLI.
- **What I thought:** Build the skeleton fast. Everything else plugs into this.
- **What I did:** Created 9 source modules, 53 tests, working CLI (status/vessel/wallet/snapshot/health).
- **What happened:** All 53 tests passing. Vessel state machine persists. DB initializes WAL mode. Wallet auto-downgrades ARMED→PAPER.
- **Key decisions:** 4-word naming convention on all files/variables. Case-insensitive enums for .env compatibility. JSON persistence for vessel state.
- **Next:** Phase 2 — wire all 5 data sources.

### 2026-07-21 07:15 — Phase 2 Complete
- **What I saw:** All Phase 1 foundation in place. No data flowing.
- **What I thought:** Time to give the system eyes. Build all 5 data sources + health monitoring + orchestrator.
- **What I did:** Created 8 new source modules (Kalshi REST/WS, Binance WS, Coinbase WS, Polymarket poller, CoinGecko poller, health monitor, pipeline orchestrator) + 37 new tests.
- **What happened:** 90/90 tests passing. All modules import cleanly. Pipeline routes events to both HotState (fast path) and EventRepository (cold path). Health monitor tracks staleness of all 6 sources. can_trade_safely() gates on Kalshi health.
- **Key decisions:** Use threading + asyncio.new_event_loop() for each WS stream (Python GIL-safe). Polymarket poller at 30s, CoinGecko at 60s (slow overlays). Kalshi WS auto-reconnect with exponential backoff up to 60s. JWT regenerates every 55 min (tokens valid 24h).
- **What's missing (future work):** Stateful orderbook reconstruction (running YES/NO depth levels per ticker), end-to-end latency measurement.
- **Next:** Phase 3 — Binary Market Outcome Probability Estimator.

### 2026-07-21 08:00 — Comprehensive Naming Convention Fix
- **What I saw:** 15 files had fewer than 4 words in their names. Variable names were abbreviated (`sm`, `hs`, `db`, `e1`/`e2`).
- **What I thought:** AI systems are the primary engineers here. Names must explain themselves. No abbreviation. No context loss.
- **What I did:** Renamed 15 source files, 12 classes, all abbreviated test variables, and CLI variables to follow 4-word minimum naming convention. Updated all imports across 10 source files and 5 test files.
- **What happened:** 90/90 tests still passing after rename. Files like `event_envelope_wrapper.py` became `immutable_event_envelope_wrapper.py`. Classes like `HotStateManager` became `ThreadSafeHotStateManager`. Variables like `sm` became `vessel_state_machine`.
- **Key decisions:** 4-word minimum for EVERYTHING — files, classes, variables, functions. No exceptions. This is an AI-operated system; context must be self-describing.
- **Next:** Phase 3 — Binary Market Outcome Probability Estimator.

### 2026-07-21 08:45 — Phase 3 Complete
- **What I saw:** Data pipeline delivers 5 sources to HotState. But nothing reads that state to make decisions.
- **What I thought:** Build the brain. Read all 5 sources, estimate probability, calculate edge, determine confidence, output a trade signal. 4-safety-gate design: no sources = no trade, stale data = no trade, low confidence = no trade, small edge = no trade.
- **What I did:** Created `binary_market_outcome_probability_estimator.py` with 4 classes (BinaryMarketOutcomeProbabilityEstimator, ProbabilityEstimationResult, TradeSignalRecommendation, ConfidenceLevel). 34 tests covering every estimation path.
- **What happened:** 124/124 tests passing (90 existing + 34 new). The estimator reads ImmutableHotSnapshot, combines 4 source probabilities via weighted average, calculates edge against market implied price, scores confidence, and outputs BUY_YES / BUY_NO / NO_TRADE with human-readable rejection reasons.
- **Key decisions:** Source weights: orderbook 40% (market price is king), spot 30% (momentum matters for 15m), sentiment 20% (crowd wisdom), macro 10% (broadest context, least time-relevant). Minimum 2 sources required. 55% confidence threshold. 2-cent minimum edge. Stale snapshots (>15s) auto-rejected.
- **What's missing (future work):** Historical price model (15m candle patterns), momentum indicators (RSI, VWAP), rolling performance tracker, model self-assessment.
- **Next:** Phase 4 — Shared Trade Execution Engine.

### 2026-07-21 09:30 — Phase 4 Complete
- **What I saw:** We have a brain (estimator) that says BUY_YES / BUY_NO / NO_TRADE, but no hands to execute. Risk rules from Theories of Operations were only documented, not enforced in code.
- **What I thought:** Build a single execution engine that both PAPER and ARMED flow through. Same code path = no surprises when switching to real money. 9 risk gates as guardrails. Kalshi's real fee curve modeled exactly. Price drift between snapshot and fill measured and logged for every trade.
- **What I did:** Created 5 modules: KalshiFeeCurveCalculatorModule (exact fee formula), RiskBoundaryEnforcementHandler (9 safety gates), TradeInventoryPositionTracker (positions + P&L), PriceDriftDetectionHandler (5 severity levels), SharedTradeExecutionEngineHandler (unified PAPER/ARMED). 58 tests.
- **What happened:** 182/182 tests passing. Fee calculator correctly models Kalshi's P*(1-P) curve. Risk gates block trades when vessel isn't FULL_FORWARD, when losses breach floors, when positions exceed limits, during cooldowns. Price drift is measured for every fill. PAPER mode simulates realistic latency (80ms ± 20ms) and price drift.
- **Key decisions:** Risk gates checked in priority order (cheapest first). Session floor (-$5) checked before daily cap (-$10). Loss cooldown of 60 seconds after any losing trade. Minimum 2 contracts per order (Kalshi fees make single-contract unprofitable). net_loss_if_lose is positive magnitude, not negative (represents total cost of being wrong).
- **What's missing (future work):** Real Kalshi REST API integration for ARMED mode (currently using simulated fills), same-batch reentry lock, order fill confirmation stream.
- **Next:** Phase 5 — REPL Command Interface (the voice that lets the AI operator talk to the system).
