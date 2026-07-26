"""Prediction scoring — evaluates forecast accuracy against outcomes.

Computes Brier score, log loss, calibration, and rolling accuracy
for a stream of PredictionRecords. Tracks prediction quality over time.

Brier score: mean((forecast - outcome)^2) — lower is better, 0.0 = perfect.
Log loss: -mean(outcome*log(forecast) + (1-outcome)*log(1-forecast)) — lower is better.
Calibration: grouping predictions by confidence bucket and checking if actual
  frequency matches predicted frequency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.prediction.baseline_prediction_engine import PredictionRecord

logger = get_logger(__name__)

# Calibration buckets: [0-20%, 20-40%, 40-60%, 60-80%, 80-100%]
CALIBRATION_BUCKETS = [
    (0.0, 0.2, "0-20%"),
    (0.2, 0.4, "20-40%"),
    (0.4, 0.6, "40-60%"),
    (0.6, 0.8, "60-80%"),
    (0.8, 1.0, "80-100%"),
]


@dataclass
class ScoringBucket:
    """A single calibration bucket."""
    label: str = ""
    count: int = 0
    sum_forecast: float = 0.0
    sum_outcome: float = 0.0

    @property
    def mean_forecast(self) -> float:
        return self.sum_forecast / self.count if self.count > 0 else 0.0

    @property
    def mean_outcome(self) -> float:
        return self.sum_outcome / self.count if self.count > 0 else 0.0

    @property
    def calibration_error(self) -> float:
        """How far off calibration this bucket is."""
        return abs(self.mean_forecast - self.mean_outcome)


@dataclass
class ScoringReport:
    """Aggregated scoring report across multiple predictions."""
    total_predictions: int = 0
    scored_predictions: int = 0
    rejected_predictions: int = 0

    # Overall metrics
    mean_brier: float | None = None
    mean_log_loss: float | None = None

    # Accuracy
    accuracy_pct: float | None = None  # % of predictions that were directionally correct
    correct_count: int = 0
    incorrect_count: int = 0

    # Calibration
    calibration_buckets: list[ScoringBucket] = field(default_factory=list)
    expected_calibration_error: float | None = None

    # Per-asset breakdown
    per_asset: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_predictions": self.total_predictions,
            "scored_predictions": self.scored_predictions,
            "rejected_predictions": self.rejected_predictions,
            "mean_brier": self.mean_brier,
            "mean_log_loss": self.mean_log_loss,
            "accuracy_pct": self.accuracy_pct,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "expected_calibration_error": self.expected_calibration_error,
            "calibration_buckets": [
                {
                    "label": b.label,
                    "count": b.count,
                    "mean_forecast": round(b.mean_forecast, 4),
                    "mean_outcome": round(b.mean_outcome, 4),
                    "calibration_error": round(b.calibration_error, 4),
                }
                for b in self.calibration_buckets
            ],
            "per_asset": self.per_asset,
        }


class PredictionScorer:
    """Scores predictions against outcomes and tracks accuracy over time."""

    def __init__(self) -> None:
        self._history: list[PredictionRecord] = []

    def score_prediction(self, record: PredictionRecord) -> PredictionRecord:
        """Score a single prediction against its outcome.

        Updates the record's score_brier and score_log_loss fields in place.
        Returns the same record.
        """
        if record.rejected or record.actual_outcome is None:
            return record

        outcome = record.actual_outcome  # 0 or 1
        forecast = record.yes_probability

        if forecast is None:
            return record

        # Clamp forecast to avoid log(0)
        forecast = max(0.001, min(0.999, forecast))

        # Brier score
        record.score_brier = (forecast - outcome) ** 2

        # Log loss
        if outcome == 1:
            record.score_log_loss = -math.log(forecast)
        else:
            record.score_log_loss = -math.log(1.0 - forecast)

        return record

    def score_batch(self, records: list[PredictionRecord]) -> list[PredictionRecord]:
        """Score a batch of predictions."""
        for record in records:
            self.score_prediction(record)
            self._history.append(record)
        return records

    def generate_report(self, records: list[PredictionRecord] | None = None) -> ScoringReport:
        """Generate a scoring report from a list of predictions (or all history).

        Args:
            records: Specific records to score, or None for full history

        Returns:
            ScoringReport with all metrics
        """
        if records is None:
            records = self._history

        report = ScoringReport()
        report.total_predictions = len(records)

        scored = [r for r in records if not r.rejected and r.actual_outcome is not None and r.yes_probability is not None]
        rejected = [r for r in records if r.rejected]

        report.scored_predictions = len(scored)
        report.rejected_predictions = len(rejected)

        if not scored:
            return report

        # Brier score
        brier_scores = [r.score_brier for r in scored if r.score_brier is not None]
        if brier_scores:
            report.mean_brier = sum(brier_scores) / len(brier_scores)

        # Log loss
        log_losses = [r.score_log_loss for r in scored if r.score_log_loss is not None]
        if log_losses:
            report.mean_log_loss = sum(log_losses) / len(log_losses)

        # Accuracy (directional: did we predict >50% for a YES outcome, or <50% for NO?)
        correct = 0
        incorrect = 0
        for r in scored:
            if r.yes_probability is not None and r.actual_outcome is not None:
                predicted_yes = r.yes_probability >= 0.5
                actual_yes = r.actual_outcome == 1
                if predicted_yes == actual_yes:
                    correct += 1
                else:
                    incorrect += 1

        report.correct_count = correct
        report.incorrect_count = incorrect
        total_correct = correct + incorrect
        if total_correct > 0:
            report.accuracy_pct = correct / total_correct * 100

        # Calibration buckets
        report.calibration_buckets = self._compute_calibration(scored)

        # Expected Calibration Error
        non_empty = [b for b in report.calibration_buckets if b.count > 0]
        if non_empty:
            report.expected_calibration_error = sum(b.calibration_error for b in non_empty) / len(non_empty)

        # Per-asset breakdown
        assets = set(r.asset for r in scored)
        for asset in assets:
            asset_records = [r for r in scored if r.asset == asset]
            asset_brier = [r.score_brier for r in asset_records if r.score_brier is not None]
            asset_correct = sum(
                1 for r in asset_records
                if r.yes_probability is not None and r.actual_outcome is not None
                and (r.yes_probability >= 0.5) == (r.actual_outcome == 1)
            )
            report.per_asset[asset] = {
                "count": len(asset_records),
                "mean_brier": sum(asset_brier) / len(asset_brier) if asset_brier else None,
                "accuracy_pct": asset_correct / len(asset_records) * 100 if asset_records else None,
            }

        return report

    def _compute_calibration(self, records: list[PredictionRecord]) -> list[ScoringBucket]:
        """Compute calibration buckets."""
        buckets = [ScoringBucket(label=label) for _, _, label in CALIBRATION_BUCKETS]

        for r in records:
            if r.yes_probability is None or r.actual_outcome is None:
                continue
            for i, (low, high, _) in enumerate(CALIBRATION_BUCKETS):
                if low <= r.yes_probability < high or (high == 1.0 and r.yes_probability == 1.0):
                    buckets[i].count += 1
                    buckets[i].sum_forecast += r.yes_probability
                    buckets[i].sum_outcome += r.actual_outcome
                    break

        return buckets

    def get_history(self) -> list[PredictionRecord]:
        """Return all scored prediction history."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear scoring history."""
        self._history.clear()


def format_report_human(report: ScoringReport) -> str:
    """Format a ScoringReport as human-readable text."""
    lines = [
        "=== Prediction Scoring Report ===",
        f"  Total predictions:  {report.total_predictions}",
        f"  Scored:             {report.scored_predictions}",
        f"  Rejected:           {report.rejected_predictions}",
    ]

    if report.mean_brier is not None:
        lines.append(f"  Brier score:        {report.mean_brier:.4f} (lower = better, 0 = perfect)")
    if report.mean_log_loss is not None:
        lines.append(f"  Log loss:           {report.mean_log_loss:.4f} (lower = better)")
    if report.accuracy_pct is not None:
        lines.append(f"  Directional acc:    {report.accuracy_pct:.1f}% ({report.correct_count}W / {report.incorrect_count}L)")
    if report.expected_calibration_error is not None:
        lines.append(f"  Calibration error:  {report.expected_calibration_error:.4f}")

    if report.calibration_buckets:
        lines.append("")
        lines.append("  Calibration:")
        for b in report.calibration_buckets:
            if b.count > 0:
                lines.append(f"    {b.label:10s}  n={b.count:3d}  forecast={b.mean_forecast:.3f}  actual={b.mean_outcome:.3f}  err={b.calibration_error:.3f}")

    if report.per_asset:
        lines.append("")
        lines.append("  Per-asset:")
        for asset, stats in sorted(report.per_asset.items()):
            acc = f"{stats['accuracy_pct']:.1f}%" if stats["accuracy_pct"] is not None else "n/a"
            brier = f"{stats['mean_brier']:.4f}" if stats["mean_brier"] is not None else "n/a"
            lines.append(f"    {asset:6s}  n={stats['count']:3d}  brier={brier}  acc={acc}")

    return "\n".join(lines)


def format_report_json(report: ScoringReport) -> str:
    """Format a ScoringReport as JSON."""
    import json
    return json.dumps(report.to_dict(), indent=2)
