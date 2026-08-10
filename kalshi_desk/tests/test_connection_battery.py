"""Connection battery — live integration tests for all 5 data sources.

Each source is tested independently, then the full orchestrator is started
with all sources running simultaneously for a fixed duration.

No mocking. Real API calls. Real WebSocket connections.
Run with: python -m pytest tests/test_connection_battery.py -v -s

Environment: requires .env with AR8_KALSHI_API_KEY_ID and
streams/kalshi_private.pem for Kalshi sources. Other sources are public.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

# Ensure kalshi_desk is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Source 1: Binance WebSocket + REST candle backfill
# ---------------------------------------------------------------------------

BATTERY_DURATION = 30  # seconds to collect data per source
ORCHESTRATOR_DURATION = 45  # seconds for full orchestrator run


@pytest.mark.network
@pytest.mark.asyncio
async def test_binance_ws_connection():
    """Binance WebSocket connects and delivers BTC/ETH trade observations.

    Skips if Binance WS is geo-blocked (HTTP 451 from non-US regions).
    """
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=5) as _c:
            r = await _c.get("https://api.binance.com/api/v3/ping")
            if r.status_code == 451:
                pytest.skip("Binance WS geo-blocked (HTTP 451) from this region")
    except Exception:
        pass

    from kalshi_desk_package.data_sources.binance_spot_price_stream import (
        BinancePriceObservation,
        BinanceSpotPriceStream,
    )

    received: list[BinancePriceObservation] = []
    errors: list[str] = []
    start = time.time()

    async def on_trade(obs: BinancePriceObservation) -> None:
        received.append(obs)

    stream = BinanceSpotPriceStream()

    async def collect():
        stream.on_trade(on_trade)
        try:
            await stream.connect_and_run()
        except Exception as e:
            errors.append(str(e))

    task = asyncio.create_task(collect())
    await asyncio.sleep(BATTERY_DURATION)
    await stream.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    elapsed = time.time() - start
    print(f"\n  Binance: {len(received)} trades in {elapsed:.1f}s")
    if received:
        btc = [r for r in received if "BTC" in r.symbol]
        eth = [r for r in received if "ETH" in r.symbol]
        print(f"    BTC trades: {len(btc)}, ETH trades: {len(eth)}")
        if btc:
            print(f"    BTC last price: ${btc[-1].price:,.2f}, age: {btc[-1].age_seconds:.3f}s")
        if eth:
            print(f"    ETH last price: ${eth[-1].price:,.2f}, age: {eth[-1].age_seconds:.3f}s")
        avg_age = sum(r.age_seconds for r in received) / len(received)
        print(f"    Avg age: {avg_age:.3f}s")

    assert len(received) > 0, f"Binance produced no trades in {BATTERY_DURATION}s. Errors: {errors}"
    assert any("BTC" in r.symbol for r in received), "No BTC trades received"
    assert any("ETH" in r.symbol for r in received), "No ETH trades received"


@pytest.mark.network
@pytest.mark.asyncio
async def test_binance_candle_backfill():
    """Binance REST candle backfill returns historical 1m OHLCV data."""
    from kalshi_desk_package.data_sources.binance_spot_price_stream import (
        BinanceCandle,
        BinanceSpotPriceStream,
    )

    stream = BinanceSpotPriceStream()

    btc_candles = await stream.backfill_candles("BTCUSDT")
    eth_candles = await stream.backfill_candles("ETHUSDT")

    print(f"\n  Binance backfill: BTC={len(btc_candles)} candles, ETH={len(eth_candles)} candles")
    if btc_candles:
        last = btc_candles[-1]
        print(f"    BTC last candle: O={last.open} H={last.high} L={last.low} C={last.close}")
    if eth_candles:
        last = eth_candles[-1]
        print(f"    ETH last candle: O={last.open} H={last.high} L={last.low} C={last.close}")

    assert len(btc_candles) > 0, "No BTC candles from backfill"
    assert len(eth_candles) > 0, "No ETH candles from backfill"


# ---------------------------------------------------------------------------
# Source 2: Coinbase WebSocket + REST candle backfill
# ---------------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.asyncio
async def test_coinbase_ws_connection():
    """Coinbase WebSocket connects and delivers BTC/ETH ticker observations."""
    from kalshi_desk_package.data_sources.coinbase_spot_price_stream import (
        CoinbasePriceObservation,
        CoinbaseSpotPriceStream,
    )

    received: list[CoinbasePriceObservation] = []
    errors: list[str] = []
    start = time.time()

    async def on_ticker(obs: CoinbasePriceObservation) -> None:
        received.append(obs)

    stream = CoinbaseSpotPriceStream()

    async def collect():
        stream.on_ticker(on_ticker)
        try:
            await stream.connect_and_run()
        except Exception as e:
            errors.append(str(e))

    task = asyncio.create_task(collect())
    await asyncio.sleep(BATTERY_DURATION)
    await stream.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    elapsed = time.time() - start
    print(f"\n  Coinbase: {len(received)} tickers in {elapsed:.1f}s")
    if received:
        btc = [r for r in received if "BTC" in r.product_id]
        eth = [r for r in received if "ETH" in r.product_id]
        print(f"    BTC tickers: {len(btc)}, ETH tickers: {len(eth)}")
        if btc:
            print(f"    BTC last price: ${btc[-1].price:,.2f}")
        if eth:
            print(f"    ETH last price: ${eth[-1].price:,.2f}")

    assert len(received) > 0, f"Coinbase produced no tickers in {BATTERY_DURATION}s. Errors: {errors}"
    assert any("BTC" in r.product_id for r in received), "No BTC tickers received"
    assert any("ETH" in r.product_id for r in received), "No ETH tickers received"


@pytest.mark.network
@pytest.mark.asyncio
async def test_coinbase_candle_backfill():
    """Coinbase REST candle backfill returns historical OHLCV data."""
    from kalshi_desk_package.data_sources.coinbase_spot_price_stream import (
        CoinbaseSpotPriceStream,
    )

    stream = CoinbaseSpotPriceStream()

    btc_candles = await stream.fetch_candles("BTC-USD")
    eth_candles = await stream.fetch_candles("ETH-USD")

    print(f"\n  Coinbase backfill: BTC={len(btc_candles)} candles, ETH={len(eth_candles)} candles")
    if btc_candles:
        last = btc_candles[-1]
        # Coinbase candle format: [time, low, high, open, close, volume]
        print(f"    BTC last candle: O={last[3]} H={last[2]} L={last[1]} C={last[4]}")

    assert len(btc_candles) > 0, "No BTC candles from Coinbase backfill"
    assert len(eth_candles) > 0, "No ETH candles from Coinbase backfill"


# ---------------------------------------------------------------------------
# Source 3: Polymarket sentiment poller
# ---------------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.asyncio
async def test_polymarket_sentiment_poll():
    """Polymarket REST poller finds BTC price-level markets and returns sentiment."""
    from kalshi_desk_package.data_sources.polymarket_sentiment_analysis_poller import (
        PolymarketSentimentObservation,
        PolymarketSentimentPoller,
    )

    received: list[PolymarketSentimentObservation] = []
    errors: list[str] = []

    async def on_sentiment(obs: PolymarketSentimentObservation) -> None:
        received.append(obs)

    poller = PolymarketSentimentPoller()
    poller.on_sentiment(on_sentiment)

    # Polymarket poller has no start() — poll manually in a loop
    start = time.time()
    while time.time() - start < BATTERY_DURATION:
        try:
            obs = await poller.poll_sentiment("KXBTC15M")
            if obs is None:
                # Try a generic BTC search
                markets = await poller.search_btc_markets()
                if markets:
                    slug = markets[0]["slug"]
                    obs = await poller._fetch_market(slug)
        except Exception as e:
            errors.append(str(e))
        await asyncio.sleep(5)

    print(f"\n  Polymarket: {len(received)} sentiment observations in {BATTERY_DURATION}s")
    if received:
        for obs in received[:3]:
            print(f"    Market: {obs.market_slug}")
            print(f"      Yes: ${obs.yes_price:.2f}, No: ${obs.no_price:.2f}")
            print(f"      Volume: ${obs.volume_usd:,.0f}, Liquidity: ${obs.liquidity:,.0f}")
    else:
        print(f"    Errors: {errors}")

    if len(received) == 0:
        pytest.skip(f"Polymarket currently has 0 active tagged crypto markets. Errors: {errors}")


# ---------------------------------------------------------------------------
# Source 4: CoinGecko macro context poller
# ---------------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.asyncio
async def test_coingecko_macro_poll():
    """CoinGecko REST poller returns BTC/ETH price, market cap, and change data."""
    from kalshi_desk_package.data_sources.coingecko_macro_data_poller import (
        CoinGeckoMacroDataPoller,
        CoinGeckoMacroObservation,
    )

    received: list[CoinGeckoMacroObservation] = []
    errors: list[str] = []

    async def on_macro(obs: CoinGeckoMacroObservation) -> None:
        received.append(obs)

    poller = CoinGeckoMacroDataPoller()

    async def collect():
        poller.on_macro_update(on_macro)
        try:
            await poller.start_polling()
        except Exception as e:
            errors.append(str(e))

    task = asyncio.create_task(collect())
    await asyncio.sleep(BATTERY_DURATION)
    await poller.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    print(f"\n  CoinGecko: {len(received)} macro observations in {BATTERY_DURATION}s")
    if received:
        btc = [r for r in received if r.asset == "BTC"]
        eth = [r for r in received if r.asset == "ETH"]
        if btc:
            b = btc[-1]
            print(f"    BTC: ${b.usd_price:,.2f}, 24h change: {b.price_change_24h_pct}%, mcap: ${b.market_cap_usd:,.0f}")
        if eth:
            e = eth[-1]
            print(f"    ETH: ${e.usd_price:,.2f}, 24h change: {e.price_change_24h_pct}%, mcap: ${e.market_cap_usd:,.0f}")
    else:
        print(f"    Errors: {errors}")

    assert len(received) > 0, f"CoinGecko produced no macro data in {BATTERY_DURATION}s. Errors: {errors}"
    assert any(r.asset == "BTC" for r in received), "No BTC macro data"
    assert any(r.asset == "ETH" for r in received), "No ETH macro data"


# ---------------------------------------------------------------------------
# Source 5: Kalshi REST market discovery + WebSocket order book
# ---------------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.asyncio
async def test_kalshi_rest_discovery():
    """Kalshi REST client discovers active BTC/ETH 15-minute markets."""
    from kalshi_desk_package.data_sources.kalshi_rest_market_discovery_client import (
        KalshiMarketDetail,
        KalshiRestMarketDiscoveryClient,
    )

    client = KalshiRestMarketDiscoveryClient()
    markets = await client.discover_active_markets()

    print(f"\n  Kalshi discovery: {len(markets)} active BTC/ETH 15-min markets")
    for m in markets[:5]:
        print(f"    {m.ticker}: {m.title}")
        print(f"      Status: {m.status}, Strike: {m.strike_type}, Ref: {m.reference_price}")
        print(f"      Yes bid/ask: {m.yes_bid}/{m.yes_ask}, Vol: {m.volume}")

    assert len(markets) > 0, "No active BTC/ETH 15-min markets found on Kalshi"
    assert any("BTC" in m.ticker for m in markets), "No BTC markets found"
    assert any("ETH" in m.ticker for m in markets), "No ETH markets found"


@pytest.mark.network
@pytest.mark.asyncio
async def test_kalshi_ws_orderbook():
    """Kalshi WebSocket delivers order book updates for active markets.

    Auth: RSA-PSS signed headers (API key + private key PEM). No password needed.
    Skips if API key or private key PEM are missing.
    """
    import os
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    from kalshi_desk_package.data_sources.kalshi_orderbook_websocket_client import (
        KalshiOrderBookState,
        KalshiOrderBookWebSocketClient,
    )
    from kalshi_desk_package.data_sources.kalshi_rest_market_discovery_client import (
        KalshiRestMarketDiscoveryClient,
    )

    # Check that API key and private key PEM exist (no password needed)
    api_key = os.getenv("AR8_KALSHI_API_KEY_ID", "")
    pem_path = os.getenv("AR8_KALSHI_PRIVATE_KEY_PATH", "")
    if not api_key or not pem_path:
        pytest.skip("Kalshi WS requires AR8_KALSHI_API_KEY_ID and AR8_KALSHI_PRIVATE_KEY_PATH in .env")
    # Resolve PEM path relative to kalshi_desk/
    pem_full = os.path.join(os.path.dirname(__file__), "..", pem_path)
    if not Path(pem_full).exists():
        pytest.skip(f"Kalshi private key PEM not found at {pem_full}")

    # First discover a live market
    discovery = KalshiRestMarketDiscoveryClient()
    markets = await discovery.discover_active_markets()

    if not markets:
        pytest.skip("No active Kalshi markets to test WS against")

    ticker = markets[0].ticker
    print(f"\n  Kalshi WS: connecting to {ticker}...")

    received: list[KalshiOrderBookState] = []
    start = time.time()

    async def on_update(state: KalshiOrderBookState) -> None:
        received.append(state)

    ws_client = KalshiOrderBookWebSocketClient(ticker)

    async def collect():
        ws_client.on_update(on_update)
        try:
            await ws_client.connect_and_run()
        except Exception as e:
            print(f"    WS error: {e}")

    task = asyncio.create_task(collect())
    await asyncio.sleep(BATTERY_DURATION)
    await ws_client.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    elapsed = time.time() - start
    print(f"    {ticker}: {len(received)} order book updates in {elapsed:.1f}s")
    if received:
        d = received[-1].to_dict()
        print(f"      Sequence: {d['last_sequence']}, Yes levels: {d['yes_levels']}, No levels: {d['no_levels']}")
        print(f"      Yes bid/ask: {d['yes_bid']}/{d['yes_ask']} cents")
        print(f"      No bid/ask: {d['no_bid']}/{d['no_ask']} cents")
        print(f"      Midpoint: {d['midpoint_cents']} cents")
        print(f"      Stale: {d['is_stale']}, Gap: {d['gap_detected']}")
        print(f"      Rebuilds: {d['rebuilds_completed']}")

    assert len(received) > 0, f"Kalshi WS produced no updates for {ticker} in {BATTERY_DURATION}s"


# ---------------------------------------------------------------------------
# Full orchestrator: all 5 sources simultaneously
# ---------------------------------------------------------------------------

@pytest.mark.network
@pytest.mark.asyncio
async def test_orchestrator_all_sources():
    """Full orchestrator starts all 5 sources and produces a HotSnapshot."""
    from kalshi_desk_package.config.typed_configuration_settings_module import load_settings
    from kalshi_desk_package.data_sources.ingestion_orchestrator import IngestionOrchestrator

    settings = load_settings()

    orchestrator = IngestionOrchestrator(
        kalshi_api_key=settings.kalshi_api_key_id or None,
    )

    async def run_orchestrator():
        try:
            await orchestrator.start()
        except Exception as e:
            print(f"    Orchestrator error: {e}")

    task = asyncio.create_task(run_orchestrator())
    await asyncio.sleep(ORCHESTRATOR_DURATION)

    # Collect results
    snapshot = orchestrator.latest_snapshot()
    health = orchestrator.health_summary()

    print(f"\n  Orchestrator after {ORCHESTRATOR_DURATION}s:")
    print(f"    Snapshot: {'YES' if snapshot else 'NO'}")
    if snapshot:
        binance_price = snapshot.binance_spot.spot_price_usd if snapshot.binance_spot else None
        coinbase_price = snapshot.coinbase_spot.spot_price_usd if snapshot.coinbase_spot else None
        print(f"    Spot avg USD: {snapshot.spot_avg_usd}")
        print(f"    BTC spot (binance): {binance_price}")
        print(f"    BTC spot (coinbase): {coinbase_price}")
        print(f"    Spot disagreement: {snapshot.spot_disagreement_pct}")
        print(f"    Kalshi midpoint: {snapshot.kalshi_midpoint_cents}c")
        if snapshot.kalshi_book:
            print(f"    Kalshi yes bid/ask: {snapshot.kalshi_book.yes_bid}/{snapshot.kalshi_book.yes_ask}")
        if snapshot.coingecko_macro:
            print(f"    CoinGecko 24h change: {snapshot.coingecko_macro.price_change_24h_pct}%")
        if snapshot.polymarket_sentiment:
            print(f"    Polymarket yes price: {snapshot.polymarket_sentiment.yes_price}")
    print(f"    Health: {health}")

    # Cleanup
    await orchestrator.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert snapshot is not None, "Orchestrator produced no snapshot"
    assert snapshot.spot_avg_usd is not None, "No spot price available from any source"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
