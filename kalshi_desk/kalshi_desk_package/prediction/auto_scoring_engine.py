"""Auto-scoring engine — matches predictions to outcomes, computes accuracy
metrics, provides a running model performance dashboard, and retrains models
on accumulated outcomes.

Runs continuously or on-demand. Wires predictions recorded in model_runs
table to outcomes in the outcomes table via (asset, window_open) matching.

Key capabilities:
  1. Score pending predictions against newly recorded outcomes
  2. Compute per-model accuracy, Brier score, log loss, PnL
  3. Determine outcomes from 15m candle window boundaries
  4. Continuous scoring loop with configurable interval
  5. Periodic model retraining on accumulated scored data
  6. Model comparison dashboard
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field

import aiosqlite

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger
from kalshi_desk_package.durable_storage.candle_persistence_store import CandlePersistenceStore
from kalshi_desk_package.prediction.backtest_engine import compute_macro_features_from_candles
from kalshi_desk_package.prediction.model_run_record_store import ModelRunRecordStore

logger = get_logger(__name__)

# Scoring interval
_SCORE_LOOP_INTERVAL_S = 30  # check for new outcomes every 30s


@dataclass
class ModelScorecard:
    """Accuracy metrics for a single model."""
    model_name: str
    asset: str
    total_predictions: int = 0
    scored_predictions: int = 0
    correct: int = 0
    incorrect: int = 0
    accuracy_pct: float = 0.0
    total_pnl_cents: float = 0.0
    avg_pnl_cents: float = 0.0
    brier_score: float = 0.0  # lower is better, 0 = perfect
    log_loss: float = 0.0  # lower is better
    avg_confidence: float = 0.0
    avg_yes_probability: float = 0.0

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "asset": self.asset,
            "total_predictions": self.total_predictions,
            "scored_predictions": self.scored_predictions,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "accuracy_pct": round(self.accuracy_pct, 2),
            "total_pnl_cents": round(self.total_pnl_cents, 2),
            "avg_pnl_cents": round(self.avg_pnl_cents, 2),
            "brier_score": round(self.brier_score, 4),
            "log_loss": round(self.log_loss, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "avg_yes_probability": round(self.avg_yes_probability, 4),
        }


@dataclass
class ScoringSummary:
    """Aggregate scoring results across all models."""
    scored_count: int = 0
    total_pending: int = 0
    models: list[ModelScorecard] = field(default_factory=list)
    scored_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "scored_count": self.scored_count,
            "total_pending": self.total_pending,
            "models": [m.to_dict() for m in self.models],
            "scored_at": self.scored_at,
        }


class AutoScoringEngine:
    """Matches predictions to outcomes, computes accuracy, retrains models, runs continuously."""

    def __init__(self, model_run_store: ModelRunRecordStore, candle_store: CandlePersistenceStore | None = None):
        self._model_run_store = model_run_store
        self._candle_store = candle_store
        self._running = asyncio.Event()
        self._task: asyncio.Task | None = None
        # Retrained model instances (populated by retrain_models)
        self._macro_models: dict[str, object] = {}  # asset -> MacroEnsemble
        self._micro_models: dict[str, object] = {}  # asset -> MicroEnsemble
        self._last_retrain_at: float = 0.0
        self._retrain_sample_count: int = 0

    # -------------------------------------------------------------------
    # Score pending predictions
    # -------------------------------------------------------------------

    async def score_pending(self) -> int:
        """Find predictions without outcomes and match them.

        Returns the number of predictions scored in this cycle.
        """
        db = self._model_run_store._db

        # Find unscored predictions that have a matching outcome
        cursor = await db.execute(
            """SELECT mr.id AS prediction_id,
                      mr.model_name, mr.asset, mr.window_open,
                      mr.yes_probability, mr.confidence,
                      o.id AS outcome_id, o.direction,
                      o.open_price, o.close_price
               FROM model_runs mr
               JOIN outcomes o
                 ON mr.asset = o.asset
                AND ABS(mr.window_open - o.window_open) < 1.0
               WHERE mr.correct IS NULL""",
        )
        rows = await cursor.fetchall()

        if not rows:
            return 0

        scored = 0
        for row in rows:
            prediction_id = row[0]
            model_name = row[1]
            yes_prob = row[4]
            outcome_direction = row[7]  # "UP" or "DOWN"

            # Prediction correct if yes_prob > 0.5 and outcome is UP,
            # or yes_prob <= 0.5 and outcome is DOWN
            predicted_yes = yes_prob > 0.5
            actual_yes = outcome_direction == "UP"
            correct = predicted_yes == actual_yes

            # PnL: simplified model
            # If correct: win (yes_prob * 100 cents - cost in cents)
            # If wrong: lose the cost
            # For now use a flat +35/-60 model as placeholder
            pnl_cents = 35.0 if correct else -60.0

            await self._model_run_store.score_prediction(
                prediction_id, row[6], correct=correct, pnl_cents=pnl_cents,
            )
            scored += 1

            logger.debug("Scored prediction %d (%s): %s (pnl=%.0f)",
                         prediction_id, model_name,
                         "CORRECT" if correct else "WRONG", pnl_cents)

        logger.info("Scored %d predictions this cycle", scored)
        return scored

    async def score_pending_model_runs(self) -> int:
        """Alias for score_pending() — called by the orchestrator scoring loop."""
        return await self.score_pending()

    # -------------------------------------------------------------------
    # Live retraining feedback loop
    # -------------------------------------------------------------------

    async def retrain_models(self) -> dict[str, dict]:
        """Fetch scored predictions with stored features, retrain models.

        Queries model_runs that have been scored (correct IS NOT NULL) and
        contain features_json. Recomputes macro features from candle windows
        if features_json is missing. Trains fresh MacroEnsemble and
        MicroEnsemble instances per asset and stores them for use by the
        prediction pipeline.

        Returns a summary dict keyed by asset with training stats.
        """
        from kalshi_desk_package.prediction.macro_prediction_model import MacroEnsemble
        from kalshi_desk_package.prediction.micro_prediction_model import MicroEnsemble

        db = self._model_run_store._db

        # Fetch scored predictions with outcomes
        cursor = await db.execute(
            """SELECT mr.id, mr.model_name, mr.asset, mr.window_open,
                      mr.yes_probability, mr.features_json, mr.correct,
                      o.direction
               FROM model_runs mr
               JOIN outcomes o
                 ON mr.asset = o.asset
                AND ABS(mr.window_open - o.window_open) < 1.0
               WHERE mr.correct IS NOT NULL
               ORDER BY mr.predicted_at ASC"""
        )
        rows = await cursor.fetchall()

        if not rows:
            logger.info("Retrain: no scored predictions with outcomes available")
            return {}

        # Group by asset
        asset_data: dict[str, list[tuple]] = {}
        for row in rows:
            asset = row[2]
            if asset not in asset_data:
                asset_data[asset] = []
            asset_data[asset].append(row)

        results: dict[str, dict] = {}

        for asset, data_rows in asset_data.items():
            feature_vectors: list[dict] = []
            outcomes: list[str] = []

            for row in data_rows:
                prediction_id, model_name, _asset, window_open, yes_prob, features_json, correct, direction = row

                # Determine outcome string from direction column
                outcome_str = "UP" if direction == "UP" else "DOWN"

                # Use stored features if available
                if features_json:
                    try:
                        features = json.loads(features_json)
                        feature_vectors.append(features)
                        outcomes.append(outcome_str)
                        continue
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Fallback: recompute features from candle data
                if self._candle_store is not None and window_open is not None:
                    try:
                        w_open = float(window_open)
                        candles = await self._candle_store.get_candles(
                            asset, "binance", "1m", limit=2000
                        )
                        if candles:
                            # Group into 15m windows
                            boundary_ts = float(int(w_open / 900) * 900)
                            window_candles = [
                                c for c in candles
                                if boundary_ts <= c["open_time"] < boundary_ts + 900
                            ]
                            if len(window_candles) >= 5:
                                # For macro features we need prior candles too
                                prior_candles = [
                                    c for c in candles
                                    if c["open_time"] < boundary_ts
                                ]
                                all_candles = prior_candles[-288:] + window_candles
                                features = compute_macro_features_from_candles(
                                    all_candles, window_ts=boundary_ts,
                                )
                                feature_vectors.append(features)
                                outcomes.append(outcome_str)
                    except Exception as e:
                        w_str = f"{float(window_open):.0f}" if window_open is not None else "unknown"
                        logger.debug("Retrain: could not recompute features for %s window %s: %s",
                                     asset, w_str, e)

            if len(feature_vectors) < 20:
                logger.info("Retrain %s: only %d samples with features (need 20+)",
                            asset, len(feature_vectors))
                results[asset] = {
                    "samples": len(feature_vectors),
                    "trained": False,
                    "reason": "insufficient_samples",
                }
                continue

            # Train macro model (FreqLookup + LightGBM)
            macro = MacroEnsemble()
            macro.freq_model.train(feature_vectors, outcomes)
            macro.lgbm_model.train(feature_vectors, outcomes)
            self._macro_models[asset] = macro

            # Train micro model (MomentumLookup + LogisticRegression)
            micro = MicroEnsemble()
            micro.momentum_model.train(feature_vectors, outcomes)
            micro.lr_model.train(feature_vectors, outcomes)
            self._micro_models[asset] = micro

            self._retrain_sample_count = len(feature_vectors)
            self._last_retrain_at = time.time()

            logger.info(
                "Retrained %s models on %d samples — freq_groups=%d, lgbm_trained=%s",
                asset, len(feature_vectors),
                len(macro.freq_model.group_stats),
                macro.lgbm_model._trained,
            )

            results[asset] = {
                "samples": len(feature_vectors),
                "trained": True,
                "freq_groups": len(macro.freq_model.group_stats),
                "lgbm_trained": macro.lgbm_model._trained,
                "micro_momentum_groups": len(micro.momentum_model.group_stats) if hasattr(micro.momentum_model, 'group_stats') else 0,
                "micro_lr_trained": micro.lr_model._trained if hasattr(micro.lr_model, '_trained') else False,
            }

        return results

    def get_macro_model(self, asset: str) -> object | None:
        """Get the latest retrained MacroEnsemble for an asset, or None."""
        return self._macro_models.get(asset)

    def get_micro_model(self, asset: str) -> object | None:
        """Get the latest retrained MicroEnsemble for an asset, or None."""
        return self._micro_models.get(asset)

    @property
    def last_retrain_at(self) -> float:
        return self._last_retrain_at

    @property
    def retrain_sample_count(self) -> int:
        return self._retrain_sample_count

    # -------------------------------------------------------------------
    # Determine outcomes from candles
    # -------------------------------------------------------------------

    async def determine_outcomes_from_candles(
        self, asset: str, source: str = "binance"
    ) -> int:
        """Look for 15m windows that have no outcome recorded yet,
        determine direction from 1m candles, and record the outcome.

        A 15m window is defined by open_time aligned to 900-second boundaries.
        Returns number of new outcomes recorded.
        """
        db = self._model_run_store._db

        # Get the latest 15m candle timestamps to find candidate windows
        candles = await self._candle_store.get_candles(asset, source, "1m", limit=2000)
        if not candles:
            return 0

        # Group 1m candles into 15m windows
        window_boundaries: dict[float, list[dict]] = {}
        for c in candles:
            # Align to 15m boundary
            boundary = int(c["open_time"] / 900) * 900
            if boundary not in window_boundaries:
                window_boundaries[boundary] = []
            window_boundaries[boundary].append(c)

        # Need complete windows (15 candles per window)
        recorded = 0
        for boundary in sorted(window_boundaries):
            window_candles = sorted(window_boundaries[boundary], key=lambda x: x["open_time"])
            if len(window_candles) < 10:
                continue  # incomplete window

            window_close = boundary + 900
            open_price = window_candles[0]["open"]
            close_price = window_candles[-1]["close"]

            # Skip if open_price == 0
            if open_price == 0:
                continue

            direction = "UP" if close_price > open_price else "DOWN"
            magnitude_pct = abs(close_price - open_price) / open_price * 100

            # Use a synthetic ticker for candle-derived outcomes
            ticker = f"{source.upper()}_{asset}_{int(boundary)}"

            await self._candle_store.record_outcome(
                asset=asset,
                ticker=ticker,
                window_open=float(boundary),
                window_close=float(window_close),
                open_price=open_price,
                close_price=close_price,
                direction=direction,
                magnitude_pct=magnitude_pct,
            )
            recorded += 1

        if recorded > 0:
            logger.info("Recorded %d outcomes from candles for %s", recorded, asset)
        return recorded

    # -------------------------------------------------------------------
    # Model accuracy dashboard
    # -------------------------------------------------------------------

    async def get_model_scorecard(
        self, model_name: str, asset: str | None = None,
    ) -> ModelScorecard:
        """Compute detailed scorecard for a model."""
        db = self._model_run_store._db

        if asset:
            cursor = await db.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END),
                          SUM(pnl_cents),
                          AVG(yes_probability),
                          AVG(confidence)
                   FROM model_runs
                   WHERE model_name = ? AND asset = ? AND correct IS NOT NULL""",
                (model_name, asset),
            )
        else:
            cursor = await db.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END),
                          SUM(pnl_cents),
                          AVG(yes_probability),
                          AVG(confidence)
                   FROM model_runs
                   WHERE model_name = ? AND correct IS NOT NULL""",
                (model_name,),
            )
        row = await cursor.fetchone()
        total = row[0] or 0
        correct = row[1] or 0
        incorrect = row[2] or 0
        pnl = row[3] or 0.0
        avg_prob = row[4] or 0.5
        avg_conf = row[5] or 0.0

        # Brier score: mean squared error of probability vs outcome
        brier = await self._compute_brier_score(model_name, asset)
        log_loss = await self._compute_log_loss(model_name, asset)

        # Total predictions (including unscored)
        total_cursor = await db.execute(
            """SELECT COUNT(*) FROM model_runs
               WHERE model_name = ?""" + (" AND asset = ?" if asset else ""),
            (model_name, asset) if asset else (model_name,),
        )
        total_row = await total_cursor.fetchone()

        return ModelScorecard(
            model_name=model_name,
            asset=asset or "ALL",
            total_predictions=total_row[0] or 0,
            scored_predictions=total,
            correct=correct,
            incorrect=incorrect,
            accuracy_pct=(correct / total * 100) if total > 0 else 0.0,
            total_pnl_cents=pnl,
            avg_pnl_cents=(pnl / total) if total > 0 else 0.0,
            brier_score=brier,
            log_loss=log_loss,
            avg_confidence=avg_conf,
            avg_yes_probability=avg_prob,
        )

    async def get_all_model_scorecards(self) -> ScoringSummary:
        """Get scorecards for all models that have predictions."""
        db = self._model_run_store._db

        # Find all unique model names
        cursor = await db.execute(
            "SELECT DISTINCT model_name FROM model_runs"
        )
        model_names = [r[0] for r in await cursor.fetchall()]

        models = []
        for name in model_names:
            # Per-asset scorecards
            asset_cursor = await db.execute(
                "SELECT DISTINCT asset FROM model_runs WHERE model_name = ?", (name,)
            )
            assets = [r[0] for r in await asset_cursor.fetchall()]

            for asset in assets:
                sc = await self.get_model_scorecard(name, asset)
                if sc.scored_predictions > 0:
                    models.append(sc)

            # Also get ALL aggregate
            sc = await self.get_model_scorecard(name)
            if sc.scored_predictions > 0:
                models.append(sc)

        # Count pending
        pending_cursor = await db.execute(
            "SELECT COUNT(*) FROM model_runs WHERE correct IS NULL"
        )
        pending_row = await pending_cursor.fetchone()

        return ScoringSummary(
            models=models,
            total_pending=pending_row[0] or 0,
        )

    async def _compute_brier_score(
        self, model_name: str, asset: str | None,
    ) -> float:
        """Compute Brier score: mean((predicted_prob - actual_outcome)^2)."""
        db = self._model_run_store._db
        query = """SELECT yes_probability, correct
                   FROM model_runs
                   WHERE model_name = ? AND correct IS NOT NULL"""
        params: tuple = (model_name,)
        if asset:
            query += " AND asset = ?"
            params += (asset,)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        if not rows:
            return 0.0

        total = 0.0
        for prob, correct in rows:
            actual = 1.0 if correct == 1 else 0.0
            total += (prob - actual) ** 2
        return total / len(rows)

    async def _compute_log_loss(
        self, model_name: str, asset: str | None,
    ) -> float:
        """Compute binary log loss."""
        db = self._model_run_store._db
        query = """SELECT yes_probability, correct
                   FROM model_runs
                   WHERE model_name = ? AND correct IS NOT NULL"""
        params: tuple = (model_name,)
        if asset:
            query += " AND asset = ?"
            params += (asset,)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        if not rows:
            return 0.0

        eps = 1e-7
        total = 0.0
        for prob, correct in rows:
            p = max(eps, min(1 - eps, prob))
            if correct == 1:
                total -= math.log(p)
            else:
                total -= math.log(1 - p)
        return total / len(rows)

    # -------------------------------------------------------------------
    # Continuous scoring loop
    # -------------------------------------------------------------------

    async def start(self) -> None:
        """Start the continuous scoring loop."""
        if self._running.is_set():
            logger.warning("Scoring engine already running")
            return

        self._running.set()
        self._task = asyncio.create_task(self._score_loop())
        logger.info("Auto-scoring engine started")

    async def stop(self) -> None:
        """Stop the scoring loop."""
        self._running.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Auto-scoring engine stopped")

    async def _score_loop(self) -> None:
        """Periodically score pending predictions and retrain models."""
        retrain_every_n_cycles = 30  # retrain every ~15 min (30 * 30s)
        cycles_since_retrain = retrain_every_n_cycles

        while self._running.is_set():
            try:
                # Try to match outcomes from candles first
                for asset in ("BTC", "ETH"):
                    await self.determine_outcomes_from_candles(asset)

                # Then score pending predictions
                scored = await self.score_pending()
                if scored > 0:
                    summary = await self.get_all_model_scorecards()
                    for m in summary.models:
                        if m.model_name != "ALL":
                            logger.info(
                                "%s %s: %.1f%% accuracy (%d/%d) pnl=%.0f cents",
                                m.asset, m.model_name, m.accuracy_pct,
                                m.correct, m.scored_predictions, m.total_pnl_cents,
                            )

                # Periodic retraining
                cycles_since_retrain += 1
                if cycles_since_retrain >= retrain_every_n_cycles:
                    try:
                        await self.retrain_models()
                    except Exception as e:
                        logger.error("Retraining error: %s", e)
                    cycles_since_retrain = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scoring cycle error: %s", e)

            await asyncio.sleep(_SCORE_LOOP_INTERVAL_S)
