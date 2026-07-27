"""Operator scorecard — aggregated view of prediction quality, coverage, and health.

Combines data from:
  - PredictionScorer (Brier, log loss, calibration, accuracy)
  - TradeJournal (open/resolved entries, hypothesis quality)
  - SessionArchive (session stats, command counts)

Produces a single-screen overview for the operator to assess session quality
and decide whether to continue, adjust, or stop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.prediction.prediction_scorer import (
    PredictionScorer,
    ScoringReport,
)

logger = get_logger(__name__)


@dataclass
class Scorecard:
    """Aggregated operator scorecard."""
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    session_id: str = ""

    # Scoring metrics (from PredictionScorer)
    scoring_report: ScoringReport | None = None

    # Journal metrics
    journal_total: int = 0
    journal_open: int = 0
    journal_resolved: int = 0
    journal_accuracy_pct: float | None = None
    journal_mean_brier: float | None = None

    # Coverage
    btc_predictions: int = 0
    eth_predictions: int = 0
    btc_accuracy_pct: float | None = None
    eth_accuracy_pct: float | None = None

    # Data health summary
    health_snapshots: int = 0
    health_degraded_pct: float | None = None
    health_stale_pct: float | None = None

    # Session stats
    session_duration_seconds: float | None = None
    commands_run: int = 0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "generated_at": self.generated_at,
            "session_id": self.session_id,
            "scoring": self.scoring_report.to_dict() if self.scoring_report else None,
            "journal": {
                "total": self.journal_total,
                "open": self.journal_open,
                "resolved": self.journal_resolved,
                "accuracy_pct": self.journal_accuracy_pct,
                "mean_brier": self.journal_mean_brier,
            },
            "coverage": {
                "btc_predictions": self.btc_predictions,
                "eth_predictions": self.eth_predictions,
                "btc_accuracy_pct": self.btc_accuracy_pct,
                "eth_accuracy_pct": self.eth_accuracy_pct,
            },
            "data_health": {
                "snapshots_received": self.health_snapshots,
                "degraded_pct": self.health_degraded_pct,
                "stale_pct": self.health_stale_pct,
            },
            "session": {
                "duration_seconds": self.session_duration_seconds,
                "commands_run": self.commands_run,
            },
        }
        return result


class ScorecardGenerator:
    """Generates an operator scorecard from available data sources."""

    def __init__(
        self,
        scorer: PredictionScorer | None = None,
        journal: Any = None,
        archive: Any = None,
    ) -> None:
        self._scorer = scorer or PredictionScorer()
        self._journal = journal
        self._archive = archive

    def generate(self) -> Scorecard:
        """Generate a scorecard from current data."""
        card = Scorecard()

        # Scoring metrics
        if self._scorer:
            card.scoring_report = self._scorer.generate_report()

        # Journal metrics
        if self._journal:
            self._fill_journal_metrics(card)

        # Coverage per-asset
        if card.scoring_report and card.scoring_report.per_asset:
            for asset, stats in card.scoring_report.per_asset.items():
                count = stats.get("count", 0)
                acc = stats.get("accuracy_pct")
                if asset.upper() == "BTC":
                    card.btc_predictions = count
                    card.btc_accuracy_pct = acc
                elif asset.upper() == "ETH":
                    card.eth_predictions = count
                    card.eth_accuracy_pct = acc

        # Session stats
        if self._archive:
            self._fill_session_metrics(card)

        logger.info("Scorecard generated: %d scored predictions, %.1f%% accuracy",
                     card.scoring_report.scored_predictions if card.scoring_report else 0,
                     card.scoring_report.accuracy_pct or 0.0)
        return card

    def _fill_journal_metrics(self, card: Scorecard) -> None:
        """Fill journal-related metrics on the scorecard."""
        if not self._journal:
            return

        summary = self._journal.summary()
        card.session_id = summary.get("session_id", "")
        card.journal_total = summary.get("total_entries", 0)
        card.journal_accuracy_pct = summary.get("accuracy_pct")
        card.journal_mean_brier = summary.get("mean_brier")

        # Count open vs resolved
        open_entries = self._journal.get_open_entries()
        resolved_entries = self._journal.get_resolved_entries()
        card.journal_open = len(open_entries)
        card.journal_resolved = len(resolved_entries)

    def _fill_session_metrics(self, card: Scorecard) -> None:
        """Fill session archive metrics on the scorecard."""
        if not self._archive:
            return

        summary = self._archive.summary()
        card.commands_run = summary.get("commands_run", 0)
        card.health_snapshots = summary.get("snapshots", 0)


def format_scorecard_human(card: Scorecard) -> str:
    """Format a Scorecard as a compact, single-screen human-readable view."""
    lines = [
        "======================================================",
        "                  OPERATOR SCORECARD",
        "======================================================",
        f"  Generated:  {card.generated_at}",
        f"  Session:    {card.session_id or '(no session)'}",
        "",
    ]

    # Scoring section
    if card.scoring_report:
        sr = card.scoring_report
        lines.append("--- Prediction Quality ---")
        lines.append(f"  Total:      {sr.total_predictions} predictions")
        lines.append(f"  Scored:     {sr.scored_predictions}  |  Rejected: {sr.rejected_predictions}")

        if sr.mean_brier is not None:
            lines.append(f"  Brier:      {sr.mean_brier:.4f}  (0=perfect, 1=worst)")
        if sr.mean_log_loss is not None:
            lines.append(f"  Log loss:   {sr.mean_log_loss:.4f}")
        if sr.accuracy_pct is not None:
            lines.append(f"  Accuracy:   {sr.accuracy_pct:.1f}%  ({sr.correct_count}W / {sr.incorrect_count}L)")
        if sr.expected_calibration_error is not None:
            lines.append(f"  Cal. error: {sr.expected_calibration_error:.4f}")
        lines.append("")
    else:
        lines.append("--- Prediction Quality ---")
        lines.append("  No scored predictions yet.")
        lines.append("")

    # Coverage section
    lines.append("--- Coverage ---")
    lines.append(f"  BTC: {card.btc_predictions} predictions", )
    if card.btc_accuracy_pct is not None:
        lines[-1] += f"  ({card.btc_accuracy_pct:.1f}% accurate)"
    lines.append(f"  ETH: {card.eth_predictions} predictions")
    if card.eth_accuracy_pct is not None:
        lines[-1] += f"  ({card.eth_accuracy_pct:.1f}% accurate)"
    if card.btc_predictions + card.eth_predictions == 0:
        lines.append("  No predictions made yet.")
    lines.append("")

    # Journal section
    lines.append("--- Journal ---")
    lines.append(f"  Total entries:  {card.journal_total}")
    lines.append(f"  Open:           {card.journal_open}")
    lines.append(f"  Resolved:       {card.journal_resolved}")
    if card.journal_accuracy_pct is not None:
        lines.append(f"  Journal acc:    {card.journal_accuracy_pct:.1f}%")
    if card.journal_mean_brier is not None:
        lines.append(f"  Journal brier:  {card.journal_mean_brier:.4f}")
    lines.append("")

    # Session section
    lines.append("--- Session ---")
    lines.append(f"  Snapshots received: {card.health_snapshots}")
    lines.append(f"  Commands run:       {card.commands_run}")
    if card.session_duration_seconds is not None:
        mins = card.session_duration_seconds / 60
        lines.append(f"  Duration:           {mins:.1f} minutes")
    lines.append("")
    lines.append("======================================================")

    return "\n".join(lines)


def format_scorecard_json(card: Scorecard) -> str:
    """Format a Scorecard as JSON."""
    return json.dumps(card.to_dict(), indent=2)
