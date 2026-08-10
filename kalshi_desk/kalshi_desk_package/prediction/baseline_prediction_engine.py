"""Baseline prediction engine — versioned probability forecasts for BTC/ETH binary markets.

Produces YES/NO probability forecasts for "Will asset be above strike at close?"
Each forecast records inputs, confidence, rejection reasons, and model version.

The baseline model is intentionally naive:
  - Primary signal: Kalshi market-implied probability (midpoint cents / 100)
  - Secondary signal: trend direction + volatility adjustment
  - Fallback: reject prediction with reason if insufficient data

This module is designed to be replaced by smarter models without changing
the recording/scoring infrastructure.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger
from kalshi_desk_package.prediction.feature_extraction_engine import PredictionFeatures

logger = get_logger(__name__)

# Model version — bump when prediction logic changes
MODEL_VERSION = "baseline_v1"
MODEL_VERSION_HASH = hashlib.sha256(MODEL_VERSION.encode()).hexdigest()[:12]


class PredictionRejection(Enum):
    """Reasons a prediction was not generated."""
    INSUFFICIENT_DATA = "insufficient_data"
    NO_KALSHI_MIDPOINT = "no_kalshi_midpoint"
    NO_SPOT_PRICE = "no_spot_price"
    MARKET_CLOSED = "market_closed"
    MARKET_EXPIRING_TOO_SOON = "market_expiring_soon"
    FEATURE_INCOMPLETE = "feature_incomplete"
    ASSET_NOT_SUPPORTED = "asset_not_supported"


@dataclass
class PredictionRecord:
    """A single prediction record — the atomic unit of the evidence loop.

    Captures everything needed to later score this prediction against reality.
    """
    # Identity
    prediction_id: str = ""
    asset: str = ""
    ticker: str = ""  # Kalshi market ticker, e.g. "KXBTC15M-26JUL23-T15:00"

    # Forecast
    forecast_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    yes_probability: float | None = None  # 0.0 - 1.0
    confidence: float | None = None       # 0.0 - 1.0, how sure we are in the forecast
    edge_pct: float | None = None         # yes_probability - kalshi_midpoint/100

    # Inputs
    snapshot_version: int = 0
    features: dict[str, Any] = field(default_factory=dict)

    # Model tracking
    model_version: str = MODEL_VERSION
    model_version_hash: str = MODEL_VERSION_HASH

    # Outcome (filled later by resolver)
    actual_outcome: int | None = None  # 1 = YES, 0 = NO
    outcome_ts: datetime | None = None
    score_brier: float | None = None
    score_log_loss: float | None = None

    # Rejection (if prediction was not made)
    rejected: bool = False
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "asset": self.asset,
            "ticker": self.ticker,
            "forecast_ts": self.forecast_ts.isoformat(),
            "yes_probability": self.yes_probability,
            "confidence": self.confidence,
            "edge_pct": self.edge_pct,
            "snapshot_version": self.snapshot_version,
            "features": self.features,
            "model_version": self.model_version,
            "model_version_hash": self.model_version_hash,
            "actual_outcome": self.actual_outcome,
            "outcome_ts": self.outcome_ts.isoformat() if self.outcome_ts else None,
            "score_brier": self.score_brier,
            "score_log_loss": self.score_log_loss,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


class BaselinePredictionEngine:
    """Produces versioned probability forecasts from features.

    Stateless — each predict() call produces an independent PredictionRecord.
    """

    def predict(
        self,
        asset: str,
        ticker: str,
        features: PredictionFeatures,
        kalshi_midpoint_override: float | None = None,
    ) -> PredictionRecord:
        """Generate a prediction from extracted features.

        Args:
            asset: "BTC" or "ETH"
            ticker: Kalshi market ticker
            features: Extracted feature vector
            kalshi_midpoint_override: Optional override for Kalshi midpoint (for testing)

        Returns:
            PredictionRecord with forecast populated, or rejected with reason.
        """
        record = PredictionRecord(
            prediction_id=self._generate_id(asset, features),
            asset=asset,
            ticker=ticker,
            snapshot_version=features.snapshot_version,
            features=features.to_dict(),
        )

        # Gate checks
        rejection = self._check_rejection(features, kalshi_midpoint_override)
        if rejection is not None:
            record.rejected = True
            record.rejection_reason = rejection.value
            logger.info("Prediction rejected for %s: %s", asset, rejection.value)
            return record

        # Extract Kalshi midpoint
        midpoint = kalshi_midpoint_override
        if midpoint is None:
            midpoint = features.kalshi_midpoint_cents

        # Baseline model: market-implied probability with trend adjustment
        market_implied = midpoint / 100.0  # cents -> probability (0.0 - 1.0)

        # Trend adjustment: shift probability based on recent direction
        trend_adjustment = self._compute_trend_adjustment(features)

        # Combine: weighted average of market-implied and trend
        # Start with 90% market-implied, 10% trend (market knows more than us)
        raw_probability = 0.9 * market_implied + 0.1 * (market_implied + trend_adjustment)

        # Clamp to [0.01, 0.99] — never predict certainty
        yes_probability = max(0.01, min(0.99, raw_probability))

        # Confidence based on feature completeness and data freshness
        confidence = self._compute_confidence(features)

        # Edge: our probability vs market-implied
        edge_pct = (yes_probability - market_implied) * 100

        record.yes_probability = round(yes_probability, 4)
        record.confidence = round(confidence, 4)
        record.edge_pct = round(edge_pct, 4)

        logger.info(
            "Prediction: %s %s YES=%.2f%% conf=%.2f edge=%.2f%%",
            asset, ticker, yes_probability * 100, confidence, edge_pct,
        )
        return record

    def _check_rejection(
        self,
        features: PredictionFeatures,
        kalshi_midpoint_override: float | None,
    ) -> PredictionRejection | None:
        """Check if we should reject this prediction."""
        midpoint = kalshi_midpoint_override or features.kalshi_midpoint_cents
        if midpoint is None:
            return PredictionRejection.NO_KALSHI_MIDPOINT

        if features.asset not in ("BTC", "ETH"):
            return PredictionRejection.ASSET_NOT_SUPPORTED

        # Reject if market is expiring in less than 60 seconds
        if features.time_to_close_seconds is not None and features.time_to_close_seconds < 60:
            return PredictionRejection.MARKET_EXPIRING_TOO_SOON

        # Reject if we have no spot price at all
        if features.spot_disagreement_pct is None and features.recent_volume_usd is None:
            return PredictionRejection.NO_SPOT_PRICE

        return None

    def _compute_trend_adjustment(self, features: PredictionFeatures) -> float:
        """Compute a small trend-based adjustment to the probability.

        Returns a value in [-0.05, +0.05] — a ±5% max shift.
        """
        adjustments = []

        if features.direction_1m is not None:
            # Short-term momentum
            adj = max(-0.05, min(0.05, features.direction_1m * 0.5))
            adjustments.append(adj * 0.5)  # weight: 50%

        if features.direction_5m is not None:
            # Medium-term trend
            adj = max(-0.05, min(0.05, features.direction_5m * 0.3))
            adjustments.append(adj * 0.3)  # weight: 30%

        if features.direction_15m is not None:
            # Longer-term trend
            adj = max(-0.05, min(0.05, features.direction_15m * 0.2))
            adjustments.append(adj * 0.2)  # weight: 20%

        if not adjustments:
            return 0.0

        return sum(adjustments)

    def _compute_confidence(self, features: PredictionFeatures) -> float:
        """Compute confidence based on feature completeness and freshness.

        Returns 0.0 - 1.0.
        """
        # Base confidence from feature completeness
        completeness = features.completeness_pct / 100.0

        # Penalty for stale data
        freshness_penalty = 0.0
        for field_val in [
            features.freshness_binance,
            features.freshness_coinbase,
            features.freshness_coingecko,
            features.freshness_kalshi,
        ]:
            if field_val is not None and field_val > 30:
                freshness_penalty += 0.05  # 5% penalty per stale source

        # Penalty for high disagreement (conflicting signals)
        disagreement_penalty = 0.0
        if features.spot_disagreement_pct is not None and features.spot_disagreement_pct > 0.1:
            disagreement_penalty = 0.1

        confidence = max(0.1, completeness - freshness_penalty - disagreement_penalty)
        return min(1.0, confidence)

    def _generate_id(self, asset: str, features: PredictionFeatures) -> str:
        """Generate a deterministic prediction ID from inputs."""
        raw = f"{asset}-{features.snapshot_version}-{features.extracted_at.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def format_prediction_human(record: PredictionRecord) -> str:
    """Format a PredictionRecord as human-readable text."""
    if record.rejected:
        return (
            f"=== {record.asset} Prediction REJECTED ===\n"
            f"  Reason: {record.rejection_reason}\n"
            f"  Model:  {record.model_version}\n"
        )

    lines = [
        f"=== {record.asset} Prediction ({record.ticker}) ===",
        f"  Model:      {record.model_version}",
        f"  YES prob:   {record.yes_probability * 100:.1f}%",
        f"  Confidence: {record.confidence * 100:.1f}%",
        f"  Edge:       {record.edge_pct:+.2f}%",
        f"  Snapshot:   v{record.snapshot_version}",
    ]

    if record.actual_outcome is not None:
        outcome_str = "YES" if record.actual_outcome == 1 else "NO"
        lines.append(f"  Actual:     {outcome_str}")
        if record.score_brier is not None:
            lines.append(f"  Brier:      {record.score_brier:.4f}")

    return "\n".join(lines)


def format_prediction_json(record: PredictionRecord) -> str:
    """Format a PredictionRecord as JSON."""
    return json.dumps(record.to_dict(), indent=2)
