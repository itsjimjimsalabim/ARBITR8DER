"""Kalshi fee curve calculator — models the exact fee structure per Theories_of_Operations.

Kalshi charges fees on a curve: fee = 0.07 * P * (1 - P) * 100 cents per contract.
At P=0.50 (fair coin), fee is max at ~1.75 cents per contract per leg.
At P=0.10 or P=0.90, fee drops to ~0.63 cents per contract per leg.
Round trip = entry fee + exit fee.

Minimum 2 contracts per order — single contract fees eat the entire edge.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Kalshi fee rate constant (7% of P*(1-P))
KALSHI_FEE_RATE = 0.07

# Minimum contracts per order — enforced by the execution engine
MINIMUM_CONTRACTS_PER_ORDER = 2


@dataclass(frozen=True)
class FeeCalculationResult:
    """Result of a fee calculation for a single trade leg."""

    price_per_share_cents: float       # Price paid/received per share
    contract_quantity: int             # Number of contracts
    fee_rate_constant: float           # 0.07 (Kalshi's constant)
    fee_per_contract_cents: float      # Fee per contract for this leg
    total_fee_cents: float             # Total fee for all contracts
    total_cost_cents: float            # Price * quantity + fees

    def to_dict(self) -> dict:
        return {
            "price_per_share_cents": self.price_per_share_cents,
            "contract_quantity": self.contract_quantity,
            "fee_rate_constant": self.fee_rate_constant,
            "fee_per_contract_cents": self.fee_per_contract_cents,
            "total_fee_cents": self.total_fee_cents,
            "total_cost_cents": self.total_cost_cents,
        }


@dataclass(frozen=True)
class RoundTripFeeEstimate:
    """Estimated fees for a full round-trip trade (entry + exit)."""

    asset_name: str
    entry_price_cents: float
    exit_price_cents: float
    contract_quantity: int
    entry_fee_cents: float
    exit_fee_cents: float
    total_round_trip_fee_cents: float
    gross_profit_if_win_cents: float    # (100 - entry_price) * quantity
    net_profit_if_win_cents: float      # gross - round_trip_fees
    net_loss_if_lose_cents: float       # entry_cost + fees (no exit income)

    def to_dict(self) -> dict:
        return {
            "asset_name": self.asset_name,
            "entry_price_cents": self.entry_price_cents,
            "exit_price_cents": self.exit_price_cents,
            "contract_quantity": self.contract_quantity,
            "entry_fee_cents": self.entry_fee_cents,
            "exit_fee_cents": self.exit_fee_cents,
            "total_round_trip_fee_cents": self.total_round_trip_fee_cents,
            "gross_profit_if_win_cents": self.gross_profit_if_win_cents,
            "net_profit_if_win_cents": self.net_profit_if_win_cents,
            "net_loss_if_lose_cents": self.net_loss_if_lose_cents,
        }


class KalshiFeeCurveCalculatorModule:
    """Calculates Kalshi trading fees using their actual fee curve.

    Kalshi's fee formula: fee_per_contract = 0.07 * P * (1 - P) * 100 cents
    where P is the price per share in the 0.00-1.00 range.

    Key properties:
      - Max fee at P=0.50: 0.07 * 0.50 * 0.50 * 100 = 1.75 cents
      - Min fee approaches 0 as P approaches 0 or 1
      - Fees are per-leg (entry and exit each incur fees)
      - Round-trip fee = entry_fee + exit_fee
    """

    def __init__(self, fee_rate: float = KALSHI_FEE_RATE):
        """Initialize with Kalshi's fee rate constant.

        Args:
            fee_rate: Kalshi's fee rate constant (default 0.07 = 7%)
        """
        self._fee_rate = fee_rate

    @property
    def fee_rate(self) -> float:
        return self._fee_rate

    def calculate_fee_per_contract(self, price_per_share_cents: float) -> float:
        """Calculate fee per contract at a given price.

        Args:
            price_per_share_cents: Price in cents (0-100 scale, e.g., 50.0 for 50 cents)

        Returns:
            Fee per contract in cents

        Formula: fee = 0.07 * P * (1 - P) * 100
        Where P = price_per_share / 100 (convert cents to 0-1 range)
        """
        # Convert cents to probability (0.00 - 1.00)
        price_probability = price_per_share_cents / 100.0

        # Clamp to valid range
        price_probability = max(0.01, min(0.99, price_probability))

        # Kalshi fee curve
        fee_cents = self._fee_rate * price_probability * (1.0 - price_probability) * 100.0

        return round(fee_cents, 4)

    def calculate_total_fee_for_leg(
        self,
        price_per_share_cents: float,
        contract_quantity: int,
    ) -> FeeCalculationResult:
        """Calculate total fee for one trade leg (entry or exit).

        Args:
            price_per_share_cents: Price per share in cents
            contract_quantity: Number of contracts

        Returns:
            FeeCalculationResult with fee breakdown

        Raises:
            ValueError: If contract_quantity < MINIMUM_CONTRACTS_PER_ORDER
        """
        if contract_quantity < MINIMUM_CONTRACTS_PER_ORDER:
            raise ValueError(
                f"Minimum {MINIMUM_CONTRACTS_PER_ORDER} contracts per order. "
                f"Got {contract_quantity}. Fees make single-contract trades unprofitable."
            )

        fee_per_contract = self.calculate_fee_per_contract(price_per_share_cents)
        total_fee = round(fee_per_contract * contract_quantity, 4)
        total_cost = round((price_per_share_cents * contract_quantity) + total_fee, 4)

        return FeeCalculationResult(
            price_per_share_cents=price_per_share_cents,
            contract_quantity=contract_quantity,
            fee_rate_constant=self._fee_rate,
            fee_per_contract_cents=fee_per_contract,
            total_fee_cents=total_fee,
            total_cost_cents=total_cost,
        )

    def estimate_round_trip_fees(
        self,
        asset_name: str,
        entry_price_cents: float,
        exit_price_cents: float,
        contract_quantity: int,
    ) -> RoundTripFeeEstimate:
        """Estimate total round-trip fees (entry + exit).

        Args:
            asset_name: "BTC" or "ETH"
            entry_price_cents: Price paid per share on entry (in cents)
            exit_price_cents: Price received per share on exit (in cents)
            contract_quantity: Number of contracts

        Returns:
            RoundTripFeeEstimate with full fee breakdown and P&L projections
        """
        entry_fee = self.calculate_total_fee_for_leg(entry_price_cents, contract_quantity)
        exit_fee = self.calculate_total_fee_for_leg(exit_price_cents, contract_quantity)

        total_round_trip_fees = entry_fee.total_fee_cents + exit_fee.total_fee_cents

        # If we WIN: we get 100 cents per share, minus what we paid
        gross_profit_if_win = (100.0 - entry_price_cents) * contract_quantity
        net_profit_if_win = gross_profit_if_win - total_round_trip_fees

        # If we LOSE: we lose our entry cost + fees (exit pays nothing)
        net_loss_if_lose = (entry_price_cents * contract_quantity) + total_round_trip_fees

        return RoundTripFeeEstimate(
            asset_name=asset_name,
            entry_price_cents=entry_price_cents,
            exit_price_cents=exit_price_cents,
            contract_quantity=contract_quantity,
            entry_fee_cents=entry_fee.total_fee_cents,
            exit_fee_cents=exit_fee.total_fee_cents,
            total_round_trip_fee_cents=total_round_trip_fees,
            gross_profit_if_win_cents=round(gross_profit_if_win, 4),
            net_profit_if_win_cents=round(net_profit_if_win, 4),
            net_loss_if_lose_cents=round(net_loss_if_lose, 4),
        )

    def minimum_profitable_edge_cents(self, price_per_share_cents: float, contract_quantity: int = 2) -> float:
        """Calculate the minimum edge (in cents) needed to be profitable after fees.

        For a trade to be profitable:
          edge * quantity > entry_fee + exit_fee

        Args:
            price_per_share_cents: Expected entry price
            contract_quantity: Number of contracts (default 2, minimum)

        Returns:
            Minimum edge in cents needed to cover round-trip fees
        """
        entry_fee = self.calculate_total_fee_for_leg(price_per_share_cents, contract_quantity)

        # Estimate exit fee at same price (conservative)
        exit_fee = self.calculate_total_fee_for_leg(price_per_share_cents, contract_quantity)

        total_fees = entry_fee.total_fee_cents + exit_fee.total_fee_cents
        minimum_edge = total_fees / contract_quantity

        return round(minimum_edge, 4)
