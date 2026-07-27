import json
from typing import Any

from arbitr8der_package.data_contracts.event_data_models import SourceHealthStatus


def format_snapshot_human(snap: Any) -> str:
    """Format a HotSnapshot as human-readable text."""
    lines: list[str] = []
    lines.append(f"=== {snap.asset.value} Snapshot v{snap.snapshot_version} ===")
    lines.append(f"  Created:      {snap.created_ts.isoformat()}")

    if snap.spot_avg_usd is not None:
        lines.append(f"  Spot avg:     ${snap.spot_avg_usd:,.2f}")
    else:
        lines.append("  Spot avg:     (no data)")

    if snap.spot_disagreement_pct is not None:
        lines.append(f"  Disagreement: {snap.spot_disagreement_pct:.6f}%")
    else:
        lines.append("  Disagreement: (no data)")

    if snap.kalshi_midpoint_cents is not None:
        lines.append(f"  Kalshi mid:   {snap.kalshi_midpoint_cents}c")
    else:
        lines.append("  Kalshi mid:   (no data)")

    # Source health
    if snap.source_health:
        lines.append("  Sources:")
        for src, status in snap.source_health.items():
            marker = "ok" if status == SourceHealthStatus.HEALTHY else status.value
            lines.append(f"    {src:25s} {marker}")

    if snap.stale_sources:
        lines.append(f"  Stale:  {', '.join(snap.stale_sources)}")
    if snap.missing_sources:
        lines.append(f"  Missing: {', '.join(snap.missing_sources)}")

    return "\n".join(lines)


def format_snapshot_json(snap: Any) -> str:
    """Format a HotSnapshot as JSON."""
    return json.dumps(snap.model_dump(mode="json"), indent=2)

def format_positions_human(positions, wallet, latest_snapshot_func):
    if not positions:
        print("No open positions.")
        print(f"Wallet: ${wallet.balance:.2f} (PnL: ${wallet.total_pnl:+.2f})")
        return

    print(f"Open positions ({len(positions)}):")
    print(
        f"{'TICKER':30s} {'SIDE':5s} {'CONTRACTS':>10s} {'AVG ENTRY':>10s} {'MID':>10s} {'COST':>10s} {'VALUE':>10s} {'UNREAL PNL':>12s}"
    )
    print("-" * 104)

    total_cost = 0.0
    total_value = 0.0
    total_pnl = 0.0

    for p in positions:
        cost = p.total_cost_usd
        total_cost += cost

        mid_cents = None
        snapshot = latest_snapshot_func(p.asset)
        if snapshot and snapshot.kalshi_midpoint_cents is not None:
            raw_val = snapshot.kalshi_midpoint_cents
            if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
                mid_cents = raw_val

        if mid_cents is not None:
            if p.side.lower() == "yes":
                value = p.contracts * mid_cents / 100.0
            else:
                value = p.contracts * (100.0 - mid_cents) / 100.0
            pnl = value - cost
            total_value += value
            total_pnl += pnl

            mid_str = f"{mid_cents:.1f}c"
            val_str = f"${value:.2f}"
            pnl_str = f"${pnl:+.2f}"
        else:
            mid_str = "N/A"
            val_str = "N/A"
            pnl_str = "N/A"

        print(
            f"{p.ticker:30s} {p.side:5s} {p.contracts:>10d} {p.avg_entry_cents:>9.1f}c {mid_str:>10s} {cost:>10.2f} {val_str:>10s} {pnl_str:>12s}"
        )

    print("-" * 104)
    val_summary = f"${total_value:.2f}" if total_value > 0 else "N/A"
    pnl_summary = f"${total_pnl:+.2f}" if total_value > 0 else "N/A"
    print(
        f"{'Total exposure:':30s} {'':5s} {'':>10s} {'':>10s} {'':>10s} {total_cost:>10.2f} {val_summary:>10s} {pnl_summary:>12s}"
    )
    print(f"Wallet: ${wallet.balance:.2f} (PnL: ${wallet.total_pnl:+.2f})")

def format_pending_orders_human(pending):
    if not pending:
        print("No pending orders.")
        return

    print(f"Pending orders ({len(pending)}):")
    print(f"{'ORDER ID':20s} {'ASSET':6s} {'SIDE':5s} {'CONTRACTS':>10s} {'LIMIT':>8s} {'TICKER':30s}")
    print("-" * 85)

    for o in pending:
        limit = f"{o.limit_cents}c" if o.limit_cents else "mkt"
        print(f"{o.order_id:20s} {o.asset:6s} {o.side:5s} {o.contracts:>10d} {limit:>8s} {o.ticker:30s}")

def format_wallet_human(wallet):
    print("=== PAPER Wallet ===")
    print(f"  Balance:       ${wallet.balance:.2f}")
    print(f"  Starting:      ${wallet.starting_balance:.2f}")
    print(f"  Total PnL:     ${wallet.total_pnl:+.2f}")
    print(f"  Total trades:  {wallet.total_trades}")

    if wallet.total_trades > 0:
        win_rate = wallet.winning_trades / wallet.total_trades * 100
        print(f"  Win rate:      {win_rate:.1f}% ({wallet.winning_trades}W / {wallet.losing_trades}L)")

def format_risk_status_human(status):
    print("=== Risk Status ===")
    print(f"  Wallet mode:       {status['wallet_mode']}")
    print(f"  Balance:           ${status['balance']:.2f}")
    print(f"  Session PnL:       ${status['session_pnl']:+.2f}")
    print(f"  Daily PnL:         ${status['daily_pnl']:+.2f}")
    print(f"  Session loss cap:  ${status['session_loss_cap']:.2f}")
    print(f"  Daily loss cap:    ${status['daily_loss_cap']:.2f}")
    print(f"  Emergency stop:    {'ACTIVE' if status['emergency_stop'] else 'off'}")
    print(f"  Cooldown:          {status['cooldown_seconds']}s")

    if status['open_positions']:
        print("  Open positions:")
        for asset, count in status['open_positions'].items():
            exposure = status['exposure'].get(asset, 0.0)
            print(f"    {asset}: {count} positions (${exposure:.2f} exposure)")
