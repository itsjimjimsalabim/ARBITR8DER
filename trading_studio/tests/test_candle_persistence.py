"""Tests for persistent candle store and collection battery.

Tests the SQLite-backed candle storage layer (upsert, query, aggregation)
and the collection battery lifecycle. No network calls — uses in-memory DB.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio

from arbitr8der_package.durable_storage.sqlite_database_engine_manager import (
    initialize_database,
)
from arbitr8der_package.durable_storage.candle_persistence_store import (
    CandlePersistenceStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db():
    """In-memory SQLite database with schema applied."""
    connection = await initialize_database(":memory:")
    yield connection
    await connection.close()


@pytest_asyncio.fixture
async def store(db):
    """CandlePersistenceStore backed by in-memory DB."""
    return CandlePersistenceStore(db)


def _make_binance_candle(
    asset: str = "BTC",
    open_time: float = 1700000000.0,
    open_p: float = 68000.0,
    close: float = 68050.0,
) -> dict:
    """Helper to create a candle row dict."""
    return {
        "asset": asset,
        "source": "binance",
        "interval": "1m",
        "open_time": open_time,
        "open": open_p,
        "high": max(open_p, close) + 10,
        "low": min(open_p, close) - 10,
        "close": close,
        "volume": 1.5,
        "quote_volume": 102000.0,
        "trades": 500,
    }


def _make_coinbase_candle(
    asset: str = "BTC",
    open_time: float = 1700000000.0,
    open_p: float = 68000.0,
    close: float = 68050.0,
) -> dict:
    """Helper to create a Coinbase candle row dict."""
    return {
        "asset": asset,
        "source": "coinbase",
        "interval": "1m",
        "open_time": open_time,
        "open": open_p,
        "high": max(open_p, close) + 10,
        "low": min(open_p, close) - 10,
        "close": close,
        "volume": 2.0,
        "quote_volume": None,
        "trades": None,
    }


# ---------------------------------------------------------------------------
# CandlePersistenceStore: upsert
# ---------------------------------------------------------------------------

class TestCandleUpsert:
    @pytest.mark.asyncio
    async def test_upsert_single_candle(self, store):
        await store.upsert_candle(
            asset="BTC", source="binance", interval="1m",
            open_time=1700000000.0, open_p=68000.0, high=68100.0,
            low=67900.0, close=68050.0, volume=1.5,
        )
        count = await store.count_candles("BTC", "binance", "1m")
        assert count == 1

    @pytest.mark.asyncio
    async def test_upsert_batch(self, store):
        rows = [_make_binance_candle(open_time=1700000000.0 + i * 60) for i in range(10)]
        stored = await store.upsert_candles(rows)
        assert stored == 10
        count = await store.count_candles("BTC", "binance", "1m")
        assert count == 10

    @pytest.mark.asyncio
    async def test_upsert_duplicate_replaces(self, store):
        """Same asset/source/interval/open_time → replaces existing."""
        row = _make_binance_candle(open_time=1700000000.0, close=68000.0)
        await store.upsert_candles([row])

        row2 = _make_binance_candle(open_time=1700000000.0, close=68999.0)
        await store.upsert_candles([row2])

        count = await store.count_candles("BTC", "binance", "1m")
        assert count == 1

        candles = await store.get_candles("BTC", "binance", "1m", limit=1)
        assert candles[0]["close"] == 68999.0

    @pytest.mark.asyncio
    async def test_upsert_empty_list(self, store):
        count = await store.upsert_candles([])
        assert count == 0


# ---------------------------------------------------------------------------
# CandlePersistenceStore: read
# ---------------------------------------------------------------------------

class TestCandleRead:
    @pytest.mark.asyncio
    async def test_get_candles_newest_first(self, store):
        rows = [_make_binance_candle(open_time=1700000000.0 + i * 60) for i in range(5)]
        await store.upsert_candles(rows)

        candles = await store.get_candles("BTC", "binance", "1m", limit=5)
        assert len(candles) == 5
        # Newest first
        assert candles[0]["open_time"] > candles[-1]["open_time"]

    @pytest.mark.asyncio
    async def test_get_candles_before_time(self, store):
        rows = [_make_binance_candle(open_time=1700000000.0 + i * 60) for i in range(10)]
        await store.upsert_candles(rows)

        # Only candles before 1700000300 (first 5)
        candles = await store.get_candles(
            "BTC", "binance", "1m", limit=100, before_time=1700000300.0
        )
        assert all(c["open_time"] < 1700000300.0 for c in candles)

    @pytest.mark.asyncio
    async def test_get_candles_since(self, store):
        rows = [_make_binance_candle(open_time=1700000000.0 + i * 60) for i in range(10)]
        await store.upsert_candles(rows)

        candles = await store.get_candles_since(
            "BTC", "binance", "1m", since_time=1700000500.0
        )
        assert len(candles) > 0
        assert all(c["open_time"] >= 1700000500.0 for c in candles)
        # Ordered oldest first
        assert candles[0]["open_time"] <= candles[-1]["open_time"]

    @pytest.mark.asyncio
    async def test_get_latest_candle_time(self, store):
        rows = [_make_binance_candle(open_time=1700000000.0 + i * 60) for i in range(5)]
        await store.upsert_candles(rows)

        latest = await store.get_latest_candle_time("BTC", "binance", "1m")
        assert latest == 1700000000.0 + 4 * 60

    @pytest.mark.asyncio
    async def test_get_latest_candle_time_empty(self, store):
        latest = await store.get_latest_candle_time("BTC", "binance", "1m")
        assert latest is None

    @pytest.mark.asyncio
    async def test_get_candle_summary(self, store):
        btc_rows = [_make_binance_candle(asset="BTC", open_time=1700000000.0 + i * 60) for i in range(3)]
        eth_rows = [_make_binance_candle(asset="ETH", open_time=1700000000.0 + i * 60) for i in range(5)]
        await store.upsert_candles(btc_rows + eth_rows)

        summary = await store.get_candle_summary()
        assert summary["BTC:binance:1m"] == 3
        assert summary["ETH:binance:1m"] == 5

    @pytest.mark.asyncio
    async def test_multi_source_same_asset(self, store):
        binance_row = _make_binance_candle(open_time=1700000000.0)
        coinbase_row = _make_coinbase_candle(open_time=1700000000.0)
        await store.upsert_candles([binance_row, coinbase_row])

        btc_binance = await store.count_candles("BTC", "binance", "1m")
        btc_coinbase = await store.count_candles("BTC", "coinbase", "1m")
        assert btc_binance == 1
        assert btc_coinbase == 1


# ---------------------------------------------------------------------------
# CandlePersistenceStore: outcomes
# ---------------------------------------------------------------------------

class TestOutcomes:
    @pytest.mark.asyncio
    async def test_record_outcome(self, store):
        oid = await store.record_outcome(
            asset="BTC", ticker="KXBTC15M-TEST",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=68050.0,
            direction="UP", magnitude_pct=0.07,
        )
        assert oid > 0

    @pytest.mark.asyncio
    async def test_get_outcomes(self, store):
        for i in range(3):
            await store.record_outcome(
                asset="BTC", ticker=f"KXBTC15M-TEST-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=68050.0,
                direction="UP",
            )

        outcomes = await store.get_outcomes("BTC", limit=10)
        assert len(outcomes) == 3
        assert outcomes[0]["direction"] == "UP"

    @pytest.mark.asyncio
    async def test_outcome_unique_constraint(self, store):
        await store.record_outcome(
            asset="BTC", ticker="KXBTC15M-TEST",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=68050.0, direction="UP",
        )
        # Duplicate insert is silently ignored
        await store.record_outcome(
            asset="BTC", ticker="KXBTC15M-TEST",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=68100.0, direction="DOWN",
        )
        outcomes = await store.get_outcomes("BTC")
        assert len(outcomes) == 1
        # Original preserved
        assert outcomes[0]["direction"] == "UP"


# ---------------------------------------------------------------------------
# CandlePersistenceStore: predictions
# ---------------------------------------------------------------------------

class TestPredictions:
    @pytest.mark.asyncio
    async def test_record_and_score_prediction(self, store):
        pid = await store.record_prediction(
            model_name="test_model", asset="BTC",
            window_open=1700000000.0, yes_probability=0.65,
            confidence=0.8,
        )
        assert pid > 0

        # Record an outcome to link
        oid = await store.record_outcome(
            asset="BTC", ticker="KXBTC15M-TEST",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=68050.0, direction="UP",
        )

        # Score: prediction said 65% YES, outcome was UP (YES=1) → correct
        await store.score_prediction(pid, oid, correct=True, pnl_cents=35.0)

        accuracy = await store.get_model_accuracy("test_model")
        assert accuracy["total_scored"] == 1
        assert accuracy["correct"] == 1
        assert accuracy["accuracy_pct"] == 100.0
        assert accuracy["total_pnl_cents"] == 35.0

    @pytest.mark.asyncio
    async def test_model_accuracy_mixed(self, store):
        for i in range(10):
            pid = await store.record_prediction(
                model_name="test_model", asset="BTC",
                window_open=1700000000.0 + i * 900,
                yes_probability=0.6, confidence=0.7,
            )
            oid = await store.record_outcome(
                asset="BTC", ticker=f"TICKER-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=68050.0,
                direction="UP" if i % 2 == 0 else "DOWN",
            )
            correct = (i % 2 == 0)  # 5 correct out of 10
            pnl = 35.0 if correct else -60.0
            await store.score_prediction(pid, oid, correct=correct, pnl_cents=pnl)

        accuracy = await store.get_model_accuracy("test_model")
        assert accuracy["total_scored"] == 10
        assert accuracy["correct"] == 5
        assert accuracy["accuracy_pct"] == 50.0


# ---------------------------------------------------------------------------
# CandlePersistenceStore: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_different_assets_independent(self, store):
        btc = _make_binance_candle(asset="BTC", open_time=1700000000.0)
        eth = _make_binance_candle(asset="ETH", open_time=1700000000.0)
        await store.upsert_candles([btc, eth])

        btc_count = await store.count_candles("BTC", "binance", "1m")
        eth_count = await store.count_candles("ETH", "binance", "1m")
        assert btc_count == 1
        assert eth_count == 1

    @pytest.mark.asyncio
    async def test_count_empty(self, store):
        count = await store.count_candles("DOES", "NOT", "1m")
        assert count == 0

    @pytest.mark.asyncio
    async def test_outcomes_since_time(self, store):
        for i in range(5):
            await store.record_outcome(
                asset="BTC", ticker=f"T-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=68050.0,
                direction="UP",
            )
        outcomes = await store.get_outcomes("BTC", since_time=1700002000.0)
        assert all(o["window_open"] >= 1700002000.0 for o in outcomes)
