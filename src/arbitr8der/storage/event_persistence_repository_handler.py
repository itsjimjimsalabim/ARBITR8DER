"""Event persistence — store and query events from the market_events table."""
from __future__ import annotations

import json
import logging
from typing import Optional

from ..market_data.immutable_event_envelope_wrapper import EventEnvelope
from .sqlite_database_connection_manager import SqliteDatabaseConnectionManager

logger = logging.getLogger(__name__)


class EventPersistenceRepositoryHandler:
    """Persist and query EventEnvelopes in SQLite."""

    def __init__(self, db: SqliteDatabaseConnectionManager):
        self._db = db

    def insert(self, event: EventEnvelope) -> None:
        """Insert a single event."""
        self._db.execute(
            """INSERT OR IGNORE INTO market_events
               (event_id, source, event_type, ticker, payload, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.source,
                event.event_type.value,
                event.ticker,
                json.dumps(dict(event.payload)),
                event.timestamp,
            ),
        )

    def insert_batch(self, events: list[EventEnvelope]) -> None:
        """Insert multiple events in one transaction."""
        rows = [
            (
                e.event_id,
                e.source,
                e.event_type.value,
                e.ticker,
                json.dumps(dict(e.payload)),
                e.timestamp,
            )
            for e in events
        ]
        self._db.execute_many(
            """INSERT OR IGNORE INTO market_events
               (event_id, source, event_type, ticker, payload, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )

    def count_events(self, event_type: Optional[str] = None) -> int:
        """Count events, optionally filtered by type."""
        if event_type:
            result = self._db.fetch_one(
                "SELECT COUNT(*) as cnt FROM market_events WHERE event_type = ?",
                (event_type,),
            )
        else:
            result = self._db.fetch_one("SELECT COUNT(*) as cnt FROM market_events")
        return result["cnt"] if result else 0

    def query_recent(
        self, event_type: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        """Fetch recent events."""
        if event_type:
            rows = self._db.fetch_all(
                """SELECT * FROM market_events
                   WHERE event_type = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (event_type, limit),
            )
        else:
            rows = self._db.fetch_all(
                "SELECT * FROM market_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]
