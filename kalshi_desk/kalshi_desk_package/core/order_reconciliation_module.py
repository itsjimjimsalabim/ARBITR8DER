"""Order reconciliation — full audit trail for the order lifecycle.

Tracks every stage of an order from intent through settlement:
  Intent → Risk Check → Fill → Position → Settlement → Journal

Provides discrepancy detection and integrates with the structured trade
journal for complete reasoning chain traceability.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


class LifecycleStage(str):
    """Order lifecycle stages."""
    INTENT = "intent"
    RISK_CHECK = "risk_check"
    FILL = "fill"
    POSITION = "position"
    SETTLEMENT = "settlement"
    JOURNAL = "journal"
    DISCREPANCY = "discrepancy"


@dataclass
class LifecycleEvent:
    """A single event in the order lifecycle."""
    event_id: str = ""
    order_id: str = ""
    timestamp: str = ""
    stage: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReconciliationReport:
    """Reconciliation report for a single order or session."""
    order_id: str = ""
    events: list[LifecycleEvent] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    total_events: int = 0
    stages_completed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "total_events": self.total_events,
            "stages_completed": self.stages_completed,
            "discrepancies": self.discrepancies,
            "events": [e.to_dict() for e in self.events],
        }


class OrderReconciler:
    """Tracks and reconciles the full order lifecycle.

    Events are persisted to JSONL for audit trail and replay.
    """

    def __init__(self, journal_dir: Path | str | None = None) -> None:
        if journal_dir is None:
            self._journal_dir = Path(__file__).resolve().parent.parent.parent / "runtime" / "archives" / "reconciliation"
        else:
            self._journal_dir = Path(journal_dir)
        self._journal_dir.mkdir(parents=True, exist_ok=True)

        self._events: list[LifecycleEvent] = []
        self._events_by_order: dict[str, list[LifecycleEvent]] = {}
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._journal_file = self._journal_dir / f"reconciliation_{self._session_id}.jsonl"

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_intent(
        self,
        order_id: str,
        asset: str,
        side: str,
        contracts: int,
        ticker: str,
        limit_cents: int | None = None,
        snapshot_version: int | None = None,
        midpoint_cents: float | None = None,
    ) -> LifecycleEvent:
        """Record an order intent."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.INTENT,
            data={
                "asset": asset,
                "side": side,
                "contracts": contracts,
                "ticker": ticker,
                "limit_cents": limit_cents,
                "snapshot_version": snapshot_version,
                "midpoint_cents": midpoint_cents,
            },
        )
        self._record(event)
        return event

    def record_risk_check(
        self,
        order_id: str,
        passed: bool,
        block_reason: str | None = None,
        block_detail: str = "",
        warnings: list[str] | None = None,
    ) -> LifecycleEvent:
        """Record a risk check result."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.RISK_CHECK,
            data={
                "passed": passed,
                "block_reason": block_reason,
                "block_detail": block_detail,
                "warnings": warnings or [],
            },
            success=passed,
            error=block_detail if not passed else None,
        )
        self._record(event)
        return event

    def record_fill(
        self,
        order_id: str,
        fill_price_cents: float,
        fill_cost_usd: float,
        fees_usd: float = 0.0,
        midpoint_at_fill: float | None = None,
    ) -> LifecycleEvent:
        """Record an order fill."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.FILL,
            data={
                "fill_price_cents": fill_price_cents,
                "fill_cost_usd": fill_cost_usd,
                "fees_usd": fees_usd,
                "midpoint_at_fill": midpoint_at_fill,
            },
        )
        self._record(event)
        return event

    def record_position_opened(
        self,
        order_id: str,
        position_id: str,
        contracts: int,
        avg_entry_cents: float,
        total_cost_usd: float,
    ) -> LifecycleEvent:
        """Record position creation/update."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.POSITION,
            data={
                "position_id": position_id,
                "contracts": contracts,
                "avg_entry_cents": avg_entry_cents,
                "total_cost_usd": total_cost_usd,
                "action": "opened",
            },
        )
        self._record(event)
        return event

    def record_settlement(
        self,
        order_id: str,
        outcome: int,
        pnl: float,
        settlement_price_cents: float,
    ) -> LifecycleEvent:
        """Record settlement."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.SETTLEMENT,
            data={
                "outcome": outcome,
                "pnl": pnl,
                "settlement_price_cents": settlement_price_cents,
            },
        )
        self._record(event)
        return event

    def record_journal_link(
        self,
        order_id: str,
        journal_entry_id: str,
        observation: str,
        hypothesis: str,
    ) -> LifecycleEvent:
        """Record journal entry linkage."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.JOURNAL,
            data={
                "journal_entry_id": journal_entry_id,
                "observation": observation,
                "hypothesis": hypothesis,
            },
        )
        self._record(event)
        return event

    def record_discrepancy(
        self,
        order_id: str,
        description: str,
        expected: Any = None,
        actual: Any = None,
    ) -> LifecycleEvent:
        """Record a discrepancy detected during reconciliation."""
        event = self._make_event(
            order_id=order_id,
            stage=LifecycleStage.DISCREPANCY,
            data={
                "description": description,
                "expected": expected,
                "actual": actual,
            },
            success=False,
            error=description,
        )
        self._record(event)
        return event

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile_order(self, order_id: str) -> ReconciliationReport:
        """Reconcile a single order's lifecycle."""
        events = self._events_by_order.get(order_id, [])
        report = ReconciliationReport(
            order_id=order_id,
            events=events,
            total_events=len(events),
        )

        stages = [e.stage for e in events]
        report.stages_completed = list(dict.fromkeys(stages))  # unique, ordered

        # Check for missing stages
        expected_stages = {LifecycleStage.INTENT, LifecycleStage.RISK_CHECK}
        completed = set(stages)

        for stage in expected_stages:
            if stage not in completed:
                report.discrepancies.append(f"Missing stage: {stage}")

        # Check for risk check failures without intent
        if LifecycleStage.FILL in completed and LifecycleStage.RISK_CHECK in completed:
            risk_events = [e for e in events if e.stage == LifecycleStage.RISK_CHECK]
            fill_events = [e for e in events if e.stage == LifecycleStage.FILL]
            if risk_events and not risk_events[-1].success and fill_events:
                report.discrepancies.append("Fill recorded after risk check failure")

        # Check for settlement without fill
        if LifecycleStage.SETTLEMENT in completed and LifecycleStage.FILL not in completed:
            report.discrepancies.append("Settlement recorded without fill")

        # Check for fill without settlement (stuck order)
        if LifecycleStage.FILL in completed and LifecycleStage.SETTLEMENT not in completed:
            report.discrepancies.append("Fill recorded without settlement (stuck order)")

        return report

    def reconcile_session(self) -> list[ReconciliationReport]:
        """Reconcile all orders in the current session."""
        reports = []
        for order_id in self._events_by_order:
            reports.append(self.reconcile_order(order_id))
        return reports

    def get_discrepancies(self) -> list[LifecycleEvent]:
        """Get all discrepancy events."""
        return [e for e in self._events if e.stage == LifecycleStage.DISCREPANCY]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_order_events(self, order_id: str) -> list[LifecycleEvent]:
        """Get all events for a specific order."""
        return list(self._events_by_order.get(order_id, []))

    def get_all_events(self) -> list[LifecycleEvent]:
        """Get all events in chronological order."""
        return list(self._events)

    def summary(self) -> dict[str, Any]:
        """Return session reconciliation summary."""
        orders = set(e.order_id for e in self._events)
        discrepancies = self.get_discrepancies()
        return {
            "session_id": self._session_id,
            "total_events": len(self._events),
            "orders_tracked": len(orders),
            "discrepancies": len(discrepancies),
            "stages_hit": list(dict.fromkeys(e.stage for e in self._events)),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_event(
        self,
        order_id: str,
        stage: str,
        data: dict[str, Any],
        success: bool = True,
        error: str | None = None,
    ) -> LifecycleEvent:
        return LifecycleEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            order_id=order_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=stage,
            data=data,
            success=success,
            error=error,
        )

    def _record(self, event: LifecycleEvent) -> None:
        """Record an event to memory and disk."""
        self._events.append(event)
        self._events_by_order.setdefault(event.order_id, []).append(event)

        try:
            with open(self._journal_file, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except OSError as exc:
            logger.error("Failed to persist reconciliation event: %s", exc)

        logger.info(
            "Reconciliation: order=%s stage=%s success=%s",
            event.order_id[:16], event.stage, event.success,
        )


def format_reconciliation_human(report: ReconciliationReport) -> str:
    """Format a reconciliation report as human-readable text."""
    lines = [
        f"=== Reconciliation: {report.order_id} ===",
        f"  Events: {report.total_events}",
        f"  Stages: {' → '.join(report.stages_completed) if report.stages_completed else '(none)'}",
    ]

    if report.discrepancies:
        lines.append("")
        lines.append("  DISCREPANCIES:")
        for d in report.discrepancies:
            lines.append(f"    - {d}")
    else:
        lines.append("  Status: CLEAN")

    return "\n".join(lines)


def format_reconciliation_json(report: ReconciliationReport) -> str:
    """Format a reconciliation report as JSON."""
    return json.dumps(report.to_dict(), indent=2)
