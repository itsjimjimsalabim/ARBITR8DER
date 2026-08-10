"""SQLite database engine with WAL mode, integrity checks, and migration support.

Provides a singleton engine that all modules share. Runs migrations on first
access and verifies integrity on startup.
"""

import aiosqlite

from kalshi_desk_package.config.cwd_independent_path_resolver import SQLITE_DB_PATH
from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

# All tables in creation order
_MIGRATIONS: list[tuple[int, str]] = [
    (1, """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""),
    (2, """
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    provider_event_id TEXT NOT NULL,
    provider_ts TEXT NOT NULL,
    receive_ts TEXT NOT NULL,
    source TEXT NOT NULL,
    asset TEXT NOT NULL,
    spot_price_usd REAL,
    bid_usd REAL,
    ask_usd REAL,
    volume_24h_usd REAL,
    sequence INTEGER,
    snapshot_version INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_obs_source_ts ON observations(source, provider_ts);
CREATE INDEX IF NOT EXISTS idx_obs_asset_ts ON observations(asset, provider_ts);
"""),
    (3, """
CREATE TABLE IF NOT EXISTS raw_provider_events (
    id TEXT PRIMARY KEY,
    provider_event_id TEXT NOT NULL UNIQUE,
    provider_ts TEXT NOT NULL,
    receive_ts TEXT NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    asset TEXT,
    market_ticker TEXT,
    payload_json TEXT NOT NULL,
    sequence INTEGER,
    snapshot_version INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rpe_source_ts ON raw_provider_events(source, provider_ts);
"""),
    (4, """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_version INTEGER PRIMARY KEY,
    created_ts TEXT NOT NULL,
    asset TEXT NOT NULL,
    kalshi_book_json TEXT,
    binance_spot_json TEXT,
    coinbase_spot_json TEXT,
    polymarket_sentiment_json TEXT,
    coingecko_macro_json TEXT,
    spot_avg_usd REAL,
    spot_disagreement_pct REAL,
    kalshi_midpoint_cents INTEGER,
    time_to_market_close_seconds REAL,
    source_health_json TEXT,
    stale_sources_json TEXT,
    missing_sources_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""),
    (5, """
CREATE TABLE IF NOT EXISTS provider_health (
    id TEXT PRIMARY KEY,
    provider_source TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL,
    error_message TEXT,
    stream_uptime_seconds REAL,
    provider_ts TEXT NOT NULL,
    receive_ts TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ph_source_ts ON provider_health(provider_source, provider_ts);
"""),
    (6, """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    created_ts TEXT NOT NULL,
    asset TEXT NOT NULL,
    market_ticker TEXT NOT NULL,
    snapshot_version INTEGER NOT NULL,
    probability_yes REAL NOT NULL,
    confidence REAL NOT NULL,
    recommendation TEXT NOT NULL,
    features_json TEXT,
    model_version TEXT,
    actual_outcome INTEGER,
    outcome_ts TEXT,
    score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pred_asset ON predictions(asset, created_ts);
"""),
    (7, """
CREATE TABLE IF NOT EXISTS trade_intents (
    intent_id TEXT PRIMARY KEY,
    created_ts TEXT NOT NULL,
    asset TEXT NOT NULL,
    market_ticker TEXT NOT NULL,
    snapshot_version INTEGER NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    limit_price_cents INTEGER,
    prediction_id TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    fill_price_cents INTEGER,
    fill_quantity INTEGER,
    fill_ts TEXT,
    fee_cents INTEGER,
    venue_order_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ti_status ON trade_intents(status);
"""),
    (8, """
CREATE TABLE IF NOT EXISTS wallet_snapshots (
    id TEXT PRIMARY KEY,
    snapshot_ts TEXT NOT NULL,
    balance_cents INTEGER NOT NULL,
    unrealized_pnl_cents INTEGER DEFAULT 0,
    realized_pnl_cents INTEGER DEFAULT 0,
    open_positions_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""),
    (9, """
CREATE TABLE IF NOT EXISTS journal_entries (
    entry_id TEXT PRIMARY KEY,
    created_ts TEXT NOT NULL,
    snapshot_version INTEGER,
    prediction_id TEXT,
    intent_id TEXT,
    entry_type TEXT NOT NULL,
    text TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_je_type ON journal_entries(entry_type, created_ts);
"""),
    (10, """
CREATE TABLE IF NOT EXISTS sensor_samples (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    sample_ts TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ss_source ON sensor_samples(source, sample_ts);
"""),
    (11, """
CREATE TABLE IF NOT EXISTS archive_manifests (
    archive_id TEXT PRIMARY KEY,
    created_ts TEXT NOT NULL,
    oldest_event_ts TEXT NOT NULL,
    newest_event_ts TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    source_files_json TEXT,
    checksum_sha256 TEXT,
    verified INTEGER DEFAULT 0,
    asset TEXT
);
"""),
    (12, """
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
);
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(asset, source, interval, open_time);
"""),
    (13, """
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
);
CREATE INDEX IF NOT EXISTS idx_outcomes_lookup ON outcomes(asset, window_open);
"""),
    (14, """
CREATE TABLE IF NOT EXISTS features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    window_open REAL NOT NULL,
    feature_set TEXT NOT NULL,
    features_json TEXT NOT NULL,
    computed_at REAL NOT NULL,
    UNIQUE(asset, window_open, feature_set)
);
CREATE INDEX IF NOT EXISTS idx_features_lookup ON features(asset, window_open);
"""),
    (15, """
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
);
CREATE INDEX IF NOT EXISTS idx_model_runs_lookup ON model_runs(model_name, asset, predicted_at);
"""),
]


async def initialize_database(db_path: str | None = None) -> aiosqlite.Connection:
    """Open the database, enable WAL, run migrations, verify integrity.

    Returns a connection ready for use.
    """
    path = db_path or str(SQLITE_DB_PATH)
    logger.info("Initializing database: %s", path)

    db = await aiosqlite.connect(path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA foreign_keys=ON")

    # Run migrations
    await _run_migrations(db)

    # Integrity check
    cursor = await db.execute("PRAGMA integrity_check")
    row = await cursor.fetchone()
    if row and row[0] == "ok":
        logger.info("Database integrity check passed")
    else:
        logger.error("Database integrity check FAILED: %s", row)

    return db


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Apply any pending migrations in order."""
    # Ensure schema_version table exists
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.commit()

    # Get current version
    cursor = await db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    row = await cursor.fetchone()
    current_version = row[0] if row else 0

    for target_version, sql in _MIGRATIONS:
        if target_version > current_version:
            logger.info("Applying migration %d", target_version)
            await db.executescript(sql)
            await db.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (target_version,)
            )
            await db.commit()

    logger.info("Database migrations complete (version %d)", len(_MIGRATIONS))


async def get_db(db_path: str | None = None) -> aiosqlite.Connection:
    """Convenience wrapper — returns an initialized connection."""
    return await initialize_database(db_path)
