"""Source health monitor — tracks per-provider health metrics and classifies state.

Maintains running counters for each data source: last update time, age,
reconnect count, sequence gaps, and error count. Classifies each source as
HEALTHY / DEGRADED / STALE / DISCONNECTED based on configurable thresholds.

All health tracking is in-memory — no persistence. The snapshot merger reads
health state from here when building HotSnapshots.
"""

from __future__ import annotations

import time
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.data_contracts.event_data_models import SourceHealthStatus

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Health thresholds (seconds)
# ---------------------------------------------------------------------------

HEALTHY_MAX_AGE_S = 10.0
DEGRADED_MAX_AGE_S = 30.0
STALE_MAX_AGE_S = 120.0

# Sequence gap threshold: if gap exceeds this, degrade
MAX_SEQUENCE_GAP = 50

# Error count threshold: too many errors = degraded
MAX_ERRORS_BEFORE_DEGRADED = 5


# ---------------------------------------------------------------------------
# Per-source health state
# ---------------------------------------------------------------------------

class SourceHealthState:
    """Mutable health tracker for a single data source.

    Updated by the ingestion orchestrator every time a provider event arrives
    (or fails to arrive). Provides a snapshot of current health for the
    snapshot merger.
    """

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self.last_update_ts: float = 0.0
        self.last_sequence: int | None = None
        self.reconnect_count: int = 0
        self.error_count: int = 0
        self.total_events: int = 0
        self.consecutive_errors: int = 0

    @property
    def age_seconds(self) -> float | None:
        """Seconds since last successful update. None if never updated."""
        if self.last_update_ts == 0:
            return None
        return max(0.0, time.time() - self.last_update_ts)

    @property
    def status(self) -> SourceHealthStatus:
        """Current health classification based on age and error state."""
        age = self.age_seconds
        if age is None:
            return SourceHealthStatus.DISCONNECTED
        if self.consecutive_errors >= MAX_ERRORS_BEFORE_DEGRADED:
            return SourceHealthStatus.DEGRADED
        if age <= HEALTHY_MAX_AGE_S:
            return SourceHealthStatus.HEALTHY
        if age <= DEGRADED_MAX_AGE_S:
            return SourceHealthStatus.DEGRADED
        if age <= STALE_MAX_AGE_S:
            return SourceHealthStatus.STALE
        return SourceHealthStatus.DISCONNECTED

    def record_update(self, sequence: int | None = None) -> None:
        """Record a successful provider event receipt."""
        self.last_update_ts = time.time()
        self.total_events += 1
        self.consecutive_errors = 0
        if sequence is not None:
            gap = self._compute_gap(sequence)
            self.last_sequence = sequence
            if gap is not None and gap > MAX_SEQUENCE_GAP:
                logger.warning(
                    "Large sequence gap for %s: %d (from %d to %d)",
                    self.source_name, gap, self.last_sequence, sequence,
                )

    def record_error(self) -> None:
        """Record a provider error (connection drop, parse failure, etc.)."""
        self.error_count += 1
        self.consecutive_errors += 1

    def record_reconnect(self) -> None:
        """Record that the provider reconnected after a disconnect."""
        self.reconnect_count += 1
        self.consecutive_errors = 0

    def _compute_gap(self, new_sequence: int) -> int | None:
        """Compute the sequence gap from the last known sequence."""
        if self.last_sequence is None:
            return None
        return max(0, new_sequence - self.last_sequence - 1)

    def to_dict(self) -> dict[str, Any]:
        """Serialize current health state for diagnostics."""
        return {
            "source_name": self.source_name,
            "status": self.status.value,
            "age_seconds": round(self.age_seconds, 2) if self.age_seconds is not None else None,
            "last_sequence": self.last_sequence,
            "reconnect_count": self.reconnect_count,
            "error_count": self.error_count,
            "consecutive_errors": self.consecutive_errors,
            "total_events": self.total_events,
        }


# ---------------------------------------------------------------------------
# Health monitor (aggregates all sources)
# ---------------------------------------------------------------------------

class SourceHealthMonitor:
    """Aggregates health state for all five data sources.

    One monitor instance is shared across the ingestion orchestrator.
    Provides a summary for the snapshot merger and a human-readable
    health report for the CLI.
    """

    def __init__(self, now_fn: Any = None) -> None:
        self._now_fn = now_fn or (lambda: time.time())
        self._sources: dict[str, SourceHealthState] = {}

    def get_or_create(self, source_name: str) -> SourceHealthState:
        """Get existing health state or create a new tracker."""
        if source_name not in self._sources:
            self._sources[source_name] = SourceHealthState(source_name)
        return self._sources[source_name]

    def record_event(self, source_name: str, sequence: int | None = None) -> None:
        """Record a successful event from a source."""
        state = self.get_or_create(source_name)
        state.record_update(sequence)

    def record_error(self, source_name: str) -> None:
        """Record an error from a source."""
        state = self.get_or_create(source_name)
        state.record_error()

    def record_reconnect(self, source_name: str) -> None:
        """Record a reconnection for a source."""
        state = self.get_or_create(source_name)
        state.record_reconnect()

    def get_status(self, source_name: str) -> SourceHealthStatus:
        """Get the current health status of a source."""
        return self.get_or_create(source_name).status

    def get_state(self, source_name: str) -> SourceHealthState:
        """Get the full health state object for a source."""
        return self.get_or_create(source_name)

    def all_states(self) -> dict[str, SourceHealthState]:
        """Return all tracked source health states."""
        return dict(self._sources)

    def summary(self) -> dict[str, Any]:
        """Produce an aggregated health summary for all sources."""
        healthy = 0
        degraded = 0
        stale = 0
        disconnected = 0
        total = 0

        source_details: dict[str, dict[str, Any]] = {}
        for name, state in self._sources.items():
            total += 1
            s = state.status
            if s == SourceHealthStatus.HEALTHY:
                healthy += 1
            elif s == SourceHealthStatus.DEGRADED:
                degraded += 1
            elif s == SourceHealthStatus.STALE:
                stale += 1
            else:
                disconnected += 1
            source_details[name] = state.to_dict()

        # Overall status
        if total == 0:
            overall = SourceHealthStatus.DISCONNECTED
        elif disconnected > 0:
            overall = SourceHealthStatus.DEGRADED
        elif degraded > 0 or stale > 0:
            overall = SourceHealthStatus.DEGRADED
        else:
            overall = SourceHealthStatus.HEALTHY

        return {
            "overall": overall.value,
            "total_sources": total,
            "healthy": healthy,
            "degraded": degraded,
            "stale": stale,
            "disconnected": disconnected,
            "sources": source_details,
        }

    def format_report(self) -> str:
        """Produce a human-readable health report for the CLI."""
        s = self.summary()
        lines = [
            f"Overall: {s['overall'].upper()}",
            f"  Sources: {s['healthy']} healthy, {s['degraded']} degraded, "
            f"{s['stale']} stale, {s['disconnected']} disconnected "
            f"(of {s['total_sources']})",
            "",
        ]
        for name, detail in sorted(s["sources"].items()):
            age_str = f"{detail['age_seconds']}s" if detail["age_seconds"] is not None else "never"
            lines.append(
                f"  {name:25s} {detail['status']:13s}  age={age_str:>8s}  "
                f"events={detail['total_events']:>5d}  "
                f"errors={detail['error_count']:>3d}  "
                f"reconnects={detail['reconnect_count']:>3d}"
            )
        return "\n".join(lines)
