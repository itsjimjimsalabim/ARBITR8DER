# ARBITR8DER Overwatch — AI Agent Trading Session Workflow

**Role**: Overwatch (AI agent operator)  
**Studio**: ARBITR8DER local trading studio  
**Markets**: Kalshi 15-min binary — BTC (KXBTC15M-*) and ETH (KXETH15M-*)  
**Modes**: PAPER (default) / ARMED (explicit confirmation required)  
**Session Window Target**: 7:30–7:45 PM PDT (quarter-hour aligned)

---

## 1. Vessel States — What Overwatch Can Do

| State | Streams | Trading | Overwatch Actions |
|-------|---------|---------|-------------------|
| **Full_Stop** | OFF | NO | `arbitr8der vessel battery` → transition to Battery |
| **Battery** | ON (data collection) | NO | `arbitr8der snapshot`, `arbitr8der opportunities`, `arbitr8der positions` (read-only), journal notes |
| **Full_Forward** | ON | YES (PAPER or ARMED) | **Launch REPL**: `arbitr8der forward start` → full command set |

**Key principle**: Full_Forward is the killswitch. The vessel state *is* the permission to trade. No automated bot decides — Overwatch decides every entry and exit.

---

## 2. Session Launch Sequence

```bash
# 1. Ensure vessel is in Full_Forward
arbitr8der vessel forward

# 2. Start AI trading session (auto-calculates duration from market close)
arbitr8der forward start
# Or specify duration: arbitr8der forward start --duration 20
```

**Session startup phases** (printed on launch):
```
[1/4] Initialising database...          → schema v3 (price_history table exists)
[2/4] Starting exchange connections...  → Kalshi REST/WS, Binance WS, DB all green
[3/4] Loading active market universe... → fetches KXBTC15M-*, KXETH15M-* with strikes
[3b/4] Backfilling historical price data → 72hr of 1m Binance klines into price_history
[4/4] Entering AI agent command loop... → REPL prompt: ff[XXXs]>
```

**Wait for "Entering AI agent command loop" before issuing commands.**

---

## 3. REPL Command Reference

| Command | Purpose | Output |
|---------|---------|--------|
| `monitor` | Start background health tick (1s interval) | Stream of health lines; press Enter to return |
| `snapshot` | Full HotSnapshot as JSON | Order books, spot prices, wallet, health |
| `opportunities` | **Primary signal** — 15-min predictions + tradeable entries | Table with P(up)/P(dn), prediction label, executable rows |
| `predict` | Focused BTC/ETH prediction for next window | Boxed output with countdown, bias, suggested side |
| `positions` | Open positions with current bid, PnL, target, stop | JSON array |
| `buy ASSET SIDE N` | Market buy (min 2 contracts) | Drift report + fill confirmation |
| `buy ASSET SIDE N LIMIT` | Limit buy at cents (e.g., `buy ETH YES 3 15`) | Pending order placed |
| `sell ASSET TICKER` | Close position by ticker | Fill confirmation + realized PnL |
| `pending` | Show pending limit orders | List of waiting orders |
| `cancel TICKER` | Cancel pending limit order | Confirmation |
| `journal TEXT` | Append reasoning to trade journal | Logged with timestamp |
| `exit` | Shutdown session cleanly | Archives run, closes connections |

---

## 4. The Prediction Pipeline — How to Read the Signal

### Data Flow
```
Binance 1m klines (72hr backfill on session start)
       ↓
SQLite price_history table (OHLCV + timestamps)
       ↓
probability_up(asset, window_minutes=15)
       ↓
detect_opportunities() enriches each market with:
  - p_up_15m: historical P(close > open | 15m window)
  - p_down_15m: 1 - p_up_15m
  - prediction: "strong UP bias", "weak DOWN bias", "neutral", "insufficient data"
```

### Reading `opportunities` Output

```
  15-MIN WINDOW PREDICTIONS  (mark:4m12s  window:3m12s)
  Asset  P(up)   P(dn)  Prediction
  ------ ------- -------  ------------------------------
     BTC    64%     36%  BTC strong UP bias (P_up=64.4%, P_down=35.6%)
     ETH    52%     48%  ETH weak UP bias (P_up=52.0%, P_down=48.0%)

  TRADEABLE ENTRY (1):
    YES  edge=12.3c  ask=48c  contracts=3  KXBTC15M-20260717T2330
  BLOCKED (1):
    ETH  YES  edge=2.1c  reason=insufficient depth
```

**Interpretation guide**:
- **P(up) ≥ 60%**: Strong historical up bias — consider YES
- **P(up) ≤ 40%**: Strong historical down bias — consider NO
- **40–60%**: Weak/neutral — edge must come from orderbook, not history
- **Executable row**: Passes depth check, edge > threshold, contracts ≥ 2
- **Blocked row**: Depth = 0, edge too thin, or no valid book

### Reading `predict` Output

```
  ╔══ 15-MIN WINDOW PREDICTION ═══════════════════════
  ║  Window:  mark:2m45s  window:1m45s
  ║  Assets:  BTC, ETH
  ╠═══════════════════════════════════════════════════
  ║  BTC: P(up)=64.4%  P(dn)=35.6%  →  BTC strong UP bias
  ║       Current YES ask: 48c  |  Historical edge: +12.3c
  ║       Suggested: BUY BTC YES 3 @ market
  ║  ETH: P(up)=52.0%  P(dn)=48.0%  →  ETH weak UP bias
  ║       Current YES ask: 34c  |  Historical edge: +1.8c
  ║       Suggested: WAIT — edge below threshold
  ╚═══════════════════════════════════════════════════
```

**Window label meaning**:
- `mark:XmYs` → seconds until next quarter-hour mark (:00, :15, :30, :45)
- `window:XmYs` → seconds until window data collection starts (1 min before mark)
- **Trade at or before `window` mark** so the 15-min binary has full life

---

## 5. Trading Workflow — The Overwatch Loop

### Pre-Window (T-5min to T-1min)
```bash
ff[300s]> monitor          # Start health watch
ff[300s]> opportunities    # Check P(up) signal, depth, executable entries
ff[300s]> predict          # Focused view for BTC/ETH
```

### At Window Open (T-1min to T+0)
```bash
ff[60s]> opportunities     # Final confirmation
ff[60s]> journal "BTC P(up)=64%, YES ask 48c, edge +12c. Entering 3 contracts YES."
ff[60s]> buy BTC YES 3     # Market order
```

### Post-Entry (during window)
```bash
ff[400s]> positions        # Check PnL, current bid vs entry
ff[400s]> journal "BTC YES +8c unrealized. Holding to settlement."
# Or exit early:
ff[400s]> sell BTC KXBTC15M-20260717T2330
```

### At Window Close (settlement)
- Positions auto-settle at market resolution (YES→$1 or $0)
- **Paper positions currently NOT auto-settled** — must sell before session end or PnL evaporates
- Journal the outcome: `journal "BTC YES settled at $1. +48c realized. P(up) signal correct."`

---

## 6. Journal Protocol — Every Decision Logged

**Required journal entries**:
1. **Pre-trade**: Signal read, reasoning, chosen side, size, limit if any
2. **Post-fill**: Drift report (slippage), actual fill price vs snapshot
3. **During hold**: Any thesis change, early exit rationale
4. **Post-settlement**: Outcome vs prediction, lesson for next window

**Format**: Free text. Timestamped automatically.
```
ff[55s]> journal "BTC P(up)=64% strong UP. YES ask 48c, edge +12c. 3 contracts. Thin depth (2 contracts) but executable."
ff[10s]> journal "Filled at 50c (drift +2c from 48c ask). Slippage within tolerance."
ff[400s]> journal "Holding to settlement. Bid now 55c."
ff[850s]> journal "Settled at $1. Realized +50c. Signal validated."
```

---

## 7. Key Operational Constraints

### Minimum Contracts
- **2 contracts minimum** enforced by ExecutionEngine
- Kalshi fees: ~1.75¢/contract/leg → 3.5¢ round-trip
- 1 contract = fees eat entire edge; 2+ = fees amortized

### Price Drift
- Engine simulates 60–100ms latency on every `buy`
- Reports: `Drift: +2c (ask moved 48c→50c during latency)`
- Factor drift into limit prices

### Market Depth
- BTC YES often 1–2 contracts; ETH YES hits 0
- `opportunities` shows `reason=insufficient depth` when blocked
- Do not force — wait for depth or reduce size

### Paper Inventory Persistence
- **Positions die with session** — no SQLite persistence yet
- If session exits before settlement, PnL is lost
- **Workaround**: Sell before `exit`, or keep session alive until settlement

### Strike Price
- Fetched from Kalshi REST during universe load
- Stored in `active_universe` and passed to Black-Scholes edge model
- If `strike=0`, edge model returns `edge=-999.0c reason=no strike or spot`

---

## 8. Timing for 7:30–7:45 PM PDT Window

| PDT Time | UTC Time | Action |
|----------|----------|--------|
| 7:15 PM | 02:15 UTC | `arbitr8der vessel forward` |
| 7:20 PM | 02:20 UTC | `arbitr8der forward start` (auto-duration to 7:45 close) |
| 7:25 PM | 02:25 UTC | `monitor`, `opportunities`, `predict` — read signal |
| 7:29 PM | 02:29 UTC | `journal` pre-trade reasoning |
| 7:30 PM | 02:30 UTC | **Window opens** — `buy` if signal confirms |
| 7:45 PM | 02:45 UTC | **Window closes** — settlement |
| 7:46 PM | 02:46 UTC | `positions`, `journal` outcome, `exit` |

**Quarter-hour marks**: :00, :15, :30, :45 UTC (which is 5:00, 5:15, 5:30, 5:45 PDT — adjust for DST)

The `_window_label()` helper shows countdown to next mark and window start.

---

## 9. Known Gaps — Do Not Assume These Work

| Gap | Impact | Workaround |
|-----|--------|------------|
| Binance WS not flowing | Spot price only updates via REST every 30s | Use `snapshot` for latest REST spot |
| Paper positions not persistent | Session exit = PnL gone | Don't exit until settled |
| No auto-settlement | Must manually `sell` before close | Set reminder at T+14min |
| Wallet snapshots not captured | No equity curve in DB | Journal balance manually |
| P(up) is simple frequency | Not a predictive model | Overwatch adds qualitative overlay |
| No `--script` mode for REPL | Piped stdin fragile | Type commands manually |

---

## 10. Quick Reference Card

```bash
# Launch
arbitr8der vessel forward
arbitr8der forward start

# Read signal
opportunities
predict

# Trade
buy BTC YES 3           # market
buy ETH NO 2 15         # limit @ 15c
sell ETH KXETH15M-...   # close
pending                 # check limits
cancel KXETH15M-...     # cancel limit

# Observe
snapshot                # full JSON
positions               # open with PnL
monitor                 # health stream (Enter to stop)

# Record
journal "reasoning here"

# End
exit
```

---

## 11. Success Criteria for This Session

1. **Session launches clean** — all 4 connections green, 72hr backfill completes
2. **Signal read at 7:25 PM** — `opportunities` shows P(up) for BTC/ETH
3. **Decision logged** — `journal` entry before any `buy`
4. **Trade executed** — `buy` fills, drift reported, position visible in `positions`
5. **Outcome recorded** — `journal` at settlement with realized PnL vs prediction
6. **Session archived** — `exit` produces run_archive JSON in `runtime/data/archives/`

---

**Overwatch Mantra**: *Read the snapshot. Trust the P(up) prior. Size to the depth. Journal the why. Verify the outcome.*