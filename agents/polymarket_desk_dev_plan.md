# Polymarket Desk Build Plan (`polymarket_desk`)

**Objective:** A high-speed, standalone Rust-based execution desk (`polymarket_desk`) for Polymarket's repeating 5-minute binary markets (BTC/ETH Up/Down). It pairs ultra-fast Rust Technical Analysis (TA) & candlestick pattern recognition with AI REPL/CLI trading oversight.

---

## 1. Core Architecture Principles

1. **Language:** Pure Rust (`cargo`) for high performance, deterministic concurrency, and minimal latency.
2. **Isolation:** Kept completely separate from `kalshi_desk/`. Dedicated credentials, WS connection pools, local runtime, and PnL accounting.
3. **Desk Cadence:** Optimized for Polymarket 5-minute repeating market cycles (`btc-updown-5m-*` and `eth-updown-5m-*`).
4. **Strategy:** 
   - High-frequency candle ingestion (Binance/Coinbase/Polymarket WS).
   - Rust-native Technical Analysis engine detecting classic candlestick & chart patterns (Engulfing, Doji, Reversals, Head & Shoulders, Wedges, Triangles).
   - Dynamic probability scoring fed into AI REPL / auto-trader.
5. **Vessel Model:** Inherits strict permissioning (`Full_Stop` $\rightarrow$ `Battery` $\rightarrow$ `Full_Forward` / PAPER Mode).

---

## 2. API & Market Research Reference

- **Polymarket Docs:** `https://docs.polymarket.com/`
- **CLOB API Base:** `https://clob.polymarket.com/`
- **Gamma Markets API:** `https://gamma-api.polymarket.com/`
- **Target Market Slugs:**
  - BTC 5-Min Up/Down: `btc-updown-5m-{timestamp}`
  - ETH 5-Min Up/Down: `eth-updown-5m-{timestamp}`

---

## 3. Phase Breakdown Plan

### Phase 1: Rust Desk Foundation & Environment Setup
- Initialize Cargo binary project in `polymarket_desk/` (`Cargo.toml`).
- Setup configuration loader for root `.env` (Polymarket API Key, Secret, Passphrase, Polygon Wallet Address/PK).
- Establish CWD-independent path resolver for `polymarket_desk/runtime/` (data, state, logs).
- Implement basic CLI entrypoint (`poly` or `polymarket_desk`).

### Phase 2: Live Ingestion & Data Engine (Rust Tokio)
- Websocket client for Polymarket CLOB (orderbook, trades, order updates).
- Spot price feed integrations (Binance/Coinbase WebSocket for real-time 1s/5s/1m/5m candles).
- Live state snapshot engine (`HotSnapshot`).

### Phase 3: Technical Analysis & Candlestick Pattern Engine
- Fast Rust TA module:
  - Moving Averages (EMA/SMA), RSI, MACD, Bollinger Bands.
  - Candlestick pattern recognition algorithms (Engulfing, Doji, Hammer, Morning/Evening Star, Three White Soldiers/Three Black Crows).
  - Chart pattern detection heuristics (Double Top/Bottom, Wedges, Triangles).
- Signal scoring pipeline producing 5-minute direction probabilities.

### Phase 4: Order Execution & Risk Controls (CTF Exchange / CLOB)
- Polymarket L1/L2 EIP-712 order signing implementation in Rust.
- Paper trading venue adapter with real-time orderbook depth matching.
- Pre-trade risk controller (max position size, max drawdown, exposure per 5m market).

### Phase 5: AI REPL & Auto-Trader Loop
- Interactive CLI/REPL for AI operator commands (`snapshot`, `predict`, `buy`, `sell`, `positions`, `autotrade`).
- Auto-trading engine for 5-minute market entry/exit execution.

---

## 4. Immediate Next Steps / User Alignment

- [ ] Confirm cargo package name & CLI binary name (`poly` or `polymarket_desk`).
- [ ] Review environment key requirements (Polygon wallet PK, API key/secret/passphrase).
- [ ] Align on initial TA indicators and pattern sensitivity thresholds.
