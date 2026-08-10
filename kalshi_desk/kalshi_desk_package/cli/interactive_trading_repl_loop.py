"""Interactive trading REPL — the main operator loop for ARBITR8DER.

Runs the ingestion orchestrator in a background thread, exposes commands
to inspect data, journal reasoning, and manage vessel state.

Entry: ``arbitr8der forward start``

Phase 7 additions:
  - PAPER trading: buy, sell, pending, cancel, positions
  - Risk controls integrated with vessel state
  - Reconciliation audit trail for all orders
  - Full_Forward required for trading (enforced by risk layer)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kalshi_desk_package.cli.repl_trading_handlers import (
    handle_buy_command,
    handle_cancel_command,
    handle_sell_command,
)
from kalshi_desk_package.cli.repl_view_renderers import (
    format_pending_orders_human,
    format_positions_human,
    format_risk_status_human,
    format_snapshot_human,
    format_snapshot_json,
    format_wallet_human,
)
from kalshi_desk_package.cli.scorecard_module import (
    ScorecardGenerator,
    format_scorecard_human,
    format_scorecard_json,
)
from kalshi_desk_package.cli.session_archive_module import (
    SessionArchive,
    format_archive_summary_human,
)
from kalshi_desk_package.cli.structured_trade_journal_module import (
    JournalEntry,
    TradeJournal,
    format_entry_human,
    format_entry_json,
)
from kalshi_desk_package.config.structured_logging_configuration_module import get_logger
from kalshi_desk_package.data_sources.ingestion_orchestrator import IngestionOrchestrator
from kalshi_desk_package.execution.paper_venue_adapter import PaperVenueAdapter
from kalshi_desk_package.prediction.prediction_scorer import PredictionScorer
from kalshi_desk_package.core.order_reconciliation_module import OrderReconciler
from kalshi_desk_package.core.risk_controls_module import RiskController
from kalshi_desk_package.core.vessel_state_machine import (
    IllegalTransitionError,
    VesselState,
    VesselStateMachine,
)

_format_snapshot_human = format_snapshot_human
_format_snapshot_json = format_snapshot_json
logger = get_logger(__name__)






def _async_worker(loop: asyncio.AbstractEventLoop, orchestrator: IngestionOrchestrator, ready: threading.Event) -> None:
    """Run the orchestrator event loop in a background thread."""

    async def _run() -> None:
        started = await orchestrator.start()
        ready.set()
        if not started:
            logger.error("Orchestrator failed to start")
            return
        # Keep the loop alive while the orchestrator runs, then let any
        # lingering background tasks drain so shutdown is clean.
        while True:
            await asyncio.sleep(0.25)
            if not orchestrator.running:
                pending = [
                    task
                    for task in asyncio.all_tasks()
                    if task is not asyncio.current_task() and not task.done()
                ]
                if not pending:
                    break

    loop.run_until_complete(_run())


def _run_script(script_path: str, json_output: bool = False) -> None:
    """Execute a script file: one command per line, with optional SLEEP <seconds> lines."""
    path = Path(script_path)
    if not path.exists():
        print(f"Script file not found: {script_path}")
        return

    lines = path.read_text().strip().splitlines()
    repl = TradingREPL(json_output=json_output)

    # Start orchestrator
    repl._loop = asyncio.new_event_loop()
    ready = threading.Event()
    repl._worker_thread = threading.Thread(
        target=_async_worker, args=(repl._loop, repl._orchestrator, ready), daemon=True
    )
    repl._worker_thread.start()
    ready.wait(timeout=10.0)
    repl._running = True

    # Same as run(): wire the Binance spot stream so predict has live candles.
    from kalshi_desk_package.data_sources.binance_spot_price_stream import BinanceSpotPriceStream
    repl._binance = BinanceSpotPriceStream()

    print(f"Executing script: {script_path} ({len(lines)} lines)")

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "sleep":
            try:
                secs = float(args)
                print(f"[script] sleeping {secs}s...")
                time.sleep(secs)
            except ValueError:
                print(f"[script] invalid sleep duration: {args}")
            continue

        print(f"[script line {i}] {line}")
        try:
            repl._dispatch(cmd, args)
        except Exception as exc:
            print(f"[script] error: {exc}")

    repl._shutdown()
    print("Script complete.")


class TradingREPL:
    """Interactive trading session controller.

    Runs the data ingestion in a background thread and provides an
    input loop for the operator to inspect data and manage state.
    """

    def __init__(self, json_output: bool = False, session_id: str | None = None) -> None:
        self._json_output = json_output
        self._machine = VesselStateMachine()
        self._orchestrator = IngestionOrchestrator()
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._worker_thread: threading.Thread | None = None
        self._binance: Any = None  # Set after orchestrator starts

        # Phase 6: structured systems
        self._scorer = PredictionScorer()
        self._journal = TradeJournal(session_id=session_id)
        self._archive = SessionArchive(session_id=self._journal.session_id)
        self._scorecard_gen = ScorecardGenerator(
            scorer=self._scorer, journal=self._journal, archive=self._archive,
        )

        # Phase 7: trading systems
        self._risk = RiskController(wallet_mode="paper")
        self._venue = PaperVenueAdapter()
        self._reconciler = OrderReconciler()
        self._last_snapshot_version: dict[str, int] = {}  # asset -> version

        # Legacy text journal (kept for backward compat)
        self._journal_lines: list[str] = []
        self._tick_count = 0
        self._predictions: list[Any] = []
        self._current_journal_entry: JournalEntry | None = None

    def run(self) -> None:
        """Enter the interactive REPL loop."""
        # Transition to Battery
        try:
            if self._machine.current_state == VesselState.FULL_STOP:
                prev = self._machine.current_state.value
                self._machine.transition(VesselState.BATTERY, reason="operator: forward start")
                self._archive.record_vessel_transition(prev, "battery", "operator: forward start")
        except IllegalTransitionError:
            pass

        print(f"Vessel: {self._machine.current_state.value}")
        print(f"Session: {self._journal.session_id}")
        print("Starting data ingestion...")

        # Start orchestrator in background thread
        self._loop = asyncio.new_event_loop()
        ready = threading.Event()
        self._worker_thread = threading.Thread(
            target=_async_worker, args=(self._loop, self._orchestrator, ready), daemon=True
        )
        self._worker_thread.start()
        ready.wait(timeout=10.0)

        # Grab references to data providers for feature extraction
        from kalshi_desk_package.data_sources.binance_spot_price_stream import BinanceSpotPriceStream
        self._binance = BinanceSpotPriceStream()

        # Share the orchestrator-owned paper venue and risk controller with the REPL.
        if self._orchestrator.paper_venue is not None:
            self._venue = self._orchestrator.paper_venue
        if self._orchestrator.risk_controller is not None:
            self._risk = self._orchestrator.risk_controller
        if self._orchestrator.auto_trader is not None:
            self._orchestrator.auto_trader.set_vessel_state_getter(
                lambda: self._machine.current_state.value.lower()
            )

        if not self._orchestrator.running:
            print("WARNING: Orchestrator failed to start. Data may be unavailable.")
            print("Check lease file or network connectivity.")

        self._running = True
        print("Data ingestion running. Type 'help' for commands.\n")

        # Settle any expired paper positions from previous runs on startup
        if self._venue is not None:
            self._sync_settle_expired_positions()

        # Reset the paper venue wallet for this session and sync the risk gate
        # balance so both agree on the real Kalshi balance (or the fallback).
        if self._venue is not None and self._risk is not None and self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._venue.reset_wallet_for_new_session(self._orchestrator.discovery_client),
                    self._loop,
                )
                reset_balance_usd = future.result(timeout=10.0)
                self._risk.set_balance(reset_balance_usd)
                print(f"Paper wallet reset for new session: ${reset_balance_usd:.2f}")
            except Exception as exc:
                logger.warning("Failed to reset paper wallet for new session: %s", exc)
                self._risk.set_balance(self._venue.get_wallet().balance)

        self._repl_loop()

    def _repl_loop(self) -> None:
        """Main input loop."""
        while self._running:
            try:
                state_label = self._machine.current_state.value
                prompt = f"arbitr8der [{state_label}]> "
                user_input = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nShutting down...")
                self._shutdown()
                return

            if not user_input:
                continue

            parts = user_input.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            self._tick_count += 1
            self._archive.record_command(cmd, args)

            try:
                self._dispatch(cmd, args)
            except Exception as exc:
                print(f"Error: {exc}")
                logger.exception("REPL command error: %s", cmd)

    def _dispatch(self, cmd: str, args: str) -> None:
        """Route a command to its handler."""
        handlers = {
            "help": self._cmd_help,
            "h": self._cmd_help,
            "snapshot": self._cmd_snapshot,
            "s": self._cmd_snapshot,
            "health": self._cmd_health,
            "markets": self._cmd_markets,
            "predict": self._cmd_predict,
            "accuracy": self._cmd_accuracy,
            "features": self._cmd_features,
            "journal": self._cmd_journal,
            "vessel": self._cmd_vessel,
            "scorecard": self._cmd_scorecard,
            "archive": self._cmd_archive,
            # Phase 7: trading commands
            "positions": self._cmd_positions,
            "pos": self._cmd_positions,
            "buy": self._cmd_buy,
            "sell": self._cmd_sell,
            "pending": self._cmd_pending,
            "cancel": self._cmd_cancel,
            "wallet": self._cmd_wallet,
            "risk": self._cmd_risk,
            "backtest": self._cmd_backtest,
            "settlement": self._cmd_settlement,
            "retrain": self._cmd_retrain,
            "autotrade": self._cmd_autotrade,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "q": self._cmd_exit,
        }
        handler = handlers.get(cmd)
        if handler:
            handler(args)
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_help(self, _args: str) -> None:
        """Show available commands."""
        print("""
Commands:
  snapshot (s)         Show latest HotSnapshot for all assets
  health               Show data source health report
  markets              Show active Kalshi BTC/ETH 15-min markets
  predict [ASSET]      Run BTC/ETH prediction (or specific asset: predict BTC)
    Options: --model baseline|macro|micro|auto (default: baseline)
  accuracy [MODEL]     Show model scoring results (all models, or specific: accuracy macro_ensemble)
  features [ASSET]     Show latest computed features for BTC/ETH
  journal <text>       Log observation/hypothesis or append note
  scorecard            Show aggregated prediction quality overview
  archive              Show session archive summary
  vessel <cmd>         Vessel state: status, battery, forward, stop

  PAPER Trading (requires vessel forward):
  positions (pos)      Show open positions with PnL
  buy ASSET SIDE N     Market buy N contracts (min 2, e.g., buy BTC yes 5)
  buy ASSET SIDE N LIMIT  Limit buy at N cents
  sell ASSET TICKER    Close position for ticker
  pending              Show pending limit orders
  cancel TICKER        Cancel pending limit order
  wallet               Show wallet balance and PnL
  risk                 Show risk status and limits

  backtest [ASSET]     Walk-forward backtest on historical candles
    Options: --model macro|micro|both (default: macro)
             --window N          train window size (default: 288)
             --retrain N         retrain every N steps (default: 10)

  settlement           Show settlement watcher status and recent outcomes

  retrain              Trigger model retraining on scored data, show results
  autotrade [on|off|status]  Toggle paper auto-trading

  exit (q)             Shutdown session and write archive
  help (h)             Show this help
""")

    def _cmd_snapshot(self, args: str) -> None:
        """Show latest HotSnapshot."""
        snapshots = self._orchestrator.latest_snapshots()
        if not snapshots:
            print("No snapshot data yet. Data sources may still be connecting.")
            return

        for asset, snap in sorted(snapshots.items(), key=lambda x: x[0].value):
            self._archive.record_snapshot(snap)
            if self._json_output:
                print(_format_snapshot_json(snap))
            else:
                print(_format_snapshot_human(snap))
                print()

    def _cmd_health(self, _args: str) -> None:
        """Show data source health report."""
        report = self._orchestrator.health_report()
        if not report or "No active data sources" in report:
            print("No health data yet. Orchestrator may not be running.")
            return
        self._archive.record_health(report)
        print(report)

    def _cmd_markets(self, _args: str) -> None:
        """Show active Kalshi markets."""
        markets = self._orchestrator.active_markets()
        if not markets:
            print("No active markets discovered yet.")
            return

        print(f"Active markets ({len(markets)}):")
        for m in markets:
            mid = f"{m.get('midpoint_cents', 'n/a')}c"
            print(f"  {m.get('ticker', '?')}")
            print(f"    Status: {m.get('status', '?')}  Midpoint: {mid}")
            if m.get("close_time"):
                print(f"    Closes: {m['close_time']}")
            print()

    def _cmd_predict(self, args: str) -> None:
        """Run BTC/ETH prediction using baseline or retrained ML models.

        Usage:
          predict              Run baseline prediction for all assets
          predict BTC          Run for BTC only
          predict --model macro   Use retrained MacroEnsemble (FreqLookup + LightGBM)
          predict --model micro   Use retrained MicroEnsemble (Momentum + LR)
          predict --model auto    Use retrained if available, else baseline
          predict --model baseline Force baseline engine (default)
        """
        from kalshi_desk_package.prediction.backtest_engine import (
            aggregate_1m_to_15m_candles,
            compute_macro_features_from_candles,
        )
        from kalshi_desk_package.prediction.baseline_prediction_engine import (
            BaselinePredictionEngine,
            format_prediction_human,
            format_prediction_json,
        )
        from kalshi_desk_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        # Parse args
        parts = args.split()
        asset_filter = None
        model_choice = "baseline"  # default

        i = 0
        while i < len(parts):
            if parts[i] == "--model" and i + 1 < len(parts):
                model_choice = parts[i + 1].lower()
                i += 2
            elif not parts[i].startswith("--"):
                asset_filter = parts[i].upper()
                i += 1
            else:
                print(f"Unknown option: {parts[i]}")
                return

        if model_choice not in ("baseline", "macro", "micro", "auto"):
            print("Error: --model must be baseline, macro, micro, or auto")
            return

        if not self._orchestrator.running:
            print("Orchestrator not running — start with 'forward start'")
            return

        snapshots = self._orchestrator.latest_snapshots()
        if not snapshots:
            print("No snapshot data yet — wait for data sources to populate")
            return

        scoring_engine = self._orchestrator.scoring_engine
        candle_store = self._orchestrator.candle_store

        for asset_name, snap in snapshots.items():
            if asset_filter and asset_name != asset_filter:
                continue

            asset_str = asset_name
            ticker = f"KX{asset_str}15M-PENDING"
            markets = self._orchestrator.active_markets()
            for m in markets:
                if asset_str in m.get("ticker", "").upper():
                    ticker = m["ticker"]
                    break

            # Determine which model to use
            macro_model = None
            micro_model = None
            used_model = "baseline_v1"

            if model_choice in ("macro", "auto") and scoring_engine is not None:
                macro_model = scoring_engine.get_macro_model(asset_str)
            if model_choice in ("micro", "auto") and scoring_engine is not None:
                micro_model = scoring_engine.get_micro_model(asset_str)

            if model_choice == "baseline":
                macro_model = None
                micro_model = None

            # Use ML model if available
            if (macro_model is not None or micro_model is not None) and candle_store is None:
                print(f"  {asset_str}: candle store not available for feature computation, falling back to baseline")
                macro_model = None
                micro_model = None

            if macro_model is not None or micro_model is not None:
                # Fetch 1m candles, aggregate to 15m, compute macro features
                try:
                    async def _fetch_candles():
                        return await candle_store.get_candles(
                            asset_str, "binance", "1m", limit=5000,
                        )

                    loop = self._loop
                    if loop is None or loop.is_closed():
                        print("Event loop not available.")
                        return
                    one_min_candles = asyncio.run_coroutine_threadsafe(
                        _fetch_candles(), loop,
                    ).result(timeout=10.0)

                    fifteen_min_candles = aggregate_1m_to_15m_candles(
                        list(reversed(one_min_candles)),  # oldest-first
                    )

                    if len(fifteen_min_candles) < 5:
                        print(f"  {asset_str}: only {len(fifteen_min_candles)} 15m windows (need 5+), falling back to baseline")
                        macro_model = None
                        micro_model = None
                    else:
                        now_ts = time.time()
                        next_boundary = (int(now_ts) // 900 + 1) * 900
                        macro_features = compute_macro_features_from_candles(
                            fifteen_min_candles, window_ts=next_boundary,
                        )
                        macro_features["asset"] = asset_str

                        # Run prediction
                        if macro_model is not None:
                            pred = macro_model.predict(macro_features)
                            used_model = "macro_ensemble"
                        else:
                            pred = micro_model.predict(macro_features)
                            used_model = "micro_ensemble"

                        yes_prob = pred.yes_probability
                        confidence = pred.confidence

                        print(f"\n  {asset_str} [{used_model}]:")
                        print(f"    Prediction:   {pred.prediction} ({yes_prob:.1%} YES)")
                        print(f"    Confidence:   {confidence:.1%}")
                        print(f"    Regime:       {macro_features.get('regime', '?')}")
                        print(f"    RSI(7):       {macro_features.get('rsi_7', 0):.1f}")
                        print(f"    Return(1h):   {macro_features.get('return_4', 0):+.2f}%")
                        print(f"    Ticker:       {ticker}")
                        print()

                        # Record to model_runs
                        model_run_store = self._orchestrator.model_run_store
                        if model_run_store is not None:
                            try:
                                features_json = json.dumps({
                                    k: v for k, v in macro_features.items()
                                    if isinstance(v, (int, float, str))
                                })
                                async def _record_ml():
                                    await model_run_store.record_prediction(
                                        model_name=used_model,
                                        asset=asset_str,
                                        window_open=float(next_boundary),
                                        yes_probability=yes_prob,
                                        confidence=confidence,
                                        features_json=features_json,
                                    )
                                asyncio.run_coroutine_threadsafe(
                                    _record_ml(), loop,
                                ).result(timeout=3.0)
                            except Exception:
                                pass  # non-critical
                        continue

                except Exception as exc:
                    print(f"  {asset_str}: ML prediction error ({exc}), falling back to baseline")

            # Baseline fallback
            engine = BaselinePredictionEngine()
            feature_extractor = FeatureExtractionEngine()
            candles = self._binance.last_candles.get(f"{asset_str}USDT", []) if self._binance else []
            features = feature_extractor.extract(
                asset=asset_str,
                snapshot_version=snap.snapshot_version,
                snapshot=snap,
                candles=candles[-16:] if candles else None,
            )

            record = engine.predict(
                asset=asset_str,
                ticker=ticker,
                features=features,
            )

            self._predictions.append(record)
            self._archive.record_prediction(record)

            # Record to model_runs
            model_run_store = self._orchestrator.model_run_store
            if model_run_store is not None and not record.rejected:
                try:
                    now_ts = time.time()
                    next_boundary = (int(now_ts) // 900 + 1) * 900

                    async def _record_baseline():
                        await model_run_store.record_prediction(
                            model_name="baseline_v1",
                            asset=asset_str,
                            window_open=float(next_boundary),
                            yes_probability=record.yes_probability if record.yes_probability is not None else 0.5,
                            confidence=record.confidence if record.confidence is not None else 0.0,
                            features_json=json.dumps(record.features) if record.features else None,
                        )
                    asyncio.run_coroutine_threadsafe(_record_baseline(), self._loop).result(timeout=3.0)
                except Exception:
                    pass  # non-critical

            if self._json_output:
                print(format_prediction_json(record))
            else:
                print(format_prediction_human(record))
            print()

    def _cmd_accuracy(self, args: str) -> None:
        """Show model scoring results from the auto-scoring engine."""
        scoring_engine = self._orchestrator.scoring_engine
        if scoring_engine is None:
            print("Scoring engine not running. Start with 'forward start'.")
            return

        model_filter = args.strip() if args.strip() else None

        async def _fetch():
            if model_filter:
                sc = await scoring_engine.get_model_scorecard(model_filter)
                return {"single": sc}
            else:
                summary = await scoring_engine.get_all_model_scorecards()
                return {"summary": summary}

        try:
            loop = self._loop
            if loop is None or loop.is_closed():
                print("Event loop not available.")
                return
            result = asyncio.run_coroutine_threadsafe(_fetch(), loop).result(timeout=5.0)
        except Exception as exc:
            print(f"Error fetching accuracy: {exc}")
            return

        if "single" in result:
            sc = result["single"]
            if self._json_output:
                print(json.dumps(sc.to_dict(), indent=2))
            else:
                print(f"=== Model: {sc.model_name} ({sc.asset}) ===")
                print(f"  Predictions:  {sc.total_predictions} total, {sc.scored_predictions} scored")
                print(f"  Correct:      {sc.correct}/{sc.scored_predictions} ({sc.accuracy_pct:.1f}%)")
                print(f"  PnL:          {sc.total_pnl_cents:+.0f} cents (avg {sc.avg_pnl_cents:+.1f})")
                print(f"  Brier score:  {sc.brier_score:.4f} (lower is better)")
                print(f"  Log loss:     {sc.log_loss:.4f} (lower is better)")
                print(f"  Avg prob:     {sc.avg_yes_probability:.3f}  Avg conf: {sc.avg_confidence:.3f}")
        else:
            summary = result["summary"]
            if self._json_output:
                print(json.dumps(summary.to_dict(), indent=2))
            else:
                if not summary.models:
                    print("No scored predictions yet. Wait for outcomes to resolve.")
                    return
                print(f"=== Accuracy Dashboard ({len(summary.models)} models) ===")
                print(f"  Pending: {summary.total_pending} predictions awaiting scoring")
                print()
                print(f"  {'MODEL':20s} {'ASSET':6s} {'CORRECT':>10s} {'ACC':>7s} {'PNL':>10s} {'BRIER':>8s}")
                print("  " + "-" * 65)
                for m in summary.models:
                    print(f"  {m.model_name:20s} {m.asset:6s} {m.correct:>4d}/{m.scored_predictions:<4d} {m.accuracy_pct:>6.1f}% {m.total_pnl_cents:>+9.0f}c {m.brier_score:>8.4f}")

    def _cmd_features(self, args: str) -> None:
        """Show latest computed features for an asset."""
        from kalshi_desk_package.prediction.feature_extraction_engine import FeatureExtractionEngine

        asset_filter = args.strip().upper() if args.strip() else None
        snapshots = self._orchestrator.latest_snapshots()

        if not snapshots:
            print("No snapshot data yet. Wait for data sources to populate.")
            return

        feature_extractor = FeatureExtractionEngine()

        for asset_name, snap in snapshots.items():
            if asset_filter and asset_name != asset_filter:
                continue

            candles = self._binance.last_candles.get(f"{asset_name}USDT", []) if self._binance else []
            features = feature_extractor.extract(
                asset=asset_name,
                snapshot_version=snap.snapshot_version,
                snapshot=snap,
                candles=candles[-16:] if candles else None,
            )

            features_dict = features.to_dict()

            if self._json_output:
                print(json.dumps(features_dict, indent=2, default=str))
            else:
                print(f"=== {asset_name} Features (v{snap.snapshot_version}) ===")
                for key, value in sorted(features_dict.items()):
                    if isinstance(value, float):
                        print(f"  {key:35s} {value:>12.4f}")
                    else:
                        print(f"  {key:35s} {str(value):>12s}")
                print()

    def _cmd_journal(self, args: str) -> None:
        """Structured journal: log observations, link predictions, record notes."""
        if not args:
            # Show recent entries
            entries = self._journal.entries
            if not entries:
                print("No journal entries yet.")
                print("Usage:")
                print("  journal observe <asset> <observation text>")
                print("  journal note <text>           — append note to current entry")
                print("  journal list                  — show all entries")
                print("  journal show <entry_id>       — show full entry")
                return

            print(f"Journal entries ({len(entries)}):")
            for e in entries[-10:]:
                print(f"  {e.entry_id:12s}  [{e.status:10s}]  {e.asset:4s}  {e.observation[:60]}")
            return

        # Parse subcommands
        parts = args.split(None, 1)
        subcmd = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""

        if subcmd == "observe":
            self._journal_observe(subargs)
        elif subcmd == "note":
            self._journal_note(subargs)
        elif subcmd == "list":
            self._journal_list()
        elif subcmd == "show":
            self._journal_show(subargs)
        elif subcmd == "open":
            self._journal_open_entries()
        else:
            # Legacy: treat as observation text with auto-detect
            self._journal_legacy(args)

    def _journal_observe(self, args: str) -> None:
        """Log an observation and hypothesis: journal observe BTC price spiking above resistance"""
        parts = args.split(None, 1)
        if len(parts) < 2:
            print("Usage: journal observe <ASSET> <observation text>")
            return

        asset = parts[0].upper()
        text = parts[1]

        # Auto-link to latest snapshot
        snapshots = self._orchestrator.latest_snapshots()
        snap_version = None
        snap_ts = None
        if asset in snapshots:
            snap = snapshots[asset]
            snap_version = snap.snapshot_version
            snap_ts = snap.created_ts.isoformat()
            self._archive.record_snapshot(snap)

        entry = self._journal.start_entry(
            asset=asset,
            observation=text,
            hypothesis="",
            snapshot_version=snap_version,
            snapshot_timestamp=snap_ts,
        )
        self._current_journal_entry = entry
        self._archive.record_journal_entry(entry)
        print(f"Entry {entry.entry_id} created for {asset} (snapshot v{snap_version or 'n/a'})")

    def _journal_note(self, text: str) -> None:
        """Append a note to the current or most recent entry."""
        if not text:
            print("Usage: journal note <text>")
            return

        entry = self._current_journal_entry
        if entry is None and self._journal.entries:
            entry = self._journal.entries[-1]
            self._current_journal_entry = entry

        if entry is None:
            print("No active journal entry. Use 'journal observe' first.")
            return

        self._journal.add_note(entry.entry_id, text)
        self._archive.record_journal_entry(entry)
        print(f"Note added to entry {entry.entry_id}")

    def _journal_list(self) -> None:
        """List all journal entries."""
        entries = self._journal.entries
        if not entries:
            print("No journal entries.")
            return

        print(f"Journal entries ({len(entries)}):")
        for e in entries:
            outcome = ""
            if e.actual_outcome is not None:
                outcome = " YES" if e.actual_outcome == 1 else " NO"
            print(f"  {e.entry_id:12s}  [{e.status:10s}]  {e.asset:4s}  v{str(e.snapshot_version or '?'):>4s}{outcome:4s}  {e.observation[:50]}")

    def _journal_show(self, entry_id: str) -> None:
        """Show a full journal entry."""
        if not entry_id:
            print("Usage: journal show <entry_id>")
            return

        for e in self._journal.entries:
            if e.entry_id == entry_id.strip():
                if self._json_output:
                    print(format_entry_json(e))
                else:
                    print(format_entry_human(e))
                return
        print(f"Entry {entry_id} not found.")

    def _journal_open_entries(self) -> None:
        """Show open (unresolved) journal entries."""
        open_entries = self._journal.get_open_entries()
        if not open_entries:
            print("No open journal entries.")
            return

        print(f"Open entries ({len(open_entries)}):")
        for e in open_entries:
            print(f"  {e.entry_id:12s}  {e.asset:4s}  {e.observation[:60]}")

    def _journal_legacy(self, text: str) -> None:
        """Legacy text journal for backward compat."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry_text = f"[{timestamp}] {text}"
        self._journal_lines.append(entry_text)
        self._archive.record_note(text)
        print(f"Journal entry {len(self._journal_lines)} recorded.")

    def _cmd_scorecard(self, _args: str) -> None:
        """Show aggregated prediction quality overview."""
        card = self._scorecard_gen.generate()
        if self._json_output:
            print(format_scorecard_json(card))
        else:
            print(format_scorecard_human(card))

    def _cmd_archive(self, _args: str) -> None:
        """Show session archive summary."""
        summary = self._archive.summary()
        if self._json_output:
            print(json.dumps(summary, indent=2))
        else:
            print(format_archive_summary_human(summary))

    # ------------------------------------------------------------------
    # Phase 7: Trading Commands
    # ------------------------------------------------------------------

    def _sync_settle_expired_positions(self) -> None:
        """Settle any expired paper positions synchronously."""
        loop = self._loop
        if (
            loop is None
            or not loop.is_running()
            or self._orchestrator is None
            or not self._orchestrator.running
            or self._venue is None
        ):
            return
        candle_store = self._orchestrator.candle_store
        discovery = self._orchestrator._kalshi_rest
        try:
            settle_future = asyncio.run_coroutine_threadsafe(
                self._venue.settle_expired_positions(candle_store, discovery),
                loop,
            )
            settled = settle_future.result(timeout=10.0)
            if settled:
                print(f"Auto-settled {len(settled)} expired position(s).")
        except Exception as exc:
            if str(exc):
                logger.warning("Failed to auto-settle expired positions: %s", exc)

    def _cmd_positions(self, _args: str) -> None:
        """Show open paper positions with unrealized PnL."""
        self._sync_settle_expired_positions()
        positions = self._venue.get_open_positions()
        wallet = self._venue.get_wallet()

        def latest_snapshot_func(asset):
            if self._orchestrator:
                return self._orchestrator.latest_snapshot(asset)
            return None

        format_positions_human(positions, wallet, latest_snapshot_func)

    def _cmd_buy(self, args: str) -> None:
        """Place a paper buy order."""
        handle_buy_command(
            args,
            self._orchestrator,
            self._risk,
            self._venue,
            self._reconciler,
            self._machine.current_state.value,
            self._last_snapshot_version
        )

    def _cmd_sell(self, args: str) -> None:
        """Close a paper position."""
        handle_sell_command(
            args,
            self._orchestrator,
            self._risk,
            self._venue,
            self._reconciler
        )

    def _cmd_pending(self, _args: str) -> None:
        """Show pending limit orders."""
        pending = self._venue.get_pending_orders()
        format_pending_orders_human(pending)

    def _cmd_cancel(self, args: str) -> None:
        """Cancel a pending limit order."""
        handle_cancel_command(args, self._venue)

    def _cmd_wallet(self, _args: str) -> None:
        """Show wallet balance and PnL."""
        self._sync_settle_expired_positions()
        wallet = self._venue.get_wallet()
        format_wallet_human(wallet)

    def _cmd_risk(self, _args: str) -> None:
        """Show risk status and limits."""
        self._sync_settle_expired_positions()
        status = self._risk.status()
        format_risk_status_human(status)

    def _cmd_vessel(self, args: str) -> None:
        """Manage vessel state."""
        subcmd = args.strip().lower() if args else "status"

        if subcmd == "status":
            info = self._machine.get_state()
            print(f"Vessel state: {info['vessel_state']}")
            if info["audit_log"]:
                print("Recent transitions:")
                for entry in info["audit_log"][-5:]:
                    print(f"  {entry['from']} -> {entry['to']} ({entry['reason']})")

        elif subcmd == "battery":
            try:
                prev = self._machine.current_state.value
                self._machine.transition(VesselState.BATTERY, reason="operator: battery command")
                self._archive.record_vessel_transition(prev, "battery", "operator: battery command")
                print("Vessel -> Battery")
            except IllegalTransitionError as exc:
                print(f"Cannot transition: {exc}")

        elif subcmd == "forward":
            try:
                if self._machine.current_state == VesselState.BATTERY:
                    prev = self._machine.current_state.value
                    self._machine.transition(VesselState.FULL_FORWARD, reason="operator: forward command")
                    self._archive.record_vessel_transition(prev, "full_forward", "operator: forward command")
                    print("Vessel -> Full_Forward")
                else:
                    print("Must be in Battery first. Run: vessel battery")
            except IllegalTransitionError as exc:
                print(f"Cannot transition: {exc}")

        elif subcmd == "stop":
            try:
                if self._machine.current_state != VesselState.FULL_STOP:
                    prev = self._machine.current_state.value
                    self._machine.transition(VesselState.FULL_STOP, reason="operator: stop command")
                    self._archive.record_vessel_transition(prev, "full_stop", "operator: stop command")
                    print("Vessel -> Full_Stop")
                else:
                    print("Already in Full_Stop.")
            except IllegalTransitionError as exc:
                print(f"Cannot transition: {exc}")

        else:
            print(f"Unknown vessel subcommand: {subcmd}")
            print("Usage: vessel [status|battery|forward|stop]")

    def _cmd_backtest(self, args: str) -> None:
        """Run walk-forward backtest on historical candles."""
        from kalshi_desk_package.prediction.backtest_engine import (
            WalkForwardBacktester,
            print_comparison,
        )

        candle_store = self._orchestrator.candle_store
        if candle_store is None:
            print("Candle store not available. Start with 'forward start'.")
            return

        # Parse args: backtest [ASSET] [--model macro|micro|both] [--window N] [--retrain N]
        parts = args.split()
        asset = "BTC"
        model_type = "macro"
        train_window = 288
        retrain_every = 10

        i = 0
        while i < len(parts):
            if parts[i] == "--model" and i + 1 < len(parts):
                model_type = parts[i + 1].lower()
                i += 2
            elif parts[i] == "--window" and i + 1 < len(parts):
                try:
                    train_window = int(parts[i + 1])
                except ValueError:
                    print("Error: --window must be a number")
                    return
                i += 2
            elif parts[i] == "--retrain" and i + 1 < len(parts):
                try:
                    retrain_every = int(parts[i + 1])
                except ValueError:
                    print("Error: --retrain must be a number")
                    return
                i += 2
            elif not parts[i].startswith("--"):
                asset = parts[i].upper()
                i += 1
            else:
                print(f"Unknown option: {parts[i]}")
                return

        if model_type not in ("macro", "micro", "both"):
            print("Error: --model must be macro, micro, or both")
            return

        print(f"Running walk-forward backtest: {asset} | model={model_type} | window={train_window} | retrain_every={retrain_every}")
        print("This may take a moment...")

        backtester = WalkForwardBacktester(
            store=candle_store,
            asset=asset,
            source="binance",
            train_window_size=train_window,
            retrain_every=retrain_every,
        )

        async def _run_backtest():
            return await backtester.run(model_type=model_type)

        try:
            loop = self._loop
            if loop is None or loop.is_closed():
                print("Event loop not available.")
                return
            result = asyncio.run_coroutine_threadsafe(_run_backtest(), loop).result(timeout=60.0)
        except Exception as exc:
            print(f"Backtest error: {exc}")
            return

        # Handle comparison mode (returns list of two results)
        if isinstance(result, list):
            macro_result, micro_result = result
            if macro_result.total_predictions == 0 and micro_result.total_predictions == 0:
                print("No predictions generated. Need more historical candle data.")
                return
            if self._json_output:
                out = {
                    "macro": macro_result.to_comparison_dict(),
                    "micro": micro_result.to_comparison_dict(),
                }
                print(json.dumps(out, indent=2))
            else:
                if macro_result.total_predictions > 0:
                    macro_result.print_summary()
                if micro_result.total_predictions > 0:
                    micro_result.print_summary()
                print_comparison(macro_result, micro_result)
            return

        # Single model result
        if result.total_predictions == 0:
            print("No predictions generated. Need more historical candle data.")
            print(f"Current candles in store: {result.candle_count}")
            return

        if self._json_output:
            out = result.to_comparison_dict()
            out["candle_count"] = result.candle_count
            out["elapsed_seconds"] = result.elapsed_seconds
            out["feature_importance"] = dict(sorted(
                result.feature_importance.items(), key=lambda x: -x[1]
            )[:10]) if result.feature_importance else {}
            print(json.dumps(out, indent=2))
        else:
            result.print_summary()

    def _cmd_settlement(self, _args: str) -> None:
        """Show settlement watcher status and recent outcomes."""
        watcher = self._orchestrator.settlement_watcher
        if watcher is None:
            print("Settlement watcher not running. Start with 'forward start'.")
            return

        status = watcher.get_status()
        print("=== Settlement Watcher ===")
        print(f"  Running:        {'yes' if status['running'] else 'no'}")
        print(f"  Outcomes found: {status['settlement_count']}")
        print(f"  Known tickers:  {status['known_tickers']}")
        print(f"  Poll interval:  {status['poll_interval_seconds']}s")

        # Show recent outcomes from the store
        candle_store = self._orchestrator.candle_store
        if candle_store is None:
            return

        async def _fetch():
            outcomes = []
            for asset in ("BTC", "ETH"):
                asset_outcomes = await candle_store.get_outcomes(asset, limit=5)
                outcomes.extend(asset_outcomes)
            return outcomes

        try:
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            outcomes = asyncio.run_coroutine_threadsafe(_fetch(), loop).result(timeout=5.0)
        except Exception as exc:
            print(f"  Error fetching outcomes: {exc}")
            return

        if not outcomes:
            print("\nNo settlement outcomes recorded yet.")
            return

        print(f"\nRecent outcomes ({len(outcomes)}):")
        print(f"  {'TICKER':30s} {'ASSET':6s} {'DIR':5s} {'STRIKE':>10s} {'CLOSE':>10s} {'MAG':>6s}")
        print("  " + "-" * 70)
        for o in outcomes:
            print(
                f"  {o.get('ticker', '?'):30s} {o.get('asset', '?'):6s} "
                f"{o.get('direction', '?'):5s} "
                f"{o.get('open_price', 0):>10.2f} "
                f"{o.get('close_price', 0):>10.2f} "
                f"{o.get('magnitude_pct', 0):>5.3f}%"
            )

    def _cmd_retrain(self, _args: str) -> None:
        """Trigger model retraining on accumulated scored data and show results."""
        scoring_engine = self._orchestrator.scoring_engine
        if scoring_engine is None:
            print("Scoring engine not running. Start with 'forward start'.")
            return

        print("Retraining models on scored predictions...")

        async def _retrain():
            return await scoring_engine.retrain_models()

        try:
            loop = self._loop
            if loop is None or loop.is_closed():
                print("Event loop not available.")
                return
            results = asyncio.run_coroutine_threadsafe(_retrain(), loop).result(timeout=30.0)
        except Exception as exc:
            print(f"Retrain error: {exc}")
            return

        if not results:
            print("No scored predictions with features available for retraining.")
            print("Predictions must be recorded to the model_runs table with features_json.")
            return

        if self._json_output:
            print(json.dumps(results, indent=2))
            return

        print("\n=== Retraining Results ===")
        for asset, info in results.items():
            trained = "OK" if info.get("trained") else "SKIPPED"
            samples = info.get("samples", 0)
            reason = info.get("reason", "")
            print(f"\n  {asset}: {trained} ({samples} samples)")
            if info.get("trained"):
                print(f"    FreqLookup groups: {info.get('freq_groups', 0)}")
                print(f"    LightGBM trained:  {info.get('lgbm_trained', False)}")
                print(f"    Momentum groups:   {info.get('micro_momentum_groups', 0)}")
                print(f"    LR trained:        {info.get('micro_lr_trained', False)}")
            elif reason:
                print(f"    Reason: {reason}")

        if scoring_engine.last_retrain_at > 0:
            ago = time.time() - scoring_engine.last_retrain_at
            print(f"\n  Last retrain: {ago:.0f}s ago ({scoring_engine.retrain_sample_count} samples)")

        # Show current accuracy for context
        print("\n  Current accuracy:")
        try:
            async def _accuracy():
                return await scoring_engine.get_all_model_scorecards()
            summary = asyncio.run_coroutine_threadsafe(_accuracy(), loop).result(timeout=5.0)
            for m in summary.models:
                if m.model_name != "ALL" and m.scored_predictions > 0:
                    print(f"    {m.asset} {m.model_name}: {m.accuracy_pct:.1f}% ({m.correct}/{m.scored_predictions})")
        except Exception:
            pass

    def _cmd_autotrade(self, args: str) -> None:
        """Toggle or inspect the background auto-trading engine."""
        engine = self._orchestrator.auto_trader
        if engine is None:
            print("Auto-trading engine not running. Start with 'forward start'.")
            return

        subcmd = args.strip().lower() if args.strip() else "status"

        if subcmd in ("status", "show"):
            status = engine.get_status()
            print("=== Auto-Trade Status ===")
            print(f"  Enabled:          {'yes' if status['enabled'] else 'no'}")
            print(f"  Running:          {'yes' if status['running'] else 'no'}")
            print(f"  Edge threshold:   {status['edge_threshold_pct']:.1f}%")
            print(f"  Contracts/trade:  {status['contracts_per_trade']}")
            print(f"  Model choice:     {status['model_choice']}")
            print(f"  Total trades:    {status['total_trades']}")
            print(f"  Total skips:     {status['total_skips']}")
            print(f"  Wallet balance:  ${status['wallet_balance']:.2f}")
            print(f"  Open positions:  {status['open_positions']}")
            print(f"  Recent decisions:{status['recent_decisions']}")

            recent_decisions = engine.recent_decisions[-5:]
            if recent_decisions:
                print("\n  Recent decisions:")
                for decision in recent_decisions:
                    outcome = "TRADE" if decision.traded else f"SKIP({decision.skip_reason})"
                    print(
                        f"    {decision.asset} {decision.market_ticker} "
                        f"{decision.model_name or 'n/a'} "
                        f"{decision.yes_probability:.1%} YES "
                        f"edge={decision.edge_pct:+.2f}% {outcome}"
                    )
            return

        if subcmd in ("on", "enable", "start"):
            if self._machine.current_state != VesselState.FULL_FORWARD:
                print("Auto-trading requires Full_Forward. Run 'vessel forward' first.")
                return

            print("\n--- Startup Reconciliation ---")
            wallet = self._venue.get_wallet()
            print(
                f"Paper Wallet: ${wallet.balance:.2f} "
                f"(PnL: ${wallet.total_pnl:.2f}, Win Rate: {wallet.win_rate_pct:.1f}%)"
            )

            open_positions = self._venue.get_open_positions()
            if open_positions:
                print(f"⚠ {len(open_positions)} open position(s) will interact with auto-trader decisions:")
                for pos in open_positions:
                    print(
                        f"  {pos.market_ticker} {pos.side.name} "
                        f"{pos.contract_count} contracts @ {pos.average_entry_price}"
                    )
            else:
                print("No open positions. Clean start.")

            print("\nRunning preflight check...")
            try:
                future = asyncio.run_coroutine_threadsafe(
                    engine.run_preflight_check(), self._loop
                )
                preflight = future.result(timeout=10.0)

                print("Preflight results:")
                for check in preflight.get("passed_checks", []):
                    print(f"  [✓] {check}")
                for warn in preflight.get("warnings", []):
                    print(f"  [!] {warn}")

                blockers = preflight.get("blockers", [])
                if blockers:
                    print("\nPreflight failed due to blockers:")
                    for blocker in blockers:
                        print(f"  [X] {blocker}")
                    print("Auto-trading NOT enabled.")
                    return
                print("Preflight OK.\n")
            except Exception as e:
                print(f"\nPreflight check failed: {e}")
                print("Auto-trading NOT enabled.")
                return

            engine.enable()
            print("Auto-trading enabled.")
            return

        if subcmd in ("off", "disable", "stop"):
            engine.disable()
            print("Auto-trading disabled.")
            return

        print("Usage: autotrade [on|off|status]")

    def _cmd_exit(self, _args: str) -> None:
        """Shutdown the session."""
        print("Shutting down...")
        self._shutdown()

    def _shutdown(self) -> None:
        """Clean shutdown: stop orchestrator, write archive, force vessel to Full_Stop."""
        self._running = False

        if self._orchestrator.running:
            print("Stopping data ingestion...")
            if self._loop:
                stop_future = asyncio.run_coroutine_threadsafe(
                    self._orchestrator.stop(), self._loop
                )
                try:
                    stop_future.result(timeout=60.0)
                except Exception as exc:
                    detail = str(exc) or "timed out waiting for orchestrator stop"
                    logger.warning("Orchestrator stop error: %s", detail)
                # Give lingering websocket tasks a moment to settle before close().
                with contextlib.suppress(Exception):
                    asyncio.run_coroutine_threadsafe(
                        asyncio.sleep(0.5), self._loop
                    ).result(timeout=2.0)
            if self._worker_thread:
                self._worker_thread.join(timeout=10.0)

        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop.close()

        # Force vessel to Full_Stop
        if self._machine.current_state != VesselState.FULL_STOP:
            try:
                prev = self._machine.current_state.value
                self._machine.transition(VesselState.FULL_STOP, reason="session shutdown")
                self._archive.record_vessel_transition(prev, "full_stop", "session shutdown")
            except IllegalTransitionError:
                pass

        # Write session archive
        archive_path = self._archive.close()
        print(f"Session archive: {archive_path}")
        print("Vessel -> Full_Stop. Session ended.")


def start_repl(json_output: bool = False, script: str | None = None) -> None:
    """Entry point for the interactive REPL."""
    if script:
        _run_script(script, json_output=json_output)
    else:
        repl = TradingREPL(json_output=json_output)
        repl.run()
