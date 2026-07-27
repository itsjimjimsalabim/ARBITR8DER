"""AI Trading Session Runner — executes live paper trading session for ARBITR8DER.

Steps:
1. Initialize SQLite prediction database and CandlePersistenceStore
2. Instantiate IngestionOrchestrator to stream live markets (Kalshi, Binance, Coinbase, Polymarket, CoinGecko)
3. Set Vessel State Machine: Full_Stop -> Battery -> Full_Forward
4. Run ML model predictions (MacroEnsemble / MicroEnsemble / Baseline)
5. Detect statistical edge against Kalshi orderbook midpoints
6. Perform risk checks and execute paper trades (buy YES / buy NO / hold)
7. Display positions, paper wallet balance, and trading journal
"""

from __future__ import annotations

import asyncio

from arbitr8der_package.cli.structured_trade_journal_module import TradeJournal
from arbitr8der_package.data_sources.ingestion_orchestrator import IngestionOrchestrator
from arbitr8der_package.vessel.vessel_state_machine import VesselState, VesselStateMachine


async def run_trading_session(duration_seconds: int = 45) -> None:
    print("=" * 70)
    print("  ARBITR8DER AI TRADING STUDIO — PAPER TRADING SESSION")
    print("=" * 70)

    # 1. Initialize Vessel State Machine
    machine = VesselStateMachine()
    print(f"Initial Vessel State: {machine.current_state.value}")

    # Transition to Battery (data soaking mode)
    machine.transition(VesselState.BATTERY, reason="AI Operator: Start Battery Data Stream")
    print(f"Vessel State -> {machine.current_state.value}")

    # Transition to Full_Forward (armed for paper trading)
    machine.transition(VesselState.FULL_FORWARD, reason="AI Operator: Arm Full_Forward Paper Trading")
    print(f"Vessel State -> {machine.current_state.value}")

    # 2. Instantiate and Start Ingestion Orchestrator
    orchestrator = IngestionOrchestrator()
    print("\nStarting Ingestion Orchestrator (Binance, Coinbase, Kalshi, Polymarket, CoinGecko)...")
    started = await orchestrator.start()
    if not started:
        print("Error: Could not acquire stream lease.")
        return

    # Sync live portfolio balance on session start and settle expired positions
    paper_venue = orchestrator.paper_venue
    discovery = orchestrator.discovery_client
    candle_store = orchestrator.candle_store
    real_kalshi_balance_usd = None
    if paper_venue and discovery and candle_store:
        print("Syncing live Kalshi portfolio balance...")
        real_kalshi_balance_usd = await paper_venue.sync_live_balance(discovery)
        if real_kalshi_balance_usd is not None:
            print(f"Live Portfolio Balance Synced: ${real_kalshi_balance_usd:,.2f}")
        else:
            print("Failed to sync live portfolio balance, falling back to cached paper wallet balance.")

        print("Checking and settling any expired paper positions from previous sessions...")
        try:
            settled = await paper_venue.settle_expired_positions(candle_store, discovery)
            if settled:
                print(f"Settled {len(settled)} expired positions on startup:")
                for s in settled:
                    print(f"  {s.ticker} ({s.side}): outcome={s.outcome}, PnL=${s.pnl:+.2f}")
            else:
                print("No expired positions to settle on startup.")
        except Exception as e:
            print(f"Warning: Failed to settle expired positions on startup: {e}")

    # Enable auto-trader
    if orchestrator.auto_trader:
        orchestrator.auto_trader.set_vessel_state_getter(lambda: machine.current_state.value.lower())
        orchestrator.auto_trader.enable()
        print("Auto-Trading Engine: ENABLED")

    journal = TradeJournal()
    paper_balance_usd = paper_venue.get_wallet().balance if paper_venue else 0.0
    print(f"Session ID: {journal.session_id}")
    if real_kalshi_balance_usd is not None:
        print(f"Real Kalshi Balance: ${real_kalshi_balance_usd:.2f} | Paper Wallet Balance: ${paper_balance_usd:.2f}")
    else:
        print(f"Real Kalshi Balance: Offline/Unconfigured | Paper Wallet Balance: ${paper_balance_usd:.2f}")

    try:
        # Wait 10 seconds for initial WebSocket/REST snapshots to populate
        print("\nSoaking data streams for 10 seconds...")
        await asyncio.sleep(10)

        # 3. Print Data Source Health
        print("\n" + "=" * 70)
        print("  DATA SOURCE HEALTH REPORT")
        print("=" * 70)
        print(orchestrator.health_report())

        # 4. Inspect Snapshots & Active Kalshi Markets
        snapshots = orchestrator.latest_snapshots()
        markets = orchestrator.active_markets()
        print(f"\nDiscovered {len(markets)} active Kalshi markets.")

        # 5. Evaluate Opportunities & Predictions
        print("\n" + "=" * 70)
        print("  MODEL PREDICTIONS & EDGE DETECTION")
        print("=" * 70)

        for asset in ("BTC", "ETH"):
            snap = snapshots.get(asset)
            if snap:
                spot_str = f"${snap.spot_avg_usd:,.2f}" if snap.spot_avg_usd else "n/a"
                kalshi_str = f"{snap.kalshi_midpoint_cents}c" if snap.kalshi_midpoint_cents else "n/a"
                disagree_str = f"{snap.spot_disagreement_pct:.4f}%" if snap.spot_disagreement_pct else "n/a"
                print(f"\n=== {asset} Live Snapshot (v{snap.snapshot_version}) ===")
                print(f"  Spot Avg:     {spot_str}")
                print(f"  Disagreement: {disagree_str}")
                print(f"  Kalshi Mid:   {kalshi_str}")

            # Check paper auto-trader decisions
            if orchestrator.auto_trader:
                decisions = [d for d in orchestrator.auto_trader.recent_decisions if d.asset == asset]
                if decisions:
                    d = decisions[-1]
                    dec_str = (
                        f"  Auto-Trade Decision: traded={d.traded}, model={d.model_name}, "
                        f"P(YES)={d.yes_probability:.1%}, edge={d.edge_pct:+.2f}%, skip_reason='{d.skip_reason}'"
                    )
                    print(dec_str)

        # 6. Perform a Manual Paper Trade Demonstration if edge or test signal exists
        paper_venue = orchestrator.paper_venue
        if paper_venue:
            print("\n" + "=" * 70)
            print("  PAPER VENUE & WALLET STATUS")
            print("=" * 70)

            wallet = paper_venue.get_wallet()
            print(f"  Paper Wallet Balance: ${wallet.balance:,.2f}")
            print(f"  Total Paper PnL:     ${wallet.total_pnl:,.2f}")
            print(f"  Total Trades:        {wallet.total_trades}")

            # If no open positions, place a sample paper limit/market buy to demonstrate paper venue fill logic
            positions = paper_venue.get_open_positions()
            print(f"  Open Positions:       {len(positions)}")
            if not positions and markets:
                ticker = markets[0].get("ticker", "KXBTC15M-DEMO")
                mid = markets[0].get("midpoint_cents", 50) or 50
                print(f"\nExecuting test paper order: Buy 2 YES contracts for {ticker} @ {mid}c...")
                order = paper_venue.submit_order(
                    asset="BTC",
                    side="yes",
                    contracts=2,
                    ticker=ticker,
                    midpoint_cents=float(mid),
                    model_version="gemini_flash_demo",
                )
                order_str = (
                    f"  Order ID: {order.order_id} | Status: {order.status} | "
                    f"Fill Price: {order.fill_price_cents}c | Cost: ${order.fill_cost_usd:.2f}"
                )
                print(order_str)

                # Log to journal
                entry = journal.start_entry(
                    asset="BTC",
                    observation=f"Sample paper trade for {ticker} @ {mid}c",
                    hypothesis="Testing paper order execution lifecycle",
                )
                journal.add_note(entry.entry_id, f"Filled order {order.order_id} status={order.status}")

            # Re-check wallet after trade
            wallet = paper_venue.get_wallet()
            positions = paper_venue.get_open_positions()
            print(f"\nUpdated Paper Wallet Balance: ${wallet.balance:,.2f}")
            print(f"Updated Open Positions: {len(positions)}")
            for p in positions:
                pos_info = (
                    f"  Position: {p.contracts}x {p.side.upper()} {p.ticker} "
                    f"@ {p.avg_entry_cents:.1f}c (Cost: ${p.total_cost_usd:.2f})"
                )
                print(pos_info)

        # Soak for remaining duration
        remaining = max(1, duration_seconds - 15)
        print(f"\nRunning active session for {remaining} seconds...")
        await asyncio.sleep(remaining)

    finally:
        print("\nShutting down session gracefully...")
        if orchestrator.auto_trader:
            orchestrator.auto_trader.disable()
        await orchestrator.stop()
        machine.transition(VesselState.FULL_STOP, reason="AI Operator: Session End")
        print(f"Vessel State -> {machine.current_state.value}")
        print("Session completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_trading_session(900))
