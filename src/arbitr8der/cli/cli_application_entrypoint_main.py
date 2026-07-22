"""ARBITR8DER CLI — the command interface for the AI trading studio.

Usage:
    arbitr8der status                     # Full system status
    arbitr8der vessel battery             # Transition to Battery mode
    arbitr8der vessel forward             # Transition to Full_Forward
    arbitr8der vessel stop                # Emergency stop
    arbitr8der snapshot                   # Current hot state
    arbitr8der health                     # Stream health check
    arbitr8der wallet                     # Wallet profile info
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

import typer

from ..application_version_identifier_module import __version__
from ..config.typed_configuration_settings_module import load_settings, Settings
from ..vessel.trading_vessel_state_machine import TradingVesselState

# ── App setup ──────────────────────────────────────────────────────────
app = typer.Typer(
    name="arbitr8der",
    help="ARBITR8DER Trading Studio — AI-operated Kalshi trading.",
    add_completion=False,
)

# Sub-commands
vessel_command_group = typer.Typer(name="vessel", help="Vessel state machine commands")
app.add_typer(vessel_command_group, name="vessel")

# ── Global state (loaded once at startup) ──────────────────────────────
_cached_application_settings: Optional[Settings] = None


def _get_cached_application_settings() -> Settings:
    global _cached_application_settings
    if _cached_application_settings is None:
        _cached_application_settings = load_settings()
    return _cached_application_settings


# ── Status ─────────────────────────────────────────────────────────────
@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
) -> None:
    """Show full system status: vessel state, wallet, streams, DB health."""
    settings = _get_cached_application_settings()

    from ..vessel.trading_vessel_state_machine import TradingVesselStateMachine
    from ..storage.wallet_profile_configuration_manager import resolve_wallet_profile
    from ..storage.database_schema_migration_handler import init_schema
    from ..storage.sqlite_database_connection_manager import SqliteDatabaseConnectionManager

    state_machine = TradingVesselStateMachine(
        state_file=__import__("pathlib").Path(settings.state_file)
    )
    vessel_state = state_machine.state

    wallet = resolve_wallet_profile(
        requested_mode=settings.wallet_mode.value,
        api_key_id=settings.kalshi_api_key_id,
        private_key_path=settings.kalshi_private_key_path,
    )

    db = SqliteDatabaseConnectionManager(settings.db_path)
    schema_version = 0
    db_healthy = False
    try:
        schema_version = init_schema(db)
        db_healthy = db.is_connected
    except Exception as exc:
        db_healthy = False

    # ── Display ────────────────────────────────────────────────────────
    state_color = {
        TradingVesselState.FULL_STOP: "🔴",
        TradingVesselState.BATTERY: "🟡",
        TradingVesselState.FULL_FORWARD: "🟢",
    }

    print(f"\n{'='*50}")
    print(f"  ARBITR8DER v{__version__}")
    print(f"{'='*50}")
    print(f"  Vessel State:  {state_color.get(vessel_state, '❓')} {vessel_state.value}")
    print(f"  Can Trade:     {'YES' if state_machine.can_trade else 'NO'}")
    print(f"  Can Stream:    {'YES' if state_machine.can_collect_data else 'NO'}")
    print(f"  Transitions:   {state_machine.transition_count}")
    print()
    print(f"  Wallet Mode:   {wallet.mode.value}")
    print(f"  Balance Est:   ${wallet.balance_estimate_cents / 100:.2f}")
    print(f"  Kalshi Auth:   {'✅ Configured' if settings.kalshi_auth_configured else '❌ Missing credentials'}")
    print()
    print(f"  Database:      {'✅ Healthy' if db_healthy else '❌ Unhealthy'}")
    print(f"  Schema:        v{schema_version}")
    print(f"  DB Path:       {settings.db_path}")

    if verbose:
        print()
        print(f"  Target Assets: {', '.join(settings.target_assets)}")
        print(f"  BTC Ticker:    {settings.btc_ticker_prefix}")
        print(f"  ETH Ticker:    {settings.eth_ticker_prefix}")
        print(f"  Kalshi URL:    {settings.kalshi_base_url}")
        print(f"  Risk Floor:    -{settings.session_floor_pct*100:.0f}% / -{settings.rolling_floor_pct*100:.0f}%")
        print(f"  Daily Cap:     -{settings.daily_loss_cap_pct*100:.0f}%")

    print(f"{'='*50}\n")

    if not db_healthy:
        raise typer.Exit(1)


# ── Vessel Commands ────────────────────────────────────────────────────
@vessel_command_group.command("battery")
def vessel_battery() -> None:
    """Transition vessel to Battery mode (stream data, no trading)."""
    settings = _get_cached_application_settings()
    from ..vessel.trading_vessel_state_machine import TradingVesselStateMachine
    from pathlib import Path

    vessel_state_machine = TradingVesselStateMachine(state_file=Path(settings.state_file))
    if not vessel_state_machine.can_transition_to(TradingVesselState.BATTERY):
        print(f"❌ Cannot transition to BATTERY from {vessel_state_machine.state.value}")
        raise typer.Exit(1)

    result = vessel_state_machine.transition_to(TradingVesselState.BATTERY)
    print(f"✅ Vessel: {result['from']} → {result['to']}")
    print(f"   Data streams: ACTIVE | Trading: DISABLED")
    print(f"   Transition #{result['transition_number']}")


@vessel_command_group.command("forward")
def vessel_forward(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Confirm live trading"),
) -> None:
    """Transition vessel to Full_Forward (live trading enabled)."""
    settings = _get_cached_application_settings()
    from ..vessel.trading_vessel_state_machine import TradingVesselStateMachine
    from ..storage.wallet_profile_configuration_manager import resolve_wallet_profile
    from pathlib import Path

    wallet = resolve_wallet_profile(
        requested_mode=settings.wallet_mode.value,
        api_key_id=settings.kalshi_api_key_id,
        private_key_path=settings.kalshi_private_key_path,
    )

    if wallet.mode.value == "PAPER" and not confirm:
        print("⚠️  Wallet is in PAPER mode. Use --confirm to proceed.")
        print("   No real money will be used.")
        confirm = typer.confirm("Proceed with PAPER trading?")

    vessel_state_machine = TradingVesselStateMachine(state_file=Path(settings.state_file))
    if not vessel_state_machine.can_transition_to(TradingVesselState.FULL_FORWARD):
        print(f"❌ Cannot transition to FULL_FORWARD from {vessel_state_machine.state.value}")
        raise typer.Exit(1)

    if not confirm:
        print("❌ Transition cancelled.")
        raise typer.Exit(0)

    result = vessel_state_machine.transition_to(TradingVesselState.FULL_FORWARD)
    print(f"🚀 Vessel: {result['from']} → {result['to']}")
    print(f"   Wallet: {wallet.mode.value} | Balance: ${wallet.balance_estimate_cents / 100:.2f}")
    print(f"   Trading: {'ENABLED' if vessel_state_machine.can_trade else 'DISABLED'}")
    print(f"   Transition #{result['transition_number']}")


@vessel_command_group.command("stop")
def vessel_stop() -> None:
    """Emergency stop — halt ALL processes immediately."""
    settings = _get_cached_application_settings()
    from ..vessel.trading_vessel_state_machine import TradingVesselStateMachine
    from pathlib import Path

    vessel_state_machine = TradingVesselStateMachine(state_file=Path(settings.state_file))
    result = vessel_state_machine.emergency_stop()

    print(f"🛑 EMERGENCY STOP")
    print(f"   {result['from']} → {result['to']}")
    print(f"   {result['message']}")
    print(f"   All trades cancelled. All streams halted.")


@vessel_command_group.command("status")
def vessel_status() -> None:
    """Show current vessel state and transition history."""
    settings = _get_cached_application_settings()
    from ..vessel.trading_vessel_state_machine import TradingVesselStateMachine
    from pathlib import Path

    vessel_state_machine = TradingVesselStateMachine(state_file=Path(settings.state_file))
    s = vessel_state_machine.summary()

    state_emoji = {
        "FULL_STOP": "🔴",
        "BATTERY": "🟡",
        "FULL_FORWARD": "🟢",
    }

    print(f"\n  Vessel State: {state_emoji.get(s['state'], '❓')} {s['state']}")
    print(f"  Can Trade:    {'✅ YES' if s['can_trade'] else '❌ NO'}")
    print(f"  Can Stream:   {'✅ YES' if s['can_collect_data'] else '❌ NO'}")
    print(f"  Transitions:  {s['transitions']}\n")


# ── Snapshot & Health ──────────────────────────────────────────────────
@app.command()
def snapshot() -> None:
    """Show current hot state snapshot (all live data)."""
    from ..market_data.thread_safe_hot_state_manager import ThreadSafeHotStateManager
    hs = ThreadSafeHotStateManager()
    snap = hs.snapshot()
    print(f"\n  Hot State Generation: {snap.generation}")
    print(f"  Last Update: {'Never (empty)' if snap.timestamp == 0 else snap.timestamp}")
    print(f"  Active Tickers: {dict(snap.active_tickers)}")
    print(f"  Spot Prices: {dict(snap.spot_prices)}")
    print(f"  Stream Health: {dict(snap.stream_health)}\n")


@app.command()
def health() -> None:
    """Show stream health status."""
    from ..market_data.thread_safe_hot_state_manager import ThreadSafeHotStateManager
    hs = ThreadSafeHotStateManager()
    snap = hs.snapshot()
    if not snap.stream_health:
        print("\n  No stream data yet. Start with: arbitr8der vessel battery\n")
        return
    print("\n  Stream Health:")
    for source, healthy in snap.stream_health.items():
        icon = "✅" if healthy else "❌"
        print(f"    {icon} {source}")
    print()


@app.command()
def wallet() -> None:
    """Show wallet profile and credentials status."""
    settings = _get_cached_application_settings()
    from ..storage.wallet_profile_configuration_manager import resolve_wallet_profile

    wallet = resolve_wallet_profile(
        requested_mode=settings.wallet_mode.value,
        api_key_id=settings.kalshi_api_key_id,
        private_key_path=settings.kalshi_private_key_path,
    )

    info = wallet.to_dict()
    print(f"\n  Wallet Mode:    {info['mode']}")
    print(f"  API Key:        {info['kalshi_api_key_id'] or '(none)'}")
    print(f"  Private Key:    {'✅ Found' if __import__('pathlib').Path(info['kalshi_private_key_path']).exists() else '❌ Missing'}")
    print(f"  Balance Est:    ${info['balance_estimate_cents'] / 100:.2f}")
    print(f"  Can Trade:      {'✅' if info['can_trade'] else '❌'}\n")


# ── Entry point ────────────────────────────────────────────────────────
def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    app()


if __name__ == "__main__":
    main()
