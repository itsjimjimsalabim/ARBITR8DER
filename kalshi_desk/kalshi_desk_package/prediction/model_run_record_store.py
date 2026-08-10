"""Persistent model run record store — SQLite-backed CRUD for prediction model runs.

Centralizes all model_runs table operations: recording predictions, scoring
them against outcomes, and querying accuracy metrics. Follows the same pattern
as CandlePersistenceStore for candle data.
"""

from __future__ import annotations

import time

import aiosqlite

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


class ModelRunRecordStore:
    """Async SQLite store for model prediction runs and their outcomes."""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def initialize(self) -> None:
        """Ensure the model_runs table schema exists.

        This is a safety net — the table is normally created by the migration
        engine in sqlite_database_engine_manager. This method only creates if
        missing, so the store can be used standalone.
        """
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS model_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                asset TEXT NOT NULL,
                window_open REAL NOT NULL,
                yes_probability REAL NOT NULL,
                confidence REAL NOT NULL,
                features_json TEXT,
                predicted_at REAL NOT NULL,
                outcome_id INTEGER,
                correct INTEGER,
                pnl_cents REAL,
                FOREIGN KEY (outcome_id) REFERENCES outcomes(id)
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_model_runs_lookup ON model_runs(model_name, asset, predicted_at)"
        )
        await self._db.commit()
        logger.debug("ModelRunRecordStore initialized")

    # -------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------

    async def record_prediction(
        self,
        model_name: str,
        asset: str,
        window_open: float,
        yes_probability: float,
        confidence: float,
        features_json: str | None = None,
    ) -> int:
        """Record a model prediction for a future window."""
        now = time.time()
        cursor = await self._db.execute(
            """INSERT INTO model_runs
               (model_name, asset, window_open, yes_probability, confidence,
                features_json, predicted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (model_name, asset, window_open, yes_probability, confidence,
             features_json, now),
        )
        await self._db.commit()
        prediction_id = cursor.lastrowid or 0
        logger.debug("Recorded prediction %d: %s %s prob=%.3f",
                     prediction_id, model_name, asset, yes_probability)
        return prediction_id

    async def score_prediction(
        self,
        prediction_id: int,
        outcome_id: int,
        correct: bool,
        pnl_cents: float,
    ) -> None:
        """Score a prediction against its actual outcome."""
        await self._db.execute(
            """UPDATE model_runs
               SET outcome_id = ?, correct = ?, pnl_cents = ?
               WHERE id = ?""",
            (outcome_id, 1 if correct else 0, pnl_cents, prediction_id),
        )
        await self._db.commit()

    # -------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------

    async def get_pending_predictions(self) -> list[dict]:
        """Get all predictions that have not yet been scored."""
        cursor = await self._db.execute(
            """SELECT id, model_name, asset, window_open,
                      yes_probability, confidence, features_json, predicted_at
               FROM model_runs
               WHERE correct IS NULL
               ORDER BY predicted_at DESC"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "model_name": r[1], "asset": r[2],
                "window_open": r[3], "yes_probability": r[4],
                "confidence": r[5], "features_json": r[6],
                "predicted_at": r[7],
            }
            for r in rows
        ]

    async def get_scored_predictions(
        self, model_name: str | None = None, asset: str | None = None,
    ) -> list[dict]:
        """Get all scored predictions, optionally filtered."""
        query = """SELECT id, model_name, asset, window_open,
                          yes_probability, confidence, predicted_at,
                          outcome_id, correct, pnl_cents
                   FROM model_runs
                   WHERE correct IS NOT NULL"""
        params: list = []
        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)
        if asset:
            query += " AND asset = ?"
            params.append(asset)
        query += " ORDER BY predicted_at DESC"

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "model_name": r[1], "asset": r[2],
                "window_open": r[3], "yes_probability": r[4],
                "confidence": r[5], "predicted_at": r[6],
                "outcome_id": r[7], "correct": r[8], "pnl_cents": r[9],
            }
            for r in rows
        ]

    async def get_model_accuracy(
        self,
        model_name: str,
        asset: str | None = None,
    ) -> dict:
        """Get accuracy stats for a model."""
        if asset:
            cursor = await self._db.execute(
                """SELECT COUNT(*), SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END),
                          SUM(pnl_cents)
                   FROM model_runs
                   WHERE model_name = ? AND asset = ? AND correct IS NOT NULL""",
                (model_name, asset),
            )
        else:
            cursor = await self._db.execute(
                """SELECT COUNT(*), SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END),
                          SUM(pnl_cents)
                   FROM model_runs
                   WHERE model_name = ? AND correct IS NOT NULL""",
                (model_name,),
            )
        row = await cursor.fetchone()
        total = row[0] or 0
        correct = row[1] or 0
        incorrect = row[2] or 0
        pnl = row[3] or 0.0
        return {
            "model_name": model_name,
            "asset": asset or "ALL",
            "total_scored": total,
            "correct": correct,
            "incorrect": incorrect,
            "accuracy_pct": (correct / total * 100) if total > 0 else 0.0,
            "total_pnl_cents": pnl,
        }

    async def count_pending(self) -> int:
        """Count predictions awaiting scoring."""
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM model_runs WHERE correct IS NULL"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def count_total(self, model_name: str | None = None) -> int:
        """Count total predictions, optionally per model."""
        if model_name:
            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM model_runs WHERE model_name = ?",
                (model_name,),
            )
        else:
            cursor = await self._db.execute("SELECT COUNT(*) FROM model_runs")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def list_model_names(self) -> list[str]:
        """Get all unique model names that have recorded predictions."""
        cursor = await self._db.execute(
            "SELECT DISTINCT model_name FROM model_runs"
        )
        return [r[0] for r in await cursor.fetchall()]
