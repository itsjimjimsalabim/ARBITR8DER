"""Persistent candle storage — SQLite-backed CRUD for 1m/5m/15m candles.

Handles upserts (INSERT OR REPLACE), range queries, and 1m→15m aggregation.
This module is the foundation for the prediction system's data pipeline.
"""

from __future__ import annotations

import time

import aiosqlite

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Candle row helpers
# ---------------------------------------------------------------------------

def candle_row_to_dict(row: tuple) -> dict:
    """Convert a SQLite row to a dict with named keys."""
    return {
        "id": row[0],
        "asset": row[1],
        "source": row[2],
        "interval": row[3],
        "open_time": row[4],
        "open": row[5],
        "high": row[6],
        "low": row[7],
        "close": row[8],
        "volume": row[9],
        "quote_volume": row[10],
        "trades": row[11],
    }


class CandlePersistenceStore:
    """Async SQLite store for OHLCV candles across assets and sources."""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def initialize(self) -> None:
        """Ensure required tables exist (candles, outcomes).

        Safety net — normally the migration engine in sqlite_database_engine_manager
        creates these. This only creates if missing so the store can work standalone.
        """
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                source TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time REAL NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL,
                trades INTEGER,
                created_at REAL DEFAULT (strftime('%s','now')),
                UNIQUE(asset, source, interval, open_time)
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(asset, source, interval, open_time)"
        )
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                ticker TEXT NOT NULL,
                window_open REAL NOT NULL,
                window_close REAL NOT NULL,
                open_price REAL NOT NULL,
                close_price REAL NOT NULL,
                direction TEXT NOT NULL,
                magnitude_pct REAL,
                created_at REAL DEFAULT (strftime('%s','now')),
                UNIQUE(asset, ticker, window_open)
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcomes_lookup ON outcomes(asset, window_open)"
        )
        await self._db.commit()

    # -------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------

    async def upsert_candle(
        self,
        asset: str,
        source: str,
        interval: str,
        open_time: float,
        open_p: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        quote_volume: float | None = None,
        trades: int | None = None,
    ) -> None:
        """Insert or replace a single candle."""
        await self._db.execute(
            """INSERT OR REPLACE INTO candles
               (asset, source, interval, open_time, open, high, low, close,
                volume, quote_volume, trades)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset, source, interval, open_time, open_p, high, low, close,
             volume, quote_volume, trades),
        )

    async def upsert_candles(self, rows: list[dict]) -> int:
        """Batch upsert candles. Each dict must have:
        asset, source, interval, open_time, open, high, low, close, volume.
        Optional: quote_volume, trades.
        Returns number of rows affected.
        """
        if not rows:
            return 0

        await self._db.executemany(
            """INSERT OR REPLACE INTO candles
               (asset, source, interval, open_time, open, high, low, close,
                volume, quote_volume, trades)
               VALUES (:asset, :source, :interval, :open_time, :open, :high,
                       :low, :close, :volume, :quote_volume, :trades)""",
            rows,
        )
        await self._db.commit()
        logger.debug("Upserted %d candles", len(rows))
        return len(rows)

    # -------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------

    async def get_candles(
        self,
        asset: str,
        source: str,
        interval: str,
        limit: int = 288,
        before_time: float | None = None,
    ) -> list[dict]:
        """Fetch candles ordered by open_time DESC (newest first).

        Args:
            asset: 'BTC' or 'ETH'
            source: 'binance', 'coinbase', etc.
            interval: '1m', '5m', '15m'
            limit: max candles to return
            before_time: if set, only candles with open_time < this value
        """
        if before_time is not None:
            cursor = await self._db.execute(
                """SELECT id, asset, source, interval, open_time,
                          open, high, low, close, volume, quote_volume, trades
                   FROM candles
                   WHERE asset = ? AND source = ? AND interval = ?
                     AND open_time < ?
                   ORDER BY open_time DESC
                   LIMIT ?""",
                (asset, source, interval, before_time, limit),
            )
        else:
            cursor = await self._db.execute(
                """SELECT id, asset, source, interval, open_time,
                          open, high, low, close, volume, quote_volume, trades
                   FROM candles
                   WHERE asset = ? AND source = ? AND interval = ?
                   ORDER BY open_time DESC
                   LIMIT ?""",
                (asset, source, interval, limit),
            )
        rows = await cursor.fetchall()
        return [candle_row_to_dict(r) for r in rows]

    async def get_candles_since(
        self,
        asset: str,
        source: str,
        interval: str,
        since_time: float,
    ) -> list[dict]:
        """Fetch candles with open_time >= since_time, ordered oldest first."""
        cursor = await self._db.execute(
            """SELECT id, asset, source, interval, open_time,
                      open, high, low, close, volume, quote_volume, trades
               FROM candles
               WHERE asset = ? AND source = ? AND interval = ?
                 AND open_time >= ?
               ORDER BY open_time ASC""",
            (asset, source, interval, since_time),
        )
        rows = await cursor.fetchall()
        return [candle_row_to_dict(r) for r in rows]

    async def get_latest_candle_time(
        self,
        asset: str,
        source: str,
        interval: str,
    ) -> float | None:
        """Return the open_time of the most recent candle, or None."""
        cursor = await self._db.execute(
            """SELECT MAX(open_time) FROM candles
               WHERE asset = ? AND source = ? AND interval = ?""",
            (asset, source, interval),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    async def count_candles(
        self,
        asset: str,
        source: str,
        interval: str,
    ) -> int:
        """Count total candles for a given asset/source/interval."""
        cursor = await self._db.execute(
            """SELECT COUNT(*) FROM candles
               WHERE asset = ? AND source = ? AND interval = ?""",
            (asset, source, interval),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_candle_summary(self) -> dict[str, int]:
        """Return {asset:source:interval: count} for all stored candles."""
        cursor = await self._db.execute(
            """SELECT asset, source, interval, COUNT(*)
               FROM candles
               GROUP BY asset, source, interval
               ORDER BY asset, source, interval"""
        )
        rows = await cursor.fetchall()
        return {f"{r[0]}:{r[1]}:{r[2]}": r[3] for r in rows}

    # -------------------------------------------------------------------
    # Outcomes
    # -------------------------------------------------------------------

    async def record_outcome(
        self,
        asset: str,
        ticker: str,
        window_open: float,
        window_close: float,
        open_price: float,
        close_price: float,
        direction: str,
        magnitude_pct: float | None = None,
    ) -> int:
        """Record the actual outcome of a 15-minute market window."""
        cursor = await self._db.execute(
            """INSERT OR IGNORE INTO outcomes
               (asset, ticker, window_open, window_close,
                open_price, close_price, direction, magnitude_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset, ticker, window_open, window_close,
             open_price, close_price, direction, magnitude_pct),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def get_outcomes(
        self,
        asset: str,
        limit: int = 288,
        since_time: float | None = None,
    ) -> list[dict]:
        """Fetch outcomes for an asset, newest first."""
        if since_time is not None:
            cursor = await self._db.execute(
                """SELECT id, asset, ticker, window_open, window_close,
                          open_price, close_price, direction, magnitude_pct
                   FROM outcomes
                   WHERE asset = ? AND window_open >= ?
                   ORDER BY window_open DESC
                   LIMIT ?""",
                (asset, since_time, limit),
            )
        else:
            cursor = await self._db.execute(
                """SELECT id, asset, ticker, window_open, window_close,
                          open_price, close_price, direction, magnitude_pct
                   FROM outcomes
                   WHERE asset = ?
                   ORDER BY window_open DESC
                   LIMIT ?""",
                (asset, limit),
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "asset": r[1], "ticker": r[2],
                "window_open": r[3], "window_close": r[4],
                "open_price": r[5], "close_price": r[6],
                "direction": r[7], "magnitude_pct": r[8],
            }
            for r in rows
        ]

    # -------------------------------------------------------------------
    # Model runs
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
        return cursor.lastrowid or 0

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
