from datetime import UTC, datetime

from arbitr8der_package.cli.repl_command_parser import parse_buy_args, parse_sell_args
from arbitr8der_package.data_contracts.event_data_models import Asset
from arbitr8der_package.risk.risk_controls_module import OrderIntent


def handle_buy_command(args, orchestrator, risk, venue, reconciler, current_state_value, last_snapshot_version_dict):
    parsed, err = parse_buy_args(args)
    if err:
        print(err)
        return

    asset = parsed["asset"]
    side = parsed["side"]
    contracts = parsed["contracts"]
    limit_cents = parsed["limit_cents"]

    snapshots = orchestrator.latest_snapshots()
    snap = snapshots.get(Asset(asset))
    midpoint_cents = None
    snapshot_version = None

    if snap:
        midpoint_cents = snap.kalshi_midpoint_cents
        snapshot_version = snap.snapshot_version
        last_snapshot_version_dict[asset] = snapshot_version

    ticker = f"KX{asset}15M-PENDING"
    markets = orchestrator.active_markets()
    for m in markets:
        if asset in m.get("ticker", "").upper():
            ticker = m["ticker"]
            break

    intent = OrderIntent(
        asset=asset,
        side=side,
        contracts=contracts,
        ticker=ticker,
        limit_cents=limit_cents,
        snapshot_version=snapshot_version,
    )

    reconciler.record_intent(
        order_id=f"intent_{asset}_{side}_{contracts}",
        asset=asset,
        side=side,
        contracts=contracts,
        ticker=ticker,
        limit_cents=limit_cents,
        snapshot_version=snapshot_version,
        midpoint_cents=midpoint_cents,
    )

    book_age = None
    if snap:
        age = (datetime.now(UTC) - snap.created_ts).total_seconds()
        book_age = age

    verdict = risk.check(
        intent,
        vessel_state=current_state_value,
        current_book_age_seconds=book_age,
    )

    reconciler.record_risk_check(
        order_id=intent.ticker,
        passed=verdict.passed,
        block_reason=verdict.block_reason.value if verdict.block_reason else None,
        block_detail=verdict.block_detail,
        warnings=verdict.warnings,
    )

    if not verdict.passed:
        print(f"ORDER BLOCKED: {verdict.block_detail}")
        if verdict.warnings:
            for w in verdict.warnings:
                print(f"  Warning: {w}")
        return

    order = venue.submit_order(
        asset=asset,
        side=side,
        contracts=contracts,
        ticker=ticker,
        limit_cents=limit_cents,
        midpoint_cents=midpoint_cents,
        snapshot_version=snapshot_version,
    )

    if order.status == "filled":
        risk.record_fill(asset, order.fill_cost_usd or 0.0)
        reconciler.record_fill(
            order_id=order.order_id,
            fill_price_cents=order.fill_price_cents or 0.0,
            fill_cost_usd=order.fill_cost_usd or 0.0,
            midpoint_at_fill=midpoint_cents,
        )
        print(f"FILLED: {side.upper()} {contracts} {asset} at {order.fill_price_cents:.1f}c (${order.fill_cost_usd:.2f})")
        print(f"Ticker: {ticker}  Order: {order.order_id}")

        if verdict.warnings:
            for w in verdict.warnings:
                print(f"  Warning: {w}")
    elif order.status == "pending":
        print(f"PENDING: {side.upper()} {contracts} {asset} at {limit_cents}c (limit order)")
        print(f"Ticker: {ticker}  Order: {order.order_id}")
    else:
        print(f"ORDER CANCELLED: {order.order_id}")

def handle_sell_command(args, orchestrator, risk, venue, reconciler):
    parsed, err = parse_sell_args(args)
    if err:
        print(err)
        return

    asset = parsed["asset"]
    ticker = parsed["ticker"]

    positions = venue.get_open_positions()
    position = None
    for p in positions:
        if p.ticker == ticker and p.asset == asset:
            position = p
            break

    if position is None:
        print(f"No open position found for {asset} {ticker}")
        return

    filled_orders = venue.get_filled_orders()
    order = None
    for o in filled_orders:
        if o.ticker == ticker and o.side == position.side:
            order = o
            break

    if order is None:
        print(f"No filled order found for {ticker}")
        return

    snap = orchestrator.latest_snapshots().get(Asset(asset))
    if snap and snap.kalshi_midpoint_cents is not None:
        current_mid = snap.kalshi_midpoint_cents
        outcome = (1 if current_mid > 50 else 0) if position.side == "yes" else 0 if current_mid > 50 else 1
    else:
        outcome = 1

    settled = venue.settle_order(order.order_id, outcome)
    if settled:
        pnl = settled.pnl or 0.0
        risk.record_settlement(asset, pnl, position.total_cost_usd)
        reconciler.record_settlement(
            order_id=order.order_id,
            outcome=outcome,
            pnl=pnl,
            settlement_price_cents=100.0 if outcome == 1 else 0.0,
        )
        outcome_str = "YES" if outcome == 1 else "NO"
        print(f"SETTLED: {ticker} {position.side.upper()} -> {outcome_str}")
        print(f"PnL: ${pnl:+.2f}")
    else:
        print(f"Failed to settle {ticker}")

def handle_cancel_command(args, venue):
    ticker = args.strip()
    if not ticker:
        print("Usage: cancel TICKER")
        return

    pending = venue.get_pending_orders()
    order = None
    for o in pending:
        if o.ticker == ticker:
            order = o
            break

    if order is None:
        print(f"No pending order found for {ticker}")
        return

    cancelled = venue.cancel_order(order.order_id)
    if cancelled:
        print(f"Cancelled: {cancelled.order_id} ({cancelled.side.upper()} {cancelled.contracts} {cancelled.asset})")
    else:
        print(f"Failed to cancel {ticker}")
