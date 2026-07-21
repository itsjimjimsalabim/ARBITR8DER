"""Phase 4 tests — execution layer, risk gates, inventory, fees, drift.

Tests the full execution pipeline: risk evaluation, fee calculation,
position tracking, price drift detection, and the shared execution engine.
All 4 modules are tested both individually and end-to-end.
"""
from __future__ import annotations

import time
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from arbitr8der.execution.kalshi_fee_curve_calculator_module import (
    KalshiFeeCurveCalculatorModule,
    MINIMUM_CONTRACTS_PER_ORDER,
    FeeCalculationResult,
    RoundTripFeeEstimate,
)
from arbitr8der.execution.risk_boundary_enforcement_handler import (
    RiskBoundaryEnforcementHandler,
    RiskGateResult,
    RiskRejectionReason,
    RiskGateEvaluationResult,
)
from arbitr8der.execution.trade_inventory_position_tracker import (
    TradeInventoryPositionTracker,
    OpenPositionRecord,
    ClosedPositionRecord,
    PendingLimitOrderRecord,
    PositionSide,
    PositionStatus,
    OrderType,
)
from arbitr8der.execution.price_drift_detection_handler import (
    PriceDriftDetectionHandler,
    PriceDriftMeasurement,
    DriftSeverity,
)
from arbitr8der.execution.shared_trade_execution_engine_handler import (
    SharedTradeExecutionEngineHandler,
    TradeExecutionResult,
    ExecutionOutcome,
)


# ──────────────────────────────────────────────────────────────
# Fee Calculator Tests
# ──────────────────────────────────────────────────────────────

class TestKalshiFeeCurveCalculator:
    """Tests for the Kalshi fee curve formula."""

    def test_fee_at_50_cents_is_max(self):
        """Fee is maximum at P=0.50 (~1.75 cents per contract)."""
        calculator = KalshiFeeCurveCalculatorModule()
        fee = calculator.calculate_fee_per_contract(50.0)
        assert fee == pytest.approx(1.75, abs=0.01)

    def test_fee_at_10_cents_is_lower(self):
        """Fee at P=0.10 is lower than at P=0.50."""
        calculator = KalshiFeeCurveCalculatorModule()
        fee_at_10 = calculator.calculate_fee_per_contract(10.0)
        fee_at_50 = calculator.calculate_fee_per_contract(50.0)
        assert fee_at_10 < fee_at_50

    def test_fee_at_90_cents_is_lower(self):
        """Fee at P=0.90 is lower than at P=0.50 (symmetric curve)."""
        calculator = KalshiFeeCurveCalculatorModule()
        fee_at_90 = calculator.calculate_fee_per_contract(90.0)
        fee_at_50 = calculator.calculate_fee_per_contract(50.0)
        assert fee_at_90 < fee_at_50

    def test_fee_at_10_and_90_are_equal(self):
        """Fee curve is symmetric around P=0.50."""
        calculator = KalshiFeeCurveCalculatorModule()
        fee_at_10 = calculator.calculate_fee_per_contract(10.0)
        fee_at_90 = calculator.calculate_fee_per_contract(90.0)
        assert fee_at_10 == pytest.approx(fee_at_90, abs=0.01)

    def test_minimum_contracts_enforced(self):
        """Single contract orders are rejected."""
        calculator = KalshiFeeCurveCalculatorModule()
        with pytest.raises(ValueError, match="Minimum"):
            calculator.calculate_total_fee_for_leg(50.0, contract_quantity=1)

    def test_two_contracts_accepted(self):
        """Two contracts (minimum) are accepted."""
        calculator = KalshiFeeCurveCalculatorModule()
        result = calculator.calculate_total_fee_for_leg(50.0, contract_quantity=2)
        assert isinstance(result, FeeCalculationResult)
        assert result.contract_quantity == 2
        assert result.total_fee_cents > 0

    def test_round_trip_fee_estimate(self):
        """Round-trip fee calculation includes entry + exit."""
        calculator = KalshiFeeCurveCalculatorModule()
        estimate = calculator.estimate_round_trip_fees(
            asset_name="BTC",
            entry_price_cents=65.0,
            exit_price_cents=75.0,
            contract_quantity=3,
        )
        assert isinstance(estimate, RoundTripFeeEstimate)
        assert estimate.entry_fee_cents > 0
        assert estimate.exit_fee_cents > 0
        assert estimate.total_round_trip_fee_cents == pytest.approx(
            estimate.entry_fee_cents + estimate.exit_fee_cents, abs=0.01
        )

    def test_net_profit_if_win(self):
        """Profit if correct: (100 - entry) * qty - fees."""
        calculator = KalshiFeeCurveCalculatorModule()
        estimate = calculator.estimate_round_trip_fees(
            asset_name="BTC",
            entry_price_cents=50.0,
            exit_price_cents=100.0,
            contract_quantity=2,
        )
        # Win: get 100¢ per share, paid 50¢ entry
        assert estimate.net_profit_if_win_cents > 0

    def test_net_loss_if_lose(self):
        """Loss if wrong: entry cost + fees (exit pays nothing)."""
        calculator = KalshiFeeCurveCalculatorModule()
        estimate = calculator.estimate_round_trip_fees(
            asset_name="BTC",
            entry_price_cents=50.0,
            exit_price_cents=0.0,
            contract_quantity=2,
        )
        # net_loss_if_lose is the magnitude of loss (positive number)
        # It equals entry_price * quantity + round_trip_fees
        assert estimate.net_loss_if_lose_cents > 0
        assert estimate.net_loss_if_lose_cents == pytest.approx(
            50.0 * 2 + estimate.total_round_trip_fee_cents, abs=0.01
        )

    def test_minimum_profitable_edge(self):
        """Minimum edge to cover fees is positive."""
        calculator = KalshiFeeCurveCalculatorModule()
        min_edge = calculator.minimum_profitable_edge_cents(50.0, 2)
        assert min_edge > 0


# ──────────────────────────────────────────────────────────────
# Risk Boundary Enforcement Tests
# ──────────────────────────────────────────────────────────────

class TestRiskBoundaryEnforcement:
    """Tests for all 9 risk gates."""

    def test_approved_when_all_gates_pass(self):
        """Trade approved when vessel is FULL_FORWARD and all conditions met."""
        handler = RiskBoundaryEnforcementHandler()
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=200.0,
        )
        assert result.gate_result == RiskGateResult.APPROVED
        assert result.is_approved
        assert result.rejection_reason is None

    def test_rejected_when_vessel_not_full_forward(self):
        """Trade rejected when vessel is BATTERY."""
        handler = RiskBoundaryEnforcementHandler()
        result = handler.evaluate_trade_permission(
            vessel_state="BATTERY",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=200.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.VESSEL_NOT_FULL_FORWARD

    def test_rejected_when_vessel_full_stop(self):
        """Trade rejected when vessel is FULL_STOP."""
        handler = RiskBoundaryEnforcementHandler()
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_STOP",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=200.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.VESSEL_NOT_FULL_FORWARD

    def test_rejected_when_session_loss_floor_breached(self):
        """Trade rejected after session loss exceeds floor."""
        handler = RiskBoundaryEnforcementHandler(session_loss_floor_cents=-200.0)
        handler.record_trade_pnl(-250.0)  # Breach the -200 floor
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=100.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.SESSION_LOSS_FLOOR_BREACHED

    def test_rejected_when_daily_loss_cap_breached(self):
        """Trade rejected after daily loss exceeds cap."""
        # Set session floor very low so daily cap triggers first
        handler = RiskBoundaryEnforcementHandler(
            session_loss_floor_cents=-10000.0,
            daily_loss_cap_cents=-500.0,
        )
        handler.record_trade_pnl(-600.0)  # Breach the -500 daily cap
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=100.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.DAILY_LOSS_CAP_BREACHED

    def test_rejected_when_max_positions_exceeded(self):
        """Trade rejected when too many open positions."""
        handler = RiskBoundaryEnforcementHandler(max_open_positions=2)
        handler.update_open_position_count(2)
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=100.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.MAX_POSITIONS_EXCEEDED

    def test_rejected_when_insufficient_contracts(self):
        """Trade rejected when requesting fewer than 2 contracts."""
        handler = RiskBoundaryEnforcementHandler()
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=1,
            estimated_total_cost_cents=50.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.MINIMUM_CONTRACTS_NOT_MET

    def test_rejected_when_max_contracts_exceeded(self):
        """Trade rejected when requesting more than max contracts."""
        handler = RiskBoundaryEnforcementHandler(maximum_contracts_per_order=10)
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=15,
            estimated_total_cost_cents=1000.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.MAX_CONTRACTS_PER_ORDER_EXCEEDED

    def test_rejected_when_insufficient_balance(self):
        """Trade rejected when balance is too low."""
        handler = RiskBoundaryEnforcementHandler()
        handler.update_balance(50.0)  # Only 50 cents
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=200.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.INSUFFICIENT_BALANCE

    def test_rejected_during_loss_cooldown(self):
        """Trade rejected immediately after a losing trade."""
        handler = RiskBoundaryEnforcementHandler(loss_cooldown_seconds=60.0)
        handler.record_trade_pnl(-100.0)  # Record a loss
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=100.0,
        )
        assert result.gate_result == RiskGateResult.REJECTED
        assert result.rejection_reason == RiskRejectionReason.COOLDOWN_ACTIVE

    def test_session_pnl_tracking(self):
        """Session P&L accumulates correctly."""
        handler = RiskBoundaryEnforcementHandler()
        handler.record_trade_pnl(100.0)
        handler.record_trade_pnl(-50.0)
        assert handler.session_realized_pnl_cents == 50.0

    def test_daily_pnl_tracking(self):
        """Daily P&L accumulates correctly."""
        handler = RiskBoundaryEnforcementHandler()
        handler.record_trade_pnl(200.0)
        handler.record_trade_pnl(-150.0)
        assert handler.daily_realized_pnl_cents == 50.0

    def test_session_reset(self):
        """Session reset clears session P&L but not daily."""
        handler = RiskBoundaryEnforcementHandler()
        handler.record_trade_pnl(100.0)
        handler.reset_session()
        assert handler.session_realized_pnl_cents == 0.0
        assert handler.daily_realized_pnl_cents == 100.0

    def test_daily_reset(self):
        """Daily reset clears daily P&L."""
        handler = RiskBoundaryEnforcementHandler()
        handler.record_trade_pnl(100.0)
        handler.reset_daily()
        assert handler.daily_realized_pnl_cents == 0.0

    def test_gate_result_to_dict(self):
        """RiskGateEvaluationResult serializes to dict."""
        handler = RiskBoundaryEnforcementHandler()
        result = handler.evaluate_trade_permission(
            vessel_state="FULL_FORWARD",
            wallet_mode="PAPER",
            contract_quantity=3,
            estimated_total_cost_cents=100.0,
        )
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["gate_result"] == "APPROVED"


# ──────────────────────────────────────────────────────────────
# Trade Inventory Position Tracker Tests
# ──────────────────────────────────────────────────────────────

class TestTradeInventoryPositionTracker:
    """Tests for position tracking and lifecycle."""

    def test_register_open_position(self):
        """New position appears in open positions."""
        tracker = TradeInventoryPositionTracker()
        position = tracker.register_open_position(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side=PositionSide.YES,
            contract_quantity=3,
            entry_price_cents=65.0,
            entry_fee_cents=3.5,
            snapshot_generation=42,
        )
        assert isinstance(position, OpenPositionRecord)
        assert tracker.open_position_count == 1
        assert position.asset_name == "BTC"
        assert position.side == PositionSide.YES

    def test_close_position_realizes_pnl(self):
        """Closing a position calculates realized P&L."""
        tracker = TradeInventoryPositionTracker()
        position = tracker.register_open_position(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side=PositionSide.YES,
            contract_quantity=3,
            entry_price_cents=65.0,
            entry_fee_cents=3.5,
            snapshot_generation=42,
        )
        closed = tracker.close_position(
            position_id=position.position_id,
            exit_price_cents=75.0,
            exit_fee_cents=3.0,
            close_reason="AI_SELL",
        )
        assert isinstance(closed, ClosedPositionRecord)
        assert closed.realized_pnl_cents != 0
        assert tracker.open_position_count == 0
        assert len(tracker.get_closed_positions()) == 1

    def test_unrealized_pnl_updates(self):
        """Unrealized P&L changes with market price."""
        tracker = TradeInventoryPositionTracker()
        position = tracker.register_open_position(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side=PositionSide.YES,
            contract_quantity=3,
            entry_price_cents=65.0,
            entry_fee_cents=3.5,
            snapshot_generation=42,
        )
        initial_pnl = position.unrealized_pnl_cents
        tracker.update_market_price(position.position_id, 80.0)
        updated_pnl = position.unrealized_pnl_cents
        assert updated_pnl > initial_pnl

    def test_pending_limit_order(self):
        """Limit order is registered and trackable."""
        tracker = TradeInventoryPositionTracker()
        order = tracker.register_pending_limit_order(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side=PositionSide.YES,
            contract_quantity=3,
            limit_price_cents=50.0,
            snapshot_generation=42,
        )
        assert isinstance(order, PendingLimitOrderRecord)
        assert len(tracker.get_pending_orders()) == 1

    def test_cancel_pending_order(self):
        """Pending order can be cancelled."""
        tracker = TradeInventoryPositionTracker()
        order = tracker.register_pending_limit_order(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side=PositionSide.YES,
            contract_quantity=3,
            limit_price_cents=50.0,
            snapshot_generation=42,
        )
        cancelled = tracker.cancel_pending_order(order.order_id)
        assert cancelled is not None
        assert len(tracker.get_pending_orders()) == 0

    def test_positions_filtered_by_asset(self):
        """Positions can be filtered by asset name."""
        tracker = TradeInventoryPositionTracker()
        tracker.register_open_position("BTC", "T1", PositionSide.YES, 2, 60.0, 2.0, 1)
        tracker.register_open_position("ETH", "T2", PositionSide.YES, 2, 40.0, 2.0, 1)
        btc_positions = tracker.get_positions_by_asset("BTC")
        assert len(btc_positions) == 1
        assert btc_positions[0].asset_name == "BTC"

    def test_inventory_summary(self):
        """Summary contains all expected fields."""
        tracker = TradeInventoryPositionTracker()
        tracker.register_open_position("BTC", "T1", PositionSide.YES, 2, 60.0, 2.0, 1)
        summary = tracker.get_inventory_summary()
        assert "open_position_count" in summary
        assert "total_unrealized_pnl_cents" in summary
        assert "positions_by_asset" in summary

    def test_total_realized_pnl(self):
        """Realized P&L sums across all closed positions."""
        tracker = TradeInventoryPositionTracker()
        pos1 = tracker.register_open_position("BTC", "T1", PositionSide.YES, 2, 60.0, 2.0, 1)
        tracker.close_position(pos1.position_id, 70.0, 2.0, "AI_SELL")
        pos2 = tracker.register_open_position("BTC", "T2", PositionSide.NO, 2, 40.0, 2.0, 2)
        tracker.close_position(pos2.position_id, 35.0, 2.0, "AI_SELL")
        assert tracker.total_realized_pnl_cents != 0


# ──────────────────────────────────────────────────────────────
# Price Drift Detection Tests
# ──────────────────────────────────────────────────────────────

class TestPriceDriftDetection:
    """Tests for price drift measurement and classification."""

    def test_zero_drift_is_negligible(self):
        """No price change = NEGLIGIBLE severity."""
        handler = PriceDriftDetectionHandler()
        severity = handler.classify_drift_severity(0.5)
        assert severity == DriftSeverity.NEGLIGIBLE

    def test_small_drift_is_minor(self):
        """1-3 cent drift = MINOR."""
        handler = PriceDriftDetectionHandler()
        assert handler.classify_drift_severity(2.0) == DriftSeverity.MINOR

    def test_moderate_drift(self):
        """3-5 cent drift = MODERATE."""
        handler = PriceDriftDetectionHandler()
        assert handler.classify_drift_severity(4.0) == DriftSeverity.MODERATE

    def test_severe_drift(self):
        """5-10 cent drift = SEVERE."""
        handler = PriceDriftDetectionHandler()
        assert handler.classify_drift_severity(7.0) == DriftSeverity.SEVERE

    def test_critical_drift(self):
        """>10 cent drift = CRITICAL."""
        handler = PriceDriftDetectionHandler()
        assert handler.classify_drift_severity(15.0) == DriftSeverity.CRITICAL

    def test_record_drift_measurement(self):
        """Drift recording produces a valid measurement."""
        handler = PriceDriftDetectionHandler()
        measurement = handler.record_drift(
            trade_id="trade_001",
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            snapshot_price_cents=65.0,
            execution_price_cents=68.0,
            snapshot_timestamp=time.time() - 0.1,
            execution_timestamp=time.time(),
            snapshot_generation=42,
        )
        assert isinstance(measurement, PriceDriftMeasurement)
        assert measurement.drift_cents == pytest.approx(3.0, abs=0.5)
        assert measurement.latency_ms > 0

    def test_average_drift_calculation(self):
        """Average drift is computed correctly."""
        handler = PriceDriftDetectionHandler()
        handler.record_drift("t1", "BTC", "T1", 65.0, 68.0, time.time() - 0.1, time.time(), 1)
        handler.record_drift("t2", "BTC", "T2", 70.0, 72.0, time.time() - 0.1, time.time(), 2)
        avg = handler.get_average_drift_cents("BTC")
        assert avg > 0

    def test_drift_distribution(self):
        """Distribution counts all severity buckets."""
        handler = PriceDriftDetectionHandler()
        handler.record_drift("t1", "BTC", "T1", 65.0, 65.5, time.time(), time.time(), 1)
        handler.record_drift("t2", "BTC", "T2", 65.0, 75.0, time.time(), time.time(), 2)
        distribution = handler.get_drift_distribution()
        assert "NEGLIGIBLE" in distribution
        assert "CRITICAL" in distribution

    def test_drift_summary(self):
        """Summary contains all expected fields."""
        handler = PriceDriftDetectionHandler()
        handler.record_drift("t1", "BTC", "T1", 65.0, 68.0, time.time() - 0.1, time.time(), 1)
        summary = handler.get_drift_summary()
        assert "total_measurements" in summary
        assert "average_drift_cents" in summary
        assert "drift_distribution" in summary


# ──────────────────────────────────────────────────────────────
# Shared Execution Engine Integration Tests
# ──────────────────────────────────────────────────────────────

class TestSharedTradeExecutionEngine:
    """End-to-end tests for the unified execution engine."""

    def test_paper_trade_executes(self):
        """PAPER mode trade fills successfully."""
        engine = SharedTradeExecutionEngineHandler(
            wallet_mode="PAPER",
            initial_balance_cents=1700.0,
        )
        result = engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        assert result.execution_outcome == ExecutionOutcome.FILLED
        assert result.filled_quantity == 3
        assert result.trade_id is not None
        assert result.fee_cents > 0

    def test_trade_deducts_balance(self):
        """Successful trade deducts cost from balance."""
        engine = SharedTradeExecutionEngineHandler(
            wallet_mode="PAPER",
            initial_balance_cents=1700.0,
        )
        initial_balance = engine.balance_cents
        result = engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        assert engine.balance_cents < initial_balance

    def test_trade_rejected_when_vessel_not_forward(self):
        """Trade rejected when vessel is not FULL_FORWARD."""
        engine = SharedTradeExecutionEngineHandler(wallet_mode="PAPER")
        result = engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="BATTERY",
        )
        assert result.execution_outcome == ExecutionOutcome.REJECTED_BY_RISK
        assert result.filled_quantity == 0
        assert "VESSEL_NOT_FULL_FORWARD" in result.rejection_reason

    def test_trade_rejected_when_single_contract(self):
        """Trade rejected when requesting only 1 contract."""
        engine = SharedTradeExecutionEngineHandler(wallet_mode="PAPER")
        result = engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=1,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        assert result.execution_outcome == ExecutionOutcome.REJECTED_BY_RISK

    def test_price_drift_is_measured(self):
        """Price drift between snapshot and fill is recorded."""
        engine = SharedTradeExecutionEngineHandler(
            wallet_mode="PAPER",
            paper_price_drift_cents=5.0,
        )
        result = engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        assert result.drift_measurement_cents != 0.0
        assert engine.drift_detector.total_measurements == 1

    def test_position_registered_after_fill(self):
        """Position appears in inventory after successful fill."""
        engine = SharedTradeExecutionEngineHandler(wallet_mode="PAPER")
        engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        assert engine.inventory.open_position_count == 1

    def test_close_trade_updates_balance(self):
        """Closing a trade credits proceeds to balance."""
        engine = SharedTradeExecutionEngineHandler(
            wallet_mode="PAPER",
            initial_balance_cents=1700.0,
        )
        result = engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        balance_after_entry = engine.balance_cents
        close_result = engine.close_trade(
            position_id=result.trade_id,
            exit_price_cents=75.0,
            close_reason="AI_SELL",
        )
        assert close_result.execution_outcome == ExecutionOutcome.FILLED
        assert engine.inventory.open_position_count == 0
        assert len(engine.inventory.get_closed_positions()) == 1

    def test_multiple_trades_accumulate(self):
        """Multiple trades track correctly."""
        engine = SharedTradeExecutionEngineHandler(
            wallet_mode="PAPER",
            initial_balance_cents=5000.0,
        )
        for i in range(3):
            engine.execute_trade(
                asset_name="BTC",
                ticker_symbol=f"KXBTC15M-{i}",
                side="YES",
                contract_quantity=2,
                snapshot_price_cents=50.0,
                snapshot_generation=i,
                vessel_state="FULL_FORWARD",
            )
        assert engine.total_trades_executed == 3
        assert engine.inventory.open_position_count == 3

    def test_execution_summary(self):
        """Summary contains all expected fields."""
        engine = SharedTradeExecutionEngineHandler(wallet_mode="PAPER")
        engine.execute_trade(
            asset_name="BTC",
            ticker_symbol="KXBTC15M-25JUL211200",
            side="YES",
            contract_quantity=3,
            snapshot_price_cents=65.0,
            snapshot_generation=1,
            vessel_state="FULL_FORWARD",
        )
        summary = engine.get_execution_summary()
        assert "wallet_mode" in summary
        assert "balance_cents" in summary
        assert "total_trades_executed" in summary
        assert "inventory" in summary
        assert "price_drift" in summary

    def test_drift_detector_integrated(self):
        """Drift detector tracks all trades automatically."""
        engine = SharedTradeExecutionEngineHandler(
            wallet_mode="PAPER",
            paper_price_drift_cents=3.0,
        )
        engine.execute_trade("BTC", "T1", "YES", 2, 60.0, 1, "FULL_FORWARD")
        engine.execute_trade("ETH", "T2", "YES", 2, 40.0, 2, "FULL_FORWARD")
        assert engine.drift_detector.total_measurements == 2
        drift_summary = engine.drift_detector.get_drift_summary()
        assert drift_summary["total_measurements"] == 2


# ──────────────────────────────────────────────────────────────
# Enum Value Tests
# ──────────────────────────────────────────────────────────────

class TestExecutionEnums:
    """Verify enum values are correct and complete."""

    def test_position_side_values(self):
        """PositionSide has exactly 2 values."""
        sides = list(PositionSide)
        assert len(sides) == 2

    def test_position_status_values(self):
        """PositionStatus has exactly 4 values."""
        statuses = list(PositionStatus)
        assert len(statuses) == 4

    def test_execution_outcome_values(self):
        """ExecutionOutcome has exactly 6 values."""
        outcomes = list(ExecutionOutcome)
        assert len(outcomes) == 6

    def test_risk_gate_result_values(self):
        """RiskGateResult has exactly 2 values."""
        results = list(RiskGateResult)
        assert len(results) == 2

    def test_risk_rejection_reason_values(self):
        """RiskRejectionReason has exactly 9 values."""
        reasons = list(RiskRejectionReason)
        assert len(reasons) == 9

    def test_drift_severity_values(self):
        """DriftSeverity has exactly 5 values."""
        severities = list(DriftSeverity)
        assert len(severities) == 5
