"""Stream health status monitor — tracks staleness of all data sources.

Monitors each stream's last message time and marks it healthy/unhealthy.
Updates the HotState with current health status.

Per Theories_of_Operations: "All aux streams have to say when their datas
are old/broken. None of them can cover for a broken Kalshi book."
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default staleness thresholds (seconds) — if no message in this window, mark unhealthy
DEFAULT_STALENESS_THRESHOLDS = {
    "kalshi_rest": 300.0,
    "kalshi_ws": 30.0,
    "binance_ws": 10.0,
    "coinbase_ws": 10.0,
    "polymarket_poll": 120.0,
    "coingecko_poll": 180.0,
}


@dataclass(frozen=True)
class StreamHealthRecord:
    """Immutable record of a single stream's health status."""
    source_name: str
    is_healthy: bool
    last_message_timestamp: float
    staleness_threshold_seconds: float
    last_error: Optional[str] = None
    consecutive_error_count: int = 0


class StreamHealthStatusMonitor:
    """Tracks health status of all data sources.

    Each stream calls record_message_received() when it gets data.
    The monitor marks streams as unhealthy if they exceed staleness thresholds.
    """

    def __init__(
        self,
        staleness_thresholds: Optional[dict[str, float]] = None,
    ):
        self._thresholds = dict(staleness_thresholds or DEFAULT_STALENESS_THRESHOLDS)
        self._stream_records: dict[str, _StreamInternalState] = {}

        # Initialize all known streams
        for source_name, threshold_seconds in self._thresholds.items():
            self._stream_records[source_name] = _StreamInternalState(
                source_name=source_name,
                staleness_threshold_seconds=threshold_seconds,
            )

    def record_message_received(
        self,
        source_name: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record that a message was received from a data source.

        Resets the staleness timer for that source. If the source isn't
        registered, it's auto-added with a default threshold.
        """
        if source_name not in self._stream_records:
            logger.info("Auto-registering stream: %s", source_name)
            self._stream_records[source_name] = _StreamInternalState(
                source_name=source_name,
                staleness_threshold_seconds=self._thresholds.get(
                    source_name, 60.0
                ),
            )

        stream_state = self._stream_records[source_name]
        stream_state.last_message_timestamp = time.time()
        stream_state.consecutive_error_count = 0
        stream_state.last_error = None

    def record_error(
        self,
        source_name: str,
        error_message: str,
    ) -> None:
        """Record that an error occurred on a data source."""
        if source_name not in self._stream_records:
            self._stream_records[source_name] = _StreamInternalState(
                source_name=source_name,
                staleness_threshold_seconds=self._thresholds.get(
                    source_name, 60.0
                ),
            )

        stream_state = self._stream_records[source_name]
        stream_state.consecutive_error_count += 1
        stream_state.last_error = error_message

    def is_source_healthy(self, source_name: str) -> bool:
        """Check if a specific data source is currently healthy."""
        if source_name not in self._stream_records:
            return False

        stream_state = self._stream_records[source_name]
        return stream_state.is_currently_healthy()

    def get_all_health_records(self) -> dict[str, StreamHealthRecord]:
        """Get health records for all registered data sources."""
        health_records: dict[str, StreamHealthRecord] = {}

        for source_name, stream_state in self._stream_records.items():
            health_records[source_name] = StreamHealthRecord(
                source_name=source_name,
                is_healthy=stream_state.is_currently_healthy(),
                last_message_timestamp=stream_state.last_message_timestamp,
                staleness_threshold_seconds=stream_state.staleness_threshold_seconds,
                last_error=stream_state.last_error,
                consecutive_error_count=stream_state.consecutive_error_count,
            )

        return health_records

    def get_health_summary(self) -> dict[str, Any]:
        """Get a compact health summary for display."""
        summary: dict[str, Any] = {
            "total_streams": len(self._stream_records),
            "healthy_count": 0,
            "unhealthy_count": 0,
            "streams": {},
        }

        for source_name, stream_state in self._stream_records.items():
            is_healthy = stream_state.is_currently_healthy()
            if is_healthy:
                summary["healthy_count"] += 1
            else:
                summary["unhealthy_count"] += 1

            age_seconds: Optional[float] = None
            if stream_state.last_message_timestamp > 0:
                age_seconds = time.time() - stream_state.last_message_timestamp

            summary["streams"][source_name] = {
                "healthy": is_healthy,
                "last_message_age_s": age_seconds,
                "error_count": stream_state.consecutive_error_count,
            }

        return summary

    def is_critical_source_healthy(self, source_name: str) -> bool:
        """Check if a critical source (Kalshi) is healthy.

        Critical sources: if unhealthy, the system should not trade.
        """
        critical_sources = {"kalshi_ws", "kalshi_rest"}
        if source_name in critical_sources:
            return self.is_source_healthy(source_name)
        return True  # Non-critical sources don't block trading

    def can_trade_safely(self) -> bool:
        """Determine if all critical sources are healthy enough to trade.

        Per Theories_of_Operations: Kalshi orderbook must be fresh and valid.
        """
        return (
            self.is_critical_source_healthy("kalshi_ws")
            and self.is_critical_source_healthy("kalshi_rest")
        )


class _StreamInternalState:
    """Internal mutable state for a single stream's health tracking."""

    __slots__ = (
        "source_name",
        "last_message_timestamp",
        "staleness_threshold_seconds",
        "last_error",
        "consecutive_error_count",
    )

    def __init__(
        self,
        source_name: str,
        staleness_threshold_seconds: float,
    ):
        self.source_name = source_name
        self.last_message_timestamp = 0.0
        self.staleness_threshold_seconds = staleness_threshold_seconds
        self.last_error: Optional[str] = None
        self.consecutive_error_count: int = 0

    def is_currently_healthy(self) -> bool:
        """Determine if this stream is currently healthy based on staleness."""
        if self.last_message_timestamp == 0:
            # Never received a message — not yet connected
            return False

        age_seconds = time.time() - self.last_message_timestamp
        return age_seconds < self.staleness_threshold_seconds
