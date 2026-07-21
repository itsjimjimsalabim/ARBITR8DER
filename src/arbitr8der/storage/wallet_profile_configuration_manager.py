"""Wallet profile manager — resolves PAPER vs ARMED mode from environment.

Per Theories_of_Operations: "If ARMED credentials are missing, auto-downgrade to PAPER."
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class WalletMode(str, enum.Enum):
    PAPER = "PAPER"
    ARMED = "ARMED"


@dataclass(frozen=True)
class ResolvedWalletProfileConfiguration:
    """Resolved wallet configuration. Immutable."""
    mode: WalletMode
    kalshi_api_key_id: str
    kalshi_private_key_path: str
    balance_estimate_cents: int
    can_trade: bool

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "kalshi_api_key_id": self.kalshi_api_key_id[:8] + "..." if self.kalshi_api_key_id else "",
            "kalshi_private_key_path": self.kalshi_private_key_path,
            "balance_estimate_cents": self.balance_estimate_cents,
            "can_trade": self.can_trade,
        }


def resolve_wallet_profile(
    requested_mode: str,
    api_key_id: str,
    private_key_path: str,
    balance_estimate_cents: int = 1700,
) -> ResolvedWalletProfileConfiguration:
    """Resolve the wallet profile from environment settings.

    If ARMED is requested but credentials are missing, auto-downgrades to PAPER.

    Args:
        requested_mode: "PAPER" or "ARMED"
        api_key_id: Kalshi API key ID from .env
        private_key_path: Path to kalshi_private.pem
        balance_estimate_cents: Starting balance in cents ($17 = 1700)

    Returns:
        Resolved wallet profile with actual effective mode.
    """
    try:
        mode = WalletMode(requested_mode.upper())
    except ValueError:
        logger.warning("Invalid wallet mode '%s', defaulting to PAPER", requested_mode)
        mode = WalletMode.PAPER

    # Check credentials for ARMED mode
    key_exists = Path(private_key_path).exists() if private_key_path else False
    has_creds = bool(api_key_id) and key_exists

    if mode == WalletMode.ARMED and not has_creds:
        missing = []
        if not api_key_id:
            missing.append("AR8_KALSHI_API_KEY_ID")
        if not key_exists:
            missing.append(private_key_path)
        logger.warning(
            "ARMED requested but credentials missing (%s). Auto-downgrading to PAPER.",
            ", ".join(missing),
        )
        mode = WalletMode.PAPER

    can_trade = True  # Both PAPER and ARMED can trade (PAPER = simulated)

    profile = ResolvedWalletProfileConfiguration(
        mode=mode,
        kalshi_api_key_id=api_key_id,
        kalshi_private_key_path=private_key_path,
        balance_estimate_cents=balance_estimate_cents,
        can_trade=can_trade,
    )

    logger.info("Wallet profile resolved: %s (balance: $%.2f)", mode.value, balance_estimate_cents / 100)
    return profile
