"""Shared trade execution engine — PAPER and ARMED use the same code path.

Per Theories_of_Operations:
  "PAPER Wallet is theoretical trading, paper trading, fake money, no risk.
   Paper Physics have to be exactly like ARMED physics: latencies have to be
   logged and applied — paper strategies have to be the same once ARMED is run
   so that there is no confusion or surprises."

  "No automated tick loop evaluates or fires trades. The code does not decide.
   It only executes the AI's expressed intent, with latency simulation,
   price-drift checks, fee accounting, and journaling as guardrails.
   The AI is the trader."

This module is the single execution path. Both PAPER and ARMED flow through here.
The only difference: ARMED calls the real Kalshi REST API, PAPER simulates fills
with the same latency model and physics.

Execution flow:
  1. AI issues a command (e.g., "buy BTC YES 3")
  2. Risk gates are checked (RiskBoundaryEnforcementHandler)
  3. Fees are calculated (KalshiFeeCurveCalculatorModule)
  4. Order is placed (real or simulated)
  5. Fill is confirmed (or rejected)
  6. Price drift is measured (PriceDriftDetectionHandler)
  7. Position is tracked (TradeInventoryPositionTracker)
  8. Balance is updated
  9. Everything is logged for audit
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from .kalshi_fee_curve_calculator_module import (
    KalshiFeeCurveCalculatorModule,
    MINIMUM_CONTRACTS_PER_ORDER,
)
from .risk_boundary_enforcement_handler import (
    RiskBoundaryEnforcementHandler,
    RiskGateResult,
)
from .trade_inventory_position_tracker import (
    TradeInventoryPositionTracker,
    PositionSide,
    OpenPositionRecord,
)
from .price_drift_detection_handler import PriceDriftDetectionHandler

logger = logging.getLogger(__name__)


class ExecutionOutcome(str, Enum):
    """What happened when we tried to execute a trade."""

    FILLED = "FILLED"
    REJECTED_BY_RISK = "REJECTED_BY_RISK"
    REJECTED_BY_EXCHANGE = "REJECTED_BY_EXCHANGE"
    REJECTED_NO_BALANCE = "REJECTED_NO_BALANCE"
    PARTIAL_FILL = "PARTIAL_FILL"
    SIMULATED_FILL = "SIMULATED_FILL"


@dataclass(frozen=True)
class TradeExecutionResult:
    """Immutable result of a trade execution attempt."""

    execution_outcome: ExecutionOutcome
    trade_id: Optional[str]
    asset_name: str
    ticker_symbol: str
    side: str
    requested_quantity: int
    filled_quantity: int
    entry_price_cents: float
    execution_price_cents: float
    fee_cents: float
    total_cost_cents: float
    drift_measurement_cents: float
    balance_after_cents: float
    rejection_reason: Optional[str]
    execution_timestamp: float
    latency_ms: float

    def to_dict(self) -> dict:
        return {
            "execution_outcome": self.execution_outcome.value,
            "trade_id": self.trade_id,
            "asset_name": self.asset_name,
            "ticker_symbol": self.ticker_symbol,
            "side": self.side,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "entry_price_cents": self.entry_price_cents,
            "execution_price_cents": self.execution_price_cents,
            "fee_cents": self.fee_cents,
            "total_cost_cents": self.total_cost_cents,
            "drift_measurement_cents": self.drift_measurement_cents,
            "balance_after_cents": self.balance_after_cents,
            "rejection_reason": self.rejection_reason,
            "execution_timestamp": self.execution_timestamp,
            "latency_ms": self.latency_ms,
        }


class SharedTradeExecutionEngineHandler:
    """Unified execution engine for PAPER and ARMED trading.

    The AI calls execute_trade() with its intent. This engine:
      1. Checks risk gates
      2. Calculates fees
      3. Simulates (PAPER) or executes (ARMED) the fill
      4. Measures price drift
      5. Tracks the position
      6. Updates the balance
      7. Returns a detailed result

    For PAPER mode:
      - Fill is simulated with configurable latency
      - Price may drift between snapshot and fill (simulated)
      - Fees are calculated using the real Kalshi fee curve
      - Everything else is identical to ARMED

    For ARMED mode:
      - Real Kalshi REST API is called
      - Real fill price and latency
      - Real fees deducted from real balance
    """

    def __init__(
        self,
        wallet_mode: str = "PAPER",
        initial_balance_cents: float = 1700.0,
        risk_handler: Optional[RiskBoundaryEnforcementHandler] = None,
        inventory_tracker: Optional[TradeInventoryPositionTracker] = None,
        drift_detector: Optional[PriceDriftDetectionHandler] = None,
        fee_calculator: Optional[KalshiFeeCurveCalculatorModule] = None,
        paper_fill_latency_ms: float = 80.0,
        paper_price_drift_cents: float = 1.0,
    ):
        """Initialize the execution engine.

        Args:
            wallet_mode: "PAPER" or "ARMED"
            initial_balance_cents: Starting balance in cents
            risk_handler: Risk gate enforcer (created if None)
            inventory_tracker: Position tracker (created if None)
            drift_detector: Price drift tracker (created if None)
            fee_calculator: Fee calculator (created if None)
            paper_fill_latency_ms: Simulated latency for PAPER fills
            paper_price_drift_cents: Max simulated price drift for PAPER fills
        """
        self._wallet_mode = wallet_mode
        self._balance_cents = initial_balance_cents
        self._risk_handler = risk_handler or RiskBoundaryEnforcementHandler()
        self._inventory_tracker = inventory_tracker or TradeInventoryPositionTracker()
        self._drift_detector = drift_detector or PriceDriftDetectionHandler()
        self._fee_calculator = fee_calculator or KalshiFeeCurveCalculatorModule()

        # PAPER simulation parameters
        self._paper_fill_latency_ms = paper_fill_latency_ms
        self._paper_price_drift_cents = paper_price_drift_cents

        # Execution statistics
        self._total_trades_executed = 0
        self._total_trades_rejected = 0
        self._total_fees_paid_cents = 0.0

    @property
    def balance_cents(self) -> float:
        return self._balance_cents

    @property
    def wallet_mode(self) -> str:
        return self._wallet_mode

    @property
    def total_trades_executed(self) -> int:
        return self._total_trades_executed

    @property
    def total_trades_rejected(self) -> int:
        return self._total_trades_rejected

    @property
    def inventory(self) -> TradeInventoryPositionTracker:
        return self._inventory_tracker

    @property
    def drift_detector(self) -> PriceDriftDetectionHandler:
        return self._drift_detector

    def execute_trade(
        self,
        asset_name: str,
        ticker_symbol: str,
        side: str,
        contract_quantity: int,
        snapshot_price_cents: float,
        snapshot_generation: int,
        vessel_state: str = "FULL_FORWARD",
    ) -> TradeExecutionResult:
        """Execute a trade — the single entry point for all trade intents.

        Both PAPER and ARMED flow through this exact same path.

        Args:
            asset_name: "BTC" or "ETH"
            ticker_symbol: Kalshi ticker (e.g., "KXBTC15M-25JUL211200")
            side: "YES" or "NO"
            contract_quantity: Number of contracts to buy
            snapshot_price_cents: Price the AI saw in its snapshot
            snapshot_generation: HotState generation at decision time
            vessel_state: Current vessel state (must be FULL_FORWARD)

        Returns:
            TradeExecutionResult with full execution details
        """
        execution_start_time = time.time()
        trade_id = f"trade_{int(execution_start_time * 1000)}"

        logger.info(
            "Trade intent: %s %s %s %d contracts @ snapshot %.2f¢ (vessel: %s)",
            asset_name, side, ticker_symbol, contract_quantity,
            snapshot_price_cents, vessel_state,
        )

        # ── Step 1: Calculate fees first (needed for cost estimate) ──
        try:
            fee_result = self._fee_calculator.calculate_total_fee_for_leg(
                price_per_share_cents=snapshot_price_cents,
                contract_quantity=contract_quantity,
            )
            estimated_total_cost = fee_result.total_cost_cents
        except ValueError as fee_error:
            return TradeExecutionResult(
                execution_outcome=ExecutionOutcome.REJECTED_BY_RISK,
                trade_id=None,
                asset_name=asset_name,
                ticker_symbol=ticker_symbol,
                side=side,
                requested_quantity=contract_quantity,
                filled_quantity=0,
                entry_price_cents=snapshot_price_cents,
                execution_price_cents=0.0,
                fee_cents=0.0,
                total_cost_cents=0.0,
                drift_measurement_cents=0.0,
                balance_after_cents=self._balance_cents,
                rejection_reason=str(fee_error),
                execution_timestamp=time.time(),
                latency_ms=0.0,
            )

        # ── Step 2: Risk gate evaluation ──
        risk_result = self._risk_handler.evaluate_trade_permission(
            vessel_state=vessel_state,
            wallet_mode=self._wallet_mode,
            contract_quantity=contract_quantity,
            estimated_total_cost_cents=estimated_total_cost,
        )

        if not risk_result.is_approved:
            self._total_trades_rejected += 1
            return TradeExecutionResult(
                execution_outcome=ExecutionOutcome.REJECTED_BY_RISK,
                trade_id=None,
                asset_name=asset_name,
                ticker_symbol=ticker_symbol,
                side=side,
                requested_quantity=contract_quantity,
                filled_quantity=0,
                entry_price_cents=snapshot_price_cents,
                execution_price_cents=0.0,
                fee_cents=0.0,
                total_cost_cents=0.0,
                drift_measurement_cents=0.0,
                balance_after_cents=self._balance_cents,
                rejection_reason=f"{risk_result.rejection_reason.value}: {risk_result.rejection_detail}",
                execution_timestamp=time.time(),
                latency_ms=0.0,
            )

        # ── Step 3: Execute the fill ──
        if self._wallet_mode == "PAPER":
            execution_price, fill_latency_ms = self._simulate_paper_fill(
                snapshot_price_cents=snapshot_price_cents,
            )
        else:
            # ARMED mode — would call real Kalshi REST API here
            # For now, use same simulation (real API integration is a future phase)
            execution_price, fill_latency_ms = self._simulate_paper_fill(
                snapshot_price_cents=snapshot_price_cents,
            )
            logger.warning("ARMED mode using simulated fill — real API not yet integrated")

        # ── Step 4: Calculate actual fees at execution price ──
        actual_fee_result = self._fee_calculator.calculate_total_fee_for_leg(
            price_per_share_cents=execution_price,
            contract_quantity=contract_quantity,
        )
        actual_total_cost = actual_fee_result.total_cost_cents

        # ── Step 5: Check balance after fill ──
        if actual_total_cost > self._balance_cents:
            self._total_trades_rejected += 1
            return TradeExecutionResult(
                execution_outcome=ExecutionOutcome.REJECTED_NO_BALANCE,
                trade_id=None,
                asset_name=asset_name,
                ticker_symbol=ticker_symbol,
                side=side,
                requested_quantity=contract_quantity,
                filled_quantity=0,
                entry_price_cents=snapshot_price_cents,
                execution_price_cents=execution_price,
                fee_cents=actual_fee_result.total_fee_cents,
                total_cost_cents=actual_total_cost,
                drift_measurement_cents=execution_price - snapshot_price_cents,
                balance_after_cents=self._balance_cents,
                rejection_reason=f"Insufficient balance: need {actual_total_cost:.2f}¢, have {self._balance_cents:.2f}¢",
                execution_timestamp=time.time(),
                latency_ms=fill_latency_ms,
            )

        # ── Step 6: Deduct balance and register position ──
        self._balance_cents -= actual_total_cost
        self._total_fees_paid_cents += actual_fee_result.total_fee_cents

        position_side = PositionSide.YES if side.upper() == "YES" else PositionSide.NO
        position = self._inventory_tracker.register_open_position(
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            side=position_side,
            contract_quantity=contract_quantity,
            entry_price_cents=execution_price,
            entry_fee_cents=actual_fee_result.total_fee_cents,
            snapshot_generation=snapshot_generation,
        )

        # ── Step 7: Measure price drift ──
        drift_measurement = self._drift_detector.record_drift(
            trade_id=position.position_id,
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            snapshot_price_cents=snapshot_price_cents,
            execution_price_cents=execution_price,
            snapshot_timestamp=execution_start_time,
            execution_timestamp=time.time(),
            snapshot_generation=snapshot_generation,
        )

        # ── Step 8: Update risk handler balance ──
        self._risk_handler.update_balance(self._balance_cents)
        self._risk_handler.update_open_position_count(
            self._inventory_tracker.open_position_count
        )

        self._total_trades_executed += 1

        logger.info(
            "Trade executed: %s %s %s %d contracts @ %.2f¢ (drift: %.2f¢, fee: %.2f¢, balance: %.2f¢)",
            position.position_id, asset_name, side, contract_quantity,
            execution_price, drift_measurement.drift_cents,
            actual_fee_result.total_fee_cents, self._balance_cents,
        )

        return TradeExecutionResult(
            execution_outcome=ExecutionOutcome.FILLED,
            trade_id=position.position_id,
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            side=side,
            requested_quantity=contract_quantity,
            filled_quantity=contract_quantity,
            entry_price_cents=snapshot_price_cents,
            execution_price_cents=execution_price,
            fee_cents=actual_fee_result.total_fee_cents,
            total_cost_cents=actual_total_cost,
            drift_measurement_cents=drift_measurement.drift_cents,
            balance_after_cents=self._balance_cents,
            rejection_reason=None,
            execution_timestamp=time.time(),
            latency_ms=fill_latency_ms,
        )

    def close_trade(
        self,
        position_id: str,
        exit_price_cents: float,
        close_reason: str = "AI_SELL",
    ) -> TradeExecutionResult:
        """Close an existing position.

        Args:
            position_id: ID of the position to close
            exit_price_cents: Price at which to sell
            close_reason: Why the position is being closed

        Returns:
            TradeExecutionResult with closing details
        """
        execution_start_time = time.time()

        # Get position info before closing
        open_positions = self._inventory_tracker.get_open_positions()
        target_position = None
        for pos in open_positions:
            if pos.position_id == position_id:
                target_position = pos
                break

        if target_position is None:
            return TradeExecutionResult(
                execution_outcome=ExecutionOutcome.REJECTED_BY_RISK,
                trade_id=position_id,
                asset_name="UNKNOWN",
                ticker_symbol="UNKNOWN",
                side="UNKNOWN",
                requested_quantity=0,
                filled_quantity=0,
                entry_price_cents=0.0,
                execution_price_cents=exit_price_cents,
                fee_cents=0.0,
                total_cost_cents=0.0,
                drift_measurement_cents=0.0,
                balance_after_cents=self._balance_cents,
                rejection_reason=f"No open position with ID: {position_id}",
                execution_timestamp=time.time(),
                latency_ms=0.0,
            )

        # Calculate exit fees
        exit_fee_result = self._fee_calculator.calculate_total_fee_for_leg(
            price_per_share_cents=exit_price_cents,
            contract_quantity=target_position.contract_quantity,
        )

        # Close the position
        closed_record = self._inventory_tracker.close_position(
            position_id=position_id,
            exit_price_cents=exit_price_cents,
            exit_fee_cents=exit_fee_result.total_fee_cents,
            close_reason=close_reason,
        )

        # Credit proceeds to balance
        exit_proceeds = (exit_price_cents * target_position.contract_quantity) - exit_fee_result.total_fee_cents
        self._balance_cents += exit_proceeds
        self._total_fees_paid_cents += exit_fee_result.total_fee_cents

        # Record PnL with risk handler
        self._risk_handler.record_trade_pnl(closed_record.realized_pnl_cents)
        self._risk_handler.update_balance(self._balance_cents)
        self._risk_handler.update_open_position_count(
            self._inventory_tracker.open_position_count
        )

        latency_ms = (time.time() - execution_start_time) * 1000.0

        logger.info(
            "Trade closed: %s P&L: %.2f¢ (exit: %.2f¢, fee: %.2f¢, balance: %.2f¢)",
            position_id, closed_record.realized_pnl_cents,
            exit_price_cents, exit_fee_result.total_fee_cents, self._balance_cents,
        )

        return TradeExecutionResult(
            execution_outcome=ExecutionOutcome.FILLED,
            trade_id=position_id,
            asset_name=target_position.asset_name,
            ticker_symbol=target_position.ticker_symbol,
            side=target_position.side.value,
            requested_quantity=target_position.contract_quantity,
            filled_quantity=target_position.contract_quantity,
            entry_price_cents=target_position.entry_price_cents,
            execution_price_cents=exit_price_cents,
            fee_cents=exit_fee_result.total_fee_cents,
            total_cost_cents=exit_proceeds,
            drift_measurement_cents=0.0,
            balance_after_cents=self._balance_cents,
            rejection_reason=None,
            execution_timestamp=time.time(),
            latency_ms=latency_ms,
        )

    def _simulate_paper_fill(
        self,
        snapshot_price_cents: float,
    ) -> tuple[float, float]:
        """Simulate a paper fill with realistic latency and price drift.

        Returns:
            Tuple of (execution_price_cents, fill_latency_ms)
        """
        import random

        # Simulate latency
        latency_ms = self._paper_fill_latency_ms + random.uniform(-20.0, 20.0)
        latency_ms = max(10.0, latency_ms)

        # Simulate price drift (random walk within threshold)
        drift_cents = random.uniform(
            -self._paper_price_drift_cents,
            self._paper_price_drift_cents,
        )
        execution_price = snapshot_price_cents + drift_cents

        # Clamp to valid range [1.0, 99.0]
        execution_price = max(1.0, min(99.0, execution_price))

        return round(execution_price, 2), round(latency_ms, 2)

    def get_execution_summary(self) -> dict:
        """Get a summary of all execution activity."""
        return {
            "wallet_mode": self._wallet_mode,
            "balance_cents": round(self._balance_cents, 2),
            "total_trades_executed": self._total_trades_executed,
            "total_trades_rejected": self._total_trades_rejected,
            "total_fees_paid_cents": round(self._total_fees_paid_cents, 4),
            "inventory": self._inventory_tracker.get_inventory_summary(),
            "price_drift": self._drift_detector.get_drift_summary(),
        }
