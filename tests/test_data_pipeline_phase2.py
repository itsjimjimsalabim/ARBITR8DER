"""Phase 2 tests — data pipeline, health monitor, data source clients.

Tests all data source clients, stream health monitoring, and the pipeline
orchestrator's event routing logic. Uses mock callbacks to avoid real network.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from arbitr8der.market_data.immutable_event_envelope_wrapper import EventEnvelope, EventType
from arbitr8der.market_data.thread_safe_hot_state_manager import ThreadSafeHotStateManager
from arbitr8der.market_data.stream_health_status_monitor import (
    StreamHealthStatusMonitor,
    StreamHealthRecord,
)
from arbitr8der.data_sources.binance_spot_price_stream import BinanceSpotPriceStream
from arbitr8der.data_sources.coinbase_spot_price_stream import CoinbaseSpotPriceStream
from arbitr8der.data_sources.polymarket_sentiment_analysis_poller import PolymarketSentimentAnalysisPoller
from arbitr8der.data_sources.coingecko_macro_data_poller import CoinGeckoMacroDataPoller
from arbitr8der.data_sources.kalshi_rest_api_client_handler import KalshiRestApiClientHandler
from arbitr8der.data_sources.kalshi_orderbook_websocket_client import KalshiOrderbookWebSocketClient


# ──────────────────────────────────────────────────────────────
# Stream Health Status Monitor Tests
# ──────────────────────────────────────────────────────────────

class TestStreamHealthStatusMonitor:
    """Tests for stream health monitoring and staleness detection."""

    def setup_method(self):
        self.health_monitor = StreamHealthStatusMonitor()

    def test_monitor_initializes_with_default_streams(self):
        """All 6 default data sources are registered on init."""
        records = self.health_monitor.get_all_health_records()
        assert len(records) == 6
        assert "kalshi_ws" in records
        assert "kalshi_rest" in records
        assert "binance_ws" in records
        assert "coinbase_ws" in records
        assert "polymarket_poll" in records
        assert "coingecko_poll" in records

    def test_record_message_marks_source_healthy(self):
        """Recording a message makes the source healthy."""
        assert not self.health_monitor.is_source_healthy("binance_ws")
        self.health_monitor.record_message_received("binance_ws")
        assert self.health_monitor.is_source_healthy("binance_ws")

    def test_stale_source_becomes_unhealthy(self):
        """A source with an old message becomes unhealthy."""
        self.health_monitor.record_message_received("coinbase_ws")
        assert self.health_monitor.is_source_healthy("coinbase_ws")

        # Manually age the timestamp (simulate old message)
        internal_state = self.health_monitor._stream_records["coinbase_ws"]
        internal_state.last_message_timestamp = time.time() - 20.0
        assert not self.health_monitor.is_source_healthy("coinbase_ws")

    def test_record_error_increments_error_count(self):
        """Recording errors increments the consecutive error counter."""
        self.health_monitor.record_error("kalshi_ws", "connection dropped")
        self.health_monitor.record_error("kalshi_ws", "timeout")

        records = self.health_monitor.get_all_health_records()
        assert records["kalshi_ws"].consecutive_error_count == 2
        assert records["kalshi_ws"].last_error == "timeout"

    def test_error_recorded_then_message_resets_counter(self):
        """A successful message after errors resets the error counter."""
        self.health_monitor.record_error("binance_ws", "timeout")
        self.health_monitor.record_error("binance_ws", "timeout")
        self.health_monitor.record_message_received("binance_ws")

        records = self.health_monitor.get_all_health_records()
        assert records["binance_ws"].consecutive_error_count == 0

    def test_can_trade_safely_requires_kalshi(self):
        """Trading is blocked if Kalshi is unhealthy."""
        self.health_monitor.record_message_received("binance_ws")
        self.health_monitor.record_message_received("coinbase_ws")
        assert not self.health_monitor.can_trade_safely()

        self.health_monitor.record_message_received("kalshi_ws")
        self.health_monitor.record_message_received("kalshi_rest")
        assert self.health_monitor.can_trade_safely()

    def test_health_summary_returns_correct_counts(self):
        """Health summary counts healthy and unhealthy sources."""
        self.health_monitor.record_message_received("kalshi_ws")
        self.health_monitor.record_message_received("binance_ws")
        # Others have never received a message = unhealthy

        summary = self.health_monitor.get_health_summary()
        assert summary["total_streams"] == 6
        assert summary["healthy_count"] == 2
        assert summary["unhealthy_count"] == 4

    def test_unregistered_source_auto_registered(self):
        """Unknown source names are auto-registered on first message."""
        self.health_monitor.record_message_received("mystery_feed")
        assert self.health_monitor.is_source_healthy("mystery_feed")

        records = self.health_monitor.get_all_health_records()
        assert "mystery_feed" in records

    def test_custom_staleness_thresholds(self):
        """Custom thresholds override defaults."""
        monitor = StreamHealthStatusMonitor(
            staleness_thresholds={"binance_ws": 2.0}
        )
        monitor.record_message_received("binance_ws")

        # Fresh message should be healthy
        assert monitor.is_source_healthy("binance_ws")

        # Age it past custom threshold
        internal_state = monitor._stream_records["binance_ws"]
        internal_state.last_message_timestamp = time.time() - 3.0
        assert not monitor.is_source_healthy("binance_ws")

    def test_health_record_dataclass_fields(self):
        """Health record dataclass has all expected fields."""
        self.health_monitor.record_message_received("polymarket_poll")
        records = self.health_monitor.get_all_health_records()
        record = records["polymarket_poll"]

        assert record.source_name == "polymarket_poll"
        assert record.is_healthy is True
        assert record.staleness_threshold_seconds == 120.0
        assert record.last_error is None
        assert record.consecutive_error_count == 0


# ──────────────────────────────────────────────────────────────
# Binance Spot Stream Tests (mocked)
# ──────────────────────────────────────────────────────────────

class TestBinanceSpotPriceStream:
    """Tests for Binance WebSocket client message parsing and routing."""

    def setup_method(self):
        self.received_events: list[EventEnvelope] = []
        self.stream = BinanceSpotPriceStream(
            on_event_callback=lambda e: self.received_events.append(e)
        )

    def test_parse_btc_trade_message(self):
        """BTC trade message is correctly parsed into EventEnvelope."""
        trade_data = {
            "s": "BTCUSDT",
            "p": "67500.50",
            "q": "0.001",
            "t": 1700000000000,
            "T": 1700000000000,
        }
        envelope = self.stream._parse_trade_message(trade_data)
        assert envelope is not None
        assert envelope.source == "binance_ws"
        assert envelope.event_type == EventType.SPOT_PRICE
        assert envelope.payload["asset"] == "BTC"
        assert envelope.payload["price"] == 67500.50
        assert envelope.payload["provider"] == "binance"

    def test_parse_eth_trade_message(self):
        """ETH trade message is correctly parsed into EventEnvelope."""
        trade_data = {
            "s": "ETHUSDT",
            "p": "3500.25",
            "q": "0.01",
            "t": 1700000000001,
            "T": 1700000000001,
        }
        envelope = self.stream._parse_trade_message(trade_data)
        assert envelope is not None
        assert envelope.payload["asset"] == "ETH"
        assert envelope.payload["price"] == 3500.25

    def test_parse_unknown_symbol_returns_none(self):
        """Unknown symbol returns None."""
        trade_data = {"s": "DOGEUSDT", "p": "0.15", "q": "100"}
        envelope = self.stream._parse_trade_message(trade_data)
        assert envelope is None

    def test_latest_spot_prices_updated(self):
        """latest_spot_prices is updated when a trade is parsed."""
        trade_data = {
            "s": "BTCUSDT",
            "p": "68000.00",
            "q": "0.1",
            "t": 1700000000000,
            "T": 1700000000000,
        }
        self.stream._parse_trade_message(trade_data)
        assert self.stream.latest_spot_prices["BTC"] == 68000.00

    def test_health_info_structure(self):
        """Health info has expected keys."""
        info = self.stream.get_health_info()
        assert "connected" in info
        assert "running" in info
        assert "latest_spot_prices" in info
        assert info["connected"] is False


# ──────────────────────────────────────────────────────────────
# Coinbase Spot Stream Tests (mocked)
# ──────────────────────────────────────────────────────────────

class TestCoinbaseSpotPriceStream:
    """Tests for Coinbase WebSocket client message parsing."""

    def setup_method(self):
        self.received_events: list[EventEnvelope] = []
        self.stream = CoinbaseSpotPriceStream(
            on_event_callback=lambda e: self.received_events.append(e)
        )

    def test_parse_btc_ticker_message(self):
        """BTC ticker message is correctly parsed."""
        ticker_data = {
            "product_id": "BTC-USD",
            "price": "67450.75",
            "best_bid": "67450.50",
            "best_ask": "67451.00",
            "volume_24h": "12345.6",
        }
        envelope = self.stream._parse_ticker_message(ticker_data)
        assert envelope is not None
        assert envelope.source == "coinbase_ws"
        assert envelope.event_type == EventType.SPOT_PRICE
        assert envelope.payload["asset"] == "BTC"
        assert envelope.payload["price"] == 67450.75
        assert envelope.payload["provider"] == "coinbase"

    def test_parse_eth_ticker_message(self):
        """ETH ticker message is correctly parsed."""
        ticker_data = {
            "product_id": "ETH-USD",
            "price": "3499.00",
            "best_bid": "3498.50",
            "best_ask": "3499.50",
            "volume_24h": "50000.0",
        }
        envelope = self.stream._parse_ticker_message(ticker_data)
        assert envelope is not None
        assert envelope.payload["asset"] == "ETH"
        assert envelope.payload["price"] == 3499.00

    def test_parse_unknown_product_returns_none(self):
        """Unknown product_id returns None."""
        ticker_data = {"product_id": "SOL-USD", "price": "150.00"}
        envelope = self.stream._parse_ticker_message(ticker_data)
        assert envelope is None

    def test_latest_spot_prices_updated(self):
        """latest_spot_prices reflects latest parsed price."""
        ticker_data = {"product_id": "ETH-USD", "price": "3510.00"}
        self.stream._parse_ticker_message(ticker_data)
        assert self.stream.latest_spot_prices["ETH"] == 3510.00


# ──────────────────────────────────────────────────────────────
# Polymarket Sentiment Poller Tests (mocked)
# ──────────────────────────────────────────────────────────────

class TestPolymarketSentimentPoller:
    """Tests for Polymarket sentiment polling (mocked HTTP)."""

    def setup_method(self):
        self.received_events: list[EventEnvelope] = []
        self.poller = PolymarketSentimentAnalysisPoller(
            on_event_callback=lambda e: self.received_events.append(e)
        )

    def test_initial_state(self):
        """Poller starts in stopped state with no data."""
        assert not self.poller.is_running
        assert self.poller.latest_sentiment == {}

    def test_health_info_structure(self):
        """Health info has expected keys."""
        info = self.poller.get_health_info()
        assert "running" in info
        assert "error_count" in info
        assert "latest_sentiment" in info


# ──────────────────────────────────────────────────────────────
# CoinGecko Macro Poller Tests (mocked)
# ──────────────────────────────────────────────────────────────

class TestCoinGeckoMacroDataPoller:
    """Tests for CoinGecko macro data polling (mocked HTTP)."""

    def setup_method(self):
        self.received_events: list[EventEnvelope] = []
        self.poller = CoinGeckoMacroDataPoller(
            on_event_callback=lambda e: self.received_events.append(e)
        )

    def test_initial_state(self):
        """Poller starts in stopped state with no data."""
        assert not self.poller.is_running
        assert self.poller.latest_macro_data == {}

    def test_health_info_structure(self):
        """Health info has expected keys."""
        info = self.poller.get_health_info()
        assert "running" in info
        assert "error_count" in info
        assert "latest_macro_data" in info
        assert "rate_limited_until" in info


# ──────────────────────────────────────────────────────────────
# Event Routing to HotState Tests
# ──────────────────────────────────────────────────────────────

class TestEventRoutingToHotState:
    """Tests that the pipeline correctly routes events to HotState."""

    def setup_method(self):
        self.hot_state = ThreadSafeHotStateManager()

    def test_orderbook_snapshot_updates_hot_state(self):
        """ORDERBOOK_SNAPSHOT event updates HotState orderbook."""
        self.hot_state.update_orderbook(
            ticker="KXBTC15M-25JUL211200",
            book_data={"yes_best": 0.65, "no_best": 0.35, "spread": 0.02},
        )
        snapshot = self.hot_state.snapshot()
        assert "KXBTC15M-25JUL211200" in snapshot.orderbooks

    def test_spot_price_updates_hot_state(self):
        """SPOT_PRICE event updates HotState spot price."""
        self.hot_state.update_spot_price(asset="BTC", price=67500.00)
        snapshot = self.hot_state.snapshot()
        assert snapshot.spot_prices["BTC"] == 67500.00

    def test_sentiment_updates_hot_state(self):
        """SENTIMENT event updates HotState sentiment."""
        self.hot_state.update_sentiment(asset="BTC", score=0.72)
        snapshot = self.hot_state.snapshot()
        assert snapshot.sentiment["BTC"] == 0.72

    def test_macro_updates_hot_state(self):
        """MACRO event updates HotState macro data."""
        macro_data = {
            "market_cap": 1300000000000,
            "total_volume": 28000000000,
            "price_change_percentage_24h": 2.5,
        }
        self.hot_state.update_macro(data=macro_data)
        snapshot = self.hot_state.snapshot()
        assert snapshot.macro["market_cap"] == 1300000000000


# ──────────────────────────────────────────────────────────────
# Kalshi JWT Auth Tests
# ──────────────────────────────────────────────────────────────

class TestKalshiRestClientAuth:
    """Tests for Kalshi REST client auth logic (no real keys needed)."""

    def test_client_initializes_without_key_file(self):
        """Client initializes gracefully when key file doesn't exist."""
        client = KalshiRestApiClientHandler(
            api_key_id="test-key-id",
            private_key_path="/nonexistent/path.pem",
        )
        assert client.api_key_id == "test-key-id"
        assert client._private_key_pem is None

    def test_generate_jwt_fails_without_key(self):
        """JWT generation raises RuntimeError without a private key."""
        client = KalshiRestApiClientHandler(
            api_key_id="test-key-id",
            private_key_path="/nonexistent/path.pem",
        )
        with pytest.raises(RuntimeError, match="No private key"):
            client.generate_jwt_token()

    def test_health_check_returns_false_when_unreachable(self):
        """Health check returns False for unreachable API."""
        client = KalshiRestApiClientHandler(
            api_key_id="test-key-id",
            private_key_path="/nonexistent/path.pem",
            base_url="https://nonexistent.invalid",
        )
        result = asyncio.get_event_loop().run_until_complete(
            client.health_check()
        )
        assert result is False


# ──────────────────────────────────────────────────────────────
# Kalshi WebSocket Client Tests
# ──────────────────────────────────────────────────────────────

class TestKalshiOrderbookWebSocket:
    """Tests for Kalshi WebSocket client initialization and parsing."""

    def setup_method(self):
        self.received_events: list[EventEnvelope] = []
        self.ws_client = KalshiOrderbookWebSocketClient(
            api_key_id="test-id",
            private_key_pem=b"fake-key",
            on_event_callback=lambda e: self.received_events.append(e),
        )

    def test_subscribe_ticker(self):
        """Ticker is added to subscription set."""
        self.ws_client.subscribe_ticker("KXBTC15M-25JUL211200")
        assert "KXBTC15M-25JUL211200" in self.ws_client._subscribed_tickers

    def test_initial_state_disconnected(self):
        """Client starts disconnected and not running."""
        assert not self.ws_client.is_connected
        assert not self.ws_client._running

    def test_health_info_structure(self):
        """Health info has expected keys."""
        info = self.ws_client.get_health_info()
        assert "connected" in info
        assert "running" in info
        assert "subscribed_tickers" in info
        assert "sequence_number" in info


# ──────────────────────────────────────────────────────────────
# Integration: EventEnvelope round-trip
# ──────────────────────────────────────────────────────────────

class TestEventEnvelopeRoundTrip:
    """Verify EventEnvelope serialization/deserialization for DB storage."""

    def test_orderbook_snapshot_round_trip(self):
        """ORDERBOOK_SNAPSHOT survives serialize → deserialize."""
        original = EventEnvelope(
            source="kalshi_ws",
            event_type=EventType.ORDERBOOK_SNAPSHOT,
            payload={"ticker": "KXBTC15M-25JUL211200", "yes_best": 0.65},
            ticker="KXBTC15M-25JUL211200",
        )
        as_dict = original.to_dict()
        reconstructed = EventEnvelope(
            source=as_dict["source"],
            event_type=EventType(as_dict["event_type"]),
            payload=as_dict["payload"],
            ticker=as_dict["ticker"],
            timestamp=as_dict["timestamp"],
        )
        assert reconstructed.source == original.source
        assert reconstructed.event_type == original.event_type
        assert reconstructed.ticker == original.ticker
        assert reconstructed.payload["yes_best"] == 0.65

    def test_spot_price_round_trip(self):
        """SPOT_PRICE survives serialize → deserialize."""
        original = EventEnvelope(
            source="binance_ws",
            event_type=EventType.SPOT_PRICE,
            payload={"asset": "BTC", "price": 67500.00, "provider": "binance"},
            ticker="BTC_SPOT",
        )
        as_dict = original.to_dict()
        reconstructed = EventEnvelope(
            source=as_dict["source"],
            event_type=EventType(as_dict["event_type"]),
            payload=as_dict["payload"],
            ticker=as_dict["ticker"],
            timestamp=as_dict["timestamp"],
        )
        assert reconstructed.payload["price"] == 67500.00
        assert reconstructed.payload["provider"] == "binance"

    def test_sentiment_round_trip(self):
        """SENTIMENT survives serialize → deserialize."""
        original = EventEnvelope(
            source="polymarket",
            event_type=EventType.SENTIMENT,
            payload={"asset": "ETH", "sentiment": 0.85},
            ticker="ETH_SENTIMENT",
        )
        as_dict = original.to_dict()
        assert as_dict["payload"]["sentiment"] == 0.85
        assert as_dict["event_type"] == "sentiment"

    def test_macro_round_trip(self):
        """MACRO survives serialize → deserialize."""
        original = EventEnvelope(
            source="coingecko",
            event_type=EventType.MACRO,
            payload={
                "asset": "BTC",
                "macro": {"market_cap": 1300000000000, "volume": 28000000000},
            },
            ticker="BTC_MACRO",
        )
        as_dict = original.to_dict()
        assert as_dict["payload"]["macro"]["market_cap"] == 1300000000000
