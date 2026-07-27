"""Feature importance analyzer — analyzes stability and rankings of
feature importance from backtest results across retraining windows.

Helps identify which features are consistently predictive vs noise.

Usage:
    analyzer = FeatureImportanceAnalyzer()
    report = analyzer.analyze(backtest_result)
    report.print_summary()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Feature importance record
# ---------------------------------------------------------------------------

@dataclass
class FeatureImportanceRecord:
    """Aggregated importance stats for a single feature."""
    feature_name: str
    mean_importance: float
    std_importance: float
    coefficient_of_variation: float  # std / mean (lower = more stable)
    rank_by_mean: int
    rank_by_stability: int  # lower CV = more stable = lower rank number
    appears_in_top_10_count: int  # how often it's in top 10
    importance_samples: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "mean_importance": round(self.mean_importance, 4),
            "std_importance": round(self.std_importance, 4),
            "coefficient_of_variation": round(self.coefficient_of_variation, 4),
            "rank_by_mean": self.rank_by_mean,
            "rank_by_stability": self.rank_by_stability,
            "appears_in_top_10_count": self.appears_in_top_10_count,
        }


# ---------------------------------------------------------------------------
# Analysis report
# ---------------------------------------------------------------------------

@dataclass
class FeatureImportanceReport:
    """Full feature importance analysis report."""
    total_features: int = 0
    total_retraining_windows: int = 0
    records: list[FeatureImportanceRecord] = field(default_factory=list)
    stability_score: float = 0.0  # 0-100, higher = more stable
    top_features: list[str] = field(default_factory=list)
    unstable_features: list[str] = field(default_factory=list)  # high CV

    def print_summary(self) -> None:
        """Pretty-print the feature importance report."""
        lines = [
            f"\n{'='*65}",
            f"  FEATURE IMPORTANCE ANALYSIS",
            f"  {self.total_features} features | {self.total_retraining_windows} retraining windows",
            f"{'='*65}",
            f"  Stability score:    {self.stability_score:.1f}/100",
            f"  Top features:       {', '.join(self.top_features[:5])}",
        ]
        if self.unstable_features:
            lines.append(f"  Unstable features:  {', '.join(self.unstable_features[:5])}")

        lines.append(f"\n  {'FEATURE':35s} {'MEAN':>10s} {'STD':>10s} {'CV':>8s} {'RANK':>6s}")
        lines.append(f"  {'-'*69}")

        for rec in self.records[:15]:  # top 15
            lines.append(
                f"  {rec.feature_name:35s} {rec.mean_importance:>10.4f} "
                f"{rec.std_importance:>10.4f} {rec.coefficient_of_variation:>8.3f} "
                f"#{rec.rank_by_mean:>4d}"
            )

        lines.append(f"{'='*65}\n")
        print("\n".join(lines))

    def to_dict(self) -> dict:
        """Return serializable dict."""
        return {
            "total_features": self.total_features,
            "total_retraining_windows": self.total_retraining_windows,
            "stability_score": round(self.stability_score, 1),
            "top_features": self.top_features,
            "unstable_features": self.unstable_features,
            "records": [r.to_dict() for r in self.records],
        }


# ---------------------------------------------------------------------------
# Feature importance analyzer
# ---------------------------------------------------------------------------

class FeatureImportanceAnalyzer:
    """Analyzes feature importance stability from backtest results.

    Takes a list of feature importance dicts (one per retraining window)
    and computes per-feature mean, std, coefficient of variation, and rankings.

    Lower coefficient of variation = more stable = more trustworthy feature.
    """

    def analyze(
        self,
        importance_snapshots: list[dict[str, float]],
    ) -> FeatureImportanceReport:
        """Analyze feature importance across multiple retraining snapshots.

        Parameters
        ----------
        importance_snapshots : list[dict[str, float]]
            List of feature importance dicts, one per retraining window.
            Each dict maps feature_name -> importance_value.

        Returns
        -------
        FeatureImportanceReport with per-feature stats and stability score.
        """
        if not importance_snapshots:
            return FeatureImportanceReport()

        # Collect all feature names
        all_features: set[str] = set()
        for snap in importance_snapshots:
            all_features.update(snap.keys())

        if not all_features:
            return FeatureImportanceReport()

        # Compute per-feature stats
        records: list[FeatureImportanceRecord] = []
        for fname in sorted(all_features):
            values = [snap.get(fname, 0.0) for snap in importance_snapshots]
            non_zero = [v for v in values if v > 0]

            mean_val = sum(values) / len(values) if values else 0.0
            std_val = 0.0
            if len(values) > 1:
                var = sum((v - mean_val) ** 2 for v in values) / (len(values) - 1)
                std_val = math.sqrt(var)

            cv = std_val / mean_val if mean_val > 0 else float("inf")

            # Count how often this feature is in top 10 of each snapshot
            top_10_count = 0
            for snap in importance_snapshots:
                sorted_features = sorted(snap.items(), key=lambda x: -x[1])
                top_10_names = [f for f, _ in sorted_features[:10]]
                if fname in top_10_names:
                    top_10_count += 1

            records.append(FeatureImportanceRecord(
                feature_name=fname,
                mean_importance=mean_val,
                std_importance=std_val,
                coefficient_of_variation=cv,
                rank_by_mean=0,  # set below
                rank_by_stability=0,  # set below
                appears_in_top_10_count=top_10_count,
                importance_samples=values,
            ))

        # Rank by mean importance (higher = better rank)
        records.sort(key=lambda r: -r.mean_importance)
        for i, rec in enumerate(records):
            rec.rank_by_mean = i + 1

        # Rank by stability (lower CV = more stable = better rank)
        stable_records = [r for r in records if r.coefficient_of_variation != float("inf")]
        unstable_records = [r for r in records if r.coefficient_of_variation == float("inf")]

        stable_records.sort(key=lambda r: r.coefficient_of_variation)
        for i, rec in enumerate(stable_records):
            rec.rank_by_stability = i + 1
        for rec in unstable_records:
            rec.rank_by_stability = len(stable_records) + 1

        # Compute stability score (0-100)
        # Based on: average rank correlation between mean and stability,
        # and proportion of features with finite CV
        finite_cv_records = [r for r in records if r.coefficient_of_variation != float("inf")]
        if finite_cv_records:
            avg_cv = sum(r.coefficient_of_variation for r in finite_cv_records) / len(finite_cv_records)
            # Lower avg CV = higher stability score
            # CV of 0.5 → score 50, CV of 0.1 → score 90, CV of 1.0 → score 20
            stability_score = max(0, min(100, (1.0 - avg_cv) * 100))
        else:
            stability_score = 0.0

        # Top features: those with highest mean importance and reasonable stability
        top_features = [r.feature_name for r in records[:10]]

        # Unstable features: high CV (>1.0) or zero mean
        unstable_features = [
            r.feature_name for r in records
            if r.coefficient_of_variation > 1.0 or r.mean_importance == 0
        ]

        return FeatureImportanceReport(
            total_features=len(records),
            total_retraining_windows=len(importance_snapshots),
            records=records,
            stability_score=stability_score,
            top_features=top_features,
            unstable_features=unstable_features,
        )

    def compare_models(
        self,
        model_a_snapshots: list[dict[str, float]],
        model_b_snapshots: list[dict[str, float]],
        model_a_name: str = "Model A",
        model_b_name: str = "Model B",
    ) -> str:
        """Compare feature importance between two models.

        Returns a human-readable comparison string.
        """
        report_a = self.analyze(model_a_snapshots)
        report_b = self.analyze(model_b_snapshots)

        lines = [
            f"\n{'='*60}",
            f"  FEATURE IMPORTANCE COMPARISON",
            f"  {model_a_name} vs {model_b_name}",
            f"{'='*60}",
            f"\n  Stability: {model_a_name}={report_a.stability_score:.1f}  {model_b_name}={report_b.stability_score:.1f}",
            f"\n  Top 5 features ({model_a_name}):",
        ]
        for i, fname in enumerate(report_a.top_features[:5], 1):
            rec = next(r for r in report_a.records if r.feature_name == fname)
            lines.append(f"    {i}. {fname:30s} (mean={rec.mean_importance:.4f}, cv={rec.coefficient_of_variation:.3f})")

        lines.append(f"\n  Top 5 features ({model_b_name}):")
        for i, fname in enumerate(report_b.top_features[:5], 1):
            rec = next(r for r in report_b.records if r.feature_name == fname)
            lines.append(f"    {i}. {fname:30s} (mean={rec.mean_importance:.4f}, cv={rec.coefficient_of_variation:.3f})")

        # Feature agreement: how many top-10 features overlap
        top_a = set(report_a.top_features[:10])
        top_b = set(report_b.top_features[:10])
        overlap = top_a & top_b
        lines.append(f"\n  Top-10 overlap: {len(overlap)}/10 features")
        if overlap:
            lines.append(f"  Shared: {', '.join(sorted(overlap)[:5])}")

        lines.append(f"{'='*60}\n")
        return "\n".join(lines)
