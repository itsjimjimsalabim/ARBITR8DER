"""Comprehensive unit tests for Phase 3 — Real provider contracts.

Tests cover parsing fixtures, state management, and offline behavior for:
  - Kalshi REST market discovery + order-book WebSocket state
  - Binance spot price stream + candle parsing
  - Coinbase spot price stream
  - Polymarket sentiment poller
  - CoinGecko macro data poller
"""

import asyncio
import json
import time

import pytest

from arbitr8der_package.data_sources.kalshi_rest_market_discovery_client import (
    KalshiMarketDetail,
    KalshiRestMarketDiscoveryClient,
)
from arbitr8der_package.data_sources.kalshi_orderbook_websocket_client import (
    KalshiOrderBookState,
    KalshiOrderBookWebSocketClient,
)
from arbitr8der_package.data_sources.binance_spot_price_stream import (
    BinanceCandle,
    BinancePriceObservation,
    BinanceSpotPriceStream,
)
from arbitr8der_package.data_sources.coinbase_spot_price_stream import (
    CoinbasePriceObservation,
    CoinbaseSpotPriceStream,
)
from arbitr8der_package.data_sources.polymarket_sentiment_analysis_poller import (
    PolymarketSentimentObservation,
    PolymarketSentimentPoller,
)
from arbitr8der_package.data_sources.coingecko_macro_data_poller import (
    CoinGeckoMacroObservation,
    CoinGeckoMacroDataPoller,
)


# =========================================================================
# Kalshi REST market discovery
# =========================================================================

class TestKalshiMarketDetail:
    def test_parse_fixture(self):
        raw = KalshiRestMarketDiscoveryClient.parse_fixture_market_response()["market"]
        detail = KalshiMarketDetail(raw)
        assert detail.ticker == "KXBTC15M-26JUL23-T15:00"
        assert detail.status == "open"
        assert detail.is_active is True
        assert detail.yes_bid == 55
        assert detail.yes_ask == 58
        assert detail.midpoint_cents == 56

    def test_is_active_closed(self):
        detail = KalshiMarketDetail({"ticker": "TEST", "status": "closed"})
        assert detail.is_active is False

    def test_midpoint_fallback_to_last_price(self):
        detail = KalshiMarketDetail({"ticker": "TEST", "last_price": 42})
        assert detail.midpoint_cents == 42

    def test_midpoint_none_when_no_data(self):
        detail = KalshiMarketDetail({"ticker": "TEST"})
        assert detail.midpoint_cents is None

    def test_to_dict(self):
        detail = KalshiMarketDetail({"ticker": "T1", "status": "open", "yes_bid": 50, "yes_ask": 52})
        d = detail.to_dict()
        assert d["ticker"] == "T1"
        assert d["yes_bid"] == 50

    def test_is_btc_or_eth_15m(self):
        assert KalshiRestMarketDiscoveryClient._is_btc_or_eth_15m("KXBTC15M-26JUL23-T15:00") is True
        assert KalshiRestMarketDiscoveryClient._is_btc_or_eth_15m("KXETH15M-26JUL23-T15:00") is True
        assert KalshiRestMarketDiscoveryClient._is_btc_or_eth_15m("KXBTC-26JUL23-T15:00") is False
        assert KalshiRestMarketDiscoveryClient._is_btc_or_eth_15m("RANDOM") is False


# =========================================================================
# Kalshi order-book state
# =========================================================================

class TestKalshiOrderBookState:
    def test_apply_snapshot(self):
        state = KalshiOrderBookState("KXBTC15M-26JUL232215-15")
        snapshot = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["msg"]
        snapshot["seq"] = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["seq"]
        state.apply_snapshot(snapshot)
        # yes_dollars_fp: ["0.5500"=55c, "0.5400"=54c, "0.5300"=53c]
        assert state.yes_bid == 55
        assert state.yes_ask == 53
        # no_dollars_fp: ["0.4500"=45c, "0.4400"=44c, "0.4300"=43c]
        assert state.no_bid == 45
        assert state.no_ask == 43
        assert state.last_sequence == 1
        assert state.is_stale is False
        assert state.rebuilds_completed == 1

    def test_apply_delta(self):
        state = KalshiOrderBookState("KXBTC15M-26JUL232215-15")
        snapshot = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["msg"]
        snapshot["seq"] = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["seq"]
        state.apply_snapshot(snapshot)
        delta = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_delta()["msg"]
        delta["seq"] = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_delta()["seq"]
        ok = state.apply_delta(delta)
        assert ok is True
        assert state.last_sequence == 2
        assert state.yes_bid == 56  # new level added at 0.5600 = 56 cents

    def test_sequence_gap_detection(self):
        state = KalshiOrderBookState("KXBTC15M-26JUL232215-15")
        snapshot = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["msg"]
        snapshot["seq"] = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["seq"]
        state.apply_snapshot(snapshot)
        # Delta with wrong sequence
        bad_delta = {"price_dollars": "0.5700", "delta_fp": "10.00", "side": "yes", "seq": 1005}
        ok = state.apply_delta(bad_delta)
        assert ok is False
        assert state.gap_detected is True
        assert state.is_stale is True

    def test_midpoint_calculation(self):
        state = KalshiOrderBookState("TEST")
        state.yes_bid = 55
        state.yes_ask = 58
        assert state.midpoint_cents == 56

    def test_midpoint_none_empty_book(self):
        state = KalshiOrderBookState("TEST")
        assert state.midpoint_cents is None

    def test_age_seconds(self):
        state = KalshiOrderBookState("TEST")
        assert state.age_seconds == float("inf")
        state.last_update_ts = time.time() - 5
        assert 4 < state.age_seconds < 6

    def test_to_dict(self):
        state = KalshiOrderBookState("TEST")
        d = state.to_dict()
        assert d["ticker"] == "TEST"
        assert d["rebuilds_completed"] == 0


# =========================================================================
# Binance spot price stream
# =========================================================================

class TestBinancePriceObservation:
    def test_from_fixture(self):
        raw = BinanceSpotPriceStream.parse_fixture_trade()
        obs = BinancePriceObservation(
            symbol=raw["s"],
            price=float(raw["p"]),
            quantity=float(raw["q"]),
            trade_ts=raw["T"] / 1000.0,
        )
        assert obs.symbol == "BTCUSDT"
        assert obs.price == 68123.45
        assert obs.quantity == 0.00123
        assert obs.age_seconds >= 0

    def test_to_dict(self):
        obs = BinancePriceObservation("ETHUSDT", 3500.0, 0.1, time.time())
        d = obs.to_dict()
        assert d["symbol"] == "ETHUSDT"
        assert d["price"] == 3500.0


class TestBinanceCandle:
    def test_parse_fixture(self):
        raw = BinanceSpotPriceStream.parse_fixture_candle()[0]
        candle = BinanceCandle(raw)
        assert candle.open == 68100.0
        assert candle.high == 68150.0
        assert candle.low == 68090.0
        assert candle.close == 68120.0
        assert candle.volume == 12.345
        assert candle.trades == 500

    def test_to_dict(self):
        raw = BinanceSpotPriceStream.parse_fixture_candle()[1]
        candle = BinanceCandle(raw)
        d = candle.to_dict()
        assert d["open"] == 68120.0
        assert "volume" in d


class TestBinanceSpotPriceStream:
    def test_fixture_trade_valid(self):
        raw = BinanceSpotPriceStream.parse_fixture_trade()
        assert raw["e"] == "trade"
        assert raw["s"] == "BTCUSDT"
        assert float(raw["p"]) > 0

    def test_fixture_candle_valid(self):
        candles = BinanceSpotPriceStream.parse_fixture_candle()
        assert len(candles) == 3
        for c in candles:
            assert len(c) >= 12


# =========================================================================
# Coinbase spot price stream
# =========================================================================

class TestCoinbasePriceObservation:
    def test_from_fixture(self):
        raw = CoinbaseSpotPriceStream.parse_fixture_ticker()
        obs = CoinbasePriceObservation(
            product_id=raw["product_id"],
            price=float(raw["price"]),
            bid=float(raw["bid"]) if "bid" in raw else None,
            ask=float(raw["ask"]) if "ask" in raw else None,
            volume_24h=float(raw["volume_24h"]) if "volume_24h" in raw else None,
            timestamp=raw["time"],
        )
        assert obs.product_id == "BTC-USD"
        assert obs.price == 68123.45
        assert obs.bid == 68120.0
        assert obs.ask == 68127.0

    def test_to_dict(self):
        obs = CoinbasePriceObservation("ETH-USD", 3500.0, 3499.0, 3501.0, 5000.0, "2026-07-23T18:50:00Z")
        d = obs.to_dict()
        assert d["product_id"] == "ETH-USD"
        assert d["price"] == 3500.0

    def test_age_seconds(self):
        obs = CoinbasePriceObservation("BTC-USD", 68000.0, None, None, None, "2026-07-23T18:50:00Z")
        age = obs.age_seconds
        assert age >= 0


class TestCoinbaseSpotPriceStream:
    def test_fixture_valid(self):
        raw = CoinbaseSpotPriceStream.parse_fixture_ticker()
        assert raw["type"] == "ticker"
        assert raw["product_id"] == "BTC-USD"
        assert float(raw["price"]) > 0


# =========================================================================
# Polymarket sentiment poller
# =========================================================================

class TestPolymarketSentimentObservation:
    def test_from_fixture(self):
        raw = PolymarketSentimentPoller.parse_fixture_market()
        obs = PolymarketSentimentObservation(
            market_slug=raw["slug"],
            condition_id=raw["conditionId"],
            question=raw["question"],
            yes_price=raw["tokens"][0]["price"],
            no_price=raw["tokens"][1]["price"],
            volume_usd=float(raw["volume"]),
            liquidity=float(raw["liquidity"]),
            end_date=raw["endDate"],
        )
        assert obs.yes_price == 0.62
        assert obs.no_price == 0.38
        assert obs.volume_usd == 125000.0

    def test_to_dict(self):
        obs = PolymarketSentimentObservation("slug", "0x123", "Q?", 0.5, 0.5, 1000.0, 500.0, None)
        d = obs.to_dict()
        assert d["market_slug"] == "slug"


class TestPolymarketSentimentPoller:
    def test_register_mapping(self):
        poller = PolymarketSentimentPoller()
        poller.register_mapping("KXBTC15M-26JUL23-T15:00", "will-bitcoin-exceed-68000")
        assert poller._market_mapping["KXBTC15M-26JUL23-T15:00"] == "will-bitcoin-exceed-68000"

    def test_fixture_valid(self):
        raw = PolymarketSentimentPoller.parse_fixture_market()
        assert "slug" in raw
        assert len(raw["tokens"]) == 2
        assert raw["active"] is True


# =========================================================================
# CoinGecko macro data poller
# =========================================================================

class TestCoinGeckoMacroObservation:
    def test_from_fixture(self):
        raw = CoinGeckoMacroDataPoller.parse_fixture_simple_price()["bitcoin"]
        obs = CoinGeckoMacroObservation(
            coin_id="bitcoin",
            asset="BTC",
            usd_price=raw["usd"],
            market_cap_usd=raw.get("usd_market_cap"),
            volume_24h_usd=raw.get("usd_24h_vol"),
            price_change_24h_pct=raw.get("usd_24h_change"),
            price_change_1h_pct=None,
        )
        assert obs.usd_price == 68123.45
        assert obs.market_cap_usd == 1_340_000_000_000
        assert obs.price_change_24h_pct == 2.34

    def test_to_dict(self):
        obs = CoinGeckoMacroObservation("bitcoin", "BTC", 68000.0, 1e12, 30e9, 1.5, None)
        d = obs.to_dict()
        assert d["asset"] == "BTC"
        assert d["usd_price"] == 68000.0


class TestCoinGeckoMacroDataPoller:
    def test_fixture_has_both_coins(self):
        raw = CoinGeckoMacroDataPoller.parse_fixture_simple_price()
        assert "bitcoin" in raw
        assert "ethereum" in raw
        assert raw["bitcoin"]["usd"] > 0
        assert raw["ethereum"]["usd"] > 0

    def test_coin_id_map(self):
        from arbitr8der_package.data_sources.coingecko_macro_data_poller import _COIN_ID_MAP
        assert _COIN_ID_MAP["BTC"] == "bitcoin"
        assert _COIN_ID_MAP["ETH"] == "ethereum"

    def test_last_observations_empty_initially(self):
        poller = CoinGeckoMacroDataPoller()
        assert poller.last_observations == {}


# =========================================================================
# Cross-provider consistency
# =========================================================================

class TestCrossProviderConsistency:
    """Verify fixtures use consistent asset names and prices are realistic."""

    def test_all_fixtures_btc_above_50k(self):
        # Kalshi
        kalshi_raw = KalshiRestMarketDiscoveryClient.parse_fixture_market_response()["market"]
        assert kalshi_raw["reference_price"] == 68000.0

        # Binance
        binance_raw = BinanceSpotPriceStream.parse_fixture_trade()
        assert float(binance_raw["p"]) > 50000

        # Coinbase
        coinbase_raw = CoinbaseSpotPriceStream.parse_fixture_ticker()
        assert float(coinbase_raw["price"]) > 50000

        # CoinGecko
        cg_raw = CoinGeckoMacroDataPoller.parse_fixture_simple_price()
        assert cg_raw["bitcoin"]["usd"] > 50000

    def test_order_book_depth_non_negative(self):
        snapshot = KalshiOrderBookWebSocketClient.parse_fixture_orderbook_snapshot()["msg"]
        for price_str, qty_str in snapshot["yes_dollars_fp"] + snapshot["no_dollars_fp"]:
            qty = float(qty_str)
            price = float(price_str)
            assert qty >= 0
            assert 0.0 <= price <= 1.0

    def test_trade_quantity_positive(self):
        raw = BinanceSpotPriceStream.parse_fixture_trade()
        assert float(raw["q"]) > 0
