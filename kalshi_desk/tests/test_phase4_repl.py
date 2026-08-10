"""Phase 4: Interactive REPL and CLI integration tests.

Tests the REPL command dispatch, formatting helpers, and vessel state
integration without requiring a live data ingestion thread.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestREPLFormatting:
    """Tests for snapshot formatting helpers."""

    def test_format_snapshot_human_with_data(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import _format_snapshot_human
        from kalshi_desk_package.data_contracts.event_data_models import Asset, SourceHealthStatus

        snap = MagicMock()
        snap.asset = Asset.BTC
        snap.snapshot_version = 42
        snap.created_ts = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        snap.spot_avg_usd = 118543.21
        snap.spot_disagreement_pct = 0.0012
        snap.kalshi_midpoint_cents = 55
        snap.source_health = {
            "binance_btc": SourceHealthStatus.HEALTHY,
            "coinbase_btc": SourceHealthStatus.DEGRADED,
        }
        snap.stale_sources = ["coingecko_btc"]
        snap.missing_sources = []

        result = _format_snapshot_human(snap)

        assert "BTC Snapshot v42" in result
        assert "$118,543.21" in result
        assert "0.001200%" in result
        assert "55c" in result
        assert "binance_btc" in result
        assert "ok" in result
        assert "coingecko_btc" in result

    def test_format_snapshot_human_no_data(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import _format_snapshot_human
        from kalshi_desk_package.data_contracts.event_data_models import Asset

        snap = MagicMock()
        snap.asset = Asset.ETH
        snap.snapshot_version = 1
        snap.created_ts = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        snap.spot_avg_usd = None
        snap.spot_disagreement_pct = None
        snap.kalshi_midpoint_cents = None
        snap.source_health = {}
        snap.stale_sources = []
        snap.missing_sources = ["binance_eth", "coinbase_eth"]

        result = _format_snapshot_human(snap)

        assert "ETH Snapshot v1" in result
        assert "(no data)" in result
        assert "Missing: binance_eth, coinbase_eth" in result

    def test_format_snapshot_json(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import _format_snapshot_json
        from kalshi_desk_package.data_contracts.event_data_models import Asset, HotSnapshot

        snap = HotSnapshot(
            asset=Asset.BTC,
            snapshot_version=5,
            created_ts=datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc),
        )
        result = _format_snapshot_json(snap)
        parsed = json.loads(result)

        assert parsed["asset"] == "BTC"
        assert parsed["snapshot_version"] == 5


class TestREPLCommandDispatch:
    """Tests for REPL command routing and vessel integration."""

    @pytest.fixture(autouse=True)
    def _mock_orchestrator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock IngestionOrchestrator so TradingREPL doesn't need real Kalshi creds."""
        mock_orch = MagicMock()
        mock_orch.running = False
        mock_orch.latest_snapshots.return_value = {}
        mock_orch.health_report.return_value = "No active data sources."
        mock_orch.active_markets.return_value = []
        monkeypatch.setattr(
            "kalshi_desk_package.cli.interactive_trading_repl_loop.IngestionOrchestrator",
            lambda **kwargs: mock_orch,
        )

    def test_repl_instantiation(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL(json_output=False)
        assert repl._running is False
        assert repl._tick_count == 0
        assert repl._journal_lines == []

    def test_repl_vessel_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_vessel("status")
        captured = capsys.readouterr()
        assert "full_stop" in captured.out

    def test_repl_vessel_transition(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL
        from kalshi_desk_package.core.vessel_state_machine import VesselState

        repl = TradingREPL()
        repl._cmd_vessel("battery")
        assert repl._machine.current_state == VesselState.BATTERY
        captured = capsys.readouterr()
        assert "Battery" in captured.out

    def test_repl_journal_record(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        # Legacy text journal still works
        repl._cmd_journal("testing edge calculation for BTC")
        assert len(repl._journal_lines) == 1
        assert "testing edge calculation for BTC" in repl._journal_lines[0]

        # Structured journal observe also works
        repl._cmd_journal("observe BTC price above resistance")
        assert len(repl._journal.entries) == 1

        repl._cmd_journal("list")
        captured = capsys.readouterr()
        assert "BTC" in captured.out

    def test_repl_unknown_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._dispatch("foobar", "")
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out

    def test_repl_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_help("")
        captured = capsys.readouterr()
        assert "snapshot" in captured.out
        assert "health" in captured.out
        assert "journal" in captured.out
        assert "exit" in captured.out

    def test_repl_snapshot_no_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_snapshot("")
        captured = capsys.readouterr()
        assert "No snapshot data yet" in captured.out

    def test_repl_markets_no_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_markets("")
        captured = capsys.readouterr()
        assert "No active markets" in captured.out

    def test_repl_predict_requires_orchestrator(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_predict("")
        captured = capsys.readouterr()
        assert "Orchestrator not running" in captured.out


class TestCLIDocking:
    """Tests that the CLI entry point correctly docks with the REPL."""

    def test_forward_start_imports(self) -> None:
        """Verify the forward_start command can import the REPL."""
        from kalshi_desk_package.cli.cli_application_entrypoint_main import forward_start
        assert forward_start is not None
