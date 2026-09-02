# ARBITR8DER Trading Studio Operating Workflow

**Audience:** Any AI agent operator (Claude, Gemini, Antigravity, OpenCode, Kilo, etc.) or human trader executing live or paper sessions.  
**Purpose:** Canonical operating manual for running the ARBITR8DER trading studio in AI Operator mode.  
**Last Verified:** 2026-09-01

## 2026-08-10 Rewrite Directive

The 2026-08-07 manual-operator stance is superseded for the next build. The current target is a fresh Rust-first Kalshi Vessel for BTC/ETH 15-minute markets. Automatic PAPER trading is allowed again after explicit run start, stream-health checks, risk gates, and append-only database journaling. Polymarket is signal-only: use its streams, prices, orderbooks, sentiment, and comparable-event movement to improve Kalshi predictions; do not place Polymarket orders or build Polymarket wallet/PnL workflows now.

No ARMED live Kalshi order is authorized by this directive. ARMED trading still requires a later explicit operator command after PAPER evidence.

---

## 1. One-Hour Paper Session Cadence (Current Operating Mode)

**Supersedes the single 15-minute window playbook below for new work.** Runs are one full hour at a time = four consecutive 15-minute market cycles. Shut the studio down between hours for analysis and upgrades. Never run continuous multi-hour automation.

### Cadence

| Hour slot (start at :59) | 15-min cycles covered | Action |
|---|---|---|
| `:59` of hour H | H+1 `:00` | Launch 1-hour paper session (4Ã—15m cycles) |
| ... | H+1 `:15`, `:30` | Continuous paper autotrade loop |
| ... | H+1 `:45` (last cycle) | Finish batch |
| H+1 `:59` | â€” | Shut down; analysis + upgrade window |

- Launch at the **:59 minute mark** so the session is live before the `:00` market rollover.
- After the 4th cycle ends, stop the studio, review journal/PnL/health, apply upgrades.
- Next hourly launch re-aligns at the next `:59` mark.

### Execution

```bash
# In repo: C:\Users\RED-Laptop\GitHub\PaulieStudios\ARBITR8DER
# Full 1-hour session (4Ã—15m batches, 3600s):
.\.venv\Scripts\python.exe .\kalshi_desk\scripts\run_ai_trading_session.py   # interactive REPL session runner
# or launch the REPL directly for the full hour:
arbitr8der forward start
```

- Use `--duration`/a `run_ai_trading_session` call with `duration_seconds=3600` for a 1-hour battery session, or run four 900s batches sequentially with a check between batches.
- Auto-trader fires paper orders only after session start, stream-health checks, risk gates, and DB journaling are online.
- After session end, `arbitr8der status` must report `full_stop` and a clean lease release before the next launch.

### Safety

- PAPER default, wallet `paper`, trading mode `hold` until armed via `vessel forward`.
- No live Kalshi order is authorized by this directive. ARMED requires a later explicit operator command.
- Stale/empty/crossed Kalshi book blocks trading; do not paper-trade on a broken book.

---

## 2. Operating Directive & Core Stance (The Pivot)

**Historical note:** This section describes the previous manual REPL stance. Preserve it as old operating context until the Rust Vessel replaces it, but follow the 2026-08-10 rewrite directive for new work.

> **Core Directive:** **NO AUTONOMOUS AUTOTRADING.** The trading engine does not route trades automatically. The AI Agent (Overwatch/Operator) inspects live market data, model predictions, and orderbook spreads, then manually executes orders via the REPL (`buy`/`sell`).

### Vessel State Machine & Killswitch Model

| State | Ingestion Streams | Trading Permission | Usage |
|---|---|---|---|
| `Full_Stop` | **OFF** | **NO** | Default state on startup. All orders blocked. |
| `Battery` | **ON** | **NO** | Data soak mode. Ingests candles, order books, and price ticks. |
| `Full_Forward` | **ON** | **YES** (PAPER / ARMED) | Active trading mode. Enables manual REPL order submission. |

*Safety rule: `VesselStateMachine` forces `Full_Stop` on every instantiation. You must transition `Full_Stop` $\rightarrow$ `Battery` $\rightarrow$ `Full_Forward` before placing orders.*

---

## 3. 15-Minute Market Cycle & Timing Cadence

15-minute Kalshi binary contracts close at `:00`, `:15`, `:30`, and `:45` of every hour.

```
T-3min (e.g. 12:12 PDT)  â”€â”€â–º Launch REPL (`arbitr8der forward start`) & Arm Vessel (`vessel forward`)
T-2min (e.g. 12:13 PDT)  â”€â”€â–º Orderbook & Candle Battery Warmup (wait 40s)
T-0min (e.g. 12:15 PDT)  â”€â”€â–º Market Rollover (`markets`, `snapshot`, `predict BTC/ETH`)
T+1min (e.g. 12:16 PDT)  â”€â”€â–º Patient Limit Order Submission (`buy ASSET SIDE N LIMIT`)
T+13min (e.g. 12:28 PDT) â”€â”€â–º Pre-Expiration Status Check (`positions`, `snapshot`)
T+15min (e.g. 12:30 PDT) â”€â”€â–º Market Expiry & Auto-Settlement (`settlement`, `wallet`)
T+16min (e.g. 12:31 PDT) â”€â”€â–º Clean Exit & Log Archival (`exit`)
```

---

## 4. Patient Limit Order Execution Strategy (Adaptation Protocol)

To maintain positive expected value and avoid overpaying for contracts:

1. **Never buy Market NO/YES at > 65Â¢** unless confidence is $>90\%$. Paying 75Â¢+ creates a 3:1 negative risk/reward ratio where a single loss wipes out 3 wins.
2. **Use Patient Limit Orders (`buy ASSET SIDE N LIMIT_CENTS`):**
   - Place limit orders at a discount to current midpoints (e.g., target 45Â¢â€“50Â¢ entries).
   - Example: `buy BTC no 2 48` (Places a limit order for 2 NO contracts at 48Â¢).
3. **Execution Advantage:**
   - Limits cost to $\le \$0.96$ per 2-contract trade (vs $\$1.50+$ market orders).
   - Improves Risk/Reward ratio to $\sim 1.1:1$ profit-to-risk.
   - Amortizes Kalshi transaction fees ($\approx 1.75\text{Â¢}$ per contract/leg).

---

## 5. REPL Session Playbook

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

## 6. Supporting Reference Documents

- [`agents/onboarding_workflow.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/onboarding_workflow.md) â€” Skeptical pre-flight and repo map.
- [`agents/agents.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/agents.md) â€” Primary directives, tool inventory, and vessel rules.
- [`agents/todo.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/todo.md) â€” Current implementation backlog and active session log.
- [`agents/dev_log.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/dev_log.md) â€” Chronological development history and session autopsies.
- [`agents/overwatch_workflow.md`](file:///mnt/c/Users/itsji/ARBITR8DER/agents/overwatch_workflow.md) â€” Legacy Overwatch playbook reference.

