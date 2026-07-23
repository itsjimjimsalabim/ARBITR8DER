# Fixes and Learnings — 2026-07-17 After 12:45 Session

## Changes Made

### 1. Binance WebSocket Fix (`binance_websocket_spot_price_stream.py`)
- **Problem**: Binance WS showed `connected: true` but `message_count: 0` in every session.
  Live spot data only arrived via REST seed snapshots, never via WS stream.
- **Root cause**: Using `stream.binance.us:9443/ws` (Binance US endpoint) which may not
  support the same stream types as `stream.binance.com`. Also, the subscription
  acknowledgment was never read — data may have been blocked waiting for the ack.
- **Fix**:
  - Switched default WS URL from `stream.binance.us` to `stream.binance.com` (international)
  - Added `conn.recv(timeout=5)` to read subscription acknowledgment after SUBSCRIBE
  - Added `@miniTicker` stream alongside `@ticker` and `@bookTicker` for redundancy
- **Note**: The `@miniTicker` stream has no bid/ask, only close price. `@bookTicker` has
  only best bid/ask, no close price. `@ticker` (24hr rolling) has both. Between the three,
  at least one should deliver useful data.

### 2. Strike Price Resolution (`full_forward_mode_ai_trading_session.py`)
- **Problem**: `active_universe` always showed `strike: 0`. The `list_tickers()` method
  returns basic market info but may not include the `strike` field. Without strike, the
  Black-Scholes edge model returns `edge=-999.0c reason=no strike or spot` for every
  opportunity.
- **Fix**: Added `fetch_market(ticker)` call after `list_tickers()` to retrieve full
  market detail including `strike`, `yes_ask_cents`, `no_ask_cents`, and `close_time`.
  This is called once per discovered ticker during universe loading.
- **Note**: `fetch_market()` is an authenticated call so it requires API keys. This is
  fine since we always have them for the session.

### 3. Limit Order System (`trade_execution_and_inventory_engine.py`, `paper_and_live_position_inventory.py`)
- **New feature**: Full limit order support for PAPER trading.
- **How it works**:
  - When AI calls `buy ETH NO 3 15` (buy 3 NO at 15¢ limit), and the market ask is
    above 15¢, a `PendingLimitOrder` is created instead of rejecting the order
  - The pending order is stored in `PaperInventory._pending_limit_orders`
  - On every `snapshot()` call (including when AI reads data or checks positions),
    `_fill_pending_limit_orders()` checks if the market ask has dropped to or below
    the limit price
  - If yes, the order fills: a `PaperPosition` is created, balance is deducted,
    and a "LIMIT ORDER FILLED" message is printed
  - The AI can check pending orders via the new `pending` REPL command
- **Commands**: `buy ETH YES 3 15` still works; when the market ask is above 15¢,
  it now places a persistent limit order instead of rejecting. When ask ≤ 15¢, the
  order fills on the next snapshot.
- **Pending order persistence**: Only in-memory within a session (matches existing
  PaperPosition behavior). New sessions start fresh with the live balance.

### 4. Minimum 2 Contracts Per Order (enforced in both REPL + engine)
- **Problem**: Kalshi fees make single-contract trades unprofitable. At 50¢, fee per
  contract is ~1.75¢. Round trip = ~3.5¢. On a 1-contract trade with 50¢ capital,
  fees eat 7% of position.
- **Fix**: Added `contracts < 2` check in both `_cmd_buy()` (REPL) and `enter_trade_ai()`
  (engine). Error: "Minimum 2 contracts per order (fees)". Also raised
  `min_contract_floor` from 1 to 2 in `evaluate_trade()` opportunity detection.

## Kalshi Limit Order API Reference
From Kalshi docs (docs.kalshi.com):

- **Endpoint**: `POST /portfolio/events/orders` (V2, preferred) or `POST /portfolio/orders` (legacy)
- **Method**: Authenticated POST with RSA signature headers
- **Request body**:
```json
{
  "ticker": "KXBTC15M-26JUL171600-00",
  "side": "bid",
  "count": "1",
  "price": "0.1500",
  "time_in_force": "good_till_canceled",
  "self_trade_prevention_type": "taker_at_cross",
  "client_order_id": "<uuid>"
}
```
- **Price format**: Fixed-point dollar string (e.g., "0.1500" = 15¢). Must be 1-99¢.
- **Side**: "bid" = buy YES, "ask" = sell YES. For NO contracts, use the opposite
  (buying NO = asking NO, which is equivalent to bidding on YES at complementary price).
- **Time in force**: `good_till_canceled`, `fill_or_kill`, `immediate_or_cancel`
- **Max open orders**: 200,000 per user
- **Rate limit**: 100 tokens per request
- **Client order ID**: UUID for deduplication. Resubmit same UUID on network failure
  to prevent double orders.
- **Response**: `order_id`, `remaining_count`, status
- **Amend**: `POST /portfolio/events/orders/{order_id}/amend`
- **Cancel**: `DELETE /portfolio/events/orders/{order_id}`
- **Status check**: Via WebSocket order/fill stream

Our PAPER limit order simulation mirrors this flow: place at limit price, wait for
market to reach it, then fill. Real Kalshi limit orders would use the actual REST
endpoint when we're in ARMED mode.

## Remaining Gaps
- Binance WS fix is unverified (need to run a session to confirm messages flow)
- Strike price now fetched but Black-Scholes model also needs spot price, which
  requires working Binance WS + the `strike` field being properly parsed
- Limit order `pending` command works but there's no `cancel` command yet
- No `--script FILE` mode for non-interactive command sequences
