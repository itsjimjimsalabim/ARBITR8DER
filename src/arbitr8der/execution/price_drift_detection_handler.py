"""Price drift detection — measures how much the market moved between read and execute.

Per Theories_of_Operations: "60-100ms synthetic latency caused BTC YES price to swing
from 50c to 18c between snapshot and fill. The AI's snapshot is stale by the time the
trade lands. Need to report drift back to the AI so it can adjust."

This module:
  - Records the snapshot price when the AI makes a decision
  - Records the execution price when the trade actually fills
  - Calculates the drift (difference in cents and percentage)
  - Flags drift that exceeds configurable thresholds
  - Logs drift events for later analysis
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class DriftSeverity(str, Enum):
    """How bad was the price drift between snapshot and execution."""

    NEGLIGIBLE = "NEGLIGIBLE"      # < 1 cent — within noise
    MINOR = "MINOR"                # 1-3 cents — noticeable but acceptable
    MODERATE = "MODERATE"          # 3-5 cents — concerning, log for analysis
    SEVERE = "SEVERE"              # 5-10 cents — significant, may invalidate edge
    CRITICAL = "CRITICAL"          # > 10 cents — edge completely eroded


@dataclass(frozen=True)
class PriceDriftMeasurement:
    """Immutable record of price drift for a single trade."""

    trade_id: str
    asset_name: str
    ticker_symbol: str
    snapshot_price_cents: float
    execution_price_cents: float
    drift_cents: float
    drift_percentage: float
    drift_severity: DriftSeverity
    snapshot_timestamp: float
    execution_timestamp: float
    latency_ms: float
    snapshot_generation: int

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "asset_name": self.asset_name,
            "ticker_symbol": self.ticker_symbol,
            "snapshot_price_cents": self.snapshot_price_cents,
            "execution_price_cents": self.execution_price_cents,
            "drift_cents": self.drift_cents,
            "drift_percentage": self.drift_percentage,
            "drift_severity": self.drift_severity.value,
            "snapshot_timestamp": self.snapshot_timestamp,
            "execution_timestamp": self.execution_timestamp,
            "latency_ms": self.latency_ms,
            "snapshot_generation": self.snapshot_generation,
        }


class PriceDriftDetectionHandler:
    """Tracks and analyzes price drift between AI decision and trade execution.

    Every time the AI decides to trade, it records the snapshot price.
    When the trade executes, it records the execution price.
    The drift is calculated and classified by severity.

    Historical drift data is kept for analysis:
      - Average drift per asset
      - Drift distribution (what % are severe/critical)
      - Latency vs drift correlation
    """

    def __init__(
        self,
        drift_warning_threshold_cents: float = 3.0,
        drift_critical_threshold_cents: float = 10.0,
    ):
        """Initialize drift detection.

        Args:
            drift_warning_threshold_cents: Drift above this triggers WARNING logging
            drift_critical_threshold_cents: Drift above this triggers CRITICAL logging
        """
        self._drift_warning_threshold = drift_warning_threshold_cents
        self._drift_critical_threshold = drift_critical_threshold_cents
        self._drift_history: list[PriceDriftMeasurement] = []

    @property
    def total_measurements(self) -> int:
        return len(self._drift_history)

    def classify_drift_severity(self, drift_cents: float) -> DriftSeverity:
        """Classify drift magnitude into a severity level."""
        absolute_drift = abs(drift_cents)
        if absolute_drift < 1.0:
            return DriftSeverity.NEGLIGIBLE
        elif absolute_drift < 3.0:
            return DriftSeverity.MINOR
        elif absolute_drift < 5.0:
            return DriftSeverity.MODERATE
        elif absolute_drift < 10.0:
            return DriftSeverity.SEVERE
        else:
            return DriftSeverity.CRITICAL

    def record_drift(
        self,
        trade_id: str,
        asset_name: str,
        ticker_symbol: str,
        snapshot_price_cents: float,
        execution_price_cents: float,
        snapshot_timestamp: float,
        execution_timestamp: float,
        snapshot_generation: int,
    ) -> PriceDriftMeasurement:
        """Record price drift for a completed trade.

        Args:
            trade_id: Unique identifier for this trade
            asset_name: "BTC" or "ETH"
            ticker_symbol: Kalshi ticker
            snapshot_price_cents: Price the AI saw in the snapshot
            execution_price_cents: Price at which the trade actually filled
            snapshot_timestamp: When the AI read the snapshot
            execution_timestamp: When the trade executed
            snapshot_generation: HotState generation at decision time

        Returns:
            PriceDriftMeasurement with full drift analysis
        """
        drift_cents = execution_price_cents - snapshot_price_cents
        drift_percentage = (
            (drift_cents / snapshot_price_cents * 100.0)
            if snapshot_price_cents > 0
            else 0.0
        )
        latency_ms = (execution_timestamp - snapshot_timestamp) * 1000.0

        severity = self.classify_drift_severity(drift_cents)

        measurement = PriceDriftMeasurement(
            trade_id=trade_id,
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            snapshot_price_cents=snapshot_price_cents,
            execution_price_cents=execution_price_cents,
            drift_cents=round(drift_cents, 4),
            drift_percentage=round(drift_percentage, 4),
            drift_severity=severity,
            snapshot_timestamp=snapshot_timestamp,
            execution_timestamp=execution_timestamp,
            latency_ms=round(latency_ms, 2),
            snapshot_generation=snapshot_generation,
        )

        self._drift_history.append(measurement)

        # Log based on severity
        if severity == DriftSeverity.CRITICAL:
            logger.critical(
                "CRITICAL PRICE DRIFT: %s %s drifted %.2f¢ (%.2f%%) in %.1fms",
                asset_name, ticker_symbol, drift_cents, drift_percentage, latency_ms,
            )
        elif severity == DriftSeverity.SEVERE:
            logger.warning(
                "SEVERE price drift: %s %s drifted %.2f¢ (%.2f%%) in %.1fms",
                asset_name, ticker_symbol, drift_cents, drift_percentage, latency_ms,
            )
        elif severity == DriftSeverity.MODERATE:
            logger.warning(
                "Moderate price drift: %s %s drifted %.2f¢ (%.2f%%) in %.1fms",
                asset_name, ticker_symbol, drift_cents, drift_percentage, latency_ms,
            )
        else:
            logger.info(
                "Price drift: %s %s drifted %.2f¢ (%.2f%%) in %.1fms",
                asset_name, ticker_symbol, drift_cents, drift_percentage, latency_ms,
            )

        return measurement

    def get_average_drift_cents(self, asset_name: Optional[str] = None) -> float:
        """Get average absolute drift, optionally filtered by asset."""
        measurements = self._drift_history
        if asset_name:
            measurements = [m for m in measurements if m.asset_name == asset_name]
        if not measurements:
            return 0.0
        return sum(abs(m.drift_cents) for m in measurements) / len(measurements)

    def get_drift_distribution(self) -> dict[str, int]:
        """Get count of measurements in each severity bucket."""
        distribution = {severity.value: 0 for severity in DriftSeverity}
        for measurement in self._drift_history:
            distribution[measurement.drift_severity.value] += 1
        return distribution

    def get_average_latency_ms(self) -> float:
        """Get average latency between snapshot and execution."""
        if not self._drift_history:
            return 0.0
        return sum(m.latency_ms for m in self._drift_history) / len(self._drift_history)

    def get_drift_history(self) -> list[PriceDriftMeasurement]:
        """Get all drift measurements."""
        return list(self._drift_history)

    def get_drift_summary(self) -> dict:
        """Get a summary of all drift data for display."""
        return {
            "total_measurements": self.total_measurements,
            "average_drift_cents": round(self.get_average_drift_cents(), 4),
            "average_latency_ms": round(self.get_average_latency_ms(), 2),
            "drift_distribution": self.get_drift_distribution(),
            "average_drift_by_asset": {
                "BTC": round(self.get_average_drift_cents("BTC"), 4),
                "ETH": round(self.get_average_drift_cents("ETH"), 4),
            },
        }
