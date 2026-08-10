"""Tests for micro_prediction_model — MomentumLookup, LogisticRegression, and Ensemble."""

from __future__ import annotations

import pytest

from kalshi_desk_package.prediction.micro_prediction_model import (
    MicroPrediction,
    MomentumLookupModel,
    LogisticRegressionClassifier,
    MicroEnsemble,
)


# ---------------------------------------------------------------------------
# MicroPrediction dataclass
# ---------------------------------------------------------------------------

class TestMicroPrediction:
    def test_prediction_up(self):
        p = MicroPrediction(asset="BTC", model_name="test", yes_probability=0.7, confidence=0.8)
        assert p.prediction == "UP"

    def test_prediction_down(self):
        p = MicroPrediction(asset="BTC", model_name="test", yes_probability=0.3, confidence=0.8)
        assert p.prediction == "DOWN"

    def test_to_dict(self):
        p = MicroPrediction(asset="ETH", model_name="m1", yes_probability=0.6, confidence=0.7)
        d = p.to_dict()
        assert d["asset"] == "ETH"
        assert d["yes_probability"] == 0.6


# ---------------------------------------------------------------------------
# MomentumLookupModel
# ---------------------------------------------------------------------------

def _make_micro_features(return_1m=0.0, return_5m=0.0, momentum_acceleration=0.0,
                          volume_spike=1.0, range_expanding=1.0, asset="BTC"):
    return {
        "return_1m": return_1m,
        "return_5m": return_5m,
        "momentum_acceleration": momentum_acceleration,
        "volume_spike": volume_spike,
        "range_expanding": range_expanding,
        "asset": asset,
    }


class TestMomentumLookupModel:
    def test_train_and_predict(self):
        model = MomentumLookupModel(min_samples=3)
        features = [_make_micro_features(return_1m=0.002, return_5m=0.001)] * 10
        outcomes = ["UP"] * 10
        model.train(features, outcomes)

        pred = model.predict(_make_micro_features(return_1m=0.002, return_5m=0.001))
        assert isinstance(pred, MicroPrediction)
        assert pred.yes_probability == 1.0
        assert pred.confidence > 0.1

    def test_predict_unknown_group(self):
        model = MomentumLookupModel(min_samples=3)
        model.train([_make_micro_features()] * 5, ["UP"] * 5)
        # Different group
        pred = model.predict(_make_micro_features(return_1m=0.005, return_5m=0.005))
        assert pred.yes_probability == 0.5
        assert pred.confidence == 0.1

    def test_mixed_outcomes(self):
        model = MomentumLookupModel(min_samples=3)
        up_feats = [_make_micro_features(return_1m=0.002)] * 7
        down_feats = [_make_micro_features(return_1m=-0.002)] * 3
        model.train(up_feats + down_feats, ["UP"] * 7 + ["DOWN"] * 3)

        pred_up = model.predict(_make_micro_features(return_1m=0.002))
        assert pred_up.yes_probability == 1.0

        pred_down = model.predict(_make_micro_features(return_1m=-0.002))
        assert pred_down.yes_probability == 0.0

    def test_return_bucket_thresholds(self):
        model = MomentumLookupModel()
        assert model._return_bucket(0.002) == "strong_up"
        assert model._return_bucket(0.0005) == "up"
        assert model._return_bucket(0.0) == "flat"
        assert model._return_bucket(-0.0005) == "down"
        assert model._return_bucket(-0.002) == "strong_down"

    def test_group_key_volume_and_range(self):
        model = MomentumLookupModel()
        key = model._group_key(_make_micro_features(
            volume_spike=3.0, range_expanding=2.0
        ))
        assert "high" in key
        assert "expanding" in key

        key2 = model._group_key(_make_micro_features(
            volume_spike=0.3, range_expanding=0.5
        ))
        assert "low" in key2
        assert "contracting" in key2


# ---------------------------------------------------------------------------
# LogisticRegressionClassifier
# ---------------------------------------------------------------------------

class TestLogisticRegressionClassifier:
    def test_train_insufficient(self):
        model = LogisticRegressionClassifier()
        result = model.train([_make_micro_features()] * 5, ["UP"] * 5)
        assert result is False

    def test_train_and_predict(self):
        model = LogisticRegressionClassifier()
        # Need 10+ samples with separable features
        features = []
        outcomes = []
        for i in range(30):
            if i % 2 == 0:
                features.append(_make_micro_features(
                    return_1m=0.002, return_5m=0.001, volume_spike=2.0
                ))
                outcomes.append("UP")
            else:
                features.append(_make_micro_features(
                    return_1m=-0.002, return_5m=-0.001, volume_spike=0.5
                ))
                outcomes.append("DOWN")

        result = model.train(features, outcomes, epochs=300)
        assert result is True

        pred = model.predict(_make_micro_features(
            return_1m=0.002, return_5m=0.001, volume_spike=2.0
        ))
        assert isinstance(pred, MicroPrediction)
        assert 0.01 <= pred.yes_probability <= 0.99
        assert pred.confidence > 0.1

    def test_predict_untrained(self):
        model = LogisticRegressionClassifier()
        pred = model.predict(_make_micro_features())
        assert pred.yes_probability == 0.5
        assert pred.confidence == 0.0

    def test_perfect_separation(self):
        """With perfectly separable data, LR should achieve high accuracy."""
        model = LogisticRegressionClassifier()
        features = []
        outcomes = []
        for i in range(20):
            features.append(_make_micro_features(return_1m=0.01 if i < 10 else -0.01))
            outcomes.append("UP" if i < 10 else "DOWN")

        model.train(features, outcomes, epochs=500, lr=0.05)

        pred_up = model.predict(_make_micro_features(return_1m=0.01))
        pred_down = model.predict(_make_micro_features(return_1m=-0.01))

        assert pred_up.yes_probability > 0.7
        assert pred_down.yes_probability < 0.3


# ---------------------------------------------------------------------------
# MicroEnsemble
# ---------------------------------------------------------------------------

class TestMicroEnsemble:
    def test_ensemble_both_trained(self):
        mom = MomentumLookupModel(min_samples=1)
        mom.train([_make_micro_features()] * 5, ["UP"] * 5)

        ensemble = MicroEnsemble(momentum_model=mom)
        pred = ensemble.predict(_make_micro_features())
        assert isinstance(pred, MicroPrediction)
        assert 0.01 <= pred.yes_probability <= 0.99

    def test_ensemble_momentum_only(self):
        mom = MomentumLookupModel(min_samples=1)
        mom.train([_make_micro_features()] * 5, ["UP"] * 5)

        ensemble = MicroEnsemble(momentum_model=mom)
        pred = ensemble.predict(_make_micro_features())
        # LR untrained → confidence 0, so uses momentum only
        assert pred.yes_probability == pytest.approx(0.99, abs=0.01)
        assert pred.confidence > 0

    def test_ensemble_neither_trained(self):
        ensemble = MicroEnsemble()
        pred = ensemble.predict(_make_micro_features())
        assert pred.yes_probability == pytest.approx(0.5, abs=0.01)
        assert pred.confidence > 0.0  # momentum gives 0.1

    def test_ensemble_custom_weights(self):
        mom = MomentumLookupModel(min_samples=1)
        mom.train([_make_micro_features()] * 5, ["UP"] * 5)

        ensemble = MicroEnsemble(momentum_model=mom, momentum_weight=1.0, lr_weight=0.0)
        pred = ensemble.predict(_make_micro_features())
        assert pred.yes_probability == pytest.approx(0.99, abs=0.01)
