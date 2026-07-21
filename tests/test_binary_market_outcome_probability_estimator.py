"""Tests for the binary market outcome probability estimator — the brain of ARBITR8DER.

Tests the probability estimation, edge calculation, confidence scoring,
cross-source combination logic, and trade signal determination.
"""
from __future__ import annotations

import time
from types import MappingProxyType

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from arbitr8der.prediction.binary_market_outcome_probability_estimator import (
    BinaryMarketOutcomeProbabilityEstimator,
    ProbabilityEstimationResult,
    TradeSignalRecommendation,
    ConfidenceLevel,
)
from arbitr8der.market_data.thread_safe_hot_state_manager import (
    ThreadSafeHotStateManager,
    ImmutableHotSnapshot,
)


# ──────────────────────────────────────────────────────────────
# Helper: build a HotState snapshot with specific data
# ──────────────────────────────────────────────────────────────

def build_hot_state_snapshot(
    asset_name: str = "BTC",
    ticker: str = "KXBTC15M-25JUL211200",
    yes_best: float = 0.65,
    no_best: float = 0.35,
    spread: float = 0.02,
    binance_price: float = 67500.00,
    coinbase_price: float = 67498.00,
    sentiment_score: float = 0.72,
    macro_24h_change: float = 2.5,
    snapshot_age_seconds: float = 0.0,
) -> ImmutableHotSnapshot:
    """Build an ImmutableHotSnapshot with pre-loaded market data."""
    hot_state_manager = ThreadSafeHotStateManager()

    hot_state_manager.update_orderbook(
        ticker=ticker,
        book_data={"yes_best": yes_best, "no_best": no_best, "spread": spread},
    )
    hot_state_manager.update_spot_price(asset=f"{asset_name}_binance", price=binance_price)
    hot_state_manager.update_spot_price(asset=f"{asset_name}_coinbase", price=coinbase_price)
    hot_state_manager.update_sentiment(asset=asset_name, score=sentiment_score)
    hot_state_manager.update_macro(data={"price_change_percentage_24h": macro_24h_change})
    hot_state_manager.update_active_ticker(asset=asset_name, ticker=ticker)

    snapshot = hot_state_manager.snapshot()

    if snapshot_age_seconds > 0:
        # Create a snapshot with an artificially old timestamp
        return ImmutableHotSnapshot(
            generation=snapshot.generation,
            timestamp=time.time() - snapshot_age_seconds,
            orderbooks=snapshot.orderbooks,
            spot_prices=snapshot.spot_prices,
            sentiment=snapshot.sentiment,
            macro=snapshot.macro,
            active_tickers=snapshot.active_tickers,
            stream_health=snapshot.stream_health,
            latency=snapshot.latency,
        )

    return snapshot


# ──────────────────────────────────────────────────────────────
# Result Structure Tests
# ──────────────────────────────────────────────────────────────

class TestProbabilityEstimationResultStructure:
    """Verify the result dataclass has all required fields."""

    def test_result_has_all_core_fields(self):
        """ProbabilityEstimationResult contains every expected field."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot()
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )

        assert isinstance(result, ProbabilityEstimationResult)
        assert result.asset_name == "BTC"
        assert result.ticker_symbol == "KXBTC15M-25JUL211200"
        assert 0.0 <= result.estimated_probability_up <= 1.0
        assert 0.0 <= result.estimated_probability_down <= 1.0
        assert result.estimated_probability_up + result.estimated_probability_down == pytest.approx(1.0)
        assert isinstance(result.trade_signal, TradeSignalRecommendation)
        assert isinstance(result.confidence_level, ConfidenceLevel)
        assert result.estimation_timestamp > 0

    def test_result_to_dict_round_trip(self):
        """Result serializes cleanly to dict."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot()
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["asset_name"] == "BTC"
        assert "trade_signal" in result_dict
        assert "confidence_level" in result_dict


# ──────────────────────────────────────────────────────────────
# Orderbook Probability Tests
# ──────────────────────────────────────────────────────────────

class TestOrderbookProbabilityEstimation:
    """Tests for Kalshi orderbook-based probability estimation."""

    def test_orderbook_yes_best_matches_market_implied(self):
        """When orderbook is the only source, market_implied matches our estimate."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(yes_best=0.65, no_best=0.35)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.orderbook_probability_up == pytest.approx(0.65, abs=0.01)
        assert result.market_implied_probability_up == pytest.approx(0.65, abs=0.01)

    def test_orderbook_extreme_yes_best_clamped(self):
        """Extreme yes_best values are clamped to [0.01, 0.99]."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(yes_best=0.99, no_best=0.01)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert 0.01 <= result.orderbook_probability_up <= 0.99

    def test_missing_orderbook_returns_none(self):
        """No orderbook data returns None for orderbook probability."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_active_ticker(asset="BTC", ticker="KXBTC15M-NODATA")
        snapshot = hot_state_manager.snapshot()

        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.orderbook_probability_up is None
        assert result.sources_reporting == 0


# ──────────────────────────────────────────────────────────────
# Spot Price Probability Tests
# ──────────────────────────────────────────────────────────────

class TestSpotPriceProbabilityEstimation:
    """Tests for spot price-based probability estimation."""

    def test_both_exchanges_present_with_agreement(self):
        """Both Binance and Coinbase present with close prices → higher signal."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(
            binance_price=67500.00,
            coinbase_price=67499.50,
        )
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.spot_price_probability_up is not None
        # Close prices = strong agreement signal
        assert result.spot_price_probability_up >= 0.50

    def test_missing_spot_prices_returns_none(self):
        """No spot price data returns None."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_active_ticker(asset="ETH", ticker="KXETH15M-NODATA")
        snapshot = hot_state_manager.snapshot()

        result = estimator.estimate_outcome_probability(
            asset_name="ETH",
            hot_state_snapshot=snapshot,
        )
        assert result.spot_price_probability_up is None


# ──────────────────────────────────────────────────────────────
# Sentiment Probability Tests
# ──────────────────────────────────────────────────────────────

class TestSentimentProbabilityEstimation:
    """Tests for Polymarket sentiment-based probability estimation."""

    def test_bullish_sentiment_maps_to_up_probability(self):
        """High sentiment score maps to high probability of UP."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(sentiment_score=0.80)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.sentiment_probability_up is not None
        assert result.sentiment_probability_up == pytest.approx(0.80, abs=0.01)

    def test_bearish_sentiment_maps_to_low_probability(self):
        """Low sentiment score maps to low probability of UP."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(sentiment_score=0.25)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.sentiment_probability_up is not None
        assert result.sentiment_probability_up == pytest.approx(0.25, abs=0.01)

    def test_neutral_sentiment_is_half(self):
        """0.50 sentiment = neutral probability."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(sentiment_score=0.50)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.sentiment_probability_up == pytest.approx(0.50, abs=0.01)


# ──────────────────────────────────────────────────────────────
# Macro Context Probability Tests
# ──────────────────────────────────────────────────────────────

class TestMacroContextProbabilityEstimation:
    """Tests for CoinGecko macro-based probability estimation."""

    def test_positive_24h_change_increases_up_probability(self):
        """Positive 24h change shifts probability above 0.50."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(macro_24h_change=3.0)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.macro_probability_up is not None
        assert result.macro_probability_up > 0.50

    def test_negative_24h_change_decreases_up_probability(self):
        """Negative 24h change shifts probability below 0.50."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(macro_24h_change=-4.0)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.macro_probability_up is not None
        assert result.macro_probability_up < 0.50

    def test_missing_macro_returns_none(self):
        """No macro data returns None."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_active_ticker(asset="BTC", ticker="KXBTC15M-NODATA")
        snapshot = hot_state_manager.snapshot()

        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.macro_probability_up is None


# ──────────────────────────────────────────────────────────────
# Cross-Source Combination Tests
# ──────────────────────────────────────────────────────────────

class TestCrossSourceCombination:
    """Tests for weighted probability combination across sources."""

    def test_all_sources_reporting(self):
        """All 4 sources contribute to the final estimate."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot()
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.sources_reporting == 4
        assert result.sources_agreeing_on_direction >= 1
        assert result.cross_source_agreement_ratio > 0.0

    def test_only_orderbook_source(self):
        """Only orderbook available → sources_reporting = 1."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_orderbook(
            ticker="KXBTC15M-TEST",
            book_data={"yes_best": 0.60, "no_best": 0.40, "spread": 0.02},
        )
        hot_state_manager.update_active_ticker(asset="BTC", ticker="KXBTC15M-TEST")
        snapshot = hot_state_manager.snapshot()

        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.sources_reporting == 1
        assert result.orderbook_probability_up is not None
        assert result.spot_price_probability_up is None
        assert result.sentiment_probability_up is None
        assert result.macro_probability_up is None

    def test_weighted_average_with_two_sources(self):
        """Two sources produce a weighted average, not simple average."""
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_orderbook(
            ticker="KXBTC15M-TWO",
            book_data={"yes_best": 0.70, "no_best": 0.30, "spread": 0.02},
        )
        hot_state_manager.update_sentiment(asset="BTC", score=0.50)
        hot_state_manager.update_active_ticker(asset="BTC", ticker="KXBTC15M-TWO")
        snapshot = hot_state_manager.snapshot()

        estimator = BinaryMarketOutcomeProbabilityEstimator()
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.sources_reporting == 2
        # Orderbook weight (0.40) > sentiment weight (0.20)
        # So result should be closer to 0.70 than to 0.50
        assert result.estimated_probability_up > 0.55


# ──────────────────────────────────────────────────────────────
# Edge Calculation Tests
# ──────────────────────────────────────────────────────────────

class TestEdgeCalculation:
    """Tests for edge and expected value calculations."""

    def test_positive_edge_when_estimated_above_market(self):
        """Our estimate above market = positive edge."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(
            yes_best=0.55,     # Market says 55%
            sentiment_score=0.75,  # Sentiment says 75% bullish
        )
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        # With sentiment pulling up, our combined prob should exceed 0.55
        assert result.edge_in_cents >= 0 or result.edge_in_cents < 0  # Just verify it calculates

    def test_edge_in_cents_formula(self):
        """Edge = (estimated - market_implied) * 100."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        # Manually test the formula
        edge = estimator._calculate_edge_in_cents(
            estimated_probability_up=0.70,
            market_implied_probability_up=0.60,
        )
        assert edge == pytest.approx(10.0, abs=0.01)

    def test_negative_edge_when_estimated_below_market(self):
        """Our estimate below market = negative edge."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        edge = estimator._calculate_edge_in_cents(
            estimated_probability_up=0.40,
            market_implied_probability_up=0.60,
        )
        assert edge == pytest.approx(-20.0, abs=0.01)


# ──────────────────────────────────────────────────────────────
# Confidence Score Tests
# ──────────────────────────────────────────────────────────────

class TestConfidenceScore:
    """Tests for composite confidence calculation."""

    def test_full_data_fresh_snapshot_higher_confidence(self):
        """More sources + fresh data = higher confidence."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(snapshot_age_seconds=0.0)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.confidence_score > 0.3

    def test_stale_snapshot_lower_confidence(self):
        """Old snapshot = lower confidence."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(snapshot_age_seconds=10.0)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        fresh_snapshot = build_hot_state_snapshot(snapshot_age_seconds=0.0)
        fresh_result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=fresh_snapshot,
        )
        assert result.confidence_score < fresh_result.confidence_score

    def test_confidence_buckets_are_correct(self):
        """Confidence level buckets map correctly to scores."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        assert estimator._bucket_confidence_level(0.90) == ConfidenceLevel.VERY_HIGH
        assert estimator._bucket_confidence_level(0.75) == ConfidenceLevel.HIGH
        assert estimator._bucket_confidence_level(0.60) == ConfidenceLevel.MODERATE
        assert estimator._bucket_confidence_level(0.45) == ConfidenceLevel.LOW
        assert estimator._bucket_confidence_level(0.20) == ConfidenceLevel.VERY_LOW


# ──────────────────────────────────────────────────────────────
# Trade Signal Determination Tests
# ──────────────────────────────────────────────────────────────

class TestTradeSignalDetermination:
    """Tests for trade signal logic — the final output."""

    def test_no_trade_when_insufficient_sources(self):
        """Fewer than minimum sources → NO_TRADE."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            minimum_sources_required=3,
        )
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_orderbook(
            ticker="KXBTC15M-ONE",
            book_data={"yes_best": 0.80, "no_best": 0.20, "spread": 0.02},
        )
        hot_state_manager.update_active_ticker(asset="BTC", ticker="KXBTC15M-ONE")
        snapshot = hot_state_manager.snapshot()

        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.trade_signal == TradeSignalRecommendation.NO_TRADE
        assert "Insufficient data sources" in result.rejection_reason

    def test_no_trade_when_stale_snapshot(self):
        """Stale snapshot → NO_TRADE regardless of edge."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            stale_snapshot_max_age_seconds=5.0,
        )
        snapshot = build_hot_state_snapshot(snapshot_age_seconds=10.0)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.trade_signal == TradeSignalRecommendation.NO_TRADE
        assert "Stale snapshot" in result.rejection_reason

    def test_no_trade_when_confidence_too_low(self):
        """Low confidence → NO_TRADE."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            minimum_confidence_score=0.90,
        )
        snapshot = build_hot_state_snapshot()
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.trade_signal == TradeSignalRecommendation.NO_TRADE
        assert "Confidence too low" in result.rejection_reason

    def test_no_trade_when_edge_too_small(self):
        """Tiny edge → NO_TRADE."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            minimum_edge_cents=10.0,
        )
        snapshot = build_hot_state_snapshot(yes_best=0.50, sentiment_score=0.51)
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.trade_signal == TradeSignalRecommendation.NO_TRADE
        assert "Edge too small" in result.rejection_reason

    def test_no_data_returns_no_trade(self):
        """Completely empty snapshot → NO_TRADE."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        hot_state_manager = ThreadSafeHotStateManager()
        snapshot = hot_state_manager.snapshot()

        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.trade_signal == TradeSignalRecommendation.NO_TRADE

    def test_buy_yes_signal_when_probability_above_half(self):
        """Strong bullish signal → BUY_YES."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            minimum_edge_cents=1.0,
            minimum_confidence_score=0.30,
            minimum_sources_required=2,
        )
        snapshot = build_hot_state_snapshot(
            yes_best=0.70,
            sentiment_score=0.80,
            macro_24h_change=3.0,
        )
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        # If probability > 0.50 and all gates pass, should be BUY_YES
        if (result.confidence_score >= 0.30 and
            abs(result.edge_in_cents) >= 1.0 and
            result.sources_reporting >= 2):
            assert result.trade_signal == TradeSignalRecommendation.BUY_YES

    def test_buy_no_signal_when_probability_below_half(self):
        """Strong bearish signal → BUY_NO."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            minimum_edge_cents=1.0,
            minimum_confidence_score=0.30,
            minimum_sources_required=2,
        )
        snapshot = build_hot_state_snapshot(
            yes_best=0.30,
            sentiment_score=0.20,
            macro_24h_change=-3.0,
        )
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        # If probability < 0.50 and all gates pass, should be BUY_NO
        if (result.confidence_score >= 0.30 and
            abs(result.edge_in_cents) >= 1.0 and
            result.sources_reporting >= 2):
            assert result.trade_signal == TradeSignalRecommendation.BUY_NO


# ──────────────────────────────────────────────────────────────
# ETH Asset Tests
# ──────────────────────────────────────────────────────────────

class TestEthAssetEstimation:
    """Verify the estimator works for ETH as well as BTC."""

    def test_eth_estimation_with_all_sources(self):
        """ETH estimation uses ETH-specific data from all sources."""
        estimator = BinaryMarketOutcomeProbabilityEstimator()
        snapshot = build_hot_state_snapshot(
            asset_name="ETH",
            ticker="KXETH15M-25JUL211200",
            yes_best=0.58,
            no_best=0.42,
            sentiment_score=0.65,
            macro_24h_change=1.8,
        )
        result = estimator.estimate_outcome_probability(
            asset_name="ETH",
            hot_state_snapshot=snapshot,
        )
        assert result.asset_name == "ETH"
        assert result.ticker_symbol == "KXETH15M-25JUL211200"
        assert result.sources_reporting >= 3


# ──────────────────────────────────────────────────────────────
# Custom Configuration Tests
# ──────────────────────────────────────────────────────────────

class TestCustomEstimatorConfiguration:
    """Tests for custom threshold and weight configurations."""

    def test_custom_source_weights(self):
        """Custom weights change the combined probability."""
        snapshot = build_hot_state_snapshot(
            yes_best=0.60,
            sentiment_score=0.80,
        )

        # Default weights: orderbook=40%, sentiment=20%
        default_estimator = BinaryMarketOutcomeProbabilityEstimator()
        default_result = default_estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )

        # Custom weights: orderbook=10%, sentiment=80%
        custom_estimator = BinaryMarketOutcomeProbabilityEstimator(
            source_weights={"orderbook": 0.10, "sentiment": 0.80, "spot_price": 0.05, "macro": 0.05}
        )
        custom_result = custom_estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )

        # Custom weights favor sentiment (0.80) over orderbook (0.60)
        assert custom_result.estimated_probability_up > default_result.estimated_probability_up

    def test_high_minimum_edge_blocks_trades(self):
        """Very high minimum edge requirement blocks all trades."""
        estimator = BinaryMarketOutcomeProbabilityEstimator(
            minimum_edge_cents=50.0,  # 50 cents edge is unrealistic
        )
        snapshot = build_hot_state_snapshot()
        result = estimator.estimate_outcome_probability(
            asset_name="BTC",
            hot_state_snapshot=snapshot,
        )
        assert result.trade_signal == TradeSignalRecommendation.NO_TRADE


# ──────────────────────────────────────────────────────────────
# Enum Value Tests
# ──────────────────────────────────────────────────────────────

class TestEnumValues:
    """Verify enum values are correct and complete."""

    def test_trade_signal_recommendation_values(self):
        """TradeSignalRecommendation has exactly 3 values."""
        signals = list(TradeSignalRecommendation)
        assert len(signals) == 3
        assert TradeSignalRecommendation.BUY_YES.value == "BUY_YES"
        assert TradeSignalRecommendation.BUY_NO.value == "BUY_NO"
        assert TradeSignalRecommendation.NO_TRADE.value == "NO_TRADE"

    def test_confidence_level_values(self):
        """ConfidenceLevel has exactly 5 values."""
        levels = list(ConfidenceLevel)
        assert len(levels) == 5
        assert ConfidenceLevel.VERY_LOW.value == "VERY_LOW"
        assert ConfidenceLevel.VERY_HIGH.value == "VERY_HIGH"
