"""Tests for settlement watcher and feature importance analyzer.

Settlement watcher tests use in-memory DB and mock Kalshi client.
Feature importance analyzer tests are pure unit tests.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from arbitr8der_package.durable_storage.sqlite_database_engine_manager import (
    initialize_database,
)
from arbitr8der_package.durable_storage.candle_persistence_store import (
    CandlePersistenceStore,
)
from arbitr8der_package.prediction.feature_importance_analyzer import (
    FeatureImportanceAnalyzer,
    FeatureImportanceReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db():
    connection = await initialize_database(":memory:")
    yield connection
    await connection.close()


@pytest_asyncio.fixture
async def store(db):
    return CandlePersistenceStore(db)


def _make_mock_kalshi_client():
    """Create a mock Kalshi discovery client."""
    client = MagicMock()
    client._settings = MagicMock()
    client._settings.kalshi_api_url = "https://api.elections.kalshi.com/trade-api/v2"
    client._api_key = "test-key"
    return client


# ---------------------------------------------------------------------------
# Unit tests: FeatureImportanceAnalyzer
# ---------------------------------------------------------------------------

class TestFeatureImportanceAnalyzer:
    def test_empty_snapshots_returns_empty_report(self):
        analyzer = FeatureImportanceAnalyzer()
        report = analyzer.analyze([])
        assert report.total_features == 0
        assert report.stability_score == 0.0

    def test_single_snapshot(self):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [{"rsi_14": 0.3, "return_1": 0.5, "bollinger_pct": 0.2}]
        report = analyzer.analyze(snapshots)
        assert report.total_features == 3
        assert report.total_retraining_windows == 1
        assert "return_1" in report.top_features

    def test_stable_features_have_low_cv(self):
        analyzer = FeatureImportanceAnalyzer()
        # Same importance every time → CV = 0 → very stable
        snapshots = [
            {"feature_a": 0.5, "feature_b": 0.3},
            {"feature_a": 0.5, "feature_b": 0.3},
            {"feature_a": 0.5, "feature_b": 0.3},
        ]
        report = analyzer.analyze(snapshots)
        for rec in report.records:
            if rec.feature_name == "feature_a":
                assert rec.coefficient_of_variation == 0.0
                assert rec.std_importance == 0.0

    def test_volatile_features_have_high_cv(self):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [
            {"feature_a": 0.1},
            {"feature_a": 0.9},
            {"feature_a": 0.2},
            {"feature_a": 0.8},
        ]
        report = analyzer.analyze(snapshots)
        rec = next(r for r in report.records if r.feature_name == "feature_a")
        assert rec.coefficient_of_variation > 0.5

    def test_stability_score_range(self):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [
            {"f1": 0.5, "f2": 0.3, "f3": 0.2},
            {"f1": 0.5, "f2": 0.3, "f3": 0.2},
        ]
        report = analyzer.analyze(snapshots)
        assert 0 <= report.stability_score <= 100

    def test_rankings_are_consistent(self):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [
            {"a": 0.8, "b": 0.5, "c": 0.2},
            {"a": 0.7, "b": 0.6, "c": 0.1},
        ]
        report = analyzer.analyze(snapshots)
        # 'a' should be ranked #1 by mean
        a_rec = next(r for r in report.records if r.feature_name == "a")
        assert a_rec.rank_by_mean == 1

    def test_top_10_count(self):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [
            {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6,
             "e": 0.5, "f": 0.4, "g": 0.3, "h": 0.2,
             "i": 0.1, "j": 0.05, "k": 0.01},
        ]
        report = analyzer.analyze(snapshots)
        a_rec = next(r for r in report.records if r.feature_name == "a")
        assert a_rec.appears_in_top_10_count == 1
        k_rec = next(r for r in report.records if r.feature_name == "k")
        assert k_rec.appears_in_top_10_count == 0

    def test_unstable_features_detected(self):
        analyzer = FeatureImportanceAnalyzer()
        # Feature with CV > 1.0 should be flagged as unstable
        snapshots = [
            {"noisy": 0.01},
            {"noisy": 0.99},
            {"noisy": 0.02},
            {"noisy": 0.98},
        ]
        report = analyzer.analyze(snapshots)
        assert "noisy" in report.unstable_features

    def test_print_summary_does_not_crash(self, capsys):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [
            {"rsi_14": 0.3, "return_1": 0.5},
            {"rsi_14": 0.4, "return_1": 0.4},
        ]
        report = analyzer.analyze(snapshots)
        report.print_summary()
        captured = capsys.readouterr()
        assert "FEATURE IMPORTANCE ANALYSIS" in captured.out

    def test_to_dict_is_serializable(self):
        import json
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [{"a": 0.5, "b": 0.3}]
        report = analyzer.analyze(snapshots)
        d = report.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_zero_importance_features(self):
        analyzer = FeatureImportanceAnalyzer()
        snapshots = [{"zero_feat": 0.0, "real_feat": 0.5}]
        report = analyzer.analyze(snapshots)
        zero_rec = next(r for r in report.records if r.feature_name == "zero_feat")
        assert zero_rec.mean_importance == 0.0
        assert zero_rec.coefficient_of_variation == float("inf")

    def test_compare_models(self):
        analyzer = FeatureImportanceAnalyzer()
        model_a = [{"a": 0.8, "b": 0.2}]
        model_b = [{"x": 0.7, "y": 0.3}]
        output = analyzer.compare_models(model_a, model_b, "Macro", "Micro")
        assert "Macro" in output
        assert "Micro" in output


# ---------------------------------------------------------------------------
# Integration tests: SettlementWatcher (with mock Kalshi client)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSettlementWatcher:
    async def test_watcher_start_stop(self, store):
        """Watcher should start and stop cleanly."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store, poll_interval_seconds=999)

        assert not watcher.running
        await watcher.start()
        assert watcher.running
        await watcher.stop()
        assert not watcher.running

    async def test_status_returns_dict(self, store):
        """get_status should return a valid dict."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        status = watcher.get_status()
        assert "running" in status
        assert "settlement_count" in status
        assert "poll_interval_seconds" in status

    async def test_parse_window_time_btc(self, store):
        """Ticker parsing should extract timestamp from BTC ticker."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        # KXBTC15M-26JUL25T1430 → 2025-07-26 14:30 UTC
        ts = watcher._parse_window_time("KXBTC15M-26JUL25T1430")
        assert ts is not None
        assert ts > 0

    async def test_parse_window_time_eth(self, store):
        """Ticker parsing should extract timestamp from ETH ticker."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        ts = watcher._parse_window_time("KXETH15M-26JUL25T1200")
        assert ts is not None
        assert ts > 0

    async def test_parse_window_time_invalid(self, store):
        """Invalid ticker should return None."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        ts = watcher._parse_window_time("INVALID-TICKER")
        assert ts is None

    async def test_determine_outcome_up(self, store):
        """Market with close > strike should be UP."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher
        from datetime import datetime, timezone

        # Compute candle time from the ticker's parsed window open
        # Ticker KXBTC15M-26JUL25T1300 → 2025-07-26 13:00 UTC
        ticker_open = datetime(2025, 7, 26, 13, 0, tzinfo=timezone.utc).timestamp()
        candle = {
            "asset": "BTC",
            "source": "binance",
            "interval": "1m",
            "open_time": ticker_open + 895,  # near window close (13:14:55)
            "open": 68100.0,
            "high": 68200.0,
            "low": 68050.0,
            "close": 68100.0,
            "volume": 1.0,
            "quote_volume": 68100.0,
            "trades": 100,
        }
        await store.upsert_candles([candle])

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        market = {
            "ticker": "KXBTC15M-26JUL25T1300",
            "reference_price": 68000.0,  # strike below close → UP
        }

        record = await watcher._determine_market_outcome(market)
        assert record is not None
        assert record.direction == "UP"
        assert record.close_price == 68100.0
        assert record.recorded is True

    async def test_determine_outcome_down(self, store):
        """Market with close < strike should be DOWN."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher
        from datetime import datetime, timezone

        # Ticker KXBTC15M-26JUL25T1315 → 2025-07-26 13:15 UTC
        ticker_open = datetime(2025, 7, 26, 13, 15, tzinfo=timezone.utc).timestamp()
        candle = {
            "asset": "BTC",
            "source": "binance",
            "interval": "1m",
            "open_time": ticker_open + 895,
            "open": 67900.0,
            "high": 67950.0,
            "low": 67850.0,
            "close": 67900.0,
            "volume": 1.0,
            "quote_volume": 67900.0,
            "trades": 100,
        }
        await store.upsert_candles([candle])

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        market = {
            "ticker": "KXBTC15M-26JUL25T1315",
            "reference_price": 68000.0,  # strike above close → DOWN
        }

        record = await watcher._determine_market_outcome(market)
        assert record is not None
        assert record.direction == "DOWN"

    async def test_determine_outcome_no_candle_data(self, store):
        """Market with no candle data should return None."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        market = {
            "ticker": "KXBTC15M-26JUL25T1330",
            "reference_price": 68000.0,
        }

        record = await watcher._determine_market_outcome(market)
        assert record is None

    async def test_determine_outcome_missing_strike(self, store):
        """Market with no reference_price should return None."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        market = {"ticker": "KXBTC15M-26JUL25T1345"}

        record = await watcher._determine_market_outcome(market)
        assert record is None

    async def test_outcome_recorded_in_db(self, store):
        """Recorded outcome should be queryable from the store."""
        from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher
        from datetime import datetime, timezone

        # Ticker KXBTC15M-26JUL25T1400 → 2025-07-26 14:00 UTC
        ticker_open = datetime(2025, 7, 26, 14, 0, tzinfo=timezone.utc).timestamp()
        candle = {
            "asset": "BTC",
            "source": "binance",
            "interval": "1m",
            "open_time": ticker_open + 895,
            "open": 68100.0,
            "high": 68200.0,
            "low": 68050.0,
            "close": 68100.0,
            "volume": 1.0,
            "quote_volume": 68100.0,
            "trades": 100,
        }
        await store.upsert_candles([candle])

        client = _make_mock_kalshi_client()
        watcher = SettlementWatcher(client, store)

        market = {
            "ticker": "KXBTC15M-26JUL25T1400",
            "reference_price": 68000.0,
        }

        await watcher._determine_market_outcome(market)

        # Verify it's in the outcomes table
        outcomes = await store.get_outcomes("BTC", limit=10)
        assert len(outcomes) > 0
        found = any(o["ticker"] == "KXBTC15M-26JUL25T1400" for o in outcomes)
        assert found


# ---------------------------------------------------------------------------
# Unit tests: AutoScoringEngine retraining
# ---------------------------------------------------------------------------

class TestAutoScoringRetraining:
    """Tests for the live retraining feedback loop."""

    async def _make_engine(self, db, store):
        """Create scoring engine with model_run_store and candle_store."""
        from arbitr8der_package.prediction.model_run_record_store import ModelRunRecordStore
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine

        model_run_store = ModelRunRecordStore(db)
        await model_run_store.initialize()
        return AutoScoringEngine(model_run_store=model_run_store, candle_store=store), model_run_store

    async def _seed_scored_predictions(self, model_run_store, store, asset="BTC", count=30):
        """Insert scored predictions with features + outcomes for retraining."""
        import json
        import random

        # Create candle windows and outcomes first
        base_ts = 1700000000.0
        for i in range(count):
            boundary = base_ts + i * 900
            direction = "UP" if random.random() > 0.4 else "DOWN"
            open_p = 60000.0 + random.uniform(-500, 500)
            close_p = open_p + (200 if direction == "UP" else -200)

            await store.record_outcome(
                asset=asset, ticker=f"BINANCE_{asset}_{int(boundary)}",
                window_open=boundary, window_close=boundary + 900,
                open_price=open_p, close_price=close_p,
                direction=direction,
                magnitude_pct=abs(close_p - open_p) / open_p * 100,
            )

            # Record prediction with features
            features = {
                "streak_length": random.randint(0, 5),
                "streak_direction": random.choice([-1, 0, 1]),
                "return_1": random.uniform(-2, 2),
                "return_4": random.uniform(-5, 5),
                "rsi_7": random.uniform(20, 80),
                "rsi_14": random.uniform(30, 70),
                "bollinger_pct": random.uniform(0, 1),
                "bollinger_width": random.uniform(0, 0.1),
                "atr_14": random.uniform(0, 0.02),
                "price_vs_sma_24": random.uniform(-0.02, 0.02),
                "price_vs_sma_96": random.uniform(-0.05, 0.05),
                "regime": random.choice(["trending_up", "trending_down", "ranging"]),
                "hour_of_day": random.randint(0, 23),
                "day_of_week": random.randint(0, 6),
            }

            await model_run_store.record_prediction(
                model_name="baseline_v1",
                asset=asset,
                window_open=boundary,
                yes_probability=random.uniform(0.2, 0.8),
                confidence=random.uniform(0.1, 0.9),
                features_json=json.dumps(features),
            )

        # Score all predictions
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine
        engine = AutoScoringEngine(model_run_store=model_run_store, candle_store=store)
        scored = await engine.score_pending()
        return scored

    @pytest.mark.asyncio
    async def test_retrain_with_enough_data(self, db, store):
        """With 30 scored predictions, retraining should succeed."""
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine

        engine, model_run_store = await self._make_engine(db, store)
        scored = await self._seed_scored_predictions(model_run_store, store, count=30)
        assert scored == 30

        results = await engine.retrain_models()
        assert "BTC" in results
        assert results["BTC"]["trained"] is True
        assert results["BTC"]["samples"] == 30
        assert results["BTC"]["freq_groups"] > 0

    @pytest.mark.asyncio
    async def test_retrain_returns_models(self, db, store):
        """Retrained models should be accessible via get_macro_model/get_micro_model."""
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine

        engine, model_run_store = await self._make_engine(db, store)
        await self._seed_scored_predictions(model_run_store, store, count=25)

        await engine.retrain_models()
        macro = engine.get_macro_model("BTC")
        micro = engine.get_micro_model("BTC")
        assert macro is not None
        assert micro is not None

    @pytest.mark.asyncio
    async def test_retrain_insufficient_data(self, db, store):
        """With fewer than 20 samples, retraining should skip gracefully."""
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine

        engine, model_run_store = await self._make_engine(db, store)
        await self._seed_scored_predictions(model_run_store, store, count=5)

        results = await engine.retrain_models()
        assert "BTC" in results
        assert results["BTC"]["trained"] is False
        assert results["BTC"]["reason"] == "insufficient_samples"

    @pytest.mark.asyncio
    async def test_retrain_empty_db(self, db, store):
        """With no data at all, retraining should return empty results."""
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine

        engine, model_run_store = await self._make_engine(db, store)
        results = await engine.retrain_models()
        assert results == {}

    @pytest.mark.asyncio
    async def test_retrain_tracks_timestamps(self, db, store):
        """After retraining, last_retrain_at and retrain_sample_count should be set."""
        from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine

        engine, model_run_store = await self._make_engine(db, store)
        await self._seed_scored_predictions(model_run_store, store, count=25)

        assert engine.last_retrain_at == 0.0
        assert engine.retrain_sample_count == 0

        await engine.retrain_models()
        assert engine.last_retrain_at > 0.0
        assert engine.retrain_sample_count == 25
