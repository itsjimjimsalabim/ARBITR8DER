# ARBITR8DER Trading Studio

Local AI trading studio for Kalshi 15-minute binary event markets.

## Install

```bash
cd ARBITR8DER
pip install -e ./kalshi_desk
```

## CLI

```bash
arbitr8der version          # show version
arbitr8der status           # vessel state + connections
arbitr8der snapshot         # live HotSnapshot
arbitr8der predict          # BTC/ETH prediction
arbitr8der forward start    # interactive REPL
# In the REPL:
#   autotrade on|off|status  # toggle the shared background paper auto-trader
```

## First-time setup

1. Copy `kalshi_desk/.env.example` to `kalshi_desk/.env`
2. Copy `streams/kalshi_private.pem` to `kalshi_desk/streams/kalshi_private.pem`
3. Set `AR8_KALSHI_API_KEY_ID` in `.env` (UUID from Kalshi dashboard)
4. `arbitr8der status` to verify

No email/password needed — Kalshi auth is API key + RSA-PSS signing only.

## Connection Status (2026-07-23)

| Source | Status | Notes |
|--------|--------|-------|
| Binance REST | WORKING | Candle backfill (72h of 1m candles) |
| Binance WS | GEO-BLOCKED | HTTP 451 from WSL; REST fallback works |
| Coinbase WS | WORKING | Real-time BTC/ETH ticker stream |
| Coinbase REST | WORKING | Historical candle backfill |
| Polymarket | WORKING | Sentiment polling for BTC price markets |
| CoinGecko | WORKING | BTC/ETH market cap, volume, 24h change |
| Kalshi REST | WORKING | Market discovery (KXBTC15M, KXETH15M) |
| Kalshi WS | WORKING | Live order book (~280 msg/sec) |

Run: `python -m pytest tests/test_connection_battery.py -v -s` (8 passed, 1 skipped)

## Project structure

```
kalshi_desk/
  pyproject.toml                 <- package metadata, deps, entry points
  kalshi_desk_package/            <- importable package
    __init__.py                  <- version
    config/                      <- typed settings (pydantic-settings)
    cli/                         <- typer entrypoint
    data_sources/                <- Polymarket, Binance, Coinbase, Coingecko, Kalshi
    execution/                   <- order routing, position tracking
    risk/                        <- limits, drawdown circuit breakers
    reconciliation/              <- trade journal, settlement
  tests/
  scripts/
  runtime/                       <- DB, logs, archives, state (gitignored)
```

## Safety

- Default mode: `paper` (no live trades)
- Default wallet: `hold` (no orders sent)
- Live trading requires explicit operator action
