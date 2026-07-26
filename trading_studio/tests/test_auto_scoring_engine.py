"""Tests for auto_scoring_engine — prediction scoring, outcome determination,
model accuracy dashboard, and continuous scoring loop.
"""

from __future__ import annotations

import asyncio
import math

import pytest
import pytest_asyncio

from arbitr8der_package.durable_storage.sqlite_database_engine_manager import (
    initialize_database,
)
from arbitr8der_package.durable_storage.candle_persistence_store import (
    CandlePersistenceStore,
)
from arbitr8der_package.prediction.auto_scoring_engine import (
    AutoScoringEngine,
    ModelScorecard,
    ScoringSummary,
)
from arbitr8der_package.prediction.model_run_record_store import (
    ModelRunRecordStore,
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


@pytest_asyncio.fixture
async def model_run_store(db):
    return ModelRunRecordStore(db)


@pytest_asyncio.fixture
async def engine(model_run_store, store):
    return AutoScoringEngine(model_run_store=model_run_store, candle_store=store)


def _make_candle_row(asset="BTC", source="binance", interval="1m",
                     open_time=1700000000.0, open_p=68000.0, close=68050.0):
    return {
        "asset": asset,
        "source": source,
        "interval": interval,
        "open_time": open_time,
        "open": open_p,
        "high": max(open_p, close) + 10,
        "low": min(open_p, close) - 10,
        "close": close,
        "volume": 1.5,
        "quote_volume": 102000.0,
        "trades": 500,
    }


# ---------------------------------------------------------------------------
# Score pending predictions
# ---------------------------------------------------------------------------

class TestScorePending:
    @pytest.mark.asyncio
    async def test_score_matching_prediction(self, engine, model_run_store, store):
        """Prediction with yes_prob > 0.5, outcome UP → correct."""
        pid = await model_run_store.record_prediction(
            model_name="test_model", asset="BTC",
            window_open=1700000000.0, yes_probability=0.65, confidence=0.8,
        )
        oid = await store.record_outcome(
            asset="BTC", ticker="TICKER-1",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=68050.0, direction="UP",
        )

        scored = await engine.score_pending()
        assert scored == 1

        accuracy = await model_run_store.get_model_accuracy("test_model")
        assert accuracy["total_scored"] == 1
        assert accuracy["correct"] == 1

    @pytest.mark.asyncio
    async def test_score_wrong_prediction(self, engine, model_run_store, store):
        """Prediction with yes_prob > 0.5, outcome DOWN → incorrect."""
        pid = await model_run_store.record_prediction(
            model_name="test_model", asset="BTC",
            window_open=1700000000.0, yes_probability=0.65, confidence=0.8,
        )
        oid = await store.record_outcome(
            asset="BTC", ticker="TICKER-1",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=67900.0, direction="DOWN",
        )

        scored = await engine.score_pending()
        assert scored == 1

        accuracy = await model_run_store.get_model_accuracy("test_model")
        assert accuracy["correct"] == 0
        assert accuracy["total_pnl_cents"] < 0

    @pytest.mark.asyncio
    async def test_no_pending_returns_zero(self, engine):
        scored = await engine.score_pending()
        assert scored == 0

    @pytest.mark.asyncio
    async def test_multiple_predictions(self, engine, model_run_store, store):
        """Score multiple predictions for same asset."""
        for i in range(5):
            await model_run_store.record_prediction(
                model_name="m1", asset="BTC",
                window_open=1700000000.0 + i * 900,
                yes_probability=0.7, confidence=0.8,
            )
            # Alternate outcomes
            direction = "UP" if i % 2 == 0 else "DOWN"
            await store.record_outcome(
                asset="BTC", ticker=f"T-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=68050.0 if direction == "UP" else 67950.0,
                direction=direction,
            )

        scored = await engine.score_pending()
        assert scored == 5

        accuracy = await model_run_store.get_model_accuracy("m1")
        assert accuracy["total_scored"] == 5
        # 0.7 > 0.5 → predicted UP. UP on 0,2,4. Correct on 0,2,4 = 3
        assert accuracy["correct"] == 3

    @pytest.mark.asyncio
    async def test_idempotent_rescoring(self, engine, model_run_store, store):
        """Scoring twice doesn't double-count."""
        await model_run_store.record_prediction(
            model_name="m1", asset="BTC",
            window_open=1700000000.0, yes_probability=0.65, confidence=0.8,
        )
        await store.record_outcome(
            asset="BTC", ticker="T-1",
            window_open=1700000000.0, window_close=1700000900.0,
            open_price=68000.0, close_price=68050.0, direction="UP",
        )

        scored1 = await engine.score_pending()
        assert scored1 == 1

        scored2 = await engine.score_pending()
        assert scored2 == 0  # already scored


# ---------------------------------------------------------------------------
# Determine outcomes from candles
# ---------------------------------------------------------------------------

class TestDetermineOutcomes:
    @pytest.mark.asyncio
    async def test_determine_up_outcome(self, engine, store):
        """15 1m candles forming a 15m window with close > open → UP."""
        boundary = 1700000000.0
        rows = []
        for i in range(15):
            # Steady uptrend: each candle slightly higher
            p = 68000.0 + i * 5
            rows.append(_make_candle_row(
                open_time=boundary + i * 60, open_p=p, close=p + 5,
            ))
        await store.upsert_candles(rows)

        recorded = await engine.determine_outcomes_from_candles("BTC")
        assert recorded >= 1

        outcomes = await store.get_outcomes("BTC")
        assert len(outcomes) >= 1
        assert outcomes[0]["direction"] == "UP"

    @pytest.mark.asyncio
    async def test_determine_down_outcome(self, engine, store):
        """15 1m candles with close < open → DOWN."""
        boundary = 1700000000.0
        rows = []
        for i in range(15):
            p = 68000.0 - i * 5
            rows.append(_make_candle_row(
                open_time=boundary + i * 60, open_p=p, close=p - 5,
            ))
        await store.upsert_candles(rows)

        recorded = await engine.determine_outcomes_from_candles("BTC")
        assert recorded >= 1

        outcomes = await store.get_outcomes("BTC")
        assert outcomes[0]["direction"] == "DOWN"

    @pytest.mark.asyncio
    async def test_incomplete_window_skipped(self, engine, store):
        """Fewer than 10 candles in a window → skipped."""
        rows = [_make_candle_row(open_time=1700000000.0 + i * 60) for i in range(5)]
        await store.upsert_candles(rows)

        recorded = await engine.determine_outcomes_from_candles("BTC")
        assert recorded == 0

    @pytest.mark.asyncio
    async def test_multiple_windows(self, engine, store):
        """Two complete 15m windows → two outcomes."""
        rows = []
        # Window 1: 1700000000 to 1700000900
        for i in range(15):
            rows.append(_make_candle_row(
                open_time=1700000000.0 + i * 60,
                open_p=68000.0 + i * 2, close=68000.0 + i * 2 + 3,
            ))
        # Window 2: 1700000900 to 1700001800
        for i in range(15):
            rows.append(_make_candle_row(
                open_time=1700000900.0 + i * 60,
                open_p=68030.0 - i * 2, close=68030.0 - i * 2 - 3,
            ))
        await store.upsert_candles(rows)

        recorded = await engine.determine_outcomes_from_candles("BTC")
        assert recorded >= 2


# ---------------------------------------------------------------------------
# Model scorecard
# ---------------------------------------------------------------------------

class TestModelScorecard:
    @pytest.mark.asyncio
    async def test_scorecard_with_predictions(self, engine, model_run_store, store):
        for i in range(10):
            await model_run_store.record_prediction(
                model_name="m1", asset="BTC",
                window_open=1700000000.0 + i * 900,
                yes_probability=0.6, confidence=0.7,
            )
            direction = "UP" if i % 2 == 0 else "DOWN"
            await store.record_outcome(
                asset="BTC", ticker=f"T-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0,
                close_price=68050.0 if direction == "UP" else 67950.0,
                direction=direction,
            )
        await engine.score_pending()

        sc = await engine.get_model_scorecard("m1", "BTC")
        assert isinstance(sc, ModelScorecard)
        assert sc.model_name == "m1"
        assert sc.asset == "BTC"
        assert sc.scored_predictions == 10
        assert sc.correct == 5
        assert sc.accuracy_pct == pytest.approx(50.0)
        assert sc.brier_score >= 0.0

    @pytest.mark.asyncio
    async def test_scorecard_empty(self, engine):
        sc = await engine.get_model_scorecard("nonexistent")
        assert sc.scored_predictions == 0

    @pytest.mark.asyncio
    async def test_all_model_scorecards(self, engine, model_run_store, store):
        for name in ("m1", "m2"):
            for i in range(5):
                await model_run_store.record_prediction(
                    model_name=name, asset="BTC",
                    window_open=1700000000.0 + i * 900,
                    yes_probability=0.6, confidence=0.7,
                )
                await store.record_outcome(
                    asset="BTC", ticker=f"{name}-T-{i}",
                    window_open=1700000000.0 + i * 900,
                    window_close=1700000900.0 + i * 900,
                    open_price=68000.0, close_price=68050.0,
                    direction="UP",
                )
        await engine.score_pending()

        summary = await engine.get_all_model_scorecards()
        assert isinstance(summary, ScoringSummary)
        # Should have 2 model-level scorecards (one per model, aggregated ALL)
        model_names = {m.model_name for m in summary.models}
        assert "m1" in model_names
        assert "m2" in model_names


# ---------------------------------------------------------------------------
# Brier score and log loss
# ---------------------------------------------------------------------------

class TestMetrics:
    @pytest.mark.asyncio
    async def test_brier_perfect(self, engine, model_run_store, store):
        """All predictions at 1.0 for correct UP → Brier = 0."""
        for i in range(5):
            await model_run_store.record_prediction(
                model_name="perfect", asset="BTC",
                window_open=1700000000.0 + i * 900,
                yes_probability=0.99, confidence=0.9,
            )
            await store.record_outcome(
                asset="BTC", ticker=f"P-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=68050.0,
                direction="UP",
            )
        await engine.score_pending()

        sc = await engine.get_model_scorecard("perfect", "BTC")
        # Brier should be close to 0 (0.01^2 per prediction)
        assert sc.brier_score < 0.01

    @pytest.mark.asyncio
    async def test_brier_worst(self, engine, model_run_store, store):
        """All predictions at 1.0 for WRONG → Brier near 1.0."""
        for i in range(5):
            await model_run_store.record_prediction(
                model_name="worst", asset="BTC",
                window_open=1700000000.0 + i * 900,
                yes_probability=0.99, confidence=0.9,
            )
            await store.record_outcome(
                asset="BTC", ticker=f"W-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=67950.0,
                direction="DOWN",
            )
        await engine.score_pending()

        sc = await engine.get_model_scorecard("worst", "BTC")
        assert sc.brier_score > 0.9

    @pytest.mark.asyncio
    async def test_log_loss_perfect(self, engine, model_run_store, store):
        """Log loss near 0 for confident correct predictions."""
        for i in range(5):
            await model_run_store.record_prediction(
                model_name="ll_perfect", asset="BTC",
                window_open=1700000000.0 + i * 900,
                yes_probability=0.99, confidence=0.9,
            )
            await store.record_outcome(
                asset="BTC", ticker=f"LL-{i}",
                window_open=1700000000.0 + i * 900,
                window_close=1700000900.0 + i * 900,
                open_price=68000.0, close_price=68050.0,
                direction="UP",
            )
        await engine.score_pending()

        sc = await engine.get_model_scorecard("ll_perfect", "BTC")
        assert sc.log_loss < 0.05

    @pytest.mark.asyncio
    async def test_scorecard_to_dict(self, engine, store):
        sc = ModelScorecard(model_name="m", asset="BTC", scored_predictions=5, correct=3)
        d = sc.to_dict()
        assert d["model_name"] == "m"
        assert d["accuracy_pct"] == 0.0  # no scoring data yet
