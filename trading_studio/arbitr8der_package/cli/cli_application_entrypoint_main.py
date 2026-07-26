"""ARBITR8DER CLI entrypoint.

Usage:
    arb status [--json]
    arb snapshot [--json]
    arb health
    arb markets
    arb predict
    arb vessel status
    arb vessel battery
    arb vessel forward
    arb vessel stop
    arb forward start
"""

import json
import time
from datetime import datetime, timezone

import typer

from arbitr8der_package import __version__
from arbitr8der_package.config.typed_configuration_settings_module import load_settings
from arbitr8der_package.vessel.vessel_state_machine import (
    IllegalTransitionError,
    VesselState,
    VesselStateMachine,
)

app = typer.Typer(
    name="arb",
    help="ARBITR8DER — local AI trading studio for Kalshi binary markets",
    no_args_is_help=True,
)

vessel_app = typer.Typer(help="Vessel state management.")
app.add_typer(vessel_app, name="vessel")

forward_app = typer.Typer(help="Trading session commands.")
app.add_typer(forward_app, name="forward")


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(f"arbitr8der {__version__}")


@app.command()
def status(json_output: bool = typer.Option(False, "--json", help="Output as JSON")) -> None:
    """Show vessel state, mode, and connections."""
    settings = load_settings()
    machine = VesselStateMachine()
    state_info = machine.get_state()

    if json_output:
        output = {
            "version": __version__,
            "vessel_state": state_info["vessel_state"],
            "wallet_mode": settings.wallet_mode,
            "trading_mode": settings.trading_mode,
            "connections": "not connected",
        }
        typer.echo(json.dumps(output, indent=2))
    else:
        typer.echo(f"Version:    {__version__}")
        typer.echo(f"Vessel:     {state_info['vessel_state']}")
        typer.echo(f"Wallet:     {settings.wallet_mode}")
        typer.echo(f"Trading:    {settings.trading_mode}")
        typer.echo("Connections: (none — data sources not yet implemented)")


@app.command()
def snapshot(json_output: bool = typer.Option(False, "--json", help="Output as JSON")) -> None:
    """Show the latest HotSnapshot built from cached provider observations.

    Reads the last observation from each data source and merges them into
    a single point-in-time snapshot. Sources that have never been updated
    are marked DISCONNECTED.
    """
    from arbitr8der_package.data_contracts.event_data_models import (
        Asset,
        CoinGeckoMacroEvent,
        KalshiOrderBookEvent,
        PolymarketSentimentEvent,
        PriceObservationEvent,
        ProviderSource,
        SourceHealthStatus,
    )
    from arbitr8der_package.data_contracts.hot_snapshot_merger import SnapshotMerger
    from arbitr8der_package.data_sources.binance_spot_price_stream import BinanceSpotPriceStream
    from arbitr8der_package.data_sources.coinbase_spot_price_stream import CoinbaseSpotPriceStream
    from arbitr8der_package.data_sources.coingecko_macro_data_poller import CoinGeckoMacroDataPoller
    from arbitr8der_package.data_sources.polymarket_sentiment_analysis_poller import PolymarketSentimentPoller

    now = datetime.now(timezone.utc)
    merger = SnapshotMerger(now_fn=lambda: now)

    # Feed cached Binance observations
    binance = BinanceSpotPriceStream()
    for sym, obs in binance.last_observations.items():
        asset = Asset.BTC if sym.upper().startswith("BTC") else Asset.ETH
        event = PriceObservationEvent(
            provider_event_id=f"binance-cache-{sym}",
            provider_ts=datetime.fromtimestamp(obs.trade_ts, tz=timezone.utc) if obs.trade_ts else now,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            asset=asset,
            price=obs.price,
        )
        merger.update_binance(asset, event)

    # Feed cached Coinbase observations
    coinbase = CoinbaseSpotPriceStream()
    for pid, obs in coinbase.last_observations.items():
        asset = Asset.BTC if "BTC" in pid.upper() else Asset.ETH
        event = PriceObservationEvent(
            provider_event_id=f"coinbase-cache-{pid}",
            provider_ts=now,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            asset=asset,
            price=obs.price,
            bid=obs.bid,
            ask=obs.ask,
            volume_24h=obs.volume_24h,
        )
        merger.update_coinbase(asset, event)

    # Feed cached CoinGecko observations
    coingecko = CoinGeckoMacroDataPoller()
    for asset_str, obs in coingecko.last_observations.items():
        asset = Asset.BTC if obs.asset.upper() == "BTC" else Asset.ETH
        event = CoinGeckoMacroEvent(
            provider_event_id=f"coingecko-cache-{asset_str}",
            provider_ts=now,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            asset=asset,
            market_cap_usd=obs.market_cap_usd,
            price_change_24h_pct=obs.price_change_24h_pct,
            total_volume_usd=obs.volume_24h_usd,
        )
        merger.update_coingecko(asset, event)

    snapshots = merger.build_snapshots()
    if not snapshots:
        typer.echo('{"status": "no assets tracked"}')
        return

    for snap in snapshots:
        if json_output:
            typer.echo(json.dumps(snap.model_dump(mode="json"), indent=2))
        else:
            typer.echo(f"=== {snap.asset.value} Snapshot v{snap.snapshot_version} ===")
            typer.echo(f"  Created:      {snap.created_ts.isoformat()}")
            typer.echo(f"  Spot avg:     ${snap.spot_avg_usd:,.2f}" if snap.spot_avg_usd else "  Spot avg:     (no data)")
            typer.echo(f"  Disagreement: {snap.spot_disagreement_pct:.6f}%" if snap.spot_disagreement_pct is not None else "  Disagreement: (no data)")
            typer.echo(f"  Kalshi mid:   {snap.kalshi_midpoint_cents}c" if snap.kalshi_midpoint_cents else "  Kalshi mid:   (no data)")
            if snap.source_health:
                typer.echo("  Sources:")
                for src, status in snap.source_health.items():
                    marker = "ok" if status == SourceHealthStatus.HEALTHY else status.value
                    typer.echo(f"    {src:25s} {marker}")
            if snap.stale_sources:
                typer.echo(f"  Stale:  {', '.join(snap.stale_sources)}")
            if snap.missing_sources:
                typer.echo(f"  Missing: {', '.join(snap.missing_sources)}")
            typer.echo()


@app.command()
def health() -> None:
    """Show health status of all data sources.

    Reports age, event count, error count, and reconnect count for each
    source. Identifies stale or disconnected sources.
    """
    from arbitr8der_package.data_sources.source_health_monitor import SourceHealthMonitor

    monitor = SourceHealthMonitor()
    # Report that no sources are active (CLI-only, not running orchestrator)
    typer.echo("Health report (CLI mode — orchestrator not running)")
    typer.echo("  No active data sources. Start the orchestrator for live health data.")
    typer.echo("")
    typer.echo("  Run 'arb vessel battery' to start data collection mode.")


@app.command()
def markets() -> None:
    """Show active Kalshi BTC/ETH 15-minute markets."""
    import asyncio

    from arbitr8der_package.data_sources.kalshi_rest_market_discovery_client import (
        KalshiRestMarketDiscoveryClient,
    )

    typer.echo("Fetching active Kalshi markets...")

    async def _fetch() -> list:
        client = KalshiRestMarketDiscoveryClient()
        return await client.discover_active_markets()

    try:
        markets_list = asyncio.run(_fetch())
    except Exception as exc:
        typer.echo(f"Error fetching markets: {exc}", err=True)
        raise typer.Exit(1)

    if not markets_list:
        typer.echo("No active BTC/ETH 15-minute markets found.")
        return

    typer.echo(f"Found {len(markets_list)} active markets:")
    typer.echo("")
    for m in markets_list:
        mid = f"{m.midpoint_cents}c" if m.midpoint_cents else "n/a"
        typer.echo(f"  {m.ticker}")
        typer.echo(f"    Status: {m.status}  Midpoint: {mid}")
        if m.close_time:
            typer.echo(f"    Closes: {m.close_time}")
        typer.echo()


@app.command()
def predict() -> None:
    """Run focused BTC/ETH prediction."""
    typer.echo("Prediction engine not yet implemented.")


# ---------------------------------------------------------------------------
# Vessel subcommands
# ---------------------------------------------------------------------------

@vessel_app.command(name="status")
def vessel_status() -> None:
    """Show current vessel state and recent audit log."""
    machine = VesselStateMachine()
    info = machine.get_state()
    typer.echo(f"Vessel state: {info['vessel_state']}")
    typer.echo(f"Last activity: {info['last_activity_ts']:.0f}")
    if info["audit_log"]:
        typer.echo("Recent transitions:")
        for entry in info["audit_log"][-5:]:
            typer.echo(f"  {entry['from']} -> {entry['to']} ({entry['reason']})")


@vessel_app.command(name="battery")
def vessel_battery() -> None:
    """Transition to Battery (data-collection mode, no live trading)."""
    machine = VesselStateMachine()
    try:
        machine.transition(VesselState.BATTERY, reason="operator: battery command")
        typer.echo("Vessel -> Battery")
    except IllegalTransitionError as exc:
        typer.echo(f"Cannot transition: {exc}", err=True)
        raise typer.Exit(1)


@vessel_app.command(name="forward")
def vessel_forward() -> None:
    """Transition to Full_Forward (live trading mode)."""
    machine = VesselStateMachine()
    try:
        machine.transition(VesselState.BATTERY, reason="operator: arm for forward")
        machine.transition(VesselState.FULL_FORWARD, reason="operator: forward command")
        typer.echo("Vessel -> Full_Forward")
    except IllegalTransitionError as exc:
        typer.echo(f"Cannot transition: {exc}", err=True)
        raise typer.Exit(1)


@vessel_app.command(name="stop")
def vessel_stop() -> None:
    """Force vessel to Full_Stop (safe shutdown)."""
    machine = VesselStateMachine()
    state = machine.current_state
    if state != VesselState.FULL_STOP:
        machine.transition(VesselState.FULL_STOP, reason="operator: stop command")
    typer.echo("Vessel -> Full_Stop")


# ---------------------------------------------------------------------------
# Forward subcommands
# ---------------------------------------------------------------------------

@forward_app.command(name="start")
def forward_start(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Enter interactive trading REPL."""
    from arbitr8der_package.cli.interactive_trading_repl_loop import start_repl
    start_repl(json_output=json_output)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
