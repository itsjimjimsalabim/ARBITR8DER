"""Execute paper bid for 7:30 PM - 7:45 PM PDT market session."""
from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
from arbitr8der_package.cli.structured_trade_journal_module import TradeJournal

def main():
    venue = PaperVenueAdapter()
    print("Initial Paper Wallet Balance: $" + f"{venue.get_wallet().balance:,.2f}")

    # Place 2 YES contracts bid for 7:30 PM PDT market
    ticker = "KXBTC15M-26JUL262230-30"
    order = venue.submit_order(
        asset="BTC",
        side="yes",
        contracts=2,
        ticker=ticker,
        midpoint_cents=52.0,
        model_version="gemini_flash_3.6",
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
        observation=f"7:30 PM PDT market bid for {ticker} @ {order.fill_price_cents}c",
        hypothesis="7:30-7:45 PM market momentum upwards towards BTC strike",
    )
    journal.add_note(entry.entry_id, f"Paper order {order.order_id} filled for {order.contracts} YES contracts at {order.fill_price_cents}c (${order.fill_cost_usd:.2f})")

    wallet = venue.get_wallet()
    print(f"\n  Updated Paper Wallet Balance: ${wallet.balance:,.2f}")
    print(f"  Total Wallet Trades:         {wallet.total_trades}")
    print(f"  Total Wallet PnL:            ${wallet.total_pnl:,.2f}")
    positions = venue.get_open_positions()
    print(f"  Open Positions Count:        {len(positions)}")
    for p in positions:
        print(f"    -> Position: {p.contracts}x {p.side.upper()} {p.ticker} @ {p.avg_entry_cents:.1f}c (Cost: ${p.total_cost_usd:.2f})")

if __name__ == "__main__":
    main()
