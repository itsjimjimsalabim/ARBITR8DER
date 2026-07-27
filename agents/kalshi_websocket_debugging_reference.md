# Kalshi WebSocket Debugging Reference

## Auth: RSA-PSS Signed HTTP Headers

Kalshi WS auth is **pure RSA-PSS signing** — no JWT, no email/password, no OAuth tokens.
User logs in via Google on the web, but the API uses API key + private key PEM.

### Required Headers
```
KALSHI-ACCESS-KEY: <UUID API key ID>
KALSHI-ACCESS-TIMESTAMP: <epoch milliseconds as string>
KALSHI-ACCESS-SIGNATURE: <base64 RSA-PSS-SHA256 signature>
Content-Type: application/json
```

### Signing Algorithm
```python
import time, base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

timestamp_ms = str(int(time.time() * 1000))
message = (timestamp_ms + "GET" + "/trade-api/ws/v2").encode("utf-8")

signature = private_key.sign(
    message,
    padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=hashes.SHA256().digest_size,  # 32 bytes, NOT MAX_LENGTH
    ),
    hashes.SHA256(),
)
```

### Critical Gotchas
1. **Salt length**: Must be `hashes.SHA256().digest_size` (32 bytes). Using `padding.PSS.MAX_LENGTH` produces a different signature that Kalshi rejects.
2. **Path in signature**: Use the WS path `/trade-api/ws/v2` (no query params, no `/trade-api/v2` prefix).
3. **websockets library**: Async API uses `extra_headers`. Sync API uses `additional_headers`. Mixing them causes `TypeError`.
4. **No subaccount needed** for basic use. If needed, append `?subaccount=N` to URL but do NOT include it in the signed path.

---

## Subscribe Message Format

Kalshi API v2 uses a `cmd`-based protocol, NOT the `type`/`channels` format.

### Correct Format
```json
{
  "id": 1,
  "cmd": "subscribe",
  "params": {
    "channels": ["orderbook_delta"],
    "market_tickers": ["KXBTC15M-26JUL232215-15"],
    "use_yes_price": true
  }
}
```

### Wrong Format (will fail with "Unknown command")
```json
{
  "type": "subscribe",
  "channels": [{"name": "orderbook_delta", "symbols": ["TICKER"]}]
}
```

### Response
```json
{"type": "subscribed", "id": 1, "msg": {"channel": "orderbook_delta", "sid": 1}}
```

---

## Message Formats

### Order Book Snapshot
```json
{
  "type": "orderbook_snapshot",
  "sid": 1,
  "seq": 1,
  "msg": {
    "market_ticker": "KXBTC15M-26JUL232215-15",
    "market_id": "d6a55151-...",
    "yes_dollars_fp": [["0.5500", "100.00"], ["0.5400", "200.00"]],
    "no_dollars_fp": [["0.4500", "80.00"], ["0.4400", "120.00"]]
  }
}
```

- `yes_dollars_fp` / `no_dollars_fp`: Arrays of `[price_string, quantity_string]`
- Prices in **dollars** (e.g., "0.5500" = 55 cents), NOT cents
- Quantities as fp strings (e.g., "100.00" = 100 contracts)
- `seq` is at the TOP level (not inside `msg`)

### Order Book Delta
```json
{
  "type": "orderbook_delta",
  "sid": 1,
  "seq": 42,
  "msg": {
    "market_ticker": "KXBTC15M-26JUL232215-15",
    "market_id": "d6a55151-...",
    "price_dollars": "0.5600",
    "delta_fp": "-458.00",
    "side": "yes",
    "ts": "2026-07-24T02:00:01.000000Z",
    "ts_ms": 1784858401000
  }
}
```

- `price_dollars`: Price level affected (string, in dollars)
- `delta_fp`: Change in quantity (negative = removed, positive = added)
- `side`: "yes" or "no"
- `seq` is at the TOP level

### Error
```json
{"type": "error", "msg": {"code": 5, "msg": "Unknown command"}}
```

---

## Market Discovery

Use REST to find active markets before subscribing:
```python
from arbitr8der_package.data_sources.kalshi_rest_market_discovery_client import KalshiRestMarketDiscoveryClient

client = KalshiRestMarketDiscoveryClient()
markets = await client.discover_active_markets()
# Returns: KXBTC15M-26JUL232215-15, KXETH15M-26JUL232215-15, etc.
```

### Ticker Format
- Pattern: `KXBTC15M-26JUL232215-15` (BTC) or `KXETH15M-26JUL232215-15` (ETH)
- `26JUL232215` = date+time (July 26, 23:25 = 7:25 PM ET)
- `-15` = 15-minute duration
- New tickers generated every 15 minutes

---

## Data Files
- Private key PEM: `trading_studio/streams/kalshi_private.pem`
- API key ID: in `trading_studio/.env` as `AR8_KALSHI_API_KEY_ID`
- All keys consolidated: `agents/KEYS`

---

## Lessons Learned

1. **Never assume API format** — the old code used `websockets.sync.client` which has different parameter names than the async API.
2. **Test auth separately** — connect, subscribe, and log the first message before assuming the book works.
3. **Prices in dollars, not cents** — Kalshi API v2 uses dollar strings internally; convert to cents for display.
4. **Sequence numbers are top-level** — not inside `msg`, at the same level as `type` and `sid`.
5. **The old ARBITR8DER code is the source of truth** — it had working Kalshi WS auth with RSA-PSS signing. The new code was written from incomplete API docs and got the subscribe format wrong.

---

## Production Operational Patterns (from old ARBITR8DER)

These are battle-tested patterns from the old ARBITR8DER codebase (`old_ARBITR8DER/`) that are relevant to keeping the Kalshi WS stable in production.

### Stream Stability Monitoring

From `analysis/archive_stream_stability_report.py`:
- Critical streams: `("kalshi.orderbook_ws", "binance.ws", "coinbase.ws")`
- Max reconnects allowed: 1
- Max quarantines allowed: 10 (CLI default: 0)
- Max waiting state: 0
- Warmup grace period: 30 seconds
- Sustained-waiting threshold: 6 seconds
- Quarantine check specifically looks for "quarantined" in health detail text for `kalshi.orderbook_ws`

### Quarantine Churn Problem

From `docs/LIVE_TRADING_DEBUGGING_LOG.md`:
- Archives logged 114+ quarantine events and 98 blocking quarantines after warmup
- Root cause: stream scorer flags `critical_stream_quarantines` and `stream_not_ready`
- Fix: exposed obsolete Kalshi WebSocket price-scale handling, now requests unified YES pricing and normalizes NO levels internally

### Subscription Churn and Watchdog

From `streams/kalshi_orderbook_stream.py`:
- Deep ITM/OTM markets often have zero orders on the losing side — requiring both sides caused ~80% of subscribed tickers to appear missing
- Subscription churn can trigger watchdog disconnects, so subscription updates are rate-limited (min 2s between changes)
- Watchdog idle timeout forces reconnection when no messages received for configurable seconds
- Subscription ACK timeout (default 15s) raises to trigger reconnect

### Error Handling and Retry Patterns

From `streams/kalshi_client.py`:
- Exponential backoff retries on transient HTTP errors (429, 500, 502-504): waits of 0, 0.5, 2, 5, 10 seconds
- WS auto-reconnect in `while self._running` loop with `_sleep_backoff()`
- `_RateLimiter` class: 15 rps for REST, 8 default
- Order reconciliation: if POST gets HTTP 599 but had `client_order_id`, search for order by ID to avoid duplicate placement

### Legacy Price Scale Fix

From `docs/DEVELOPMENT_ATLAS.md` (lines 58-62):
- Subscription ACK/sequence requirements must be met before processing
- Orderbook replacement churn from overlapping ladder updates
- Deprecated legacy WS price toggle: now uses unified YES pricing with internal NO normalization

### Stream Soak Testing

From `run/live_battery_stream_soak.py`:
- Checks `stream_events` for live status per stream name before launching vessels
- Uses the same critical streams list as the stability evaluator
