"""Phase 6: AI Operator Workflow and Journals tests.

Tests structured journal, session archive, scorecard, and REPL integration.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class FakePredictionRecord:
    prediction_id: str = "pred_001"
    asset: str = "BTC"
    ticker: str = "KXBTC15M-260723T1230"
    yes_probability: float = 0.65
    confidence: float = 0.72
    edge_pct: float = 3.5
    model_version: str = "baseline_v1"
    rejected: bool = False
    rejection_reason: str | None = None
    actual_outcome: int | None = None
    score_brier: float | None = None
    score_log_loss: float | None = None
    snapshot_version: int = 10
    features: Any = None


# ---------------------------------------------------------------------------
# Structured Journal Tests
# ---------------------------------------------------------------------------

class TestStructuredJournal:
    """Tests for the structured trade journal."""

    @pytest.fixture(autouse=True)
    def _tmp_journal(self, tmp_path: Path) -> None:
        """Create a journal with a temp directory."""
        from kalshi_desk_package.cli.structured_trade_journal_module import TradeJournal
        self.journal = TradeJournal(session_id="test_session_001", journal_dir=tmp_path / "journal")

    def test_start_entry(self) -> None:
        entry = self.journal.start_entry(
            asset="BTC",
            observation="Price above $118k resistance",
            hypothesis="Will break upward in next 15m",
            snapshot_version=42,
        )

        assert entry.asset == "BTC"
        assert entry.observation == "Price above $118k resistance"
        assert entry.hypothesis == "Will break upward in next 15m"
        assert entry.snapshot_version == 42
        assert entry.status == "hypothesis"
        assert len(self.journal.entries) == 1

    def test_link_prediction(self) -> None:
        entry = self.journal.start_entry(
            asset="ETH", observation="test", hypothesis="test",
        )

        record = FakePredictionRecord(asset="ETH", yes_probability=0.7)
        result = self.journal.record_prediction(entry.entry_id, record)

        assert result is not None
        assert result.status == "predicted"
        assert result.yes_probability == 0.7
        assert result.prediction_id == "pred_001"

    def test_resolve_entry(self) -> None:
        entry = self.journal.start_entry(
            asset="BTC", observation="test", hypothesis="test",
        )
        record = FakePredictionRecord()
        self.journal.record_prediction(entry.entry_id, record)

        result = self.journal.resolve_entry(entry.entry_id, actual_outcome=1, score_brier=0.12)

        assert result is not None
        assert result.status == "resolved"
        assert result.actual_outcome == 1
        assert result.score_brier == 0.12

    def test_add_note(self) -> None:
        entry = self.journal.start_entry(
            asset="BTC", observation="test", hypothesis="test",
        )
        result = self.journal.add_note(entry.entry_id, "testing note")

        assert result is not None
        assert len(result.notes) == 1
        assert "testing note" in result.notes[0]

    def test_set_next_experiment(self) -> None:
        entry = self.journal.start_entry(
            asset="BTC", observation="test", hypothesis="test",
        )
        result = self.journal.set_next_experiment(entry.entry_id, "try lower threshold")

        assert result is not None
        assert result.next_experiment == "try lower threshold"

    def test_get_open_entries(self) -> None:
        self.journal.start_entry(asset="BTC", observation="o1", hypothesis="h1")
        self.journal.start_entry(asset="ETH", observation="o2", hypothesis="h2")
        entry3 = self.journal.start_entry(asset="BTC", observation="o3", hypothesis="h3")
        self.journal.resolve_entry(entry3.entry_id, actual_outcome=0)

        open_entries = self.journal.get_open_entries()
        assert len(open_entries) == 2

        open_btc = self.journal.get_open_entries(asset="BTC")
        assert len(open_btc) == 1

    def test_get_resolved_entries(self) -> None:
        entry1 = self.journal.start_entry(asset="BTC", observation="o1", hypothesis="h1")
        entry2 = self.journal.start_entry(asset="ETH", observation="o2", hypothesis="h2")
        self.journal.resolve_entry(entry1.entry_id, actual_outcome=1)

        resolved = self.journal.get_resolved_entries()
        assert len(resolved) == 1
        assert resolved[0].entry_id == entry1.entry_id

    def test_summary(self) -> None:
        entry = self.journal.start_entry(asset="BTC", observation="test", hypothesis="test")
        # Link a prediction so yes_probability is set for accuracy calc
        record = FakePredictionRecord(yes_probability=0.65)
        self.journal.record_prediction(entry.entry_id, record)
        self.journal.resolve_entry(entry.entry_id, actual_outcome=1, score_brier=0.16)

        summary = self.journal.summary()
        assert summary["total_entries"] == 1
        assert summary["resolved_count"] == 1
        assert summary["accuracy_pct"] == 100.0  # 0.65 >= 0.5 matches outcome=1
        assert summary["mean_brier"] is not None

    def test_format_entry_human(self) -> None:
        from kalshi_desk_package.cli.structured_trade_journal_module import format_entry_human

        entry = self.journal.start_entry(
            asset="BTC", observation="price up", hypothesis="continues",
        )
        entry.add_note("first note")

        text = format_entry_human(entry)
        assert "BTC" in text
        assert "price up" in text
        assert "hypothesis" in text
        assert "first note" in text

    def test_format_entry_json(self) -> None:
        from kalshi_desk_package.cli.structured_trade_journal_module import format_entry_json

        entry = self.journal.start_entry(
            asset="BTC", observation="test", hypothesis="test",
        )
        text = format_entry_json(entry)
        parsed = json.loads(text)
        assert parsed["asset"] == "BTC"

    def test_persistence(self, tmp_path: Path) -> None:
        """Verify entries persist to JSONL file."""
        from kalshi_desk_package.cli.structured_trade_journal_module import TradeJournal

        j = TradeJournal(session_id="persist_test", journal_dir=tmp_path / "journal_persist")
        j.start_entry(asset="BTC", observation="test", hypothesis="test")

        journal_file = j._journal_file
        assert journal_file.exists()

        lines = journal_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["asset"] == "BTC"

    def test_nonexistent_entry(self) -> None:
        result = self.journal.record_prediction("nonexistent", FakePredictionRecord())
        assert result is None

        result = self.journal.resolve_entry("nonexistent", actual_outcome=1)
        assert result is None


# ---------------------------------------------------------------------------
# Session Archive Tests
# ---------------------------------------------------------------------------

class TestSessionArchive:
    """Tests for the session archive."""

    @pytest.fixture(autouse=True)
    def _tmp_archive(self, tmp_path: Path) -> None:
        from kalshi_desk_package.cli.session_archive_module import SessionArchive
        self.archive = SessionArchive(session_id="test_archive_001")
        # Override the default directory to use tmp_path
        self.archive._archive_dir = tmp_path / "sessions"
        self.archive._archive_dir.mkdir(parents=True, exist_ok=True)

    def test_record_snapshot(self) -> None:
        snap = MagicMock()
        snap.model_dump.return_value = {"asset": "BTC", "snapshot_version": 5}
        self.archive.record_snapshot(snap)

        assert len(self.archive.snapshots) == 1
        assert len(self.archive.events) == 1
        assert self.archive.events[0]["type"] == "snapshot"

    def test_record_prediction(self) -> None:
        record = FakePredictionRecord()
        self.archive.record_prediction(record)

        assert len(self.archive.predictions) == 1
        assert self.archive.events[0]["type"] == "prediction"

    def test_record_journal_entry(self) -> None:
        entry = MagicMock()
        entry.to_dict.return_value = {"entry_id": "abc", "asset": "BTC"}
        self.archive.record_journal_entry(entry)

        assert len(self.archive.journal_entries) == 1

    def test_record_health(self) -> None:
        self.archive.record_health("All sources healthy")
        assert len(self.archive.health_reports) == 1

    def test_record_vessel_transition(self) -> None:
        self.archive.record_vessel_transition("full_stop", "battery", "operator start")
        assert len(self.archive.vessel_transitions) == 1
        assert self.archive.vessel_transitions[0]["from"] == "full_stop"

    def test_record_command(self) -> None:
        self.archive.record_command("predict", "BTC")
        assert len(self.archive.events) == 1
        assert self.archive.events[0]["cmd"] == "predict"

    def test_close_writes_files(self) -> None:
        self.archive.record_command("snapshot", "")
        self.archive.record_snapshot(MagicMock(model_dump=MagicMock(return_value={"asset": "BTC"})))

        archive_path = self.archive.close()

        assert archive_path.exists()
        assert self.archive.ended_at is not None

        # Summary file
        summary_file = archive_path.parent / f"session_{self.archive.session_id}_summary.json"
        assert summary_file.exists()
        summary = json.loads(summary_file.read_text())
        assert summary["command_count"] == 1
        assert summary["snapshot_count"] == 1

    def test_summary(self) -> None:
        self.archive.record_command("test", "")
        self.archive.record_command("test2", "")

        summary = self.archive.summary()
        assert summary["session_id"] == "test_archive_001"
        assert summary["commands_run"] == 2

    def test_format_archive_summary_human(self) -> None:
        from kalshi_desk_package.cli.session_archive_module import format_archive_summary_human

        self.archive.record_command("test", "")
        summary = self.archive.summary()
        text = format_archive_summary_human(summary)
        assert "test_archive_001" in text
        assert "Commands" in text


# ---------------------------------------------------------------------------
# Scorecard Tests
# ---------------------------------------------------------------------------

class TestScorecard:
    """Tests for the scorecard generator."""

    @pytest.fixture(autouse=True)
    def _tmp_scorecard(self, tmp_path: Path) -> None:
        from kalshi_desk_package.cli.session_archive_module import SessionArchive
        from kalshi_desk_package.cli.structured_trade_journal_module import TradeJournal
        from kalshi_desk_package.prediction.prediction_scorer import PredictionScorer

        self.scorer = PredictionScorer()
        self.journal = TradeJournal(session_id="sc_test", journal_dir=tmp_path / "sc_journal")
        self.archive = SessionArchive(session_id="sc_test")
        self.archive._archive_dir = tmp_path / "sc_sessions"
        self.archive._archive_dir.mkdir(parents=True, exist_ok=True)

    def test_empty_scorecard(self) -> None:
        from kalshi_desk_package.cli.scorecard_module import ScorecardGenerator

        gen = ScorecardGenerator(scorer=self.scorer, journal=self.journal, archive=self.archive)
        card = gen.generate()

        assert card.scoring_report is not None
        assert card.scoring_report.total_predictions == 0
        assert card.journal_total == 0

    def test_scorecard_with_data(self) -> None:
        from kalshi_desk_package.cli.scorecard_module import ScorecardGenerator

        # Add a journal entry with linked prediction
        entry = self.journal.start_entry(asset="BTC", observation="test", hypothesis="test")
        record = FakePredictionRecord(yes_probability=0.65)
        self.journal.record_prediction(entry.entry_id, record)
        self.journal.resolve_entry(entry.entry_id, actual_outcome=1, score_brier=0.16)

        gen = ScorecardGenerator(scorer=self.scorer, journal=self.journal, archive=self.archive)
        card = gen.generate()

        assert card.journal_total == 1
        assert card.journal_resolved == 1
        assert card.journal_accuracy_pct == 100.0

    def test_format_scorecard_human(self) -> None:
        from kalshi_desk_package.cli.scorecard_module import ScorecardGenerator, format_scorecard_human

        gen = ScorecardGenerator(scorer=self.scorer, journal=self.journal, archive=self.archive)
        card = gen.generate()
        text = format_scorecard_human(card)

        assert "SCORECARD" in text
        assert "Prediction Quality" in text
        assert "Coverage" in text
        assert "Journal" in text
        assert "Session" in text

    def test_format_scorecard_json(self) -> None:
        from kalshi_desk_package.cli.scorecard_module import ScorecardGenerator, format_scorecard_json

        gen = ScorecardGenerator(scorer=self.scorer, journal=self.journal, archive=self.archive)
        card = gen.generate()
        text = format_scorecard_json(card)
        parsed = json.loads(text)

        assert "scoring" in parsed
        assert "journal" in parsed
        assert "coverage" in parsed


# ---------------------------------------------------------------------------
# REPL Integration Tests
# ---------------------------------------------------------------------------

class TestREPLPhase6Integration:
    """Tests for Phase 6 REPL commands."""

    @pytest.fixture(autouse=True)
    def _mock_orchestrator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_orch = MagicMock()
        mock_orch.running = False
        mock_orch.latest_snapshots.return_value = {}
        mock_orch.health_report.return_value = "No active data sources."
        mock_orch.active_markets.return_value = []
        monkeypatch.setattr(
            "kalshi_desk_package.cli.interactive_trading_repl_loop.IngestionOrchestrator",
            lambda **kwargs: mock_orch,
        )

    def test_repl_has_journal(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        assert repl._journal is not None
        assert repl._journal.session_id is not None

    def test_repl_has_archive(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        assert repl._archive is not None

    def test_repl_has_scorer(self) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        assert repl._scorer is not None

    def test_repl_scorecard_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_scorecard("")
        captured = capsys.readouterr()
        assert "SCORECARD" in captured.out

    def test_repl_archive_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_archive("")
        captured = capsys.readouterr()
        assert "Session Archive" in captured.out

    def test_repl_journal_observe(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_journal("observe BTC price above resistance")
        captured = capsys.readouterr()
        assert "created for BTC" in captured.out
        assert len(repl._journal.entries) == 1

    def test_repl_journal_note(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_journal("observe BTC test observation")
        repl._cmd_journal("note additional context")
        captured = capsys.readouterr()
        assert "Note added" in captured.out

    def test_repl_journal_list_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_journal("list")
        captured = capsys.readouterr()
        # When no subcommand and no args, shows usage
        assert "No journal entries" in captured.out or "observe" in captured.out

    def test_repl_journal_list_with_entries(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_journal("observe BTC test one")
        repl._cmd_journal("observe ETH test two")
        repl._cmd_journal("list")
        captured = capsys.readouterr()
        assert "BTC" in captured.out
        assert "ETH" in captured.out

    def test_repl_journal_show(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_journal("observe BTC test observation")
        entry_id = repl._journal.entries[0].entry_id
        repl._cmd_journal(f"show {entry_id}")
        captured = capsys.readouterr()
        assert "BTC" in captured.out

    def test_repl_help_includes_new_commands(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_help("")
        captured = capsys.readouterr()
        assert "scorecard" in captured.out
        assert "archive" in captured.out
        assert "journal" in captured.out

    def test_repl_legacy_journal_compat(self, capsys: pytest.CaptureFixture[str]) -> None:
        from kalshi_desk_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_journal("testing legacy text entry")
        captured = capsys.readouterr()
        assert "recorded" in captured.out
        assert len(repl._journal_lines) == 1
