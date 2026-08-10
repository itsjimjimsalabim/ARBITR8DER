# ARBITR8DER Trading Studio Operating Workflow

**Audience:** Any AI agent operator (Claude, Gemini, Antigravity, OpenCode, Kilo, etc.) or human trader executing live or paper sessions.  
**Purpose:** Canonical operating manual for running the ARBITR8DER trading studio in AI Operator mode.  
**Last Verified:** 2026-08-07

---

## 1. Operating Directive & Core Stance (The Pivot)

> **Core Directive:** **NO AUTONOMOUS AUTOTRADING.** The trading engine does not route trades automatically. The AI Agent (Overwatch/Operator) inspects live market data, model predictions, and orderbook spreads, then manually executes orders via the REPL (`buy`/`sell`).

### Vessel State Machine & Killswitch Model

| State | Ingestion Streams | Trading Permission | Usage |
|---|---|---|---|
| `Full_Stop` | **OFF** | **NO** | Default state on startup. All orders blocked. |
| `Battery` | **ON** | **NO** | Data soak mode. Ingests candles, order books, and price ticks. |
| `Full_Forward` | **ON** | **YES** (PAPER / ARMED) | Active trading mode. Enables manual REPL order submission. |

*Safety rule: `VesselStateMachine` forces `Full_Stop` on every instantiation. You must transition `Full_Stop` $\rightarrow$ `Battery` $\rightarrow$ `Full_Forward` before placing orders.*

---

## 2. 15-Minute Market Cycle & Timing Cadence

15-minute Kalshi binary contracts close at `:00`, `:15`, `:30`, and `:45` of every hour.

```
T-3min (e.g. 12:12 PDT)  ──► Launch REPL (`arbitr8der forward start`) & Arm Vessel (`vessel forward`)
T-2min (e.g. 12:13 PDT)  ──► Orderbook & Candle Battery Warmup (wait 40s)
T-0min (e.g. 12:15 PDT)  ──► Market Rollover (`markets`, `snapshot`, `predict BTC/ETH`)
T+1min (e.g. 12:16 PDT)  ──► Patient Limit Order Submission (`buy ASSET SIDE N LIMIT`)
T+13min (e.g. 12:28 PDT) ──► Pre-Expiration Status Check (`positions`, `snapshot`)
T+15min (e.g. 12:30 PDT) ──► Market Expiry & Auto-Settlement (`settlement`, `wallet`)
T+16min (e.g. 12:31 PDT) ──► Clean Exit & Log Archival (`exit`)
```

---

## 3. Patient Limit Order Execution Strategy (Adaptation Protocol)

To maintain positive expected value and avoid overpaying for contracts:

1. **Never buy Market NO/YES at > 65¢** unless confidence is $>90\%$. Paying 75¢+ creates a 3:1 negative risk/reward ratio where a single loss wipes out 3 wins.
2. **Use Patient Limit Orders (`buy ASSET SIDE N LIMIT_CENTS`):**
   - Place limit orders at a discount to current midpoints (e.g., target 45¢–50¢ entries).
   - Example: `buy BTC no 2 48` (Places a limit order for 2 NO contracts at 48¢).
3. **Execution Advantage:**
   - Limits cost to $\le \$0.96$ per 2-contract trade (vs $\$1.50+$ market orders).
   - Improves Risk/Reward ratio to $\sim 1.1:1$ profit-to-risk.
   - Amortizes Kalshi transaction fees ($\approx 1.75\text{¢}$ per contract/leg).

---

## 4. REPL Session Playbook

### Step 1: Pre-Flight & Launch

```bash
# 1. Check CLI version and status
arbitr8der status

# 2. Launch interactive REPL session (starts in Battery mode, auto-syncs live Kalshi cash balance)
arbitr8der forward start
```

### Step 2: Arm Vessel & Inspect Universe

```text
arbitr8der [battery]> vessel forward
Vessel -> Full_Forward

arbitr8der [full_forward]> snapshot
arbitr8der [full_forward]> markets
```

### Step 3: Run Model Predictions & Evaluate Signals

```text
arbitr8der [full_forward]> predict BTC --model auto
arbitr8der [full_forward]> predict ETH --model auto
```

- **Interpretation:**
  - `macro_ensemble`: Combines LightGBM + Frequency Lookup (72h candle window).
  - `baseline_v1`: Spot disagreement + candle momentum fallback.
  - Directional Bias: `P(YES) < 40%` $\rightarrow$ Strong NO bias; `P(YES) > 60%` $\rightarrow$ Strong YES bias.

### Step 4: Submit Patient Limit Orders

```text
# Buy 2 NO contracts of BTC at 48 cents limit
arbitr8der [full_forward]> buy BTC no 2 48

# Buy 2 NO contracts of ETH at 48 cents limit
arbitr8der [full_forward]> buy ETH no 2 48

# Verify order fills and open positions
arbitr8der [full_forward]> positions
arbitr8der [full_forward]> pending
```

### Step 5: Post-Settlement Verification & Shutdown

```text
# Inspect auto-settlement results after window close
arbitr8der [full_forward]> wallet
arbitr8der [full_forward]> settlement

# Journal reasoning and session exit
arbitr8der [full_forward]> journal "12:15-12:30 run complete. Patient limit entry @ 48c successful."
arbitr8der [full_forward]> exit
```

---

## 5. Supporting Reference Documents

- [`agents/onboarding_workflow.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/onboarding_workflow.md) — Skeptical pre-flight and repo map.
- [`agents/agents.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/agents.md) — Primary directives, tool inventory, and vessel rules.
- [`agents/todo.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/todo.md) — Current implementation backlog and active session log.
- [`agents/dev_log.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/dev_log.md) — Chronological development history and session autopsies.
- [`agents/overwatch_workflow.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/overwatch_workflow.md) — Legacy Overwatch playbook reference.
