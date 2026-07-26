"""Phase 7: PAPER Order Lifecycle tests.

Tests risk controls, paper venue adapter, reconciliation, and REPL
trading commands without requiring live Kalshi connections.
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Risk Controls Tests
# ---------------------------------------------------------------------------

class TestRiskControls:
    """Tests for the risk controller."""

    def test_risk_allows_valid_order(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController

        risk = RiskController(wallet_mode="paper")
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is True

    def test_risk_blocks_below_minimum_contracts(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper")
        intent = OrderIntent(asset="BTC", side="yes", contracts=1, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.BELOW_MIN_CONTRACTS

    def test_risk_blocks_wrong_vessel_state(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper")
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_stop")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.VESSEL_NOT_FORWARD

    def test_risk_blocks_battery_state(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper")
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="battery")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.VESSEL_NOT_FORWARD

    def test_risk_blocks_non_paper_mode(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="armed")
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.WALLET_NOT_PAPER

    def test_risk_blocks_insufficient_balance(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper")
        # 2001 contracts at 50c = $1000.50 > $17 balance
        intent = OrderIntent(asset="BTC", side="yes", contracts=2001, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.INSUFFICIENT_BALANCE

    def test_risk_blocks_stale_book(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper")
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward", current_book_age_seconds=600)
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.STALE_BOOK

    def test_risk_blocks_emergency_stop(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper")
        risk.emergency_stop()
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.EMERGENCY_STOP

    def test_risk_allows_after_emergency_reset(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController

        risk = RiskController(wallet_mode="paper")
        risk.emergency_stop()
        risk.reset_emergency_stop()
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is True

    def test_risk_blocks_session_loss_cap(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper", session_loss_cap=10.0)
        risk._session_pnl = -15.0  # Exceed cap
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.SESSION_LOSS_CAP

    def test_risk_blocks_cooldown(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController, RiskBlockReason

        risk = RiskController(wallet_mode="paper", cooldown_seconds=10.0)
        risk._last_trade_time = time.time()  # Just traded
        intent = OrderIntent(asset="BTC", side="yes", contracts=5, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is False
        assert verdict.block_reason == RiskBlockReason.COOLDOWN

    def test_risk_records_fill(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import RiskController

        risk = RiskController(wallet_mode="paper")
        initial_balance = risk._balance

        risk.record_fill("BTC", 25.0)

        assert risk._balance == initial_balance - 25.0
        assert risk._open_position_count["BTC"] == 1
        assert risk._exposure_by_asset["BTC"] == 25.0

    def test_risk_records_settlement(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import RiskController

        risk = RiskController(wallet_mode="paper")
        risk.record_fill("BTC", 25.0)
        initial_balance = risk._balance

        risk.record_settlement("BTC", 5.0, 25.0)

        assert risk._balance == initial_balance + 25.0 + 5.0
        assert risk._session_pnl == 5.0
        assert risk._open_position_count["BTC"] == 0

    def test_risk_status(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import RiskController

        risk = RiskController(wallet_mode="paper")
        status = risk.status()

        assert status["wallet_mode"] == "paper"
        assert status["balance"] == 17.00
        assert status["emergency_stop"] is False

    def test_risk_warnings_for_small_order(self) -> None:
        from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController

        risk = RiskController(wallet_mode="paper")
        intent = OrderIntent(asset="BTC", side="yes", contracts=2, ticker="KXBTC15M-TEST")

        verdict = risk.check(intent, vessel_state="full_forward")
        assert verdict.passed is True
        assert len(verdict.warnings) > 0
        assert "Small order" in verdict.warnings[0]


# ---------------------------------------------------------------------------
# Paper Venue Adapter Tests
# ---------------------------------------------------------------------------

class TestPaperVenueAdapter:
    """Tests for the paper venue adapter."""

    @pytest.fixture(autouse=True)
    def _tmp_adapter(self, tmp_path: Path) -> None:
        from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
        self.adapter = PaperVenueAdapter(db_path=tmp_path / "test_wallet.db")

    def test_initial_balance(self) -> None:
        wallet = self.adapter.get_wallet()
        assert wallet.balance == 17.00
        assert wallet.total_trades == 0

    def test_submit_market_order(self) -> None:
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )

        assert order.status == "filled"
        assert order.fill_price_cents == 55.0
        assert order.fill_cost_usd == 5 * 55.0 / 100.0

    def test_submit_limit_order_filled(self) -> None:
        """Limit order fills at midpoint (better price), not limit."""
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", limit_cents=55, midpoint_cents=50.0,
        )

        assert order.status == "filled"
        assert order.fill_price_cents == 50.0  # Fills at midpoint, not limit

    def test_submit_limit_order_pending(self) -> None:
        """Limit order stays pending when midpoint is worse than limit."""
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", limit_cents=45, midpoint_cents=55.0,
        )

        assert order.status == "pending"

    def test_cancel_order(self) -> None:
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", limit_cents=45, midpoint_cents=55.0,
        )

        cancelled = self.adapter.cancel_order(order.order_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"

    def test_cancel_nonexistent_order(self) -> None:
        result = self.adapter.cancel_order("nonexistent")
        assert result is None

    def test_settle_win(self) -> None:
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )

        settled = self.adapter.settle_order(order.order_id, outcome=1)
        assert settled is not None
        assert settled.pnl > 0
        assert settled.outcome == 1

    def test_settle_loss(self) -> None:
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )

        settled = self.adapter.settle_order(order.order_id, outcome=0)
        assert settled is not None
        assert settled.pnl < 0
        assert settled.outcome == 0

    def test_position_tracking(self) -> None:
        self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )

        positions = self.adapter.get_open_positions()
        assert len(positions) == 1
        assert positions[0].contracts == 5
        assert positions[0].avg_entry_cents == 55.0

    def test_position_averaging(self) -> None:
        """Multiple fills on same ticker+side average into one position."""
        self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )
        self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=65.0,
        )

        positions = self.adapter.get_open_positions()
        assert len(positions) == 1
        assert positions[0].contracts == 10
        assert positions[0].avg_entry_cents == 60.0  # (55+65)/2

    def test_position_removed_on_settle(self) -> None:
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )
        self.adapter.settle_order(order.order_id, outcome=1)

        positions = self.adapter.get_open_positions()
        assert len(positions) == 0

    def test_pending_orders(self) -> None:
        self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", limit_cents=45, midpoint_cents=55.0,
        )

        pending = self.adapter.get_pending_orders()
        assert len(pending) == 1

    def test_wallet_pnl_tracking(self) -> None:
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=5,
            ticker="KXBTC15M-TEST", midpoint_cents=55.0,
        )
        self.adapter.settle_order(order.order_id, outcome=1)

        wallet = self.adapter.get_wallet()
        assert wallet.total_trades == 1
        assert wallet.winning_trades == 1
        assert wallet.total_pnl > 0

    def test_summary(self) -> None:
        summary = self.adapter.summary()
        assert "balance" in summary
        assert "open_positions" in summary
        assert "pending_orders" in summary

    def test_insufficient_balance_cancels(self) -> None:
        """Order is cancelled when balance is insufficient."""
        order = self.adapter.submit_order(
            asset="BTC", side="yes", contracts=2001,
            ticker="KXBTC15M-TEST", midpoint_cents=50.0,
        )

        assert order.status == "cancelled"


# ---------------------------------------------------------------------------
# Reconciliation Tests
# ---------------------------------------------------------------------------

class TestOrderReconciler:
    """Tests for the order reconciler."""

    @pytest.fixture(autouse=True)
    def _tmp_reconciler(self, tmp_path: Path) -> None:
        from arbitr8der_package.reconciliation.order_reconciliation_module import OrderReconciler
        self.reconciler = OrderReconciler(journal_dir=tmp_path / "recon")

    def test_record_intent(self) -> None:
        event = self.reconciler.record_intent(
            order_id="order_001", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )

        assert event.stage == "intent"
        assert event.success is True

    def test_record_risk_check_pass(self) -> None:
        event = self.reconciler.record_risk_check(
            order_id="order_001", passed=True,
        )

        assert event.stage == "risk_check"
        assert event.success is True

    def test_record_risk_check_fail(self) -> None:
        event = self.reconciler.record_risk_check(
            order_id="order_001", passed=False,
            block_reason="below_minimum_contracts",
            block_detail="Minimum order is 2 contracts",
        )

        assert event.stage == "risk_check"
        assert event.success is False

    def test_record_fill(self) -> None:
        event = self.reconciler.record_fill(
            order_id="order_001",
            fill_price_cents=55.0,
            fill_cost_usd=27.5,
        )

        assert event.stage == "fill"
        assert event.data["fill_price_cents"] == 55.0

    def test_record_settlement(self) -> None:
        event = self.reconciler.record_settlement(
            order_id="order_001",
            outcome=1,
            pnl=5.0,
            settlement_price_cents=100.0,
        )

        assert event.stage == "settlement"
        assert event.data["pnl"] == 5.0

    def test_reconcile_clean_order(self) -> None:
        self.reconciler.record_intent(
            order_id="order_001", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )
        self.reconciler.record_risk_check(order_id="order_001", passed=True)
        self.reconciler.record_fill(order_id="order_001", fill_price_cents=55.0, fill_cost_usd=27.5)
        self.reconciler.record_settlement(order_id="order_001", outcome=1, pnl=5.0, settlement_price_cents=100.0)

        report = self.reconciler.reconcile_order("order_001")
        assert len(report.discrepancies) == 0
        assert "intent" in report.stages_completed
        assert "settlement" in report.stages_completed

    def test_reconcile_fill_without_settlement(self) -> None:
        """Fill without settlement is flagged as stuck order."""
        self.reconciler.record_intent(
            order_id="order_002", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )
        self.reconciler.record_risk_check(order_id="order_002", passed=True)
        self.reconciler.record_fill(order_id="order_002", fill_price_cents=55.0, fill_cost_usd=27.5)
        # No settlement

        report = self.reconciler.reconcile_order("order_002")
        assert any("stuck order" in d for d in report.discrepancies)

    def test_reconcile_missing_intent(self) -> None:
        self.reconciler.record_fill(order_id="order_001", fill_price_cents=55.0, fill_cost_usd=27.5)

        report = self.reconciler.reconcile_order("order_001")
        assert len(report.discrepancies) > 0
        assert any("Missing stage: intent" in d for d in report.discrepancies)

    def test_reconcile_settlement_without_fill(self) -> None:
        self.reconciler.record_intent(
            order_id="order_001", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )
        self.reconciler.record_settlement(order_id="order_001", outcome=1, pnl=5.0, settlement_price_cents=100.0)

        report = self.reconciler.reconcile_order("order_001")
        assert any("Settlement recorded without fill" in d for d in report.discrepancies)

    def test_summary(self) -> None:
        self.reconciler.record_intent(
            order_id="order_001", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )
        summary = self.reconciler.summary()

        assert summary["total_events"] == 1
        assert summary["orders_tracked"] == 1

    def test_get_order_events(self) -> None:
        self.reconciler.record_intent(
            order_id="order_001", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )
        self.reconciler.record_fill(order_id="order_001", fill_price_cents=55.0, fill_cost_usd=27.5)

        events = self.reconciler.get_order_events("order_001")
        assert len(events) == 2

    def test_format_human(self) -> None:
        from arbitr8der_package.reconciliation.order_reconciliation_module import format_reconciliation_human

        self.reconciler.record_intent(
            order_id="order_001", asset="BTC", side="yes",
            contracts=5, ticker="KXBTC15M-TEST",
        )
        self.reconciler.record_risk_check(order_id="order_001", passed=True)
        report = self.reconciler.reconcile_order("order_001")
        text = format_reconciliation_human(report)

        assert "order_001" in text
        assert "CLEAN" in text


# ---------------------------------------------------------------------------
# REPL Trading Command Tests
# ---------------------------------------------------------------------------

class TestREPLPhase7Integration:
    """Tests for Phase 7 REPL trading commands."""

    @pytest.fixture(autouse=True)
    def _mock_orchestrator(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        mock_orch = MagicMock()
        mock_orch.running = False
        mock_orch.latest_snapshots.return_value = {}
        mock_orch.health_report.return_value = "No active data sources."
        mock_orch.active_markets.return_value = []
        monkeypatch.setattr(
            "arbitr8der_package.cli.interactive_trading_repl_loop.IngestionOrchestrator",
            lambda **kwargs: mock_orch,
        )
        # Patch PaperVenueAdapter to use temp DB for each test
        from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
        original_init = PaperVenueAdapter.__init__

        def patched_init(self_adapter, db_path=None, **kwargs):
            original_init(self_adapter, db_path=tmp_path / "test_wallet.db", **kwargs)

        monkeypatch.setattr(
            "arbitr8der_package.execution.paper_venue_adapter.PaperVenueAdapter.__init__",
            patched_init,
        )

    def test_repl_has_risk(self) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        assert repl._risk is not None

    def test_repl_has_venue(self) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        assert repl._venue is not None

    def test_repl_has_reconciler(self) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        assert repl._reconciler is not None

    def test_repl_positions_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_positions("")
        captured = capsys.readouterr()
        assert "No open positions" in captured.out

    def test_repl_wallet(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_wallet("")
        captured = capsys.readouterr()
        assert "PAPER Wallet" in captured.out
        assert "$17.00" in captured.out

    def test_repl_risk(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_risk("")
        captured = capsys.readouterr()
        assert "Risk Status" in captured.out
        assert "paper" in captured.out

    def test_repl_pending_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_pending("")
        captured = capsys.readouterr()
        assert "No pending orders" in captured.out

    def test_repl_buy_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_buy("")
        captured = capsys.readouterr()
        assert "Usage: buy" in captured.out

    def test_repl_buy_blocks_wrong_vessel(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_buy("BTC yes 5")
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    def test_repl_buy_valid_in_forward(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL
        from arbitr8der_package.vessel.vessel_state_machine import VesselState

        repl = TradingREPL()
        repl._machine._current_state = VesselState.FULL_FORWARD
        repl._cmd_buy("BTC yes 5")
        captured = capsys.readouterr()
        assert "FILLED" in captured.out

    def test_repl_sell_no_position(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_sell("BTC KXBTC15M-TEST")
        captured = capsys.readouterr()
        assert "No open position" in captured.out

    def test_repl_sell_with_position(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL
        from arbitr8der_package.vessel.vessel_state_machine import VesselState

        repl = TradingREPL()
        repl._machine._current_state = VesselState.FULL_FORWARD

        # Buy first
        repl._cmd_buy("BTC yes 5")
        capsys.readouterr()  # clear

        # Get the ticker from the position
        positions = repl._venue.get_open_positions()
        assert len(positions) == 1
        ticker = positions[0].ticker

        # Sell
        repl._cmd_sell(f"BTC {ticker}")
        captured = capsys.readouterr()
        assert "SETTLED" in captured.out

        # Verify position closed
        positions = repl._venue.get_open_positions()
        assert len(positions) == 0

    def test_repl_help_includes_trading(self, capsys: pytest.CaptureFixture[str]) -> None:
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL

        repl = TradingREPL()
        repl._cmd_help("")
        captured = capsys.readouterr()
        assert "buy" in captured.out
        assert "sell" in captured.out
        assert "positions" in captured.out
        assert "pending" in captured.out
        assert "wallet" in captured.out

    def test_full_trading_cycle(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test buy -> position -> settle -> wallet update cycle."""
        from arbitr8der_package.cli.interactive_trading_repl_loop import TradingREPL
        from arbitr8der_package.vessel.vessel_state_machine import VesselState

        repl = TradingREPL()

        # Switch to forward mode
        repl._machine._current_state = VesselState.FULL_FORWARD

        # Buy
        repl._cmd_buy("BTC yes 5")
        captured = capsys.readouterr()
        assert "FILLED" in captured.out

        # Check positions
        repl._cmd_positions("")
        captured = capsys.readouterr()
        assert "BTC" in captured.out

        # Check wallet - balance should be less than starting
        repl._cmd_wallet("")
        captured = capsys.readouterr()
        assert "Balance:" in captured.out
        assert "Starting:" in captured.out
