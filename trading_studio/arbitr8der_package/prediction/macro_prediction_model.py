"""Macro prediction model — predicts UP/DOWN for 15-minute BTC/ETH markets
using 72h of 15-minute candle data.

Two model approaches:
  1. FrequencyLookupModel: Groups historical windows by conditions, counts outcomes
  2. LightGBMClassifier: Gradient boosted trees on all macro features

Both produce a yes_probability (0.0-1.0) for the next 15-minute window.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.prediction.feature_engine_v2 import (
    FeatureEngine,
    MacroFeatures,
)

logger = get_logger(__name__)

MODEL_VERSION = "macro_v1"


@dataclass
class MacroPrediction:
    """Result of a macro model prediction."""
    asset: str
    model_name: str
    yes_probability: float  # [0.0, 1.0]
    confidence: float  # [0.0, 1.0]
    features_used: dict[str, Any] = field(default_factory=dict)
    predicted_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "model_name": self.model_name,
            "yes_probability": self.yes_probability,
            "confidence": self.confidence,
            "predicted_at": self.predicted_at,
        }

    @property
    def prediction(self) -> str:
        return "UP" if self.yes_probability > 0.5 else "DOWN"


# ---------------------------------------------------------------------------
# Frequency Lookup Model
# ---------------------------------------------------------------------------

class FrequencyLookupModel:
    """Predicts by grouping historical windows by similar conditions
    and counting how often UP occurred in each group.

    Features used for grouping:
      - regime (trending_up, trending_down, ranging, volatile)
      - streak_direction + streak_length bucket (0, 1-3, 4+)
      - hour_of_day bucket (0-5, 6-11, 12-17, 18-23)
      - rsi_7 bucket (<30, 30-50, 50-70, >70)
    """

    def __init__(self, min_samples: int = 5):
        self._min_samples = min_samples
        self._groups: dict[str, dict] = {}  # group_key → {up_count, total}

    def train(self, feature_vectors: list[dict], outcomes: list[str]) -> None:
        """Train on historical features + outcomes.

        Args:
            feature_vectors: list of macro feature dicts
            outcomes: list of 'UP' or 'DOWN' strings
        """
        self._groups = {}

        for features, outcome in zip(feature_vectors, outcomes):
            key = self._group_key(features)
            if key not in self._groups:
                self._groups[key] = {"up_count": 0, "total": 0}
            self._groups[key]["total"] += 1
            if outcome == "UP":
                self._groups[key]["up_count"] += 1

        logger.info("FrequencyLookup trained on %d samples, %d unique groups",
                     len(outcomes), len(self._groups))

    def predict(self, features: dict) -> MacroPrediction:
        """Predict probability of UP for given features."""
        key = self._group_key(features)

        if key in self._groups and self._groups[key]["total"] >= self._min_samples:
            group = self._groups[key]
            prob = group["up_count"] / group["total"]
            # Confidence scales with sample count (more data = more confident)
            confidence = min(1.0, group["total"] / 30)  # full confidence at 30+ samples
        else:
            # Unknown group: default to 50/50 with low confidence
            prob = 0.5
            confidence = 0.1

        return MacroPrediction(
            asset=features.get("asset", "BTC"),
            model_name=f"{MODEL_VERSION}_freq",
            yes_probability=prob,
            confidence=confidence,
            features_used={"group_key": key,
                           "group_count": self._groups.get(key, {}).get("total", 0)},
        )

    def _group_key(self, features: dict) -> str:
        """Create a group key from feature buckets."""
        regime = features.get("regime", "unknown")

        streak_dir = features.get("streak_direction", 0)
        streak_len = features.get("streak_length", 0)
        if streak_len == 0:
            streak_bucket = "none"
        elif streak_len <= 3:
            streak_bucket = f"{'up' if streak_dir > 0 else 'down'}_short"
        else:
            streak_bucket = f"{'up' if streak_dir > 0 else 'down'}_long"

        hour = features.get("hour_of_day", 0)
        if hour < 6:
            hour_bucket = "night"
        elif hour < 12:
            hour_bucket = "morning"
        elif hour < 18:
            hour_bucket = "afternoon"
        else:
            hour_bucket = "evening"

        rsi = features.get("rsi_7", 50)
        if rsi < 30:
            rsi_bucket = "oversold"
        elif rsi < 50:
            rsi_bucket = "below_mid"
        elif rsi < 70:
            rsi_bucket = "above_mid"
        else:
            rsi_bucket = "overbought"

        return f"{regime}|{streak_bucket}|{hour_bucket}|{rsi_bucket}"

    @property
    def group_stats(self) -> dict[str, dict]:
        """Return group statistics for inspection."""
        return dict(self._groups)


# ---------------------------------------------------------------------------
# LightGBM Classifier
# ---------------------------------------------------------------------------

class LightGBMClassifier:
    """Gradient boosted tree classifier for 15-minute market prediction.

    Uses macro features to predict UP/DOWN probability.
    Falls back to 0.5 if not enough training data or model unavailable.
    """

    def __init__(self, version: str = f"{MODEL_VERSION}_lgbm"):
        self._version = version
        self._model = None
        self._feature_names: list[str] = []
        self._trained = False
        self._train_samples = 0

    def train(self, feature_vectors: list[dict], outcomes: list[str]) -> bool:
        """Train on historical features + outcomes.

        Returns True if training succeeded, False otherwise.
        """
        if len(feature_vectors) < 20:
            logger.warning("Need at least 20 samples for LightGBM, got %d",
                           len(feature_vectors))
            return False

        try:
            import lightgbm as lgb
        except ImportError:
            logger.warning("LightGBM not installed — install with: pip install lightgbm")
            return False

        # Convert features to numpy arrays
        if not self._feature_names:
            # Use all numeric keys from first feature vector
            self._feature_names = [
                k for k, v in feature_vectors[0].items()
                if isinstance(v, (int, float))
            ]

        X = []
        for fv in feature_vectors:
            row = [float(fv.get(k, 0.0)) for k in self._feature_names]
            X.append(row)

        X_arr = np.array(X, dtype=np.float32)
        y_arr = np.array([1 if o == "UP" else 0 for o in outcomes], dtype=np.int32)

        # Replace NaN/inf
        X_arr = np.nan_to_num(X_arr, nan=0.0, posinf=1e6, neginf=-1e6)

        # Train with 80/20 split (time-based, not random)
        split = int(len(X_arr) * 0.8)
        X_train, X_val = X_arr[:split], X_arr[split:]
        y_train, y_val = y_arr[:split], y_arr[split:]

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
            "min_child_samples": 10,
        }

        self._model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
            valid_sets=[val_data],
            callbacks=[lgb.log_evaluation(0)],  # silent
        )

        self._trained = True
        self._train_samples = len(X_arr)

        # Log validation accuracy
        val_pred = self._model.predict(X_val)
        val_correct = sum(
            1 for p, y in zip(val_pred, y_val)
            if (p > 0.5) == (y == 1)
        )
        val_acc = val_correct / len(y_val) if len(y_val) > 0 else 0
        logger.info("LightGBM trained on %d samples, val accuracy: %.1f%%",
                     self._train_samples, val_acc * 100)

        return True

    def predict(self, features: dict) -> MacroPrediction:
        """Predict probability of UP for given features."""
        if not self._trained or self._model is None:
            return MacroPrediction(
                asset=features.get("asset", "BTC"),
                model_name=self._version,
                yes_probability=0.5,
                confidence=0.0,
                features_used={"error": "model not trained"},
            )

        row = [float(features.get(k, 0.0)) for k in self._feature_names]
        X = np.array([row], dtype=np.float32)
        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)

        prob = float(self._model.predict(X)[0])
        prob = max(0.01, min(0.99, prob))  # clamp away from extremes

        # Confidence based on distance from 0.5 (more certain = further from 0.5)
        confidence = abs(prob - 0.5) * 2  # 0 at 50%, 1 at 0% or 100%
        confidence = max(0.1, min(1.0, confidence))

        return MacroPrediction(
            asset=features.get("asset", "BTC"),
            model_name=self._version,
            yes_probability=prob,
            confidence=confidence,
            features_used={"features_used": self._feature_names},
        )

    def get_feature_importance(self) -> dict[str, float]:
        """Return feature importance rankings."""
        if not self._trained or self._model is None:
            return {}
        importance = self._model.feature_importance(importance_type="gain")
        return dict(sorted(
            zip(self._feature_names, importance.tolist()),
            key=lambda x: x[1],
            reverse=True,
        ))


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

class MacroEnsemble:
    """Combines FrequencyLookup and LightGBM predictions."""

    def __init__(
        self,
        freq_model: FrequencyLookupModel | None = None,
        lgbm_model: LightGBMClassifier | None = None,
        freq_weight: float = 0.3,
        lgbm_weight: float = 0.7,
    ):
        self._freq = freq_model or FrequencyLookupModel()
        self._lgbm = lgbm_model or LightGBMClassifier()
        self._freq_weight = freq_weight
        self._lgbm_weight = lgbm_weight

    @property
    def freq_model(self) -> FrequencyLookupModel:
        return self._freq

    @property
    def lgbm_model(self) -> LightGBMClassifier:
        return self._lgbm

    def predict(self, features: dict) -> MacroPrediction:
        """Ensemble prediction combining both models."""
        freq_pred = self._freq.predict(features)
        lgbm_pred = self._lgbm.predict(features)

        # Weight by model availability and confidence
        if lgbm_pred.confidence > 0 and freq_pred.confidence > 0:
            combined_prob = (
                self._freq_weight * freq_pred.yes_probability +
                self._lgbm_weight * lgbm_pred.yes_probability
            )
            combined_conf = (
                self._freq_weight * freq_pred.confidence +
                self._lgbm_weight * lgbm_pred.confidence
            )
        elif lgbm_pred.confidence > 0:
            combined_prob = lgbm_pred.yes_probability
            combined_conf = lgbm_pred.confidence
        elif freq_pred.confidence > 0:
            combined_prob = freq_pred.yes_probability
            combined_conf = freq_pred.confidence
        else:
            combined_prob = 0.5
            combined_conf = 0.0

        return MacroPrediction(
            asset=features.get("asset", "BTC"),
            model_name=f"{MODEL_VERSION}_ensemble",
            yes_probability=max(0.01, min(0.99, combined_prob)),
            confidence=max(0.0, min(1.0, combined_conf)),
            features_used={
                "freq": freq_pred.to_dict(),
                "lgbm": lgbm_pred.to_dict(),
                "freq_weight": self._freq_weight,
                "lgbm_weight": self._lgbm_weight,
            },
        )
