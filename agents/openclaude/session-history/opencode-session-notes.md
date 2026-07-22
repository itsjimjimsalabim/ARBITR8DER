# OpenCode Session Notes — 2026-07-17 12:45

## Summary
First real debugging session after Claude Desktop gave up. OpenCode (Gemini model)
did all the work. ARBITR8DER went from broken to running.

## What Was Done
1. Found and fixed WebSocket endpoint (binance_us -> binance.com)
2. Fixed strike price resolution (added fetch_market() call)
3. Built limit order system from scratch
4. Added paper trading auto-closer for 30min expiration
5. Changed all timeout values across 6+ files

## Key Commands Run
- `python runtime_cli.py status` — showed Full_Stop
- `python runtime_cli.py start` — triggered emergency shutdown
- `python runtime_cli.py resume` — unlocked after engine changes
- `python runtime_cli.py paper-status` — showed $5000 balance
- `python runtime_cli.py paper-buy BTC YES $0.50 10 --market-id=270916`
- `python runtime_cli.py paper-sell 270916 $0.55`

## Binance WebSocket Fix
- Changed from `wss://stream.binance.us:9443/ws` to `wss://stream.binance.com/ws`
- Added `conn.recv(timeout=5)` for SUBSCRIBE ack
- Added @miniTicker stream for redundancy

## Limit Order System (NEW)
- `limit_orders` table in hot-state.db
- `engine.submit_limit_order()` -> returns order_id
- `check_and_fill_pending_orders(snap)` called each tick
- Fills at <= yes_ask (buys) or >= no_bid (sends)

## Auto-Closer
- `engine.check_and_close_30min()` runs every tick
- Finds PAPER fills where remaining_minutes < 30
- Checks Polymarket API for actual resolution
- Sets `exit_price`, `exit_reason`, `resolved_at`
- Deduplicates by checking existing exit_price

## Config Changes
- All time values in .env changed from 3min to 30min
- `STALENESS_THRESHOLD_SECONDS=1800`
- `RESOLUTION_TIMEOUT_MINUTES=28`
- `EXPIRATION_GRACE_SECONDS=60`
- All 6 `time.sleep(60)` -> `time.sleep(300)`
- Added `UNIVERSE_REFRESH_SECONDS=300`
- Added `HEARTBEAT_INTERVAL=180`

## .env Updates
```
PAPER_LIFECYCLE_MODE=auto
PAPER_MAX_POSITIONS=10
PAPER_MAX_EXPOSURE_USD=2000
PAPER_CIRCUIT_BREAKER_LOSSES=3
PAPER_BASE_BET_USD=100
PAPER_DEFAULT_PROBABILITY_THRESHOLD=0.6
```
