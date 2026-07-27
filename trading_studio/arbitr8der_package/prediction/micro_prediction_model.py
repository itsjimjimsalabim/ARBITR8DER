"""Micro prediction model — predicts UP/DOWN for 15-minute BTC/ETH markets
using recent 1-minute candle momentum and order flow signals.

Two model approaches:
  1. MomentumLookupModel: Short-horizon momentum bucketing with streak analysis
  2. LogisticRegressionClassifier: Regularized logistic regression on micro features

Both produce a yes_probability (0.0-1.0) for the next 15-minute window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.prediction.feature_engine_v2 import (
    FeatureEngine,
    MicroFeatures,
)

logger = get_logger(__name__)

MODEL_VERSION = "micro_v1"


@dataclass
class MicroPrediction:
    """Result of a micro model prediction."""
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
# Momentum Lookup Model
# ---------------------------------------------------------------------------

class MomentumLookupModel:
    """Predicts by grouping recent momentum conditions and counting outcomes.

    Features used for grouping:
      - return_1m bucket (strong_down, down, flat, up, strong_up)
      - return_5m bucket (same)
      - momentum_acceleration bucket (decelerating, neutral, accelerating)
      - volume_spike bucket (low, normal, high)
      - range_expanding bucket (contracting, normal, expanding)
    """

    def __init__(self, min_samples: int = 5):
        self._min_samples = min_samples
        self._groups: dict[str, dict] = {}

    def train(self, feature_vectors: list[dict], outcomes: list[str]) -> None:
        """Train on historical micro features + outcomes."""
        self._groups = {}

        for features, outcome in zip(feature_vectors, outcomes):
            key = self._group_key(features)
            if key not in self._groups:
                self._groups[key] = {"up_count": 0, "total": 0}
            self._groups[key]["total"] += 1
            if outcome == "UP":
                self._groups[key]["up_count"] += 1

        logger.info("MomentumLookup trained on %d samples, %d unique groups",
                     len(outcomes), len(self._groups))

    def predict(self, features: dict) -> MicroPrediction:
        """Predict probability of UP for given micro features."""
        key = self._group_key(features)

        if key in self._groups and self._groups[key]["total"] >= self._min_samples:
            group = self._groups[key]
            prob = group["up_count"] / group["total"]
            confidence = min(1.0, group["total"] / 20)
        else:
            prob = 0.5
            confidence = 0.1

        return MicroPrediction(
            asset=features.get("asset", "BTC"),
            model_name=f"{MODEL_VERSION}_momentum",
            yes_probability=prob,
            confidence=confidence,
            features_used={"group_key": key,
                           "group_count": self._groups.get(key, {}).get("total", 0)},
        )

    def _group_key(self, features: dict) -> str:
        """Create a group key from micro feature buckets."""
        r1 = features.get("return_1m", 0.0)
        r1_bucket = self._return_bucket(r1)

        r5 = features.get("return_5m", 0.0)
        r5_bucket = self._return_bucket(r5)

        accel = features.get("momentum_acceleration", 0.0)
        if accel > 0.0005:
            accel_bucket = "accelerating"
        elif accel < -0.0005:
            accel_bucket = "decelerating"
        else:
            accel_bucket = "neutral"

        vol_spike = features.get("volume_spike", 1.0)
        if vol_spike > 2.0:
            vol_bucket = "high"
        elif vol_spike < 0.5:
            vol_bucket = "low"
        else:
            vol_bucket = "normal"

        range_exp = features.get("range_expanding", 1.0)
        if range_exp > 1.5:
            range_bucket = "expanding"
        elif range_exp < 0.67:
            range_bucket = "contracting"
        else:
            range_bucket = "normal"

        return f"{r1_bucket}|{r5_bucket}|{accel_bucket}|{vol_bucket}|{range_bucket}"

    def _return_bucket(self, ret: float) -> str:
        """Bucket a return value into categories."""
        if ret > 0.001:
            return "strong_up"
        elif ret > 0.0002:
            return "up"
        elif ret < -0.001:
            return "strong_down"
        elif ret < -0.0002:
            return "down"
        else:
            return "flat"

    @property
    def group_stats(self) -> dict[str, dict]:
        return dict(self._groups)


# ---------------------------------------------------------------------------
# Logistic Regression Classifier
# ---------------------------------------------------------------------------

class LogisticRegressionClassifier:
    """Regularized logistic regression for micro-horizon prediction.

    Falls back to 0.5 if not enough training data or model unavailable.
    """

    def __init__(self, version: str = f"{MODEL_VERSION}_lr"):
        self._version = version
        self._weights: np.ndarray | None = None
        self._bias: float = 0.0
        self._feature_names: list[str] = []
        self._means: np.ndarray | None = None
        self._stds: np.ndarray | None = None
        self._trained = False
        self._train_samples = 0

    def train(self, feature_vectors: list[dict], outcomes: list[str],
              lr: float = 0.01, epochs: int = 200, l2: float = 0.001) -> bool:
        """Train logistic regression with gradient descent.

        Returns True if training succeeded, False otherwise.
        """
        if len(feature_vectors) < 10:
            logger.warning("Need at least 10 samples for LR, got %d",
                           len(feature_vectors))
            return False

        if not self._feature_names:
            self._feature_names = [
                k for k, v in feature_vectors[0].items()
                if isinstance(v, (int, float))
            ]

        X = np.array(
            [[float(fv.get(k, 0.0)) for k in self._feature_names]
             for fv in feature_vectors],
            dtype=np.float64,
        )
        y = np.array([1 if o == "UP" else 0 for o in outcomes], dtype=np.float64)

        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)

        # Standardize features
        self._means = X.mean(axis=0)
        self._stds = X.std(axis=0)
        self._stds[self._stds < 1e-8] = 1.0
        X_norm = (X - self._means) / self._stds

        # Train with gradient descent
        n_features = X_norm.shape[1]
        self._weights = np.zeros(n_features, dtype=np.float64)
        self._bias = 0.0

        for epoch in range(epochs):
            logits = X_norm @ self._weights + self._bias
            probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -500, 500)))

            error = probs - y
            grad_w = X_norm.T @ error / len(y) + l2 * self._weights
            grad_b = error.mean()

            self._weights -= lr * grad_w
            self._bias -= lr * grad_b

        self._trained = True
        self._train_samples = len(X)

        # Training accuracy
        pred_probs = 1.0 / (1.0 + np.exp(-np.clip(X_norm @ self._weights + self._bias, -500, 500)))
        train_correct = sum(1 for p, t in zip(pred_probs, y) if (p > 0.5) == (t == 1.0))
        train_acc = train_correct / len(y) if len(y) > 0 else 0
        logger.info("LogisticRegression trained on %d samples, train accuracy: %.1f%%",
                     self._train_samples, train_acc * 100)

        return True

    def predict(self, features: dict) -> MicroPrediction:
        """Predict probability of UP for given micro features."""
        if not self._trained or self._weights is None:
            return MicroPrediction(
                asset=features.get("asset", "BTC"),
                model_name=self._version,
                yes_probability=0.5,
                confidence=0.0,
                features_used={"error": "model not trained"},
            )

        row = np.array([float(features.get(k, 0.0)) for k in self._feature_names],
                       dtype=np.float64)
        row = np.nan_to_num(row, nan=0.0, posinf=1e6, neginf=-1e6)
        row_norm = (row - self._means) / self._stds

        logit = float(row_norm @ self._weights + self._bias)
        prob = 1.0 / (1.0 + np.exp(-np.clip(logit, -500, 500)))
        prob = max(0.01, min(0.99, prob))

        confidence = abs(prob - 0.5) * 2
        confidence = max(0.1, min(1.0, confidence))

        return MicroPrediction(
            asset=features.get("asset", "BTC"),
            model_name=self._version,
            yes_probability=prob,
            confidence=confidence,
            features_used={"features_used": self._feature_names},
        )


# ---------------------------------------------------------------------------
# Micro Ensemble
# ---------------------------------------------------------------------------

class MicroEnsemble:
    """Combines MomentumLookup and LogisticRegression predictions."""

    def __init__(
        self,
        momentum_model: MomentumLookupModel | None = None,
        lr_model: LogisticRegressionClassifier | None = None,
        momentum_weight: float = 0.4,
        lr_weight: float = 0.6,
    ):
        self._momentum = momentum_model or MomentumLookupModel()
        self._lr = lr_model or LogisticRegressionClassifier()
        self._momentum_weight = momentum_weight
        self._lr_weight = lr_weight

    @property
    def momentum_model(self) -> MomentumLookupModel:
        return self._momentum

    @property
    def lr_model(self) -> LogisticRegressionClassifier:
        return self._lr

    def predict(self, features: dict) -> MicroPrediction:
        """Ensemble prediction combining both models."""
        mom_pred = self._momentum.predict(features)
        lr_pred = self._lr.predict(features)

        if lr_pred.confidence > 0 and mom_pred.confidence > 0:
            combined_prob = (
                self._momentum_weight * mom_pred.yes_probability +
                self._lr_weight * lr_pred.yes_probability
            )
            combined_conf = (
                self._momentum_weight * mom_pred.confidence +
                self._lr_weight * lr_pred.confidence
            )
        elif lr_pred.confidence > 0:
            combined_prob = lr_pred.yes_probability
            combined_conf = lr_pred.confidence
        elif mom_pred.confidence > 0:
            combined_prob = mom_pred.yes_probability
            combined_conf = mom_pred.confidence
        else:
            combined_prob = 0.5
            combined_conf = 0.0

        return MicroPrediction(
            asset=features.get("asset", "BTC"),
            model_name=f"{MODEL_VERSION}_ensemble",
            yes_probability=max(0.01, min(0.99, combined_prob)),
            confidence=max(0.0, min(1.0, combined_conf)),
            features_used={
                "momentum": mom_pred.to_dict(),
                "lr": lr_pred.to_dict(),
                "momentum_weight": self._momentum_weight,
                "lr_weight": self._lr_weight,
            },
        )
