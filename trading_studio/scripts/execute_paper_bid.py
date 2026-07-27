"""Execute a paper bid for an active BTC 15-minute market session.

Usage:
    python scripts/execute_paper_bid.py [TICKER] [SIDE] [CONTRACTS] [PRICE_CENTS]

If TICKER is omitted, the script dynamically discovers the current active BTC 15-minute
market on Kalshi and executes a paper order at the current market midpoint.
"""

from __future__ import annotations

import asyncio
import sys

from arbitr8der_package.cli.structured_trade_journal_module import TradeJournal
from arbitr8der_package.data_sources.kalshi_rest_market_discovery_client import (
    KalshiRestMarketDiscoveryClient,
)
from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter


async def discover_target_market() -> tuple[str, float]:
    """Find an active BTC 15-minute market and midpoint price from Kalshi REST."""
    client = KalshiRestMarketDiscoveryClient()
    try:
        markets = await client.discover_active_markets()
        btc_markets = [m for m in markets if m.ticker.startswith("KXBTC15M")]
        if btc_markets:
            target = btc_markets[0]
            mid = target.midpoint_cents or 50.0
            return target.ticker, float(mid)
    except Exception as exc:
        print(f"Warning: Could not discover active markets via Kalshi REST API: {exc}")

    return "KXBTC15M-DEMO", 50.0


async def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else None
    side = sys.argv[2] if len(sys.argv) > 2 else "yes"
    contracts = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    midpoint_cents = float(sys.argv[4]) if len(sys.argv) > 4 else None

    if not ticker or midpoint_cents is None:
        disc_ticker, disc_mid = await discover_target_market()
        ticker = ticker or disc_ticker
        midpoint_cents = midpoint_cents if midpoint_cents is not None else disc_mid

    venue = PaperVenueAdapter()
    print(f"Initial Paper Wallet Balance: ${venue.get_wallet().balance:,.2f}")

    order = venue.submit_order(
        asset="BTC",
        side=side,
        contracts=contracts,
        ticker=ticker,
        midpoint_cents=midpoint_cents,
        model_version="manual_paper_bid",
    )

    print("\n==========================================================")
    print("  PAPER ORDER EXECUTED & FILLED")
    print("==========================================================")
    print(f"  Order ID:       {order.order_id}")
    print(f"  Status:         {order.status}")
    print(f"  Ticker:         {order.ticker}")
    print(f"  Side:           {order.side.upper()}")
    print(f"  Contracts:      {order.contracts}x")
    print(f"  Fill Price:     {order.fill_price_cents:.1f}c")
    print(f"  Total Cost:     ${order.fill_cost_usd:.2f}")

    # Log to structured journal
    journal = TradeJournal()
    entry = journal.start_entry(
        asset="BTC",
        observation=f"Paper bid for {ticker} @ {order.fill_price_cents}c",
        hypothesis="Testing paper order execution lifecycle",
    )
    fill_note = (
        f"Paper order {order.order_id} filled for {order.contracts} {order.side.upper()} "
        f"contracts at {order.fill_price_cents}c (${order.fill_cost_usd:.2f})"
    )
    journal.add_note(entry.entry_id, fill_note)

    wallet = venue.get_wallet()
    print(f"\n  Updated Paper Wallet Balance: ${wallet.balance:,.2f}")
    print(f"  Total Wallet Trades:         {wallet.total_trades}")
    print(f"  Total Wallet PnL:            ${wallet.total_pnl:,.2f}")
    positions = venue.get_open_positions()
    print(f"  Open Positions Count:        {len(positions)}")
    for p in positions:
        pos_str = (
            f"    -> Position: {p.contracts}x {p.side.upper()} {p.ticker} "
            f"@ {p.avg_entry_cents:.1f}c (Cost: ${p.total_cost_usd:.2f})"
        )
        print(pos_str)


if __name__ == "__main__":
    asyncio.run(main())
