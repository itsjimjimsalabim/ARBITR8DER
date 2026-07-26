"""Risk controls for the trading vessel.

Implements the pre-trade risk checks that gate every order intent before
it reaches a venue adapter. Checks are layered and fail-fast:

  1. Vessel state (Full_Forward required)
  2. Wallet mode (paper enforced unless armed)
  3. Minimum 2-contract rule (Kalshi minimum)
  4. Balance sufficiency
  5. Per-asset exposure limits
  6. Max open positions
  7. Session and daily loss caps
  8. Trade cooldown between orders
  9. Stale book block (market data freshness)
 10. Emergency stop (instant halt + cancel all pending)

All checks return a RiskVerdict — either PASS with optional warnings,
or BLOCK with a reason string. The venue adapter must not execute
a blocked intent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


class RiskBlockReason(StrEnum):
    """Why an order intent was blocked."""
    VESSEL_NOT_FORWARD = "vessel_not_full_forward"
    WALLET_NOT_PAPER = "wallet_not_paper"
    BELOW_MIN_CONTRACTS = "below_minimum_contracts"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    EXPOSURE_LIMIT = "exposure_limit_exceeded"
    MAX_POSITIONS = "max_positions_reached"
    SESSION_LOSS_CAP = "session_loss_cap_hit"
    DAILY_LOSS_CAP = "daily_loss_cap_hit"
    COOLDOWN = "trade_cooldown_active"
    STALE_BOOK = "stale_market_data"
    EMERGENCY_STOP = "emergency_stop_active"
    REJECTED = "order_rejected"


@dataclass
class RiskVerdict:
    """Result of a risk check on an order intent."""
    passed: bool
    block_reason: RiskBlockReason | None = None
    block_detail: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, warnings: list[str] | None = None) -> RiskVerdict:
        return cls(passed=True, warnings=warnings or [])

    @classmethod
    def blocked(cls, reason: RiskBlockReason, detail: str = "") -> RiskVerdict:
        return cls(passed=False, block_reason=reason, block_detail=detail)


@dataclass
class OrderIntent:
    """A pre-trade order intent to be validated by risk controls."""
    asset: str
    side: str  # "yes" or "no"
    contracts: int
    ticker: str = ""
    limit_cents: int | None = None  # None = market order
    snapshot_version: int | None = None  # required for Full_Forward
    timestamp: float = field(default_factory=time.time)


class RiskController:
    """Pre-trade risk gate. All intents pass through here before execution.

    State is reset on each new session (VesselStateMachine forces Full_Stop).
    """

    def __init__(
        self,
        *,
        wallet_mode: str = "paper",
        max_positions_per_asset: int = 10,
        max_balance_per_order: float = 500.0,
        max_exposure_per_asset: float = 2000.0,
        session_loss_cap: float = 100.0,
        daily_loss_cap: float = 500.0,
        cooldown_seconds: float = 5.0,
        stale_book_max_age_seconds: float = 300.0,  # 5 minutes
        min_contracts: int = 2,
    ) -> None:
        self._wallet_mode = wallet_mode
        self._max_positions_per_asset = max_positions_per_asset
        self._max_balance_per_order = max_balance_per_order
        self._max_exposure_per_asset = max_exposure_per_asset
        self._session_loss_cap = session_loss_cap
        self._daily_loss_cap = daily_loss_cap
        self._cooldown_seconds = cooldown_seconds
        self._stale_book_max_age_seconds = stale_book_max_age_seconds
        self._min_contracts = min_contracts

        # Runtime state
        self._emergency_stop_active = False
        self._last_trade_time: float = 0.0
        self._session_pnl: float = 0.0
        self._daily_pnl: float = 0.0
        self._daily_reset_date: str = self._today_str()
        self._open_position_count: dict[str, int] = {}  # asset -> count
        self._exposure_by_asset: dict[str, float] = {}  # asset -> notional exposure
        self._balance: float = 17.00  # starting paper balance (matches real Kalshi balance)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def check(
        self,
        intent: OrderIntent,
        vessel_state: str,
        current_book_age_seconds: float | None = None,
    ) -> RiskVerdict:
        """Run all risk checks on an order intent. Fail-fast on first block."""
        warnings: list[str] = []

        # 1. Emergency stop
        if self._emergency_stop_active:
            return RiskVerdict.blocked(
                RiskBlockReason.EMERGENCY_STOP,
                "Emergency stop is active. Operator must reset.",
            )

        # 2. Vessel state
        if vessel_state != "full_forward":
            return RiskVerdict.blocked(
                RiskBlockReason.VESSEL_NOT_FORWARD,
                f"Vessel is in '{vessel_state}', must be 'full_forward' to trade.",
            )

        # 3. Wallet mode
        if self._wallet_mode != "paper":
            return RiskVerdict.blocked(
                RiskBlockReason.WALLET_NOT_PAPER,
                f"Wallet mode is '{self._wallet_mode}', only 'paper' allowed in Phase 7.",
            )

        # 4. Minimum contracts
        if intent.contracts < self._min_contracts:
            return RiskVerdict.blocked(
                RiskBlockReason.BELOW_MIN_CONTRACTS,
                f"Minimum order is {self._min_contracts} contracts, got {intent.contracts}.",
            )

        # 5. Balance sufficiency
        cost = intent.contracts * (intent.limit_cents or 50) / 100.0
        if cost > self._balance:
            return RiskVerdict.blocked(
                RiskBlockReason.INSUFFICIENT_BALANCE,
                f"Order cost ${cost:.2f} exceeds balance ${self._balance:.2f}.",
            )

        # 6. Balance per order limit
        if cost > self._max_balance_per_order:
            return RiskVerdict.blocked(
                RiskBlockReason.INSUFFICIENT_BALANCE,
                f"Order cost ${cost:.2f} exceeds per-order limit ${self._max_balance_per_order:.2f}.",
            )

        # 7. Exposure limit per asset
        current_exposure = self._exposure_by_asset.get(intent.asset, 0.0)
        if current_exposure + cost > self._max_exposure_per_asset:
            return RiskVerdict.blocked(
                RiskBlockReason.EXPOSURE_LIMIT,
                f"Asset {intent.asset} exposure ${current_exposure + cost:.2f} "
                f"would exceed limit ${self._max_exposure_per_asset:.2f}.",
            )

        # 8. Max positions per asset
        position_count = self._open_position_count.get(intent.asset, 0)
        if position_count >= self._max_positions_per_asset:
            return RiskVerdict.blocked(
                RiskBlockReason.MAX_POSITIONS,
                f"Asset {intent.asset} has {position_count} open positions, "
                f"max is {self._max_positions_per_asset}.",
            )

        # 9. Session loss cap
        if self._session_pnl <= -self._session_loss_cap:
            return RiskVerdict.blocked(
                RiskBlockReason.SESSION_LOSS_CAP,
                f"Session loss ${abs(self._session_pnl):.2f} hit cap ${self._session_loss_cap:.2f}.",
            )

        # 10. Daily loss cap
        self._maybe_reset_daily()
        if self._daily_pnl <= -self._daily_loss_cap:
            return RiskVerdict.blocked(
                RiskBlockReason.DAILY_LOSS_CAP,
                f"Daily loss ${abs(self._daily_pnl):.2f} hit cap ${self._daily_loss_cap:.2f}.",
            )

        # 11. Trade cooldown
        elapsed = time.time() - self._last_trade_time
        if elapsed < self._cooldown_seconds:
            remaining = self._cooldown_seconds - elapsed
            return RiskVerdict.blocked(
                RiskBlockReason.COOLDOWN,
                f"Cooldown active, {remaining:.1f}s remaining.",
            )

        # 12. Stale book check
        if current_book_age_seconds is not None:
            if current_book_age_seconds > self._stale_book_max_age_seconds:
                return RiskVerdict.blocked(
                    RiskBlockReason.STALE_BOOK,
                    f"Market data is {current_book_age_seconds:.0f}s old, "
                    f"max is {self._stale_book_max_age_seconds:.0f}s.",
                )

        # Warnings (non-blocking)
        if intent.contracts < 4:
            warnings.append(f"Small order: {intent.contracts} contracts.")
        if position_count >= self._max_positions_per_asset - 2:
            warnings.append(f"Approaching max positions ({position_count}/{self._max_positions_per_asset}).")
        if self._session_pnl < 0 and abs(self._session_pnl) > self._session_loss_cap * 0.7:
            warnings.append(f"Session loss ${abs(self._session_pnl):.2f} approaching cap.")

        return RiskVerdict.ok(warnings=warnings)

    def record_fill(self, asset: str, cost: float) -> None:
        """Record a successful fill for position/exposure tracking."""
        self._last_trade_time = time.time()
        self._balance -= cost
        self._open_position_count[asset] = self._open_position_count.get(asset, 0) + 1
        self._exposure_by_asset[asset] = self._exposure_by_asset.get(asset, 0.0) + cost
        logger.info("Risk: fill recorded for %s, cost=$%.2f, balance=$%.2f", asset, cost, self._balance)

    def record_settlement(self, asset: str, pnl: float, exposure: float) -> None:
        """Record a settlement — removes position and updates PnL."""
        self._session_pnl += pnl
        self._daily_pnl += pnl
        self._balance += exposure + pnl  # return exposure + add PnL
        self._open_position_count[asset] = max(0, self._open_position_count.get(asset, 1) - 1)
        self._exposure_by_asset[asset] = max(0.0, self._exposure_by_asset.get(asset, 0.0) - exposure)
        logger.info("Risk: settlement for %s, pnl=$%.2f, balance=$%.2f", asset, pnl, self._balance)

    def emergency_stop(self) -> None:
        """Activate emergency stop — blocks all new orders."""
        self._emergency_stop_active = True
        logger.warning("Risk: EMERGENCY STOP ACTIVATED")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop (operator action required)."""
        self._emergency_stop_active = False
        logger.info("Risk: emergency stop reset")

    def status(self) -> dict[str, Any]:
        """Return current risk status for display."""
        self._maybe_reset_daily()
        return {
            "wallet_mode": self._wallet_mode,
            "balance": self._balance,
            "session_pnl": self._session_pnl,
            "daily_pnl": self._daily_pnl,
            "session_loss_cap": self._session_loss_cap,
            "daily_loss_cap": self._daily_loss_cap,
            "open_positions": dict(self._open_position_count),
            "exposure": dict(self._exposure_by_asset),
            "emergency_stop": self._emergency_stop_active,
            "cooldown_seconds": self._cooldown_seconds,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _maybe_reset_daily(self) -> None:
        today = self._today_str()
        if today != self._daily_reset_date:
            self._daily_pnl = 0.0
            self._daily_reset_date = today
