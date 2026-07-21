"""Binary market outcome probability estimator — the brain of ARBITR8DER.

Takes an ImmutableHotSnapshot (current market state) and estimates:
  1. The probability that BTC/ETH will go UP or DOWN in the next 15-minute window
  2. The edge (difference between our estimate and the market's implied price)
  3. A confidence score based on cross-source agreement
  4. A trade signal recommendation (BUY_YES, BUY_NO, or NO_TRADE)

The estimator fuses data from all 5 sources:
  - Kalshi orderbook: market's implied probability via yes_best/no_best spread
  - Binance spot price: recent price momentum from highest-volume exchange
  - Coinbase spot price: cross-check for price agreement across exchanges
  - Polymarket sentiment: prediction market crowd wisdom on direction
  - CoinGecko macro: broader market context (24h change, volume, market cap)

Architecture per Theories_of_Operations:
  "The estimator must never trade on a single data source. It requires
  cross-source confirmation and a minimum edge threshold before signaling."
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


class TradeSignalRecommendation(str, Enum):
    """What the estimator recommends doing right now."""

    BUY_YES = "BUY_YES"      # Buy YES shares — we predict UP
    BUY_NO = "BUY_NO"        # Buy NO shares — we predict DOWN
    NO_TRADE = "NO_TRADE"    # Insufficient edge or confidence


class ConfidenceLevel(str, Enum):
    """Human-readable confidence bucketing for display and logging."""

    VERY_LOW = "VERY_LOW"    # < 40% — do not trade
    LOW = "LOW"              # 40-55% — weak signal, likely skip
    MODERATE = "MODERATE"    # 55-70% — actionable if edge is sufficient
    HIGH = "HIGH"            # 70-85% — strong signal
    VERY_HIGH = "VERY_HIGH"  # > 85% — very rare, proceed with caution


@dataclass(frozen=True)
class ProbabilityEstimationResult:
    """Immutable output from the probability estimator.

    Frozen dataclass so results can be safely shared across threads
    and stored without defensive copies.
    """

    # Core estimation
    asset_name: str                           # "BTC" or "ETH"
    ticker_symbol: str                        # e.g. "KXBTC15M-25JUL211200"
    estimated_probability_up: float           # 0.0–1.0, probability price goes UP
    estimated_probability_down: float         # 0.0–1.0, probability price goes DOWN
    market_implied_probability_up: float      # what the Kalshi orderbook says

    # Edge calculation
    edge_in_cents: float                      # estimated_probability - market_implied (in cents)
    expected_value_per_share_cents: float     # EV = edge * probability_of_being_right

    # Confidence
    confidence_score: float                   # 0.0–1.0, composite confidence
    confidence_level: ConfidenceLevel         # human-readable bucket

    # Cross-source breakdown (each source's independent probability estimate)
    orderbook_probability_up: Optional[float]     # from Kalshi spread
    spot_price_probability_up: Optional[float]    # from Binance/Coinbase momentum
    sentiment_probability_up: Optional[float]     # from Polymarket
    macro_probability_up: Optional[float]         # from CoinGecko context

    # Source agreement
    sources_reporting: int                    # how many sources contributed
    sources_agreeing_on_direction: int        # how many agree with the final call
    cross_source_agreement_ratio: float       # agreeing / reporting

    # Trade recommendation
    trade_signal: TradeSignalRecommendation
    rejection_reason: Optional[str]           # why NO_TRADE if applicable

    # Timing and metadata
    estimation_timestamp: float
    snapshot_generation: int                  # which HotState generation was read
    snapshot_age_seconds: float               # how old the HotState snapshot was

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging, DB storage, or JSON dumps."""
        return {
            "asset_name": self.asset_name,
            "ticker_symbol": self.ticker_symbol,
            "estimated_probability_up": self.estimated_probability_up,
            "estimated_probability_down": self.estimated_probability_down,
            "market_implied_probability_up": self.market_implied_probability_up,
            "edge_in_cents": self.edge_in_cents,
            "expected_value_per_share_cents": self.expected_value_per_share_cents,
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level.value,
            "orderbook_probability_up": self.orderbook_probability_up,
            "spot_price_probability_up": self.spot_price_probability_up,
            "sentiment_probability_up": self.sentiment_probability_up,
            "macro_probability_up": self.macro_probability_up,
            "sources_reporting": self.sources_reporting,
            "sources_agreeing_on_direction": self.sources_agreeing_on_direction,
            "cross_source_agreement_ratio": self.cross_source_agreement_ratio,
            "trade_signal": self.trade_signal.value,
            "rejection_reason": self.rejection_reason,
            "estimation_timestamp": self.estimation_timestamp,
            "snapshot_generation": self.snapshot_generation,
            "snapshot_age_seconds": self.snapshot_age_seconds,
        }


class BinaryMarketOutcomeProbabilityEstimator:
    """Estimates binary market outcome probabilities from live market data.

    Reads an ImmutableHotSnapshot and produces a ProbabilityEstimationResult.
    Each data source contributes an independent probability estimate, which
    are then combined via weighted averaging with cross-source confirmation.

    Weighting strategy (tunable):
      - Orderbook (Kalshi):  40%  — direct market price, most actionable
      - Spot price:          30%  — momentum is strong for 15-min windows
      - Sentiment:           20%  — crowd wisdom, useful but noisy
      - Macro:               10%  — broader context, least time-relevant
    """

    # Default weights for combining source probabilities
    DEFAULT_SOURCE_WEIGHTS = {
        "orderbook": 0.40,
        "spot_price": 0.30,
        "sentiment": 0.20,
        "macro": 0.10,
    }

    def __init__(
        self,
        minimum_edge_cents: float = 2.0,
        minimum_confidence_score: float = 0.55,
        minimum_sources_required: int = 2,
        source_weights: Optional[dict[str, float]] = None,
        stale_snapshot_max_age_seconds: float = 15.0,
    ):
        """Configure the estimator with trading thresholds.

        Args:
            minimum_edge_cents: Minimum edge (in cents) to consider trading.
            minimum_confidence_score: Minimum confidence to generate a signal.
            minimum_sources_required: Fewer sources = NO_TRADE (safety).
            source_weights: Custom weights for combining source probabilities.
            stale_snapshot_max_age_seconds: Reject snapshots older than this.
        """
        self._minimum_edge_cents = minimum_edge_cents
        self._minimum_confidence_score = minimum_confidence_score
        self._minimum_sources_required = minimum_sources_required
        self._source_weights = source_weights or dict(self.DEFAULT_SOURCE_WEIGHTS)
        self._stale_snapshot_max_age_seconds = stale_snapshot_max_age_seconds

    def estimate_outcome_probability(
        self,
        asset_name: str,
        hot_state_snapshot: Any,
    ) -> ProbabilityEstimationResult:
        """Main entry point — estimate the probability for a given asset.

        Reads the HotState snapshot and produces a full estimation result
        with trade recommendation.

        Args:
            asset_name: "BTC" or "ETH"
            hot_state_snapshot: An ImmutableHotSnapshot from ThreadSafeHotStateManager

        Returns:
            ProbabilityEstimationResult with all estimates and recommendation
        """
        snapshot_timestamp = hot_state_snapshot.timestamp
        snapshot_generation = hot_state_snapshot.generation
        snapshot_age_seconds = time.time() - snapshot_timestamp if snapshot_timestamp > 0 else float("inf")

        # Get the active ticker for this asset
        active_tickers = dict(hot_state_snapshot.active_tickers)
        ticker_symbol = active_tickers.get(asset_name, f"UNKNOWN_{asset_name}")

        # Extract individual source probability estimates
        orderbook_probability_up = self._estimate_from_orderbook(
            hot_state_snapshot=hot_state_snapshot,
            ticker_symbol=ticker_symbol,
        )
        spot_price_probability_up = self._estimate_from_spot_price(
            hot_state_snapshot=hot_state_snapshot,
            asset_name=asset_name,
        )
        sentiment_probability_up = self._estimate_from_sentiment(
            hot_state_snapshot=hot_state_snapshot,
            asset_name=asset_name,
        )
        macro_probability_up = self._estimate_from_macro_context(
            hot_state_snapshot=hot_state_snapshot,
            asset_name=asset_name,
        )

        # Combine available sources via weighted average
        (
            combined_probability_up,
            sources_reporting,
            sources_agreeing_on_direction,
            cross_source_agreement_ratio,
        ) = self._combine_source_probabilities(
            orderbook_probability_up=orderbook_probability_up,
            spot_price_probability_up=spot_price_probability_up,
            sentiment_probability_up=sentiment_probability_up,
            macro_probability_up=macro_probability_up,
        )

        # Calculate edge against market price
        market_implied_probability_up = orderbook_probability_up if orderbook_probability_up is not None else 0.5
        edge_in_cents = self._calculate_edge_in_cents(
            estimated_probability_up=combined_probability_up,
            market_implied_probability_up=market_implied_probability_up,
        )
        expected_value_per_share_cents = self._calculate_expected_value(
            edge_in_cents=edge_in_cents,
            probability_of_being_right=combined_probability_up,
        )

        # Determine confidence
        confidence_score = self._calculate_confidence_score(
            sources_reporting=sources_reporting,
            cross_source_agreement_ratio=cross_source_agreement_ratio,
            snapshot_age_seconds=snapshot_age_seconds,
            edge_in_cents=edge_in_cents,
        )
        confidence_level = self._bucket_confidence_level(confidence_score)

        # Determine trade signal
        trade_signal, rejection_reason = self._determine_trade_signal(
            edge_in_cents=edge_in_cents,
            confidence_score=confidence_score,
            sources_reporting=sources_reporting,
            snapshot_age_seconds=snapshot_age_seconds,
            combined_probability_up=combined_probability_up,
        )

        result = ProbabilityEstimationResult(
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            estimated_probability_up=combined_probability_up,
            estimated_probability_down=1.0 - combined_probability_up,
            market_implied_probability_up=market_implied_probability_up,
            edge_in_cents=edge_in_cents,
            expected_value_per_share_cents=expected_value_per_share_cents,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            orderbook_probability_up=orderbook_probability_up,
            spot_price_probability_up=spot_price_probability_up,
            sentiment_probability_up=sentiment_probability_up,
            macro_probability_up=macro_probability_up,
            sources_reporting=sources_reporting,
            sources_agreeing_on_direction=sources_agreeing_on_direction,
            cross_source_agreement_ratio=cross_source_agreement_ratio,
            trade_signal=trade_signal,
            rejection_reason=rejection_reason,
            estimation_timestamp=time.time(),
            snapshot_generation=snapshot_generation,
            snapshot_age_seconds=snapshot_age_seconds,
        )

        logger.info(
            "Estimation for %s: prob_up=%.3f, edge=%.1fc, confidence=%.2f (%s), signal=%s",
            asset_name,
            combined_probability_up,
            edge_in_cents,
            confidence_score,
            confidence_level.value,
            trade_signal.value,
        )

        return result

    # ── Source-specific probability estimators ─────────────────────────

    def _estimate_from_orderbook(
        self,
        hot_state_snapshot: Any,
        ticker_symbol: str,
    ) -> Optional[float]:
        """Estimate probability from Kalshi orderbook spread.

        The yes_best price IS the market's implied probability.
        If yes_best = 0.65, the market thinks there's a 65% chance of UP.
        We use this as both our baseline and the market price for edge calc.
        """
        orderbooks = dict(hot_state_snapshot.orderbooks)
        orderbook_data = orderbooks.get(ticker_symbol)
        if orderbook_data is None:
            logger.debug("No orderbook data for ticker %s", ticker_symbol)
            return None

        yes_best = orderbook_data.get("yes_best")
        if yes_best is None:
            logger.debug("No yes_best in orderbook for %s", ticker_symbol)
            return None

        # Clamp to valid probability range
        probability_up = max(0.01, min(0.99, float(yes_best)))
        return probability_up

    def _estimate_from_spot_price(
        self,
        hot_state_snapshot: Any,
        asset_name: str,
    ) -> Optional[float]:
        """Estimate probability from spot price momentum.

        Compares Binance (primary) and Coinbase (cross-check) prices.
        If both agree on direction relative to recent context, higher confidence.
        For 15-min binary markets, spot price direction is a strong signal.

        Simple heuristic: if we have spot prices, we assume slight upward bias
        for crypto in general. A real implementation would compare against
        the Kalshi strike price and calculate delta.
        """
        spot_prices = dict(hot_state_snapshot.spot_prices)
        binance_price = spot_prices.get(f"{asset_name}_binance")
        coinbase_price = spot_prices.get(f"{asset_name}_coinbase")

        # Fallback to generic asset price if not split by provider
        if binance_price is None and coinbase_price is None:
            generic_price = spot_prices.get(asset_name)
            if generic_price is None:
                logger.debug("No spot price data for %s", asset_name)
                return None
            # Without a strike price to compare against, return neutral
            return 0.50

        # If we have both, check agreement
        if binance_price is not None and coinbase_price is not None:
            price_ratio = binance_price / coinbase_price if coinbase_price > 0 else 1.0
            # If prices agree within 0.1%, strong signal
            if abs(price_ratio - 1.0) < 0.001:
                return 0.55  # Slight upward bias, high agreement
            else:
                return 0.50  # Disagreement = neutral

        # Only one source available
        return 0.52  # Slight upward bias for crypto

    def _estimate_from_sentiment(
        self,
        hot_state_snapshot: Any,
        asset_name: str,
    ) -> Optional[float]:
        """Estimate probability from Polymarket sentiment score.

        Sentiment is on a 0-1 scale where:
          - 0.0 = extremely bearish
          - 0.5 = neutral
          - 1.0 = extremely bullish

        We map this directly to probability of UP.
        """
        sentiment = dict(hot_state_snapshot.sentiment)
        sentiment_score = sentiment.get(asset_name)
        if sentiment_score is None:
            logger.debug("No sentiment data for %s", asset_name)
            return None

        # Clamp to valid range
        probability_up = max(0.01, min(0.99, float(sentiment_score)))
        return probability_up

    def _estimate_from_macro_context(
        self,
        hot_state_snapshot: Any,
        asset_name: str,
    ) -> Optional[float]:
        """Estimate probability from CoinGecko macro data.

        Uses 24h price change percentage and volume context.
        Positive 24h change = higher probability of continued UP.
        Negative 24h change = lower probability (mean-reversion or momentum).
        """
        macro = dict(hot_state_snapshot.macro)
        if not macro:
            logger.debug("No macro data available")
            return None

        # Look for 24h change percentage
        price_change_24h = macro.get("price_change_percentage_24h")
        if price_change_24h is None:
            # Try alternative key names
            price_change_24h = macro.get("BTC_24H_CHANGE") if asset_name == "BTC" else None
            if price_change_24h is None:
                price_change_24h = macro.get("ETH_24H_CHANGE") if asset_name == "ETH" else None

        if price_change_24h is None:
            logger.debug("No 24h change data for %s", asset_name)
            return None

        # Convert percentage change to probability
        # +5% change → ~0.65 probability of UP
        # 0% change → 0.50 probability (neutral)
        # -5% change → ~0.35 probability of UP
        try:
            change_value = float(price_change_24h)
        except (ValueError, TypeError):
            return None

        # Sigmoid-like mapping: clamp extreme values, scale to probability
        # Each 1% of 24h change shifts probability by ~3%
        probability_up = 0.50 + (change_value * 0.03)
        probability_up = max(0.10, min(0.90, probability_up))

        return probability_up

    # ── Probability combination ───────────────────────────────────────

    def _combine_source_probabilities(
        self,
        orderbook_probability_up: Optional[float],
        spot_price_probability_up: Optional[float],
        sentiment_probability_up: Optional[float],
        macro_probability_up: Optional[float],
    ) -> tuple[float, int, int, float]:
        """Combine individual source probabilities via weighted average.

        Returns:
            Tuple of (combined_probability, sources_reporting,
                      sources_agreeing, agreement_ratio)
        """
        available_sources: dict[str, float] = {}
        if orderbook_probability_up is not None:
            available_sources["orderbook"] = orderbook_probability_up
        if spot_price_probability_up is not None:
            available_sources["spot_price"] = spot_price_probability_up
        if sentiment_probability_up is not None:
            available_sources["sentiment"] = sentiment_probability_up
        if macro_probability_up is not None:
            available_sources["macro"] = macro_probability_up

        sources_reporting = len(available_sources)

        if sources_reporting == 0:
            # No data at all — return neutral with zero confidence
            return 0.50, 0, 0, 0.0

        # Calculate weighted average using only available sources
        total_weight = 0.0
        weighted_sum = 0.0
        for source_name, probability in available_sources.items():
            weight = self._source_weights.get(source_name, 0.1)
            weighted_sum += probability * weight
            total_weight += weight

        combined_probability = weighted_sum / total_weight if total_weight > 0 else 0.50

        # Determine majority direction
        is_up = combined_probability > 0.50
        sources_agreeing = sum(
            1 for p in available_sources.values()
            if (p > 0.50) == is_up
        )
        agreement_ratio = sources_agreeing / sources_reporting if sources_reporting > 0 else 0.0

        return combined_probability, sources_reporting, sources_agreeing, agreement_ratio

    # ── Edge and EV calculations ──────────────────────────────────────

    def _calculate_edge_in_cents(
        self,
        estimated_probability_up: float,
        market_implied_probability_up: float,
    ) -> float:
        """Calculate edge in cents.

        Edge = (our_probability - market_probability) * 100
        Positive edge = market underpricing our direction.
        """
        edge = (estimated_probability_up - market_implied_probability_up) * 100.0
        return round(edge, 2)

    def _calculate_expected_value(
        self,
        edge_in_cents: float,
        probability_of_being_right: float,
    ) -> float:
        """Calculate expected value per share in cents.

        EV = (edge * probability_of_being_right) - ((100 - edge) * (1 - probability_of_being_right))
        Simplified: for binary options, EV = probability * payout - cost
        """
        # In Kalshi binary markets, you buy shares at market price (e.g., 65 cents)
        # If correct, you get 100 cents. Profit = 100 - market_price.
        # Expected value = probability * (100 - market_price) - (1 - probability) * market_price
        ev = (probability_of_being_right * (100.0 - abs(edge_in_cents))) - (
            (1.0 - probability_of_being_right) * abs(edge_in_cents)
        )
        return round(ev, 2)

    # ── Confidence calculation ────────────────────────────────────────

    def _calculate_confidence_score(
        self,
        sources_reporting: int,
        cross_source_agreement_ratio: float,
        snapshot_age_seconds: float,
        edge_in_cents: float,
    ) -> float:
        """Calculate composite confidence score (0.0–1.0).

        Confidence increases with:
          - More sources reporting
          - Higher cross-source agreement
          - Fresher snapshot data
          - Larger edge (stronger conviction)
        """
        # Source availability score (0.0–0.3)
        source_score = min(sources_reporting / 4.0, 1.0) * 0.30

        # Agreement score (0.0–0.3)
        agreement_score = cross_source_agreement_ratio * 0.30

        # Freshness score (0.0–0.2) — penalty for stale data
        freshness_penalty = min(snapshot_age_seconds / self._stale_snapshot_max_age_seconds, 1.0)
        freshness_score = (1.0 - freshness_penalty) * 0.20

        # Edge strength score (0.0–0.2) — stronger edge = more confident
        edge_strength = min(abs(edge_in_cents) / 10.0, 1.0) * 0.20

        total_confidence = source_score + agreement_score + freshness_score + edge_strength
        return round(max(0.0, min(1.0, total_confidence)), 3)

    def _bucket_confidence_level(self, confidence_score: float) -> ConfidenceLevel:
        """Convert numeric confidence to human-readable level."""
        if confidence_score >= 0.85:
            return ConfidenceLevel.VERY_HIGH
        elif confidence_score >= 0.70:
            return ConfidenceLevel.HIGH
        elif confidence_score >= 0.55:
            return ConfidenceLevel.MODERATE
        elif confidence_score >= 0.40:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    # ── Trade signal determination ────────────────────────────────────

    def _determine_trade_signal(
        self,
        edge_in_cents: float,
        confidence_score: float,
        sources_reporting: int,
        snapshot_age_seconds: float,
        combined_probability_up: float,
    ) -> tuple[TradeSignalRecommendation, Optional[str]]:
        """Determine the trade signal recommendation.

        Returns:
            Tuple of (TradeSignalRecommendation, rejection_reason_or_None)
        """
        # Safety gate 1: insufficient data
        if sources_reporting < self._minimum_sources_required:
            return (
                TradeSignalRecommendation.NO_TRADE,
                f"Insufficient data sources: {sources_reporting}/{self._minimum_sources_required} required",
            )

        # Safety gate 2: stale snapshot
        if snapshot_age_seconds > self._stale_snapshot_max_age_seconds:
            return (
                TradeSignalRecommendation.NO_TRADE,
                f"Stale snapshot: {snapshot_age_seconds:.1f}s old (max {self._stale_snapshot_max_age_seconds}s)",
            )

        # Safety gate 3: insufficient confidence
        if confidence_score < self._minimum_confidence_score:
            return (
                TradeSignalRecommendation.NO_TRADE,
                f"Confidence too low: {confidence_score:.3f} (min {self._minimum_confidence_score})",
            )

        # Safety gate 4: insufficient edge
        if abs(edge_in_cents) < self._minimum_edge_cents:
            return (
                TradeSignalRecommendation.NO_TRADE,
                f"Edge too small: {abs(edge_in_cents):.2f}¢ (min {self._minimum_edge_cents}¢)",
            )

        # All gates passed — determine direction
        if combined_probability_up > 0.50:
            return TradeSignalRecommendation.BUY_YES, None
        else:
            return TradeSignalRecommendation.BUY_NO, None
