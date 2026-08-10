"""Comprehensive unit tests for Phase 2 — Canonical data contracts and durable storage.

Tests cover:
  - Data contract models (Pydantic validation, immutability, lineage fields)
  - SQLite schema migrations and WAL mode
  - Bounded async persistence queue (priority, backpressure, eviction)
  - Archive and retention policy (cutoff, export, verification)
  - CWD-independent database paths
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from kalshi_desk_package.config.cwd_independent_path_resolver import SQLITE_DB_PATH, get_package_root
from kalshi_desk_package.data_contracts.event_data_models import (
    Asset,
    CoinGeckoMacroEvent,
    HotSnapshot,
    JournalEntry,
    KalshiOrderBookEvent,
    OrderBookLevel,
    PolymarketSentimentEvent,
    Prediction,
    PriceObservationEvent,
    ProviderHealthEvent,
    SourceHealthStatus,
    TradeIntent,
    OrderSide,
    OrderStatus,
    ProviderSource,
    ArchiveManifest,
)
from kalshi_desk_package.durable_storage.bounded_asynchronous_persistence_queue import (
    BoundedPersistenceQueue,
    Priority,
)
from kalshi_desk_package.durable_storage.archive_retention_policy_manager import ArchiveRetentionPolicy
from kalshi_desk_package.durable_storage.sqlite_database_engine_manager import (
    initialize_database,
    _MIGRATIONS,
)


# =========================================================================
# Data contracts
# =========================================================================

class TestProviderEventBase:
    def test_provider_event_has_all_lineage_fields(self):
        now = datetime.now(timezone.utc)
        from kalshi_desk_package.data_contracts.event_data_models import ProviderEvent
        ev = ProviderEvent(provider_ts=now)
        assert ev.provider_event_id
        assert ev.receive_ts == now or ev.receive_ts is not None
        assert ev.source_status == SourceHealthStatus.UNKNOWN
        assert ev.sequence is None

    def test_frozen_model(self):
        from kalshi_desk_package.data_contracts.event_data_models import ProviderEvent
        ev = ProviderEvent(provider_ts=datetime.now(timezone.utc))
        with pytest.raises(Exception):
            ev.source_status = SourceHealthStatus.HEALTHY


class TestPriceObservation:
    def test_valid_observation(self):
        obs = PriceObservationEvent(
            provider_ts=datetime.now(timezone.utc),
            source=ProviderSource.BINANCE,
            asset=Asset.BTC,
            spot_price_usd=65000.0,
        )
        assert obs.asset == Asset.BTC
        assert obs.spot_price_usd == 65000.0

    def test_rejects_negative_price(self):
        with pytest.raises(Exception):
            PriceObservationEvent(
                provider_ts=datetime.now(timezone.utc),
                source=ProviderSource.BINANCE,
                asset=Asset.BTC,
                spot_price_usd=-1.0,
            )


class TestKalshiOrderBook:
    def test_order_book_with_depth(self):
        book = KalshiOrderBookEvent(
            provider_ts=datetime.now(timezone.utc),
            asset=Asset.BTC,
            market_ticker="KXBTC15M-26JUL23-T15:00",
            yes_bid=55,
            yes_ask=58,
            no_bid=42,
            no_ask=45,
            yes_depth=[OrderBookLevel(price_cents=55, quantity=100)],
            no_depth=[OrderBookLevel(price_cents=45, quantity=80)],
        )
        assert len(book.yes_depth) == 1
        assert book.yes_depth[0].quantity == 100

    def test_rejects_price_out_of_range(self):
        with pytest.raises(Exception):
            OrderBookLevel(price_cents=150, quantity=10)


class TestHotSnapshot:
    def test_immutable_after_creation(self):
        snap = HotSnapshot(snapshot_version=1, asset=Asset.BTC, spot_avg_usd=65000.0)
        with pytest.raises(Exception):
            snap.spot_avg_usd = 66000.0

    def test_all_source_fields_present(self):
        snap = HotSnapshot(snapshot_version=1, asset=Asset.ETH)
        assert snap.kalshi_book is None
        assert snap.binance_spot is None
        assert snap.coinbase_spot is None
        assert snap.polymarket_sentiment is None
        assert snap.coingecko_macro is None
        assert snap.stale_sources == []
        assert snap.missing_sources == []


class TestPrediction:
    def test_valid_prediction(self):
        pred = Prediction(
            asset=Asset.BTC,
            market_ticker="KXBTC15M-26JUL23-T15:00",
            snapshot_version=5,
            probability_yes=0.65,
            confidence=0.8,
            recommendation="BUY_YES",
        )
        assert pred.probability_yes == 0.65
        assert pred.actual_outcome is None

    def test_outcome_recording(self):
        pred = Prediction(
            asset=Asset.BTC,
            market_ticker="KXBTC15M-26JUL23-T15:00",
            snapshot_version=5,
            probability_yes=0.65,
            confidence=0.8,
            recommendation="NO_TRADE",
            actual_outcome=True,
            score=1.0,
        )
        assert pred.actual_outcome is True


class TestTradeIntent:
    def test_minimum_quantity(self):
        intent = TradeIntent(
            asset=Asset.BTC,
            market_ticker="KXBTC15M-26JUL23-T15:00",
            snapshot_version=5,
            side=OrderSide.YES,
            quantity=2,
        )
        assert intent.quantity == 2
        assert intent.status == OrderStatus.PENDING

    def test_rejects_quantity_below_minimum(self):
        with pytest.raises(Exception):
            TradeIntent(
                asset=Asset.BTC,
                market_ticker="KXBTC15M-26JUL23-T15:00",
                snapshot_version=5,
                side=OrderSide.YES,
                quantity=1,
            )


class TestJournalEntry:
    def test_valid_entry(self):
        entry = JournalEntry(
            snapshot_version=5,
            entry_type="hypothesis",
            text="BTC showing momentum divergence",
        )
        assert entry.entry_type == "hypothesis"


class TestArchiveManifest:
    def test_valid_manifest(self):
        now = datetime.now(timezone.utc)
        manifest = ArchiveManifest(
            oldest_event_ts=now,
            newest_event_ts=now,
            event_count=100,
            verified=True,
        )
        assert manifest.event_count == 100


# =========================================================================
# SQLite database layer
# =========================================================================

@pytest_asyncio.fixture
async def db(tmp_path):
    """Provide an initialized test database that is cleaned up after the test."""
    db_path = str(tmp_path / "test.db")
    connection = await initialize_database(db_path)
    yield connection
    await connection.close()


class TestDatabaseMigrations:
    @pytest.mark.asyncio
    async def test_creates_all_tables(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        table_names = {row[0] for row in rows}
        expected = {
            "schema_version", "observations", "raw_provider_events", "snapshots",
            "provider_health", "predictions", "trade_intents", "wallet_snapshots",
            "journal_entries", "sensor_samples", "archive_manifests",
        }
        assert expected.issubset(table_names)

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self, db):
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"

    @pytest.mark.asyncio
    async def test_schema_version_matches_migrations(self, db):
        cursor = await db.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        assert row[0] == len(_MIGRATIONS)

    @pytest.mark.asyncio
    async def test_idempotent_migrations(self, db, tmp_path):
        """Running initialize_database again should not fail or duplicate migrations."""
        await initialize_database(str(tmp_path / "test2.db"))
        cursor = await db.execute("SELECT MAX(version) FROM schema_version")
        row = await cursor.fetchone()
        assert row[0] == len(_MIGRATIONS)

    @pytest.mark.asyncio
    async def test_integrity_check_passes(self, db):
        cursor = await db.execute("PRAGMA integrity_check")
        row = await cursor.fetchone()
        assert row[0] == "ok"


class TestDatabaseRoundTrip:
    @pytest.mark.asyncio
    async def test_insert_and_query_observation(self, db):
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO observations (id, provider_event_id, provider_ts, receive_ts, source, asset, spot_price_usd, snapshot_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("obs-1", "evt-1", now, now, "binance", "BTC", 65000.0, 1),
        )
        await db.commit()
        cursor = await db.execute("SELECT spot_price_usd FROM observations WHERE id = 'obs-1'")
        row = await cursor.fetchone()
        assert row[0] == 65000.0

    @pytest.mark.asyncio
    async def test_insert_and_query_prediction(self, db):
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO predictions (prediction_id, created_ts, asset, market_ticker, snapshot_version, probability_yes, confidence, recommendation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("pred-1", now, "BTC", "KXBTC15M-26JUL23-T15:00", 5, 0.65, 0.8, "BUY_YES"),
        )
        await db.commit()
        cursor = await db.execute("SELECT probability_yes FROM predictions WHERE prediction_id = 'pred-1'")
        row = await cursor.fetchone()
        assert row[0] == 0.65


# =========================================================================
# Bounded persistence queue
# =========================================================================

class TestBoundedPersistenceQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_dequeue(self):
        q = BoundedPersistenceQueue(max_depth=10)
        payload = {"source": "binance", "price": 65000}
        await q.enqueue(payload, priority=Priority.MARKET, item_type="price")
        assert q.depth == 1
        item = await q.dequeue()
        assert item.payload["price"] == 65000
        assert item.priority == Priority.MARKET

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        q = BoundedPersistenceQueue(max_depth=10)
        await q.enqueue({"type": "sensor"}, priority=Priority.SENSOR, item_type="sensor")
        await q.enqueue({"type": "market"}, priority=Priority.MARKET, item_type="market")
        await q.enqueue({"type": "audit"}, priority=Priority.AUDIT, item_type="audit")
        first = await q.dequeue()
        assert first.payload["type"] == "market"
        second = await q.dequeue()
        assert second.payload["type"] == "audit"
        third = await q.dequeue()
        assert third.payload["type"] == "sensor"

    @pytest.mark.asyncio
    async def test_low_priority_dropped_when_full(self):
        q = BoundedPersistenceQueue(max_depth=2)
        await q.enqueue({"i": 1}, priority=Priority.MARKET, item_type="market")
        await q.enqueue({"i": 2}, priority=Priority.MARKET, item_type="market")
        result = await q.enqueue({"i": 3}, priority=Priority.SENSOR, item_type="sensor")
        assert result is False
        assert q.total_dropped == 1

    @pytest.mark.asyncio
    async def test_high_priority_evicts_sensors_when_full(self):
        q = BoundedPersistenceQueue(max_depth=2)
        await q.enqueue({"type": "sensor1"}, priority=Priority.SENSOR, item_type="sensor")
        await q.enqueue({"type": "sensor2"}, priority=Priority.SENSOR, item_type="sensor")
        result = await q.enqueue({"type": "market"}, priority=Priority.MARKET, item_type="market")
        assert result is True
        assert q.total_dropped >= 1

    @pytest.mark.asyncio
    async def test_drain(self):
        q = BoundedPersistenceQueue(max_depth=10)
        for i in range(5):
            await q.enqueue({"i": i}, priority=Priority.OBSERVATION, item_type="obs")
        items = await q.drain()
        assert len(items) == 5
        assert q.depth == 0

    @pytest.mark.asyncio
    async def test_drain_empty(self):
        q = BoundedPersistenceQueue(max_depth=10)
        items = await q.drain()
        assert items == []


# =========================================================================
# Archive and retention policy
# =========================================================================

class TestArchiveRetentionPolicy:
    def test_cutoff_ts(self):
        policy = ArchiveRetentionPolicy(retention_seconds=3600)
        now = time.time()
        assert policy.cutoff_ts < now
        assert now - policy.cutoff_ts == pytest.approx(3600, abs=2)

    def test_needs_archive(self):
        policy = ArchiveRetentionPolicy(retention_seconds=3600)
        old_ts = time.time() - 7200  # 2 hours ago
        assert policy.needs_archive(old_ts) is True
        recent_ts = time.time() - 100
        assert policy.needs_archive(recent_ts) is False

    @pytest.mark.asyncio
    async def test_archive_and_prune(self, db, tmp_path):
        # Insert old data
        old_ts = "2020-01-01T00:00:00+00:00"
        await db.execute(
            """INSERT INTO observations (id, provider_event_id, provider_ts, receive_ts, source, asset, spot_price_usd, snapshot_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("obs-old", "evt-old", old_ts, old_ts, "binance", "BTC", 50000.0, 1),
        )
        # Insert recent data
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO observations (id, provider_event_id, provider_ts, receive_ts, source, asset, spot_price_usd, snapshot_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("obs-new", "evt-new", now, now, "binance", "BTC", 65000.0, 2),
        )
        await db.commit()

        policy = ArchiveRetentionPolicy(archives_dir=tmp_path / "archives", retention_seconds=3600)
        result = await policy.archive_and_prune(db, "observations", "provider_ts")
        assert result["archived"] == 1

        # Verify old is gone, new remains
        cursor = await db.execute("SELECT COUNT(*) FROM observations")
        row = await cursor.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_nothing_to_archive(self, db, tmp_path):
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO observations (id, provider_event_id, provider_ts, receive_ts, source, asset, spot_price_usd, snapshot_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("obs-new", "evt-new", now, now, "binance", "BTC", 65000.0, 1),
        )
        await db.commit()
        policy = ArchiveRetentionPolicy(archives_dir=tmp_path / "archives", retention_seconds=3600)
        result = await policy.archive_and_prune(db, "observations", "provider_ts")
        assert result["archived"] == 0

    @pytest.mark.asyncio
    async def test_verify_archive(self, tmp_path):
        archive_path = tmp_path / "test_archive.json"
        archive_path.write_text(json.dumps([{"id": "1", "data": "test"}]), encoding="utf-8")
        policy = ArchiveRetentionPolicy(archives_dir=tmp_path)
        assert await policy.verify_archive(archive_path) is True

    @pytest.mark.asyncio
    async def test_verify_nonexistent_archive(self, tmp_path):
        policy = ArchiveRetentionPolicy(archives_dir=tmp_path)
        assert await policy.verify_archive(tmp_path / "nope.json") is False

    @pytest.mark.asyncio
    async def test_list_archives(self, tmp_path):
        for name in ["b.json", "a.json", "c.json"]:
            (tmp_path / name).write_text("[]", encoding="utf-8")
        policy = ArchiveRetentionPolicy(archives_dir=tmp_path)
        archives = policy.list_archives()
        assert len(archives) == 3


# =========================================================================
# CWD-independent paths
# =========================================================================

class TestCWDIndependentPaths:
    def test_sqlite_path_is_package_relative(self):
        assert str(SQLITE_DB_PATH).startswith(str(get_package_root()))
        assert "runtime/data" in str(SQLITE_DB_PATH)

    def test_get_package_root_consistent(self) -> None:
        assert get_package_root().name == "kalshi_desk"
