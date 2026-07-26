"""Tests for macro_prediction_model — FrequencyLookup, LightGBM, and Ensemble.

Tests the model training, prediction, and ensemble logic using synthetic
feature vectors. LightGBM tests are conditional on the library being installed.
"""

from __future__ import annotations

import pytest

from arbitr8der_package.prediction.macro_prediction_model import (
    MacroPrediction,
    FrequencyLookupModel,
    LightGBMClassifier,
    MacroEnsemble,
)


# ---------------------------------------------------------------------------
# MacroPrediction dataclass
# ---------------------------------------------------------------------------

class TestMacroPrediction:
    def test_prediction_up(self):
        p = MacroPrediction(asset="BTC", model_name="test", yes_probability=0.7, confidence=0.8)
        assert p.prediction == "UP"

    def test_prediction_down(self):
        p = MacroPrediction(asset="BTC", model_name="test", yes_probability=0.3, confidence=0.8)
        assert p.prediction == "DOWN"

    def test_prediction_boundary(self):
        p = MacroPrediction(asset="BTC", model_name="test", yes_probability=0.5, confidence=0.5)
        assert p.prediction == "DOWN"  # 0.5 is not > 0.5

    def test_to_dict(self):
        p = MacroPrediction(asset="ETH", model_name="m1", yes_probability=0.6, confidence=0.7)
        d = p.to_dict()
        assert d["asset"] == "ETH"
        assert d["model_name"] == "m1"
        assert d["yes_probability"] == 0.6


# ---------------------------------------------------------------------------
# FrequencyLookupModel
# ---------------------------------------------------------------------------

def _make_features(regime="ranging", streak_dir=0, streak_len=0,
                   hour=12, rsi=50, asset="BTC"):
    return {
        "regime": regime,
        "streak_direction": streak_dir,
        "streak_length": streak_len,
        "hour_of_day": hour,
        "rsi_7": rsi,
        "asset": asset,
    }


class TestFrequencyLookupModel:
    def test_train_and_predict(self):
        model = FrequencyLookupModel(min_samples=3)

        # Create training data: all UP in ranging + morning + oversold
        features = [
            _make_features(regime="ranging", streak_dir=1, streak_len=4, hour=8, rsi=25)
            for _ in range(10)
        ]
        outcomes = ["UP"] * 10

        model.train(features, outcomes)
        assert len(model.group_stats) == 1

        pred = model.predict(_make_features(
            regime="ranging", streak_dir=1, streak_len=4, hour=8, rsi=25
        ))
        assert isinstance(pred, MacroPrediction)
        assert pred.yes_probability == 1.0  # all UP
        assert pred.confidence > 0.1

    def test_predict_unknown_group(self):
        model = FrequencyLookupModel(min_samples=3)
        model.train(
            [_make_features(regime="ranging") for _ in range(5)],
            ["UP"] * 5,
        )
        # Different group key
        pred = model.predict(_make_features(regime="trending_up"))
        assert pred.yes_probability == 0.5
        assert pred.confidence == 0.1

    def test_predict_below_min_samples(self):
        model = FrequencyLookupModel(min_samples=10)
        model.train(
            [_make_features(regime="ranging") for _ in range(5)],
            ["UP"] * 5,
        )
        pred = model.predict(_make_features(regime="ranging"))
        assert pred.yes_probability == 0.5  # not enough samples
        assert pred.confidence == 0.1

    def test_group_key_buckets(self):
        model = FrequencyLookupModel()

        key1 = model._group_key(_make_features(streak_dir=1, streak_len=1, hour=2, rsi=25))
        assert "up_short" in key1
        assert "night" in key1
        assert "oversold" in key1

        key2 = model._group_key(_make_features(streak_dir=-1, streak_len=5, hour=14, rsi=75))
        assert "down_long" in key2
        assert "afternoon" in key2
        assert "overbought" in key2

    def test_mixed_outcomes(self):
        model = FrequencyLookupModel(min_samples=3)
        features_up = [_make_features(regime="ranging", hour=12, rsi=50)] * 7
        features_down = [_make_features(regime="trending_up", hour=12, rsi=50)] * 3
        outcomes_up = ["UP"] * 7
        outcomes_down = ["DOWN"] * 3

        model.train(features_up + features_down, outcomes_up + outcomes_down)

        # Ranging group: 7/7 UP
        pred1 = model.predict(_make_features(regime="ranging", hour=12, rsi=50))
        assert pred1.yes_probability == 1.0

        # Trending_up group: 0/3 UP
        pred2 = model.predict(_make_features(regime="trending_up", hour=12, rsi=50))
        assert pred2.yes_probability == 0.0

    def test_empty_train(self):
        model = FrequencyLookupModel()
        model.train([], [])
        pred = model.predict(_make_features())
        assert pred.yes_probability == 0.5
        assert pred.confidence == 0.1


# ---------------------------------------------------------------------------
# LightGBMClassifier
# ---------------------------------------------------------------------------

try:
    import lightgbm as _lgb
    _HAS_LGBM = True
except ImportError:
    _HAS_LGBM = False


@pytest.mark.skipif(not _HAS_LGBM, reason="LightGBM not installed")
class TestLightGBMClassifier:
    def test_train_insufficient_data(self):
        model = LightGBMClassifier()
        result = model.train(
            [_make_features() for _ in range(5)],
            ["UP"] * 5,
        )
        assert result is False

    def test_train_and_predict(self):
        model = LightGBMClassifier()
        # Need 20+ samples
        features = [_make_features(
            regime="ranging" if i % 2 == 0 else "trending_up",
            rsi=30 + i,
        ) for i in range(50)]
        outcomes = ["UP" if i % 3 == 0 else "DOWN" for i in range(50)]

        result = model.train(features, outcomes)
        assert result is True

        pred = model.predict(_make_features(regime="ranging", rsi=40))
        assert isinstance(pred, MacroPrediction)
        assert 0.01 <= pred.yes_probability <= 0.99
        assert 0.1 <= pred.confidence <= 1.0

    def test_predict_untrained(self):
        model = LightGBMClassifier()
        pred = model.predict(_make_features())
        assert pred.yes_probability == 0.5
        assert pred.confidence == 0.0

    def test_feature_importance(self):
        model = LightGBMClassifier()
        features = [_make_features(regime="ranging" if i % 2 == 0 else "trending_up",
                                   rsi=30 + i) for i in range(50)]
        outcomes = ["UP" if i % 3 == 0 else "DOWN" for i in range(50)]
        model.train(features, outcomes)

        importance = model.get_feature_importance()
        assert len(importance) > 0
        # All importance values should be non-negative
        assert all(v >= 0 for v in importance.values())


# ---------------------------------------------------------------------------
# MacroEnsemble
# ---------------------------------------------------------------------------

class TestMacroEnsemble:
    def test_ensemble_both_models(self):
        freq = FrequencyLookupModel(min_samples=1)
        freq.train(
            [_make_features(regime="ranging")] * 5,
            ["UP"] * 5,
        )
        # LightGBM won't be trained, so it'll use fallback
        ensemble = MacroEnsemble(freq_model=freq)
        pred = ensemble.predict(_make_features(regime="ranging"))
        assert isinstance(pred, MacroPrediction)
        assert 0.01 <= pred.yes_probability <= 0.99

    def test_ensemble_freq_only(self):
        freq = FrequencyLookupModel(min_samples=1)
        freq.train(
            [_make_features(regime="ranging")] * 10,
            ["UP"] * 10,
        )
        # lgbm untrained → confidence 0
        ensemble = MacroEnsemble(freq_model=freq)
        pred = ensemble.predict(_make_features(regime="ranging"))
        # Should use freq only since lgbm confidence is 0
        assert pred.yes_probability == pytest.approx(0.99, abs=0.01)
        assert pred.confidence > 0

    def test_ensemble_neither_trained(self):
        ensemble = MacroEnsemble()
        pred = ensemble.predict(_make_features())
        # Both models untrained: freq→0.5/0.1, lgbm→0.5/0.0
        # Only freq has confidence > 0, so combined = freq_only
        assert pred.yes_probability == pytest.approx(0.5, abs=0.01)
        assert pred.confidence > 0.0  # freq contributes some confidence

    def test_ensemble_custom_weights(self):
        freq = FrequencyLookupModel(min_samples=1)
        freq.train(
            [_make_features(regime="ranging")] * 5,
            ["UP"] * 5,
        )
        ensemble = MacroEnsemble(freq_model=freq, freq_weight=1.0, lgbm_weight=0.0)
        pred = ensemble.predict(_make_features(regime="ranging"))
        assert pred.yes_probability == pytest.approx(0.99, abs=0.01)
