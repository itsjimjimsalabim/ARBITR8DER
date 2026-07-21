"""Trade inventory position tracker — tracks all open and closed positions.

Per Theories_of_Operations: "The AI reads live HotSnapshot data, evaluates edges,
and issues explicit commands. The code does not decide. It only executes the AI's
expressed intent, with latency simulation, price-drift checks, fee accounting,
and journaling as guardrails."

This module tracks:
  - Open positions (what the AI currently holds)
  - Closed positions (settled or sold, with realized P&L)
  - Pending limit orders (waiting to fill)
  - Total exposure and inventory value
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .kalshi_fee_curve_calculator_module import KalshiFeeCurveCalculatorModule

logger = logging.getLogger(__name__)


class PositionSide(str, Enum):
    """Which side of the binary market the position is on."""

    YES = "YES"
    NO = "NO"


class PositionStatus(str, Enum):
    """Lifecycle status of a position."""

    OPEN = "OPEN"
    CLOSED_FILLED = "CLOSED_FILLED"
    CLOSED_SETTLED = "CLOSED_SETTLED"
    CLOSED_CANCELLED = "CLOSED_CANCELLED"


class OrderType(str, Enum):
    """Order type for pending limit orders."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class OpenPositionRecord:
    """An active position the AI is holding.

    Mutable because the position tracks running P&L that updates
    as market prices change.
    """

    position_id: str
    asset_name: str
    ticker_symbol: str
    side: PositionSide
    contract_quantity: int
    entry_price_cents: float
    entry_fee_cents: float
    entry_timestamp: float
    snapshot_generation_at_entry: int
    current_market_price_cents: float
    status: PositionStatus = PositionStatus.OPEN

    @property
    def total_cost_cents(self) -> float:
        """Total cost including fees."""
        return (self.entry_price_cents * self.contract_quantity) + self.entry_fee_cents

    @property
    def unrealized_pnl_cents(self) -> float:
        """Unrealized P&L based on current market price."""
        if self.status != PositionStatus.OPEN:
            return 0.0
        market_value = self.current_market_price_cents * self.contract_quantity
        return market_value - self.total_cost_cents

    @property
    def unrealized_pnl_percentage(self) -> float:
        """Unrealized P&L as percentage of cost."""
        if self.total_cost_cents == 0:
            return 0.0
        return (self.unrealized_pnl_cents / self.total_cost_cents) * 100.0

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "asset_name": self.asset_name,
            "ticker_symbol": self.ticker_symbol,
            "side": self.side.value,
            "contract_quantity": self.contract_quantity,
            "entry_price_cents": self.entry_price_cents,
            "entry_fee_cents": self.entry_fee_cents,
            "total_cost_cents": self.total_cost_cents,
            "current_market_price_cents": self.current_market_price_cents,
            "unrealized_pnl_cents": self.unrealized_pnl_cents,
            "unrealized_pnl_percentage": round(self.unrealized_pnl_percentage, 2),
            "entry_timestamp": self.entry_timestamp,
            "snapshot_generation_at_entry": self.snapshot_generation_at_entry,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class ClosedPositionRecord:
    """A closed position with realized P&L — immutable audit record."""

    position_id: str
    asset_name: str
    ticker_symbol: str
    side: PositionSide
    contract_quantity: int
    entry_price_cents: float
    entry_fee_cents: float
    exit_price_cents: float
    exit_fee_cents: float
    realized_pnl_cents: float
    entry_timestamp: float
    exit_timestamp: float
    close_reason: str

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "asset_name": self.asset_name,
            "ticker_symbol": self.ticker_symbol,
            "side": self.side.value,
            "contract_quantity": self.contract_quantity,
            "entry_price_cents": self.entry_price_cents,
            "entry_fee_cents": self.entry_fee_cents,
            "exit_price_cents": self.exit_price_cents,
            "exit_fee_cents": self.exit_fee_cents,
            "realized_pnl_cents": self.realized_pnl_cents,
            "entry_timestamp": self.entry_timestamp,
            "exit_timestamp": self.exit_timestamp,
            "close_reason": self.close_reason,
        }


@dataclass(frozen=True)
class PendingLimitOrderRecord:
    """A pending limit order waiting to fill at the target price."""

    order_id: str
    asset_name: str
    ticker_symbol: str
    side: PositionSide
    contract_quantity: int
    limit_price_cents: float
    order_type: OrderType
    placed_timestamp: float
    snapshot_generation_at_placement: int

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "asset_name": self.asset_name,
            "ticker_symbol": self.ticker_symbol,
            "side": self.side.value,
            "contract_quantity": self.contract_quantity,
            "limit_price_cents": self.limit_price_cents,
            "order_type": self.order_type.value,
            "placed_timestamp": self.placed_timestamp,
            "snapshot_generation_at_placement": self.snapshot_generation_at_placement,
        }


class TradeInventoryPositionTracker:
    """Tracks all trading positions and pending orders.

    The AI holds one of these per session. It tracks open positions,
    closed positions, and pending limit orders. The execution engine
    updates it after every trade action.
    """

    def __init__(self):
        self._open_positions: dict[str, OpenPositionRecord] = {}
        self._closed_positions: list[ClosedPositionRecord] = []
        self._pending_orders: dict[str, PendingLimitOrderRecord] = {}
        self._fee_calculator = KalshiFeeCurveCalculatorModule()

    @property
    def open_position_count(self) -> int:
        return len(self._open_positions)

    @property
    def total_unrealized_pnl_cents(self) -> float:
        return sum(p.unrealized_pnl_cents for p in self._open_positions.values())

    @property
    def total_realized_pnl_cents(self) -> float:
        return sum(p.realized_pnl_cents for p in self._closed_positions)

    def register_open_position(
        self,
        asset_name: str,
        ticker_symbol: str,
        side: PositionSide,
        contract_quantity: int,
        entry_price_cents: float,
        entry_fee_cents: float,
        snapshot_generation: int,
    ) -> OpenPositionRecord:
        """Register a new open position after a successful fill.

        Args:
            asset_name: "BTC" or "ETH"
            ticker_symbol: Kalshi ticker (e.g., "KXBTC15M-25JUL211200")
            side: YES or NO
            contract_quantity: Number of contracts
            entry_price_cents: Price paid per share
            entry_fee_cents: Total fees paid
            snapshot_generation: HotState generation at time of trade

        Returns:
            The newly created OpenPositionRecord
        """
        position_id = f"pos_{uuid.uuid4().hex[:12]}"
        timestamp = time.time()

        position = OpenPositionRecord(
            position_id=position_id,
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            side=side,
            contract_quantity=contract_quantity,
            entry_price_cents=entry_price_cents,
            entry_fee_cents=entry_fee_cents,
            entry_timestamp=timestamp,
            snapshot_generation_at_entry=snapshot_generation,
            current_market_price_cents=entry_price_cents,
        )

        self._open_positions[position_id] = position
        logger.info(
            "Position opened: %s %s %s %d contracts @ %.2f¢ (fee: %.2f¢)",
            position_id, asset_name, side.value, contract_quantity,
            entry_price_cents, entry_fee_cents,
        )
        return position

    def close_position(
        self,
        position_id: str,
        exit_price_cents: float,
        exit_fee_cents: float,
        close_reason: str,
    ) -> ClosedPositionRecord:
        """Close an open position and record realized P&L.

        Args:
            position_id: ID of the position to close
            exit_price_cents: Price received per share on exit
            exit_fee_cents: Total fees paid on exit
            close_reason: Why the position was closed

        Returns:
            ClosedPositionRecord with realized P&L

        Raises:
            KeyError: If position_id is not found in open positions
        """
        if position_id not in self._open_positions:
            raise KeyError(f"No open position with ID: {position_id}")

        position = self._open_positions[position_id]
        timestamp = time.time()

        # Calculate realized P&L
        exit_proceeds = exit_price_cents * position.contract_quantity
        total_cost = position.total_cost_cents
        realized_pnl = exit_proceeds - exit_fee_cents - total_cost

        closed_record = ClosedPositionRecord(
            position_id=position_id,
            asset_name=position.asset_name,
            ticker_symbol=position.ticker_symbol,
            side=position.side,
            contract_quantity=position.contract_quantity,
            entry_price_cents=position.entry_price_cents,
            entry_fee_cents=position.entry_fee_cents,
            exit_price_cents=exit_price_cents,
            exit_fee_cents=exit_fee_cents,
            realized_pnl_cents=round(realized_pnl, 4),
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=timestamp,
            close_reason=close_reason,
        )

        # Move from open to closed
        del self._open_positions[position_id]
        self._closed_positions.append(closed_record)

        logger.info(
            "Position closed: %s %s %s %d contracts, P&L: %.2f¢ (%s)",
            position_id, position.asset_name, position.side.value,
            position.contract_quantity, realized_pnl, close_reason,
        )
        return closed_record

    def update_market_price(self, position_id: str, new_price_cents: float) -> None:
        """Update the current market price for an open position (for unrealized P&L)."""
        if position_id in self._open_positions:
            self._open_positions[position_id].current_market_price_cents = new_price_cents

    def register_pending_limit_order(
        self,
        asset_name: str,
        ticker_symbol: str,
        side: PositionSide,
        contract_quantity: int,
        limit_price_cents: float,
        snapshot_generation: int,
    ) -> PendingLimitOrderRecord:
        """Register a pending limit order."""
        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        timestamp = time.time()

        order = PendingLimitOrderRecord(
            order_id=order_id,
            asset_name=asset_name,
            ticker_symbol=ticker_symbol,
            side=side,
            contract_quantity=contract_quantity,
            limit_price_cents=limit_price_cents,
            order_type=OrderType.LIMIT,
            placed_timestamp=timestamp,
            snapshot_generation_at_placement=snapshot_generation,
        )

        self._pending_orders[order_id] = order
        logger.info(
            "Limit order placed: %s %s %s %d contracts @ limit %.2f¢",
            order_id, asset_name, side.value, contract_quantity, limit_price_cents,
        )
        return order

    def cancel_pending_order(self, order_id: str) -> Optional[PendingLimitOrderRecord]:
        """Cancel a pending limit order."""
        if order_id in self._pending_orders:
            order = self._pending_orders.pop(order_id)
            logger.info("Limit order cancelled: %s", order_id)
            return order
        return None

    def check_pending_orders_for_fills(self, current_prices: dict[str, float]) -> list[str]:
        """Check if any pending limit orders should fill based on current prices.

        Args:
            current_prices: Dict of ticker -> current market price in cents

        Returns:
            List of order_ids that were filled
        """
        filled_order_ids = []

        for order_id, order in list(self._pending_orders.items()):
            current_price = current_prices.get(order.ticker_symbol)
            if current_price is None:
                continue

            # Limit order fills when market price drops to or below limit
            if current_price <= order.limit_price_cents:
                filled_order_ids.append(order_id)
                logger.info(
                    "Limit order filled: %s at %.2f¢ (limit was %.2f¢)",
                    order_id, current_price, order.limit_price_cents,
                )

        return filled_order_ids

    def get_open_positions(self) -> list[OpenPositionRecord]:
        """Get all open positions."""
        return list(self._open_positions.values())

    def get_closed_positions(self) -> list[ClosedPositionRecord]:
        """Get all closed positions."""
        return list(self._closed_positions)

    def get_pending_orders(self) -> list[PendingLimitOrderRecord]:
        """Get all pending limit orders."""
        return list(self._pending_orders.values())

    def get_positions_by_asset(self, asset_name: str) -> list[OpenPositionRecord]:
        """Get open positions filtered by asset."""
        return [p for p in self._open_positions.values() if p.asset_name == asset_name]

    def get_positions_by_ticker(self, ticker_symbol: str) -> list[OpenPositionRecord]:
        """Get open positions filtered by ticker."""
        return [p for p in self._open_positions.values() if p.ticker_symbol == ticker_symbol]

    def get_inventory_summary(self) -> dict:
        """Get a summary of current inventory for display."""
        open_positions = self.get_open_positions()
        return {
            "open_position_count": self.open_position_count,
            "total_unrealized_pnl_cents": round(self.total_unrealized_pnl_cents, 4),
            "total_realized_pnl_cents": round(self.total_realized_pnl_cents, 4),
            "total_closed_count": len(self._closed_positions),
            "pending_order_count": len(self._pending_orders),
            "positions_by_asset": {
                "BTC": len(self.get_positions_by_asset("BTC")),
                "ETH": len(self.get_positions_by_asset("ETH")),
            },
        }
