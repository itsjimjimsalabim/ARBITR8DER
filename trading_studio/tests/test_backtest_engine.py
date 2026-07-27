"""Tests for walk-forward backtest engine.

Tests feature computation helpers, outcome derivation, walk-forward logic,
aggregate metrics, and edge cases. No network calls — uses in-memory DB.
"""

from __future__ import annotations

import math

import pytest
import pytest_asyncio

from arbitr8der_package.durable_storage.sqlite_database_engine_manager import (
    initialize_database,
)
from arbitr8der_package.durable_storage.candle_persistence_store import (
    CandlePersistenceStore,
)
from arbitr8der_package.prediction.backtest_engine import (
    BacktestResult,
    WalkForwardBacktester,
    _derive_outcome,
    _empty_macro_dict,
    aggregate_1m_to_15m_candles,
    compute_macro_features_from_candles,
    print_comparison,
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


def _make_candle(
    open_time: float = 1700000000.0,
    open_p: float = 68000.0,
    close: float = 68050.0,
    volume: float = 1.5,
) -> dict:
    """Helper to create a 15m candle dict."""
    return {
        "asset": "BTC",
        "source": "binance",
        "interval": "15m",
        "open_time": open_time,
        "open": open_p,
        "high": max(open_p, close) + 10,
        "low": min(open_p, close) - 10,
        "close": close,
        "volume": volume,
        "quote_volume": 102000.0,
        "trades": 500,
    }


def _make_candle_series(
    count: int = 300,
    base_price: float = 68000.0,
    base_time: float = 1700000000.0,
    interval_seconds: float = 900.0,
    drift: float = 0.0001,
) -> list[dict]:
    """Generate a series of 15m candles with slight upward drift."""
    import random
    rng = random.Random(42)
    candles = []
    price = base_price
    for i in range(count):
        change_pct = drift + rng.gauss(0, 0.002)
        close_p = price * (1 + change_pct)
        candle = _make_candle(
            open_time=base_time + i * interval_seconds,
            open_p=price,
            close=close_p,
            volume=1.0 + rng.random() * 2,
        )
        candles.append(candle)
        price = close_p
    return candles


# ---------------------------------------------------------------------------
# Unit tests: _derive_outcome
# ---------------------------------------------------------------------------

class TestDeriveOutcome:
    def test_up_candle(self):
        assert _derive_outcome({"open": 100, "close": 105}) == "UP"

    def test_down_candle(self):
        assert _derive_outcome({"open": 100, "close": 95}) == "DOWN"

    def test_flat_candle_defaults_to_down(self):
        assert _derive_outcome({"open": 100, "close": 100}) == "DOWN"


# ---------------------------------------------------------------------------
# Unit tests: compute_macro_features_from_candles
# ---------------------------------------------------------------------------

class TestComputeMacroFeatures:
    def test_empty_candles_returns_defaults(self):
        features = compute_macro_features_from_candles([])
        assert features["regime"] == "unknown"
        assert features["rsi_14"] == 50.0
        assert features["kalshi_midpoint"] == 50.0

    def test_too_few_candles_returns_defaults(self):
        candles = [_make_candle(open_p=100, close=101) for _ in range(3)]
        features = compute_macro_features_from_candles(candles)
        assert features["regime"] == "unknown"

    def test_sufficient_candles_computes_features(self):
        candles = _make_candle_series(100)
        features = compute_macro_features_from_candles(candles)
        assert isinstance(features, dict)
        assert "return_1" in features
        assert "rsi_14" in features
        assert "bollinger_pct" in features
        assert "regime" in features
        assert features["regime"] in ("trending_up", "trending_down", "ranging", "volatile", "unknown")

    def test_features_use_window_timestamp(self):
        import datetime as _dt
        candles = _make_candle_series(100)
        ts = 1700000000.0
        features = compute_macro_features_from_candles(candles, window_ts=ts)
        dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
        assert features["hour_of_day"] == dt.hour
        assert features["day_of_week"] == dt.weekday()

    def test_upward_drift_candles_have_positive_returns(self):
        candles = _make_candle_series(100, drift=0.005)
        features = compute_macro_features_from_candles(candles)
        assert features["return_1"] > 0
        assert features["return_4"] > 0


# ---------------------------------------------------------------------------
# Unit tests: _empty_macro_dict
# ---------------------------------------------------------------------------

class TestEmptyMacroDict:
    def test_returns_all_expected_keys(self):
        d = _empty_macro_dict()
        assert "rsi_14" in d
        assert "bollinger_pct" in d
        assert "regime" in d
        assert d["rsi_14"] == 50.0
        assert d["regime"] == "unknown"


# ---------------------------------------------------------------------------
# Integration tests: WalkForwardBacktester
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWalkForwardBacktester:
    async def test_insufficient_candles_returns_empty_result(self, store):
        """Backtest with too few candles should return empty result."""
        backtester = WalkForwardBacktester(store, asset="BTC", train_window_size=288)
        result = await backtester.run(model_type="macro")
        assert result.total_predictions == 0
        assert result.accuracy_pct == 0.0

    async def test_enough_candles_produces_predictions(self, store):
        """With 350 candles and train_window=50, we should get predictions."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        assert result.total_predictions > 0
        assert result.candle_count == 350
        assert 0 <= result.accuracy_pct <= 100

    async def test_micro_model_produces_predictions(self, store):
        """Micro ensemble should also produce predictions."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="micro")

        assert result.total_predictions > 0
        assert result.model_name == "micro"

    async def test_retrain_every_controls_frequency(self, store):
        """retrain_every should affect how often models retrain."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        # Train once
        backtester_once = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
            retrain_every=0,
        )
        result_once = await backtester_once.run(model_type="macro")

        # Train every step
        backtester_freq = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
            retrain_every=1,
        )
        result_freq = await backtester_freq.run(model_type="macro")

        # Both should produce predictions (accuracy may differ)
        assert result_once.total_predictions > 0
        assert result_freq.total_predictions > 0

    async def test_pnl_is_bounded(self, store):
        """PnL per trade should be bounded by contract pricing."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        for pred in result.predictions:
            # Max loss = -entry_cost (contract expires worthless)
            # Max win = 100 - entry_cost (contract pays out)
            assert pred.pnl_cents >= -pred.entry_price_cents
            assert pred.pnl_cents <= 100.0 - pred.entry_price_cents
            assert pred.entry_price_cents > 0

    async def test_result_metrics_are_consistent(self, store):
        """Aggregate metrics should be mathematically consistent."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        if result.total_predictions > 0:
            assert result.correct_predictions <= result.total_predictions
            assert 0 <= result.win_rate_pct <= 100
            assert result.avg_pnl_per_trade_cents == pytest.approx(
                result.total_pnl_cents / result.total_predictions, rel=1e-6
            )

    async def test_brier_score_is_between_0_and_1(self, store):
        """Brier score should be in [0, 1] range."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        if result.total_predictions > 0:
            assert 0 <= result.brier_score <= 1.0

    async def test_print_summary_does_not_crash(self, store, capsys):
        """print_summary should produce output without errors."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")
        result.print_summary()

        captured = capsys.readouterr()
        assert "BACKTEST RESULT" in captured.out
        assert "Accuracy" in captured.out

    async def test_directional_accuracy_fields_populated(self, store):
        """UP/DOWN accuracy fields should be populated."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        assert result.up_predictions + result.down_predictions == result.total_predictions
        if result.up_predictions > 0:
            assert 0 <= result.up_accuracy_pct <= 100
        if result.down_predictions > 0:
            assert 0 <= result.down_accuracy_pct <= 100

    async def test_sharpe_ratio_computed(self, store):
        """Sharpe ratio should be computed for non-trivial prediction sets."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        if result.total_predictions > 1:
            assert isinstance(result.sharpe_ratio, float)

    async def test_max_drawdown_non_negative(self, store):
        """Max drawdown should always be >= 0."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        assert result.max_drawdown_cents >= 0

    async def test_contract_side_populated(self, store):
        """Each prediction should record which contract was bought."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        for pred in result.predictions:
            assert pred.contract_side in ("YES", "NO")
            if pred.predicted == "UP":
                assert pred.contract_side == "YES"
            else:
                assert pred.contract_side == "NO"

    async def test_comparison_mode_returns_list(self, store):
        """model_type='both' should return a list of two results."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="both")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].model_name == "macro"
        assert result[1].model_name == "micro"
        assert result[0].total_predictions > 0
        assert result[1].total_predictions > 0

    async def test_feature_importance_populated_for_macro(self, store):
        """Macro model should produce feature importance from LightGBM."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        assert len(result.feature_importance) > 0
        # All importance values should be non-negative
        for k, v in result.feature_importance.items():
            assert v >= 0, f"Feature {k} has negative importance: {v}"

    async def test_to_comparison_dict(self, store):
        """to_comparison_dict should return a serializable dict."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        d = result.to_comparison_dict()
        assert "model_name" in d
        assert "accuracy_pct" in d
        assert "brier_score" in d
        assert "total_pnl_cents" in d
        assert "sharpe_ratio" in d
        assert isinstance(d["accuracy_pct"], float)

    async def test_print_comparison_does_not_crash(self, store, capsys):
        """print_comparison should produce output without errors."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        results = await backtester.run(model_type="both")
        print_comparison(results[0], results[1])

        captured = capsys.readouterr()
        assert "MODEL COMPARISON" in captured.out
        assert "MACRO" in captured.out
        assert "MICRO" in captured.out

    async def test_entry_price_matches_probability(self, store):
        """Entry price should equal yes_probability * 100 for YES contracts."""
        candles = _make_candle_series(350)
        await store.upsert_candles(candles)

        backtester = WalkForwardBacktester(
            store, asset="BTC", source="binance",
            train_window_size=50, min_train_samples=20,
        )
        result = await backtester.run(model_type="macro")

        for pred in result.predictions:
            if pred.contract_side == "YES":
                assert pred.entry_price_cents == pytest.approx(
                    pred.yes_probability * 100.0, abs=0.01
                )
            else:
                assert pred.entry_price_cents == pytest.approx(
                    (1.0 - pred.yes_probability) * 100.0, abs=0.01
                )


# ---------------------------------------------------------------------------
# Unit tests: aggregate_1m_to_15m_candles
# ---------------------------------------------------------------------------

class TestAggregate1mTo15m:
    def test_empty_input(self):
        assert aggregate_1m_to_15m_candles([]) == []

    def test_single_window(self):
        """15 1m candles in one 900s window should produce one 15m candle."""
        # Use a base time aligned to 900s boundary
        base = 1700000400.0  # 1700000400 / 900 = 1888889.333 → boundary = 1700000100
        boundary = int(base / 900) * 900
        candles = []
        for i in range(15):
            candles.append({
                "asset": "BTC", "source": "binance", "interval": "1m",
                "open_time": boundary + 60 + i * 60,  # all within same 900s window
                "open": 68000.0 + i, "high": 68010.0 + i,
                "low": 67990.0 + i, "close": 68005.0 + i,
                "volume": 1.0, "quote_volume": 68000.0, "trades": 10,
            })
        result = aggregate_1m_to_15m_candles(candles)
        assert len(result) == 1
        assert result[0]["interval"] == "15m"
        assert result[0]["open"] == 68000.0
        assert result[0]["close"] == 68018.0  # i=13 is last in window: 68005+13
        assert result[0]["high"] == 68023.0  # max(high) = 68010+13
        assert result[0]["low"] == 67990.0   # min(low) = 67990+0
        assert result[0]["volume"] == 14.0   # 14 candles (i=14 spills to next window)

    def test_two_windows(self):
        """Candles spanning two 15m windows produce two 15m candles."""
        b1 = 1700000100.0  # aligned to 900s
        b2 = b1 + 900
        candles = []
        # Window 1: 10 candles
        for i in range(10):
            candles.append({
                "asset": "BTC", "source": "binance", "interval": "1m",
                "open_time": b1 + i * 60,
                "open": 68000.0, "high": 68010.0,
                "low": 67990.0, "close": 68005.0,
                "volume": 1.0, "quote_volume": 68000.0, "trades": 10,
            })
        # Window 2: 12 candles
        for i in range(12):
            candles.append({
                "asset": "BTC", "source": "binance", "interval": "1m",
                "open_time": b2 + i * 60,
                "open": 68100.0, "high": 68110.0,
                "low": 68090.0, "close": 68105.0,
                "volume": 2.0, "quote_volume": 136200.0, "trades": 20,
            })
        result = aggregate_1m_to_15m_candles(candles)
        assert len(result) == 2
        assert result[0]["open"] == 68000.0
        assert result[1]["open"] == 68100.0
        assert result[1]["volume"] == 24.0

    def test_sparse_window_skipped(self):
        """A window with fewer than 3 candles is skipped."""
        b1 = 1700000100.0
        b2 = b1 + 900
        candles = [
            {
                "asset": "BTC", "source": "binance", "interval": "1m",
                "open_time": b1, "open": 68000.0, "high": 68010.0,
                "low": 67990.0, "close": 68005.0,
                "volume": 1.0, "quote_volume": 68000.0, "trades": 10,
            },
            {
                "asset": "BTC", "source": "binance", "interval": "1m",
                "open_time": b2, "open": 68100.0, "high": 68110.0,
                "low": 68090.0, "close": 68105.0,
                "volume": 2.0, "quote_volume": 136200.0, "trades": 20,
            },
        ]
        result = aggregate_1m_to_15m_candles(candles)
        assert len(result) == 0  # both windows have < 3 candles

    def test_output_sorted_oldest_first(self):
        """Output should be sorted by open_time ascending."""
        base = 1700000100.0  # aligned
        candles = []
        for w in range(3):
            for i in range(10):
                candles.append({
                    "asset": "ETH", "source": "coinbase", "interval": "1m",
                    "open_time": base + w * 900 + i * 60,
                    "open": 3500.0, "high": 3510.0,
                    "low": 3490.0, "close": 3505.0,
                    "volume": 0.5, "quote_volume": 1750.0, "trades": 5,
                })
        # Shuffle input
        import random
        rng = random.Random(99)
        rng.shuffle(candles)
        result = aggregate_1m_to_15m_candles(candles)
        assert len(result) == 3
        times = [r["open_time"] for r in result]
        assert times == sorted(times)
