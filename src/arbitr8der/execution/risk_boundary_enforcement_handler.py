"""Risk boundary enforcement — the guardrails that prevent account blowup.

Per Theories_of_Operations: "The AI is the trader. Code only executes expressed intent,
with latency simulation, price-drift checks, fee accounting, and journaling as guardrails."

Risk gates checked BEFORE any trade is placed:
  1. Vessel state must be FULL_FORWARD (permission gate)
  2. Wallet mode must be resolved (PAPER or ARMED)
  3. Session loss floor not breached
  4. Daily loss cap not breached
  5. Maximum open position limit not exceeded
  6. Minimum 2 contracts per order (fee viability)
  7. Sufficient balance for trade cost + fees
  8. No cooldown violation (lane-specific or global)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class RiskGateResult(str, Enum):
    """Did the trade pass all risk gates?"""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskRejectionReason(str, Enum):
    """Why a trade was rejected — for logging and AI feedback."""

    VESSEL_NOT_FULL_FORWARD = "VESSEL_NOT_FULL_FORWARD"
    WALLET_NOT_READY = "WALLET_NOT_READY"
    SESSION_LOSS_FLOOR_BREACHED = "SESSION_LOSS_FLOOR_BREACHED"
    DAILY_LOSS_CAP_BREACHED = "DAILY_LOSS_CAP_BREACHED"
    MAX_POSITIONS_EXCEEDED = "MAX_POSITIONS_EXCEEDED"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    MINIMUM_CONTRACTS_NOT_MET = "MINIMUM_CONTRACTS_NOT_MET"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    MAX_CONTRACTS_PER_ORDER_EXCEEDED = "MAX_CONTRACTS_PER_ORDER_EXCEEDED"


@dataclass(frozen=True)
class RiskGateEvaluationResult:
    """Result of checking all risk gates before a trade."""

    gate_result: RiskGateResult
    rejection_reason: Optional[RiskRejectionReason]
    rejection_detail: Optional[str]
    session_realized_pnl_cents: float
    daily_realized_pnl_cents: float
    current_open_positions: int
    current_balance_cents: float
    evaluation_timestamp: float

    @property
    def is_approved(self) -> bool:
        return self.gate_result == RiskGateResult.APPROVED

    def to_dict(self) -> dict:
        return {
            "gate_result": self.gate_result.value,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "rejection_detail": self.rejection_detail,
            "session_realized_pnl_cents": self.session_realized_pnl_cents,
            "daily_realized_pnl_cents": self.daily_realized_pnl_cents,
            "current_open_positions": self.current_open_positions,
            "current_balance_cents": self.current_balance_cents,
            "evaluation_timestamp": self.evaluation_timestamp,
        }


class RiskBoundaryEnforcementHandler:
    """Enforces all risk boundaries before trade execution.

    Called by SharedTradeExecutionEngineHandler BEFORE placing any order.
    If any gate fails, the trade is rejected with a specific reason
    so the AI knows exactly why it was blocked.

    Default thresholds tuned for $17 starting balance:
      - Session loss floor: -$5.00 (stop trading if down $5 in one session)
      - Daily loss cap: -$10.00 (hard stop for the day)
      - Max open positions: 4 (don't over-concentrate)
      - Max contracts per order: 10 (sizing limit for $17 balance)
      - Cooldown after loss: 60 seconds (pause after a losing trade)
    """

    def __init__(
        self,
        session_loss_floor_cents: float = -500.0,
        daily_loss_cap_cents: float = -1000.0,
        max_open_positions: int = 4,
        minimum_contracts_per_order: int = 2,
        maximum_contracts_per_order: int = 10,
        loss_cooldown_seconds: float = 60.0,
    ):
        self._session_loss_floor_cents = session_loss_floor_cents
        self._daily_loss_cap_cents = daily_loss_cap_cents
        self._max_open_positions = max_open_positions
        self._minimum_contracts_per_order = minimum_contracts_per_order
        self._maximum_contracts_per_order = maximum_contracts_per_order
        self._loss_cooldown_seconds = loss_cooldown_seconds

        # Running state
        self._session_realized_pnl_cents: float = 0.0
        self._daily_realized_pnl_cents: float = 0.0
        self._open_position_count: int = 0
        self._last_loss_timestamp: float = 0.0
        self._session_start_timestamp: float = time.time()
        self._current_balance_cents: float = 1700.0

    @property
    def session_realized_pnl_cents(self) -> float:
        return self._session_realized_pnl_cents

    @property
    def daily_realized_pnl_cents(self) -> float:
        return self._daily_realized_pnl_cents

    @property
    def current_balance_cents(self) -> float:
        return self._current_balance_cents

    def update_balance(self, new_balance_cents: float) -> None:
        """Update the current balance (called after fills/settlements)."""
        self._current_balance_cents = new_balance_cents

    def update_open_position_count(self, count: int) -> None:
        """Update the current open position count."""
        self._open_position_count = count

    def record_trade_pnl(self, pnl_cents: float) -> None:
        """Record realized P&L from a completed trade."""
        self._session_realized_pnl_cents += pnl_cents
        self._daily_realized_pnl_cents += pnl_cents

        if pnl_cents < 0:
            self._last_loss_timestamp = time.time()
            logger.info(
                "Loss recorded: %.2f¢ (session total: %.2f¢, daily total: %.2f¢)",
                pnl_cents,
                self._session_realized_pnl_cents,
                self._daily_realized_pnl_cents,
            )

    def reset_session(self) -> None:
        """Reset session-level counters (new trading session)."""
        self._session_realized_pnl_cents = 0.0
        self._session_start_timestamp = time.time()
        logger.info("Session risk counters reset")

    def reset_daily(self) -> None:
        """Reset daily counters (new day)."""
        self._daily_realized_pnl_cents = 0.0
        self._last_loss_timestamp = 0.0
        logger.info("Daily risk counters reset")

    def evaluate_trade_permission(
        self,
        vessel_state: str,
        wallet_mode: str,
        contract_quantity: int,
        estimated_total_cost_cents: float,
    ) -> RiskGateEvaluationResult:
        """Evaluate ALL risk gates before allowing a trade.

        This is the single entry point called by the execution engine.
        Checks gates in priority order (cheapest first).

        Args:
            vessel_state: Current vessel state string ("FULL_FORWARD", "BATTERY", "FULL_STOP")
            wallet_mode: Resolved wallet mode ("PAPER" or "ARMED")
            contract_quantity: Number of contracts requested
            estimated_total_cost_cents: Total cost including fees

        Returns:
            RiskGateEvaluationResult with approval/rejection and context
        """
        timestamp = time.time()

        # Gate 1: Vessel state (cheapest check)
        if vessel_state != "FULL_FORWARD":
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.VESSEL_NOT_FULL_FORWARD,
                rejection_detail=f"Vessel is {vessel_state}, must be FULL_FORWARD to trade",
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 2: Wallet mode
        if wallet_mode not in ("PAPER", "ARMED"):
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.WALLET_NOT_READY,
                rejection_detail=f"Invalid wallet mode: {wallet_mode}",
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 3: Session loss floor
        if self._session_realized_pnl_cents <= self._session_loss_floor_cents:
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.SESSION_LOSS_FLOOR_BREACHED,
                rejection_detail=(
                    f"Session P&L {self._session_realized_pnl_cents:.2f}¢ "
                    f"breaches floor of {self._session_loss_floor_cents:.2f}¢"
                ),
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 4: Daily loss cap
        if self._daily_realized_pnl_cents <= self._daily_loss_cap_cents:
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.DAILY_LOSS_CAP_BREACHED,
                rejection_detail=(
                    f"Daily P&L {self._daily_realized_pnl_cents:.2f}¢ "
                    f"breaches cap of {self._daily_loss_cap_cents:.2f}¢"
                ),
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 5: Maximum open positions
        if self._open_position_count >= self._max_open_positions:
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.MAX_POSITIONS_EXCEEDED,
                rejection_detail=(
                    f"Open positions: {self._open_position_count}/{self._max_open_positions}"
                ),
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 6: Minimum contracts per order
        if contract_quantity < self._minimum_contracts_per_order:
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.MINIMUM_CONTRACTS_NOT_MET,
                rejection_detail=(
                    f"Requested {contract_quantity} contracts, "
                    f"minimum is {self._minimum_contracts_per_order}"
                ),
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 7: Maximum contracts per order
        if contract_quantity > self._maximum_contracts_per_order:
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.MAX_CONTRACTS_PER_ORDER_EXCEEDED,
                rejection_detail=(
                    f"Requested {contract_quantity} contracts, "
                    f"maximum is {self._maximum_contracts_per_order}"
                ),
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 8: Sufficient balance
        if estimated_total_cost_cents > self._current_balance_cents:
            return RiskGateEvaluationResult(
                gate_result=RiskGateResult.REJECTED,
                rejection_reason=RiskRejectionReason.INSUFFICIENT_BALANCE,
                rejection_detail=(
                    f"Trade cost {estimated_total_cost_cents:.2f}¢ exceeds "
                    f"balance {self._current_balance_cents:.2f}¢"
                ),
                session_realized_pnl_cents=self._session_realized_pnl_cents,
                daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                current_open_positions=self._open_position_count,
                current_balance_cents=self._current_balance_cents,
                evaluation_timestamp=timestamp,
            )

        # Gate 9: Loss cooldown
        if self._last_loss_timestamp > 0:
            seconds_since_loss = timestamp - self._last_loss_timestamp
            if seconds_since_loss < self._loss_cooldown_seconds:
                remaining_cooldown = self._loss_cooldown_seconds - seconds_since_loss
                return RiskGateEvaluationResult(
                    gate_result=RiskGateResult.REJECTED,
                    rejection_reason=RiskRejectionReason.COOLDOWN_ACTIVE,
                    rejection_detail=(
                        f"Loss cooldown active: {remaining_cooldown:.1f}s remaining "
                        f"(last loss {seconds_since_loss:.1f}s ago)"
                    ),
                    session_realized_pnl_cents=self._session_realized_pnl_cents,
                    daily_realized_pnl_cents=self._daily_realized_pnl_cents,
                    current_open_positions=self._open_position_count,
                    current_balance_cents=self._current_balance_cents,
                    evaluation_timestamp=timestamp,
                )

        # All gates passed
        return RiskGateEvaluationResult(
            gate_result=RiskGateResult.APPROVED,
            rejection_reason=None,
            rejection_detail=None,
            session_realized_pnl_cents=self._session_realized_pnl_cents,
            daily_realized_pnl_cents=self._daily_realized_pnl_cents,
            current_open_positions=self._open_position_count,
            current_balance_cents=self._current_balance_cents,
            evaluation_timestamp=timestamp,
        )
