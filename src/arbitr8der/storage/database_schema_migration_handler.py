"""Database schema — table creation and migrations.

Schema v1 tables:
  market_events     — all events (orderbook, spot, sentiment, etc.)
  health_log        — stream health checks
  wallet_snapshots  — balance tracking over time
  sensor_samples    — system metrics (CPU, RAM, disk)
  trade_journal     — every trade: entry, exit, edge, fill, pnl
  session_archive   — per-session JSON dumps after archival
  schema_version    — tracks DB migrations
"""
from __future__ import annotations

import logging

from .sqlite_database_connection_manager import SqliteDatabaseConnectionManager

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    applied_at REAL NOT NULL
);

-- All events flowing through the system
CREATE TABLE IF NOT EXISTS market_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    ticker TEXT,
    payload TEXT NOT NULL,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON market_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ticker ON market_events(ticker);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON market_events(timestamp);

-- Stream health monitoring
CREATE TABLE IF NOT EXISTS health_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    healthy INTEGER NOT NULL,
    details TEXT,
    latency_ms REAL,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_health_source ON health_log(source);

-- Wallet balance snapshots
CREATE TABLE IF NOT EXISTS wallet_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    balance_cents INTEGER NOT NULL,
    positions_open INTEGER DEFAULT 0,
    unrealized_pnl_cents INTEGER DEFAULT 0,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);

-- System sensor samples (lightweight)
CREATE TABLE IF NOT EXISTS sensor_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu_pct REAL,
    ram_pct REAL,
    disk_free_gb REAL,
    internet_latency_ms REAL,
    timestamp REAL NOT NULL,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);

-- Trade journal (the money table)
CREATE TABLE IF NOT EXISTS trade_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,
    ticker TEXT NOT NULL,
    lane TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    entry_edge REAL,
    entry_fair_value REAL,
    entry_timestamp REAL NOT NULL,
    exit_price REAL,
    exit_timestamp REAL,
    exit_reason TEXT,
    pnl_cents INTEGER DEFAULT 0,
    fees_cents INTEGER DEFAULT 0,
    reasoning TEXT,
    snapshot_generation INTEGER,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trade_journal(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_lane ON trade_journal(lane);

-- Session archive (JSON dumps after 72hr)
CREATE TABLE IF NOT EXISTS session_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    vessel_state TEXT,
    trade_count INTEGER DEFAULT 0,
    pnl_cents INTEGER DEFAULT 0,
    archive_json TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
"""


def initialize_database_schema_handler(db: SqliteDatabaseConnectionManager) -> int:
    """Initialize or migrate the database schema.

    Returns the schema version after migration.
    """
    db.connect()

    current = db.get_schema_version()
    if current >= CURRENT_SCHEMA_VERSION:
        logger.info("Schema up to date (v%d)", current)
        return current

    # Apply schema
    with db.transaction() as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION, __import__("time").time()),
        )

    logger.info("Schema initialized: v%d -> v%d", current, CURRENT_SCHEMA_VERSION)
    return CURRENT_SCHEMA_VERSION
