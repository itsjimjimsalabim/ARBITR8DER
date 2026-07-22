# Fixes and Learnings — 2026-07-17 After 12:45 Session

## Changes Made

### 1. Binance WebSocket Fix
- Problem: WS showed connected but no messages
- Root cause: Using stream.binance.us which may not support same streams
- Fix: Switched to stream.binance.com, added SUBSCRIBE ack read, added @miniTicker

### 2. Strike Price Resolution
- Problem: active_universe always showed strike: 0
- Fix: Added fetch_market(ticker) after list_tickers() for full market detail
- Note: fetch_market() is authenticated, requires API keys

### 3. Limit Order System
- Built from scratch: table, submit, check_and_fill, paper_and_live
- Atomic DB operations via context managers with proper error handling
- PAPER orders fill at yes_ask_cents, live orders at limit price

### 4. Paper Auto-Closer
- 30-minute expiration with Polymarket resolution check
- Atomic DB operations, deduplication, stale-price fallback
- New CLI command: `paper-close-resolved`

### 5. Engine Integration
- load_active_universe: auto-fills missing strikes via fetch_market()
- check_and_fill_pending_orders: called each tick
- check_and_close_30min: called each tick
- Added _safe_exit helper for exception handling in threads

### 6. .env Changes
- All timeouts changed from 3min to 30min
- Added paper trading env vars
- Added universe refresh and heartbeat intervals
