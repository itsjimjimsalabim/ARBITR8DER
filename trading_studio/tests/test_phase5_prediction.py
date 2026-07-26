"""Phase 5: Prediction evidence loop tests.

Tests the feature extraction engine, baseline prediction engine,
market outcome resolver, and prediction scorer — all offline (no live APIs).
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# Fixtures — fake data objects that match real API shapes
# =========================================================================

@dataclass
class FakeCandle:
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    quote_volume: float = 0.0


@dataclass
class FakeSnapshot:
    asset: MagicMock = field(default_factory=lambda: MagicMock(value="BTC"))
    snapshot_version: int = 1
    spot_avg_usd: float | None = 100000.0
    spot_disagreement_pct: float | None = 0.001
    kalshi_midpoint_cents: int | None = 55
    source_health: dict = field(default_factory=lambda: {
        "binance_btc": MagicMock(value="healthy"),
        "coinbase_btc": MagicMock(value="healthy"),
    })
    stale_sources: list = field(default_factory=list)
    missing_sources: list = field(default_factory=list)


@dataclass
class FakeKalshiMarket:
    ticker: str = "KXBTC15M-26JUL23-T15:00"
    midpoint_cents: int | None = 55
    yes_bid: int | None = 54
    yes_ask: int | None = 56
    close_time: str = "2026-07-23T19:00:00+00:00"


@dataclass
class FakeCoinGeckoObs:
    market_cap_usd: float = 2_000_000_000_000.0


def _make_candles(n: int = 16, base_price: float = 100000.0, drift: float = 0.001) -> list[FakeCandle]:
    """Generate N candles with slight upward drift."""
    candles = []
    price = base_price
    for i in range(n):
        change = price * drift
        c = FakeCandle(
            open=price,
            high=price + abs(change),
            low=price - abs(change) * 0.5,
            close=price + change,
            quote_volume=price * 100,
        )
        candles.append(c)
        price = c.close
    return candles


# =========================================================================
# Feature Extraction Engine
# =========================================================================

class TestFeatureExtractionEngine:
    def test_extract_basic_features(self) -> None:
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        engine = FeatureExtractionEngine()
        candles = _make_candles(16, base_price=100000.0, drift=0.001)
        snapshot = FakeSnapshot()
        kalshi = FakeKalshiMarket()
        coingecko = FakeCoinGeckoObs()

        features = engine.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=snapshot,
            candles=candles,
            kalshi_market=kalshi,
            coingecko_obs=coingecko,
        )

        assert features.asset == "BTC"
        assert features.snapshot_version == 1
        assert features.direction_1m is not None
        assert features.direction_5m is not None
        assert features.direction_15m is not None
        assert features.realized_vol_5m is not None
        assert features.realized_vol_15m is not None
        assert features.spot_disagreement_pct == 0.001
        assert features.recent_volume_usd is not None
        assert features.market_cap_usd is not None
        assert features.kalshi_midpoint_cents == 55.0
        assert features.kalshi_spread_cents == 2.0

    def test_extract_without_candles(self) -> None:
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        engine = FeatureExtractionEngine()
        snapshot = FakeSnapshot()

        features = engine.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=snapshot,
        )

        assert features.direction_1m is None
        assert features.direction_5m is None
        assert features.spot_disagreement_pct == 0.001

    def test_feature_completeness(self) -> None:
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        engine = FeatureExtractionEngine()
        candles = _make_candles(16)
        snapshot = FakeSnapshot()
        kalshi = FakeKalshiMarket()
        coingecko = FakeCoinGeckoObs()

        features = engine.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=snapshot,
            candles=candles,
            kalshi_market=kalshi,
            coingecko_obs=coingecko,
        )

        assert features.completeness_pct > 50  # Should have most features

    def test_feature_to_dict(self) -> None:
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        engine = FeatureExtractionEngine()
        features = engine.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=FakeSnapshot(),
        )

        d = features.to_dict()
        assert "asset" in d
        assert "snapshot_version" in d
        assert "direction_1m" in d
        assert "kalshi_midpoint_cents" in d

    def test_direction_computation(self) -> None:
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        engine = FeatureExtractionEngine()

        # Upward candles
        candles = _make_candles(16, base_price=100.0, drift=0.01)
        features = engine.extract(asset="BTC", snapshot_version=1, snapshot=FakeSnapshot(), candles=candles)
        assert features.direction_1m is not None
        assert features.direction_1m > 0  # Should be positive

        # Downward candles
        candles = _make_candles(16, base_price=100.0, drift=-0.01)
        features = engine.extract(asset="BTC", snapshot_version=1, snapshot=FakeSnapshot(), candles=candles)
        assert features.direction_1m is not None
        assert features.direction_1m < 0  # Should be negative


# =========================================================================
# Baseline Prediction Engine
# =========================================================================

class TestBaselinePredictionEngine:
    def test_predict_with_valid_features(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import BaselinePredictionEngine
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        fe = FeatureExtractionEngine()
        candles = _make_candles(16)
        features = fe.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=FakeSnapshot(),
            candles=candles,
            kalshi_market=FakeKalshiMarket(),
            coingecko_obs=FakeCoinGeckoObs(),
        )

        engine = BaselinePredictionEngine()
        record = engine.predict(asset="BTC", ticker="KXBTC15M-26JUL23-T15:00", features=features)

        assert record.rejected is False
        assert record.yes_probability is not None
        assert 0.01 <= record.yes_probability <= 0.99
        assert record.confidence is not None
        assert record.edge_pct is not None
        assert record.model_version == "baseline_v1"

    def test_predict_rejects_no_midpoint(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import BaselinePredictionEngine
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        fe = FeatureExtractionEngine()
        features = fe.extract(asset="BTC", snapshot_version=1, snapshot=FakeSnapshot())
        # Force no midpoint
        features.kalshi_midpoint_cents = None

        engine = BaselinePredictionEngine()
        record = engine.predict(asset="BTC", ticker="TEST", features=features)

        assert record.rejected is True
        assert record.rejection_reason == "no_kalshi_midpoint"

    def test_predict_with_midpoint_override(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import BaselinePredictionEngine
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        fe = FeatureExtractionEngine()
        features = fe.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=FakeSnapshot(),
            candles=_make_candles(16),
            kalshi_market=FakeKalshiMarket(),
        )

        engine = BaselinePredictionEngine()
        record = engine.predict(
            asset="BTC",
            ticker="TEST",
            features=features,
            kalshi_midpoint_override=70.0,
        )

        assert record.rejected is False
        # Probability should be close to 70% (market-implied with small trend adjustment)
        assert 0.5 < record.yes_probability < 0.9

    def test_edge_is_computed(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import BaselinePredictionEngine
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        fe = FeatureExtractionEngine()
        features = fe.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=FakeSnapshot(),
            candles=_make_candles(16),
            kalshi_market=FakeKalshiMarket(),
        )

        engine = BaselinePredictionEngine()
        record = engine.predict(asset="BTC", ticker="TEST", features=features)

        # Edge should be small (we're ~90% market-implied)
        assert record.edge_pct is not None
        assert abs(record.edge_pct) < 5.0

    def test_prediction_record_serialization(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import BaselinePredictionEngine
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        fe = FeatureExtractionEngine()
        features = fe.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=FakeSnapshot(),
            candles=_make_candles(16),
            kalshi_market=FakeKalshiMarket(),
        )

        engine = BaselinePredictionEngine()
        record = engine.predict(asset="BTC", ticker="TEST", features=features)

        d = record.to_dict()
        assert "prediction_id" in d
        assert "yes_probability" in d
        assert "features" in d
        assert "model_version" in d

    def test_format_prediction_human(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import (
            BaselinePredictionEngine,
            format_prediction_human,
        )
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        fe = FeatureExtractionEngine()
        features = fe.extract(
            asset="BTC",
            snapshot_version=1,
            snapshot=FakeSnapshot(),
            candles=_make_candles(16),
            kalshi_market=FakeKalshiMarket(),
        )

        engine = BaselinePredictionEngine()
        record = engine.predict(asset="BTC", ticker="KXBTC15M-TEST", features=features)
        output = format_prediction_human(record)

        assert "BTC" in output
        assert "YES prob" in output
        assert "Confidence" in output
        assert "Edge" in output

    def test_format_prediction_human_rejected(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import (
            BaselinePredictionEngine,
            format_prediction_human,
        )

        engine = BaselinePredictionEngine()
        from arbitr8der_package.prediction.feature_extraction_engine import FeatureExtractionEngine
        fe = FeatureExtractionEngine()
        features = fe.extract(asset="BTC", snapshot_version=1, snapshot=FakeSnapshot())
        features.kalshi_midpoint_cents = None

        record = engine.predict(asset="BTC", ticker="TEST", features=features)
        output = format_prediction_human(record)

        assert "REJECTED" in output
        assert "no_kalshi_midpoint" in output


# =========================================================================
# Market Outcome Resolver
# =========================================================================

class TestMarketOutcomeResolver:
    def test_parse_settled_yes(self) -> None:
        from arbitr8der_package.prediction.market_outcome_resolver import MarketOutcomeResolver

        resolver = MarketOutcomeResolver.__new__(MarketOutcomeResolver)
        fixture = MarketOutcomeResolver.parse_fixture_settled_response()
        outcome = resolver._parse_outcome("KXBTC15M-26JUL23-T15:00", fixture["market"])

        assert outcome.resolved is True
        assert outcome.actual_outcome == 1  # YES
        assert outcome.market_status == "settled"

    def test_parse_closed_not_settled(self) -> None:
        from arbitr8der_package.prediction.market_outcome_resolver import MarketOutcomeResolver

        resolver = MarketOutcomeResolver.__new__(MarketOutcomeResolver)
        fixture = MarketOutcomeResolver.parse_fixture_closed_response()
        outcome = resolver._parse_outcome("KXBTC15M-26JUL23-T16:00", fixture["market"])

        assert outcome.resolved is False
        assert outcome.actual_outcome is None
        assert outcome.market_status == "closed"

    def test_outcome_to_dict(self) -> None:
        from arbitr8der_package.prediction.market_outcome_resolver import MarketOutcome, MarketOutcomeResolver

        outcome = MarketOutcome(
            ticker="TEST",
            resolved=True,
            actual_outcome=1,
            market_status="settled",
        )
        d = outcome.to_dict()
        assert d["ticker"] == "TEST"
        assert d["resolved"] is True
        assert d["actual_outcome"] == 1

    def test_resolve_predictions_updates_records(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.market_outcome_resolver import MarketOutcomeResolver

        # Create a prediction record
        pred = PredictionRecord(
            prediction_id="test-1",
            asset="BTC",
            ticker="KXBTC15M-26JUL23-T15:00",
            yes_probability=0.65,
        )

        # Mock the resolver to return a settled outcome
        resolver = MarketOutcomeResolver.__new__(MarketOutcomeResolver)
        resolver._base_url = "http://fake"
        resolver._headers = {}

        from arbitr8der_package.prediction.market_outcome_resolver import MarketOutcome
        fake_outcome = MarketOutcome(
            ticker="KXBTC15M-26JUL23-T15:00",
            resolved=True,
            actual_outcome=1,
            market_status="settled",
            resolved_at=datetime.now(timezone.utc),
        )

        with patch.object(resolver, 'resolve_market', return_value=fake_outcome):
            import asyncio
            results = asyncio.run(resolver.resolve_predictions([pred]))

        assert results[0].actual_outcome == 1
        assert results[0].outcome_ts is not None


# =========================================================================
# Prediction Scorer
# =========================================================================

class TestPredictionScorer:
    def test_score_correct_prediction(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        record = PredictionRecord(
            asset="BTC",
            yes_probability=0.8,
            actual_outcome=1,
        )

        scored = scorer.score_prediction(record)
        assert scored.score_brier is not None
        assert scored.score_brier < 0.1  # Good prediction, low Brier
        assert scored.score_log_loss is not None
        assert scored.score_log_loss < 1.0

    def test_score_wrong_prediction(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        record = PredictionRecord(
            asset="BTC",
            yes_probability=0.8,
            actual_outcome=0,  # Wrong!
        )

        scored = scorer.score_prediction(record)
        assert scored.score_brier is not None
        assert scored.score_brier > 0.5  # Bad prediction, high Brier

    def test_score_skips_rejected(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        record = PredictionRecord(
            asset="BTC",
            rejected=True,
            rejection_reason="no_kalshi_midpoint",
        )

        scored = scorer.score_prediction(record)
        assert scored.score_brier is None

    def test_batch_scoring(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        records = [
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
            PredictionRecord(asset="BTC", yes_probability=0.3, actual_outcome=0),
            PredictionRecord(asset="ETH", yes_probability=0.6, actual_outcome=1),
        ]

        scored = scorer.score_batch(records)
        assert all(r.score_brier is not None for r in scored)
        assert len(scorer.get_history()) == 3

    def test_report_generation(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        records = [
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
            PredictionRecord(asset="BTC", yes_probability=0.3, actual_outcome=0),
            PredictionRecord(asset="ETH", yes_probability=0.6, actual_outcome=1),
            PredictionRecord(asset="ETH", yes_probability=0.4, actual_outcome=0),
        ]

        scorer.score_batch(records)
        report = scorer.generate_report()

        assert report.total_predictions == 4
        assert report.scored_predictions == 4
        assert report.mean_brier is not None
        assert report.accuracy_pct is not None
        assert report.accuracy_pct == 100.0  # All correct (>=0.5 for YES, <0.5 for NO)

    def test_report_per_asset(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        records = [
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
            PredictionRecord(asset="ETH", yes_probability=0.3, actual_outcome=0),
        ]

        scorer.score_batch(records)
        report = scorer.generate_report()

        assert "BTC" in report.per_asset
        assert "ETH" in report.per_asset
        assert report.per_asset["BTC"]["count"] == 1
        assert report.per_asset["ETH"]["count"] == 1

    def test_report_with_rejections(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        records = [
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
            PredictionRecord(asset="BTC", rejected=True, rejection_reason="no_kalshi_midpoint"),
        ]

        scorer.score_batch(records)
        report = scorer.generate_report()

        assert report.total_predictions == 2
        assert report.scored_predictions == 1
        assert report.rejected_predictions == 1

    def test_report_format_human(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer, format_report_human

        scorer = PredictionScorer()
        records = [
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
            PredictionRecord(asset="BTC", yes_probability=0.3, actual_outcome=0),
        ]

        scorer.score_batch(records)
        report = scorer.generate_report()
        output = format_report_human(report)

        assert "Scoring Report" in output
        assert "Brier" in output
        assert "BTC" in output

    def test_report_format_json(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer, format_report_json

        scorer = PredictionScorer()
        records = [
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
        ]

        scorer.score_batch(records)
        report = scorer.generate_report()
        output = format_report_json(report)
        parsed = json.loads(output)

        assert "mean_brier" in parsed
        assert "accuracy_pct" in parsed

    def test_brier_score_bounds(self) -> None:
        """Brier score should always be between 0 and 1."""
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()

        # Best possible: predict 1.0, outcome 1.0
        best = PredictionRecord(asset="BTC", yes_probability=0.999, actual_outcome=1)
        scorer.score_prediction(best)
        assert 0 <= best.score_brier < 0.001

        # Worst possible: predict 1.0, outcome 0.0
        worst = PredictionRecord(asset="BTC", yes_probability=0.999, actual_outcome=0)
        scorer.score_prediction(worst)
        assert worst.score_brier > 0.99

    def test_log_loss_bounds(self) -> None:
        """Log loss should always be positive."""
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()

        record = PredictionRecord(asset="BTC", yes_probability=0.7, actual_outcome=1)
        scorer.score_prediction(record)
        assert record.score_log_loss > 0

        # Low probability for YES outcome = high log loss
        record2 = PredictionRecord(asset="BTC", yes_probability=0.1, actual_outcome=1)
        scorer.score_prediction(record2)
        assert record2.score_log_loss > record.score_log_loss

    def test_clear_history(self) -> None:
        from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord
        from arbitr8der_package.prediction.prediction_scorer import PredictionScorer

        scorer = PredictionScorer()
        scorer.score_batch([
            PredictionRecord(asset="BTC", yes_probability=0.8, actual_outcome=1),
        ])
        assert len(scorer.get_history()) == 1

        scorer.clear_history()
        assert len(scorer.get_history()) == 0


# =========================================================================
# REPL integration with predict
# =========================================================================

class TestREPLPredictIntegration:
    def test_repl_predict_requires_orchestrator(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_predict("")
        captured = capsys.readouterr()
        assert "Orchestrator not running" in captured.out

    def test_repl_predict_with_mock_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test predict command with mocked orchestrator and data."""
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._orchestrator = MagicMock()
        repl._orchestrator.running = True
        repl._orchestrator.latest_snapshots.return_value = {}
        repl._binance = MagicMock()
        repl._binance.last_candles = {}

        repl._cmd_predict("")
        captured = capsys.readouterr()
        assert "No snapshot data yet" in captured.out
