#!/usr/bin/env python3
"""Fetch real Kalshi account balance and set paper wallet to match.

Usage:
    python scripts/fetch_real_balance.py [--set-balance]

This script:
1. Connects to Kalshi REST API with your API key
2. Fetches your real account balance
3. Updates the paper wallet to match (if --set-balance flag)

Your paper trading will then start with your actual balance (~$17),
making the experience realistic for when you go live.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from arbitr8der_package.data_sources.kalshi_rest_market_discovery_client import KalshiRestMarketDiscoveryClient
from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
from arbitr8der_package.config.typed_configuration_settings_module import load_settings


async def fetch_balance() -> float | None:
    """Fetch real Kalshi balance."""
    settings = load_settings()

    if not settings.kalshi_api_key_id:
        print("ERROR: No Kalshi API key configured.")
        print("Set KALSHI_API_KEY_ID in .env or environment.")
        return None

    client = KalshiRestMarketDiscoveryClient(api_key=settings.kalshi_api_key_id)
    balance_data = await client.get_balance()

    if balance_data is None:
        print("ERROR: Could not fetch balance from Kalshi.")
        print("Check your API key and network connection.")
        return None

    balance_cents = balance_data.get("balance", 0)
    balance_usd = balance_cents / 100.0

    print(f"Real Kalshi balance: ${balance_usd:.2f} ({balance_cents} cents)")
    return balance_usd


def set_paper_balance(balance_usd: float) -> None:
    """Update paper wallet to match real balance."""
    db_path = Path(__file__).parent.parent / "runtime" / "paper_wallet.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Delete existing wallet to force recreation with new balance
    import sqlite3
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM wallet WHERE id = 1")
        conn.commit()
        conn.close()
        print(f"Deleted existing wallet entry.")

    # Create new adapter with real balance
    venue = PaperVenueAdapter(db_path=db_path, initial_balance=balance_usd)
    wallet = venue.get_wallet()

    print(f"Paper wallet set to: ${wallet.balance:.2f}")
    print(f"Starting balance: ${wallet.starting_balance:.2f}")
    venue.close()


async def main() -> None:
    set_balance = "--set-balance" in sys.argv

    print("=== Kalshi Balance Fetcher ===\n")

    balance = await fetch_balance()
    if balance is None:
        sys.exit(1)

    if set_balance:
        print(f"\nSetting paper wallet to ${balance:.2f}...")
        set_paper_balance(balance)
        print("\nDone! Paper trading will now start with your real balance.")
    else:
        print(f"\nTo set paper wallet to ${balance:.2f}, run:")
        print(f"  python scripts/fetch_real_balance.py --set-balance")


if __name__ == "__main__":
    asyncio.run(main())
