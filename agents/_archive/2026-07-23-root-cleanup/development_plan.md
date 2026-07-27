# ARBITR8DER Development Plan — v2.0 "Clean Slate"

**Author:** Claude (OpenClaude)
**Date:** 2026-07-21
**Operator:** Paulie (Paulie Studios)
**Machine:** ZEN-LAPTOP (AMD Ryzen AI 9 465, 32GB RAM, Windows 11)

---

## Mission Statement

Build a 24/7 AI-operated trading studio that profits on Kalshi 15-minute binary
markets (BTC/ETH). Claude operates, analyzes, and engineers. Paulie sleeps.

**Current balance:** $17
**Markets:** KXBTC15M-* (BTC), KXETH15M-* (ETH) only
**Default state:** Full_Stop
**Safety:** No trade without explicit ARMED + operator confirmation

---

## Architecture Principles (from Theories_of_Operations.md)

1. **3 States:** Full_Stop -> Battery -> Full_Forward. State = permission to trade.
2. **PAPER = ARMED physics.** One execution code path. Paper uses fake order IDs.
3. **Orderbook is truth.** No trade without valid, sequenced orderbook.
4. **5 data sources:** Kalshi (execution), Binance+Coinbase (spot), Polymarket (sentiment), Coingecko (macro).
5. **Hyper-modular:** No file > 1000 lines. Clean subsystem boundaries.
6. **Hot/Cold split:** RAM for hot data, SQLite for cold persistence.
7. **End-to-end latency:** Measured provider -> received -> snapshot -> AI read -> decision -> executed.
8. **Journal everything:** Every trade, every decision, every session archived.
9. **Risk management:** Rolling floor, daily caps, lane cooldowns, fee awareness.
10. **Local only:** No cloud. No Docker. Runs on ZEN-LAPTOP.

---

## Package Structure (Target)

```
ARBITR8DER/
├── .env                          # KEPT — Kalshi credentials
├── .gitignore                    # KEPT
├── pyproject.toml                # KEPT — updated for new deps
├── requirements.txt              # KEPT — updated
├── streams/
│   └── kalshi_private.pem        # KEPT — RSA key
├── docs/
│   ├── Theories_of_Operations.md # KEPT — canonical design
│   ├── overwatch_workflow.md     # KEPT — REPL commands
│   ├── dev_log.md                # NEW — this build's journal
│   └── development_plan.md       # NEW — this file
├── agents/
│   └── claude/CLAUDE.md          # KEPT — agent memory
├── config/                       # Runtime config (non-secret)
├── scripts/                      # Utility scripts
├── UI/                           # Future terminal UI
├── runtime/
│   ├── data/                     # SQLite DBs, archives
│   ├── logs/                     # Session logs
│   ├── journals/                 # Trade journals
│   └── state/                    # Vessel state persistence
├── tests/                        # Test suite
└── src/
    └── arbitr8der/
        ├── __init__.py
        ├── _version.py                   # Version string
        ├── cli/
        │   ├── __init__.py
        │   ├── app.py                    # Typer CLI entry point
        │   ├── vessel_commands.py        # vessel stop/battery/forward
        │   ├── forward_commands.py       # forward start/stop/status
        │   └── diagnostic_commands.py    # status/snapshot/opportunities
        ├── config/
        │   ├── __init__.py
        │   └── settings.py              # Pydantic-settings, AR8_ prefix
        ├── vessel/
        │   ├── __init__.py
        │   └── state_machine.py         # 3-state machine + persistence
        ├── market_data/
        │   ├── __init__.py
        │   ├── event_envelope.py        # Immutable event wrapper
        │   ├── hot_state.py             # Thread-safe in-memory snapshot
        │   └── ticker_registry.py       # Active ticker discovery + rollover
        ├── integrations/
        │   ├── __init__.py
        │   ├── kalshi_rest.py           # JWT auth, market discovery, orders
        │   ├── kalshi_ws.py             # Orderbook deltas + snapshots
        │   ├── binance_ws.py            # Spot BTC/ETH real-time
        │   ├── coinbase_ws.py           # Spot cross-check
        │   ├── polymarket.py            # Sentiment polling
        │   ├── coingecko.py             # Macro context polling
        │   └── connection_manager.py    # Lifecycle for all 5 streams
        ├── storage/
        │   ├── __init__.py
        │   ├── db.py                    # SQLite WAL connection manager
        │   ├── schema.py                # Table creation + migrations
        │   ├── events.py                # Event persistence
        │   ├── health.py                # Stream health logging
        │   ├── wallet.py                # Wallet snapshots
        │   ├── trades.py                # Trade journal
        │   └── sensors.py              # System metrics (light)
        ├── orderbook/
        │   ├── __init__.py
        │   ├── book.py                  # Stateful orderbook (running levels)
        │   ├── depth.py                 # Best bid/ask, spread, depth analysis
        │   └── integrity.py             # Sequence tracking, staleness, trust
        ├── prediction/
        │   ├── __init__.py
        │   ├── price_model.py           # BTC/ETH 15m window price model
        │   ├── fair_value.py            # Kalshi contract fair value estimator
        │   ├── signals.py               # Momentum, volatility, cross-exchange
        │   ├── edge.py                  # Expected profit calculator
        │   └── confidence.py            # Position sizing confidence
        ├── execution/
        │   ├── __init__.py
        │   ├── engine.py                # Shared PAPER/ARMED execution path
        │   ├── risk.py                  # Floors, caps, cooldowns
        │   ├── inventory.py             # Current positions + PnL
        │   └── fees.py                  # Kalshi fee curve
        ├── journal/
        │   ├── __init__.py
        │   ├── scoreboard.py            # Cumulative stats
        │   ├── decision_log.py          # What I saw/thought/did/happened
        │   └── archive.py               # Session archival
        └── sensors/
            ├── __init__.py
            └── metrics.py               # CPU/RAM/disk (lightweight)
```

---

## Phase Details

### Phase 1: Foundation — "The Skeleton" ✅ COMPLETE
**Goal:** Bootable CLI with vessel state, config, DB, and empty hot state.
**Depends on:** Nothing (clean start)
**Completed:** 2026-07-21
**Vessel state at completion:** Full_Stop (default)

**Deliverables:**
- Package installs via `pip install -e .`
- `arbitr8der status` shows vessel state, config summary, DB health
- `arbitr8der vessel battery` transitions to Battery
- `arbitr8der vessel forward` transitions to Full_Forward (requires confirmation)
- `arbitr8der vessel stop` emergency stops
- SQLite creates 7 tables on first run (WAL mode)
- HotState accepts and returns immutable snapshots
- EventEnvelope wraps events with timestamps
- Wallet reads .env and resolves PAPER profile
- 53 unit tests passing

**Exit Criteria:** `arbitr8der status` runs clean, all tests green. ✅

---

### Phase 2: Data Pipeline — "The Eyes" ✅ COMPLETE
**Goal:** All 5 data sources streaming into HotState.
**Depends on:** Phase 1
**Completed:** 2026-07-21
**Vessel state at completion:** Battery (data flowing, no trading)

**Deliverables:**
- Kalshi REST: JWT auth works, discovers active KXBTC15M-* and KXETH15M-* tickers ✅
- Kalshi WS: Connects, receives orderbook snapshots + deltas, auto-reconnect ✅
- Binance WS: Real-time BTC/ETH spot price streaming ✅
- Coinbase WS: Cross-check spot price ✅
- Polymarket: Polls BTC/ETH sentiment every 30s ✅
- Coingecko: Polls macro context every 60s (rate limit aware) ✅
- DataPipelineOrchestrator: starts/stops all sources, routes to HotState + DB ✅
- StreamHealthStatusMonitor: staleness tracking, can_trade_safely() gate ✅
- Active ticker discovery + closest-to-expiry selection ✅
- 90 unit tests passing (37 new in Phase 2) ✅

**Still TODO (deferred):**
- Stateful orderbook reconstruction (running YES/NO levels per ticker)
- End-to-end latency measurement (provider → snapshot → AI read)

**Exit Criteria:** All data sources import cleanly, events route to HotState, health monitor tracks all 6 sources. ✅

---

### Phase 3: Prediction Engine — "The Brain"
**Goal:** Predict BTC/ETH 15-minute price direction with measurable edge.
**Depends on:** Phase 2
**Estimated time:** Days 3-5
**Vessel state at completion:** Battery (predicting, not trading)

**Deliverables:**
- Historical data backfill (72hr of 1m candles from Binance)
- Price model: given current price + momentum + volatility, predict 15m direction
- Fair value estimator: what IS the fair value of a YES contract given spot + model?
- Signal generators: RSI, VWAP, spread, delta velocity, cross-exchange divergence
- Edge calculator: fair_value - ask - fees - slippage = expected_profit
- Confidence scorer: how sure am I? ranges 0.0-1.0
- Rolling performance tracker: win rate, avg edge, Sharpe by lane
- Model self-assessment: am I actually better than 50/50?

**Exit Criteria:** Model can predict historical 15m windows with >55% accuracy on test data.

---

### Phase 4: Execution Layer — "The Hands"
**Goal:** Place and manage trades with identical PAPER/ARMED physics.
**Depends on:** Phase 3
**Estimated time:** Days 5-7
**Vessel state at completion:** Full_Forward (paper trading)

**Deliverables:**
- Shared execution engine (one code path, PAPER uses fake order IDs)
- Kalshi order submission (limit + market)
- Fill confirmation + reconciliation
- Risk manager: session floor, rolling floor, daily loss cap, lane cooldowns
- Exit logic: settlement warning, profit-taking, stop-loss
- Inventory tracker: current positions, cost basis, unrealized PnL
- Fee calculator: Kalshi curve 0.07 * P * (1-P) * 100
- Slippage model based on orderbook depth
- Same-batch reentry lock

**Exit Criteria:** `arbitr8der forward start` runs a 15-min paper session, places orders, logs fills, archives results.

---

### Phase 5: Journal & Scoreboard — "The Memory"
**Goal:** Every trade logged, every session archived, every review possible.
**Depends on:** Phase 4
**Estimated time:** Days 7-8

**Deliverables:**
- Trade journal table (entry/exit/edge/fill/pnl/reasoning)
- Session archive (JSON dump + hot table truncation after 72hr)
- Scoreboard (cumulative PnL, win rate, best/worst lane, streak)
- Decision log (what I saw, what I thought, what I did, what happened)
- Sensor sampling (CPU/RAM/disk — lightweight)
- Wallet snapshots (balance tracking)
- Replay system (re-run session from archive)

---

### Phase 6: Paper Proof Loop — "The Test"
**Goal:** Three consecutive profitable paper sessions before any live trade.
**Depends on:** Phase 5
**Estimated time:** Week 2

**Deliverables:**
- Run 15-minute paper sessions at market close
- Gate check: profit-positive + stream-stable + flat closure
- 3 consecutive passes required
- Review session journals for edge quality
- Adjust prediction model based on results
- Verify PAPER = ARMED physics (audit)

---

### Phase 7: ARMED Transition — "The Real Thing"
**Goal:** Live trading on Kalshi with real money.
**Depends on:** Phase 6 passes + Paulie's explicit confirmation
**Estimated time:** When ready

**Deliverables:**
- ARMED wallet profile validated
- CLI requires typing "ARMED" to enter live mode
- Position sizing scaled to balance
- Max loss per session capped
- Emergency stop: vessel -> Full_Stop, cancel all open orders
- Live trade journal with real fills
- Paulie notified via journal/log

---

## Risk Management Rules

1. **Session floor:** -20% of starting balance triggers caution
2. **Rolling floor:** -30% of starting balance triggers pause
3. **Daily loss cap:** -50% of starting balance = HARD STOP for the day
4. **Lane cooldown:** After loss in a lane, wait 2 periods before re-entry
5. **Fee awareness:** Never enter a trade where fees > expected edge
6. **Flat closure:** All positions closed at settlement warning
7. **Stale orderbook = no trade:** If book is stale/gapped, NO TRADE in that lane
8. **Same-batch reentry lock:** After sell, cannot re-enter same lane in same 15m window
9. **Position cap:** Max 30% of balance in any single position
10. **Emergency stop:** Full_Stop kills everything — no trades, no data, clean shutdown

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Paper win rate | > 55% (better than coin flip) |
| Average edge per trade | > 2 cents after fees |
| Session PnL | Positive in 2/3 sessions |
| Stream uptime | > 99% during active windows |
| Latency (snapshot -> decision) | < 5 seconds |
| Time to first profitable paper trade | < 2 weeks |
| Time to first ARMED trade | < 4 weeks |

---

*"The goal is not to trade often. The goal is to trade well."*
