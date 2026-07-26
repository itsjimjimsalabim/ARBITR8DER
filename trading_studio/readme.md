# ARBITR8DER Trading Studio

Local AI trading studio for Kalshi 15-minute binary event markets.

## Install

```bash
cd ARBITR8DER
pip install -e ./trading_studio
```

## CLI

```bash
arb version          # show version
arb status           # vessel state + connections
arb snapshot         # live HotSnapshot
arb predict          # BTC/ETH prediction
arb forward start    # interactive REPL
# In the REPL:
#   autotrade on|off|status  # toggle the shared background paper auto-trader
```

## First-time setup

1. Copy `trading_studio/.env.example` to `trading_studio/.env`
2. Copy `streams/kalshi_private.pem` to `trading_studio/streams/kalshi_private.pem`
3. Set `AR8_KALSHI_API_KEY_ID` in `.env` (UUID from Kalshi dashboard)
4. `arb status` to verify

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
trading_studio/
  pyproject.toml                 <- package metadata, deps, entry points
  arbitr8der_package/            <- importable package
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
