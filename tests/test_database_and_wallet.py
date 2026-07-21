"""Tests for database, schema, and wallet profile manager."""
import time
from pathlib import Path

import pytest

from arbitr8der.storage.sqlite_database_connection_manager import SqliteDatabaseConnectionManager
from arbitr8der.storage.database_schema_migration_handler import initialize_database_schema_handler, CURRENT_SCHEMA_VERSION
from arbitr8der.storage.wallet_profile_configuration_manager import (
    resolve_wallet_profile,
    WalletMode,
)


class TestDatabaseManager:
    """Database connection and query tests."""

    def test_connect_creates_db_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        database_connection_manager = SqliteDatabaseConnectionManager(str(db_path))
        database_connection_manager.connect()
        assert db_path.exists()
        assert database_connection_manager.is_connected
        database_connection_manager.close()

    def test_connect_creates_parent_dirs(self, tmp_path):
        db_path = tmp_path / "sub" / "dir" / "test.db"
        database_connection_manager = SqliteDatabaseConnectionManager(str(db_path))
        database_connection_manager.connect()
        assert db_path.exists()
        database_connection_manager.close()

    def test_execute_query(self, tmp_path):
        database_connection_manager = SqliteDatabaseConnectionManager(str(tmp_path / "test.db"))
        database_connection_manager.connect()
        database_connection_manager.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
        database_connection_manager.execute("INSERT INTO test_table VALUES (1, 'hello')")
        result = database_connection_manager.fetch_one("SELECT * FROM test_table WHERE id = 1")
        assert result is not None
        assert result["name"] == "hello"
        database_connection_manager.close()

    def test_execute_many(self, tmp_path):
        database_connection_manager = SqliteDatabaseConnectionManager(str(tmp_path / "test.db"))
        database_connection_manager.connect()
        database_connection_manager.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
        database_connection_manager.execute_many(
            "INSERT INTO test_table VALUES (?, ?)",
            [(1, "a"), (2, "b"), (3, "c")],
        )
        results = database_connection_manager.fetch_all("SELECT * FROM test_table ORDER BY id")
        assert len(results) == 3
        database_connection_manager.close()

    def test_table_exists(self, tmp_path):
        database_connection_manager = SqliteDatabaseConnectionManager(str(tmp_path / "test.db"))
        database_connection_manager.connect()
        assert not database_connection_manager.table_exists("nonexistent")
        database_connection_manager.execute("CREATE TABLE exists_table (id INTEGER)")
        assert database_connection_manager.table_exists("exists_table")
        database_connection_manager.close()

    def test_close_and_reconnect(self, tmp_path):
        db_path = tmp_path / "test.db"
        database_connection_manager = SqliteDatabaseConnectionManager(str(db_path))
        database_connection_manager.connect()
        database_connection_manager.execute("CREATE TABLE t (id INTEGER)")
        database_connection_manager.close()
        assert not database_connection_manager.is_connected

        db2 = SqliteDatabaseConnectionManager(str(db_path))
        db2.connect()
        assert db2.table_exists("t")
        db2.close()


class TestSchemaMigrations:
    """Schema initialization and versioning tests."""

    def test_init_schema_creates_tables(self, tmp_path):
        database_connection_manager = SqliteDatabaseConnectionManager(str(tmp_path / "test.db"))
        version = initialize_database_schema_handler(database_connection_manager)
        assert version == CURRENT_SCHEMA_VERSION

        expected_tables = [
            "market_events",
            "health_log",
            "wallet_snapshots",
            "sensor_samples",
            "trade_journal",
            "session_archive",
            "schema_version",
        ]
        for table in expected_tables:
            assert database_connection_manager.table_exists(table), f"Missing table: {table}"
        database_connection_manager.close()

    def test_init_schema_is_idempotent(self, tmp_path):
        database_connection_manager = SqliteDatabaseConnectionManager(str(tmp_path / "test.db"))
        initialize_database_schema_handler(database_connection_manager)
        version = initialize_database_schema_handler(database_connection_manager)
        assert version == CURRENT_SCHEMA_VERSION
        database_connection_manager.close()


class TestWalletProfileManager:
    """Wallet profile resolution tests."""

    def test_paper_mode(self, tmp_path):
        pem = tmp_path / "test.pem"
        pem.write_text("fake key")
        profile = resolve_wallet_profile(
            requested_mode="PAPER",
            api_key_id="test-key-id",
            private_key_path=str(pem),
        )
        assert profile.mode == WalletMode.PAPER
        assert profile.can_trade
        assert profile.balance_estimate_cents == 1700

    def test_armed_mode_with_valid_credentials(self, tmp_path):
        pem = tmp_path / "test.pem"
        pem.write_text("fake key")
        profile = resolve_wallet_profile(
            requested_mode="ARMED",
            api_key_id="b3728069-1234-5678-9012-abcdef123456",
            private_key_path=str(pem),
        )
        assert profile.mode == WalletMode.ARMED
        assert profile.can_trade

    def test_armed_downgrades_to_paper_without_key(self):
        profile = resolve_wallet_profile(
            requested_mode="ARMED",
            api_key_id="test-key-id",
            private_key_path="/nonexistent/path.pem",
        )
        assert profile.mode == WalletMode.PAPER
        assert profile.can_trade

    def test_armed_downgrades_to_paper_without_api_key(self, tmp_path):
        pem = tmp_path / "test.pem"
        pem.write_text("fake key")
        profile = resolve_wallet_profile(
            requested_mode="ARMED",
            api_key_id="",
            private_key_path=str(pem),
        )
        assert profile.mode == WalletMode.PAPER

    def test_invalid_mode_defaults_to_paper(self):
        profile = resolve_wallet_profile(
            requested_mode="INVALID",
            api_key_id="",
            private_key_path="",
        )
        assert profile.mode == WalletMode.PAPER

    def test_profile_to_dict(self, tmp_path):
        pem = tmp_path / "test.pem"
        pem.write_text("fake key")
        profile = resolve_wallet_profile(
            requested_mode="PAPER",
            api_key_id="test12345",
            private_key_path=str(pem),
        )
        d = profile.to_dict()
        assert d["mode"] == "PAPER"
        assert "balance_estimate_cents" in d
        assert "can_trade" in d
