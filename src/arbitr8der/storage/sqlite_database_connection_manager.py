"""SQLite connection manager — WAL mode, thread-safe, single connection pool.

Per Theories_of_Operations: "SQLite with WAL and proper checkpointing.
Async reads are nice but synchronous reads are fine too."
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# WAL mode settings for safe concurrent reads
_WAL_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA foreign_keys=ON",
    "PRAGMA cache_size=-64000",  # 64MB page cache
    "PRAGMA temp_store=MEMORY",
]


class SqliteDatabaseConnectionManager:
    """Thread-safe SQLite connection manager with WAL mode.

    Creates the database file and parent directories if they don't exist.
    Applies WAL pragmas on every connection. Provides context-managed
    connections for safe transaction handling.
    """

    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._connection: Optional[sqlite3.Connection] = None
        self._connected: bool = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Open connection and apply WAL pragmas."""
        with self._lock:
            if self._connected:
                return

            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row

            for pragma in _WAL_PRAGMAS:
                self._connection.execute(pragma)

            self._connected = True
            logger.info("Database connected: %s", self._db_path)

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None
                self._connected = False
                logger.info("Database closed")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection with an active transaction.

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT INTO ...")
        """
        if not self._connected:
            raise RuntimeError("Database not connected. Call connect() first.")

        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    @contextmanager
    def read_only(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection for read-only operations (no transaction)."""
        if not self._connected:
            raise RuntimeError("Database not connected. Call connect() first.")
        # Read-only access doesn't need the lock in WAL mode
        yield self._connection

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single statement (auto-commits)."""
        if not self._connected:
            raise RuntimeError("Database not connected. Call connect() first.")
        with self._lock:
            cursor = self._connection.execute(sql, params)
            self._connection.commit()
            return cursor

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute many statements in one transaction."""
        if not self._connected:
            raise RuntimeError("Database not connected. Call connect() first.")
        with self._lock:
            self._connection.executemany(sql, params_list)
            self._connection.commit()

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row."""
        if not self._connected:
            raise RuntimeError("Database not connected. Call connect() first.")
        with self._lock:
            return self._connection.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all matching rows."""
        if not self._connected:
            raise RuntimeError("Database not connected. Call connect() first.")
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        result = self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return result is not None

    def get_schema_version(self) -> int:
        """Get current schema version."""
        if not self.table_exists("schema_version"):
            return 0
        result = self.fetch_one("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1")
        return result["version"] if result else 0
