"""Auto-trading engine — bridges predictions to paper order execution.

Runs as a background task in the orchestrator. Periodically:
  1. Fetches candles and computes features for each asset
  2. Runs retrained ML models (or baseline fallback)
  3. Compares prediction to Kalshi market midpoint
  4. If edge exceeds threshold, submits a paper order
  5. Records everything for audit trail

Default: DISABLED. Must be explicitly enabled via REPL `autotrade on`.
All orders go through RiskController before reaching PaperVenueAdapter.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from arbitr8der_package.config.cwd_independent_path_resolver import RUNTIME_DIR, ensure_runtime_dirs
from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.durable_storage.candle_persistence_store import CandlePersistenceStore
from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
from arbitr8der_package.prediction.model_run_record_store import ModelRunRecordStore
from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskController

logger = get_logger(__name__)

# Auto-trade loop interval — check every 60s, but only trade near boundaries
_AUTO_TRADE_LOOP_INTERVAL_S = 60

# Minimum seconds before a 15m boundary to submit an order
_MIN_SECONDS_BEFORE_BOUNDARY = 120

# Maximum seconds after a 15m boundary (don't trade stale windows)
_MAX_SECONDS_AFTER_BOUNDARY = 300


@dataclass
class AutoTradeDecision:
    """Record of one auto-trade decision (trade or skip)."""

    asset: str
    market_ticker: str
    snapshot_version: int | None
    model_name: str
    yes_probability: float
    confidence: float
    market_midpoint: float
    edge_pct: float
    traded: bool
    order_id: str | None = None
    skip_reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "market_ticker": self.market_ticker,
            "snapshot_version": self.snapshot_version,
            "model_name": self.model_name,
            "yes_probability": round(self.yes_probability, 4),
            "confidence": round(self.confidence, 4),
            "market_midpoint": round(self.market_midpoint, 2),
            "edge_pct": round(self.edge_pct, 4),
            "traded": self.traded,
            "order_id": self.order_id,
            "skip_reason": self.skip_reason,
            "timestamp": self.timestamp,
        }


class AutoTradingEngine:
    """Background auto-trader: predict → edge detection → paper order execution.

    Dependencies are injected — this class owns no DB or network connections.
    """

    def __init__(
        self,
        *,
        candle_store: CandlePersistenceStore,
        scoring_engine: Any,
        model_run_store: ModelRunRecordStore,
        snapshot_getter: Callable[[str], Any | None],
        market_ticker_getter: Callable[[str], str | None],
        paper_venue: PaperVenueAdapter,
        risk_controller: RiskController,
        discovery_client: Any | None = None,
        vessel_state_getter: Callable[[], str] | None = None,
        edge_threshold_pct: float = 2.0,
        contracts_per_trade: int = 2,
        max_positions_per_asset: int = 5,
        model_choice: str = "auto",
        max_trades_per_session: int = 50,
        max_session_loss_usd: float = 10.0,
    ):
        self._candle_store = candle_store
        self._scoring_engine = scoring_engine
        self._model_run_store = model_run_store
        self._snapshot_getter = snapshot_getter
        self._market_ticker_getter = market_ticker_getter
        self._paper_venue = paper_venue
        self._risk = risk_controller
        self._discovery_client = discovery_client
        self._vessel_state_getter = vessel_state_getter or (lambda: "full_stop")
        self._edge_threshold_pct = edge_threshold_pct
        self._contracts_per_trade = contracts_per_trade
        self._max_positions_per_asset = max_positions_per_asset
        self._model_choice = model_choice
        self._max_trades_per_session = max_trades_per_session
        self._max_session_loss_usd = max_session_loss_usd

        self._enabled = False
        self._running = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._decisions: list[AutoTradeDecision] = []
        self._trade_count = 0
        self._skip_count = 0
        self._last_trade_window_by_asset: dict[str, int] = {}

        self._session_trade_count: int = 0
        self._session_realized_pnl: float = 0.0
        self._last_evaluated_at: float = 0.0
        self._last_evaluation_duration_ms: float = 0.0

        ensure_runtime_dirs()
        self._decision_log_path = Path(RUNTIME_DIR) / "logs" / "auto_trade_decisions.jsonl"
        self._decision_log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_preflight_check(self) -> dict[str, Any]:
        """Validate system state before enabling auto-trading."""
        checks = {}
        warnings = []
        blockers = []

        # Check snapshot
        snapshot = self._snapshot_getter("BTC")
        if snapshot is not None:
            checks["snapshot"] = "passed"
        else:
            checks["snapshot"] = "failed"
            blockers.append("Snapshot for BTC is unavailable")

        # Check market ticker
        ticker = self._market_ticker_getter("BTC")
        if ticker is not None:
            checks["ticker"] = "passed"
        else:
            checks["ticker"] = "failed"
            blockers.append("Market ticker for BTC is unavailable")

        # Check candle recency
        try:
            latest_time = await self._candle_store.get_latest_candle_time("BTC", "binance", "1m")
            if latest_time is not None and (time.time() - latest_time) <= 300:
                checks["candles"] = "passed"
            else:
                checks["candles"] = "failed"
                blockers.append("Candles are stale or missing (no candle in last 300s)")
        except Exception as e:
            checks["candles"] = "failed"
            blockers.append(f"Candle check error: {e}")

        # Check wallet
        try:
            wallet = self._paper_venue.get_wallet()
            if wallet.balance > 0:
                checks["wallet"] = "passed"
            else:
                checks["wallet"] = "failed"
                blockers.append("Wallet balance is 0")
        except Exception as e:
            checks["wallet"] = "failed"
            blockers.append(f"Wallet check error: {e}")

        # Check model
        model = self._scoring_engine.get_macro_model("BTC")
        if model is not None:
            checks["model"] = "passed"
        else:
            checks["model"] = "warning"
            warnings.append("Macro model for BTC is unavailable")

        return {"passed": len(blockers) == 0, "checks": checks, "warnings": warnings, "blockers": blockers}

    async def enable_with_preflight(self) -> dict[str, Any]:
        result = await self.run_preflight_check()
        if result["passed"]:
            self.enable()
        else:
            logger.warning("Preflight checks failed, not enabling auto-trade. Blockers: %s", result["blockers"])
            print(f"Auto-trade preflight failed. Blockers: {result['blockers']}")
        return result

    def enable(self) -> None:
        self._enabled = True
        logger.info(
            "Auto-trading ENABLED (edge>%.1f%%, %d contracts)", self._edge_threshold_pct, self._contracts_per_trade
        )

    def disable(self) -> None:
        self._enabled = False
        logger.info("Auto-trading DISABLED")

    def record_trade_outcome(self, pnl_usd: float) -> None:
        self._session_realized_pnl += pnl_usd
        if self._session_realized_pnl <= -self._max_session_loss_usd:
            logger.warning("Kill switch triggered due to session loss: %.2f", self._session_realized_pnl)
            self.disable()

    def set_vessel_state_getter(self, vessel_state_getter: Callable[[], str]) -> None:
        """Inject the live vessel-state getter after the orchestrator starts."""
        self._vessel_state_getter = vessel_state_getter

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def skip_count(self) -> int:
        return self._skip_count

    @property
    def recent_decisions(self) -> list[AutoTradeDecision]:
        return list(self._decisions[-50:])

    def get_status(self) -> dict:
        wallet = self._paper_venue.get_wallet()
        positions = self._paper_venue.get_open_positions()

        last_eval_iso = "never"
        if self._last_evaluated_at > 0:
            last_eval_iso = datetime.fromtimestamp(self._last_evaluated_at, tz=UTC).isoformat()

        seconds_since_eval = time.time() - self._last_evaluated_at if self._last_evaluated_at > 0 else 0.0

        kill_switch_triggered = (
            self._session_trade_count >= self._max_trades_per_session
            or self._session_realized_pnl <= -self._max_session_loss_usd
        )

        return {
            "enabled": self._enabled,
            "running": self._running.is_set(),
            "edge_threshold_pct": self._edge_threshold_pct,
            "contracts_per_trade": self._contracts_per_trade,
            "model_choice": self._model_choice,
            "total_trades": self._trade_count,
            "total_skips": self._skip_count,
            "wallet_balance": wallet.balance,
            "open_positions": len(positions),
            "recent_decisions": len(self._decisions),
            "last_evaluated_at": last_eval_iso,
            "last_evaluation_duration_ms": self._last_evaluation_duration_ms,
            "seconds_since_last_evaluation": seconds_since_eval,
            "session_trade_count": self._session_trade_count,
            "session_realized_pnl": self._session_realized_pnl,
            "max_trades_per_session": self._max_trades_per_session,
            "max_session_loss_usd": self._max_session_loss_usd,
            "kill_switch_triggered": kill_switch_triggered,
        }

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self._task = asyncio.create_task(self._trade_loop())
        logger.info("Auto-trading engine started (disabled by default)")

    async def stop(self) -> None:
        self._running.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Auto-trading engine stopped")

    async def _trade_loop(self) -> None:
        while self._running.is_set():
            try:
                if self._enabled and self._vessel_state_getter().lower() == "full_forward":
                    await self._evaluate_all_assets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Auto-trade loop error: %s", e)

            await asyncio.sleep(_AUTO_TRADE_LOOP_INTERVAL_S)

    async def _evaluate_all_assets(self) -> None:
        """Evaluate auto-trade opportunity for each asset."""
        start_time = time.perf_counter()

        # Auto-settle any expired paper positions before running new trades
        try:
            settled = await self._paper_venue.settle_expired_positions(
                self._candle_store, self._discovery_client
            )
            if settled:
                logger.info("Auto-trading engine settled %d expired position(s)", len(settled))
        except Exception as e:
            logger.error("Auto-trading engine failed to auto-settle expired positions: %s", e)

        from arbitr8der_package.prediction.backtest_engine import (
            aggregate_1m_to_15m_candles,
            compute_macro_features_from_candles,
        )

        for asset in ("BTC", "ETH"):
            try:
                await self._evaluate_asset(
                    asset,
                    compute_macro_features_from_candles,
                    aggregate_1m_to_15m_candles,
                )
            except Exception as e:
                logger.error("Auto-trade eval error for %s: %s", asset, e)

        end_time = time.perf_counter()
        self._last_evaluated_at = time.time()
        self._last_evaluation_duration_ms = (end_time - start_time) * 1000.0

    async def _evaluate_asset(
        self,
        asset: str,
        compute_features_fn,
        aggregate_fn,
    ) -> None:
        """Evaluate auto-trade for a single asset."""
        snapshot = self._snapshot_getter(asset)
        if snapshot is None:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker="",
                    snapshot_version=None,
                    model_name="",
                    yes_probability=0,
                    confidence=0,
                    market_midpoint=0,
                    edge_pct=0,
                    traded=False,
                    skip_reason="no_snapshot",
                )
            )
            return

        if snapshot.kalshi_midpoint_cents is None:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=self._market_ticker_getter(asset) or "",
                    snapshot_version=snapshot.snapshot_version,
                    model_name="",
                    yes_probability=0,
                    confidence=0,
                    market_midpoint=0,
                    edge_pct=0,
                    traded=False,
                    skip_reason="no_kalshi_midpoint",
                )
            )
            return

        market_ticker = self._market_ticker_getter(asset) or f"KX{asset}15M-PENDING"
        midpoint = float(snapshot.kalshi_midpoint_cents)
        book_age_seconds = max(0.0, time.time() - snapshot.created_ts.timestamp())
        current_window = int(time.time()) // 900

        # Only one trade attempt per asset per 15m window.
        if self._last_trade_window_by_asset.get(asset) == current_window:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name="",
                    yes_probability=0,
                    confidence=0,
                    market_midpoint=midpoint,
                    edge_pct=0,
                    traded=False,
                    skip_reason="window_already_traded",
                )
            )
            return

        # Check position limit
        positions = self._paper_venue.get_open_positions()
        asset_positions = [p for p in positions if p.asset == asset]
        if len(asset_positions) >= self._max_positions_per_asset:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name="",
                    yes_probability=0,
                    confidence=0,
                    market_midpoint=midpoint,
                    edge_pct=0,
                    traded=False,
                    skip_reason="max_positions_reached",
                )
            )
            return

        # Fetch candles and compute features
        one_min_candles = await self._candle_store.get_candles(
            asset,
            "binance",
            "1m",
            limit=5000,
        )
        if not one_min_candles:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name="",
                    yes_probability=0,
                    confidence=0,
                    market_midpoint=midpoint,
                    edge_pct=0,
                    traded=False,
                    skip_reason="no_candles",
                )
            )
            return

        fifteen_min_candles = aggregate_fn(list(reversed(one_min_candles)))
        if len(fifteen_min_candles) < 5:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name="",
                    yes_probability=0,
                    confidence=0,
                    market_midpoint=midpoint,
                    edge_pct=0,
                    traded=False,
                    skip_reason=f"insufficient_15m_candles_{len(fifteen_min_candles)}",
                )
            )
            return

        now_ts = time.time()
        next_boundary = (int(now_ts) // 900 + 1) * 900
        macro_features = compute_features_fn(fifteen_min_candles, window_ts=next_boundary)
        macro_features["asset"] = asset

        # Run prediction
        macro_model = self._scoring_engine.get_macro_model(asset)
        micro_model = self._scoring_engine.get_micro_model(asset)

        yes_prob = 0.5
        confidence = 0.0
        model_name = "baseline_v1"

        if self._model_choice in ("macro", "auto") and macro_model is not None:
            pred = macro_model.predict(macro_features)
            yes_prob = pred.yes_probability
            confidence = pred.confidence
            model_name = "macro_ensemble"
        elif self._model_choice in ("micro", "auto") and micro_model is not None:
            pred = micro_model.predict(macro_features)
            yes_prob = pred.yes_probability
            confidence = pred.confidence
            model_name = "micro_ensemble"
        else:
            # Baseline fallback — use midpoint as probability
            yes_prob = midpoint / 100.0
            confidence = 0.2
            model_name = "baseline_v1"

        # Compute edge
        market_prob = midpoint / 100.0
        edge_pct = (yes_prob - market_prob) * 100.0

        # Record prediction to model_runs
        try:
            features_json = json.dumps({k: v for k, v in macro_features.items() if isinstance(v, (int, float, str))})
            await self._model_run_store.record_prediction(
                model_name=model_name,
                asset=asset,
                window_open=float(next_boundary),
                yes_probability=yes_prob,
                confidence=confidence,
                features_json=features_json,
            )
        except Exception:
            pass

        # Check edge threshold
        if abs(edge_pct) < self._edge_threshold_pct:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name=model_name,
                    yes_probability=yes_prob,
                    confidence=confidence,
                    market_midpoint=midpoint,
                    edge_pct=edge_pct,
                    traded=False,
                    skip_reason="edge_below_threshold",
                )
            )
            return

        # Determine side: if model says YES is underpriced, buy YES
        if edge_pct > 0:
            side = "yes"
        else:
            side = "no"
            edge_pct = abs(edge_pct)  # normalize for logging

        # Resolve ticker

        # Unattended session kill switch checks
        if self._session_trade_count >= self._max_trades_per_session:
            logger.warning("Auto-trading disabled: max trades per session reached (%d)", self._max_trades_per_session)
            self.disable()
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name=model_name,
                    yes_probability=yes_prob,
                    confidence=confidence,
                    market_midpoint=midpoint,
                    edge_pct=edge_pct,
                    traded=False,
                    skip_reason="max_session_trades_reached",
                )
            )
            return

        if self._session_realized_pnl <= -self._max_session_loss_usd:
            logger.warning("Auto-trading disabled: max session loss reached (%.2f)", self._session_realized_pnl)
            self.disable()
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name=model_name,
                    yes_probability=yes_prob,
                    confidence=confidence,
                    market_midpoint=midpoint,
                    edge_pct=edge_pct,
                    traded=False,
                    skip_reason="max_session_loss_reached",
                )
            )
            return

        # Create order intent and risk check
        intent = OrderIntent(
            asset=asset,
            side=side,
            contracts=self._contracts_per_trade,
            ticker=market_ticker,
            snapshot_version=snapshot.snapshot_version,
            midpoint_cents=midpoint,
        )

        # Risk check — vessel state must be full_forward
        # We'll pass "full_forward" if enabled, since auto-trade implies operator intent
        verdict = self._risk.check(
            intent,
            vessel_state=self._vessel_state_getter(),
            current_book_age_seconds=book_age_seconds,
        )

        if not verdict.passed:
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name=model_name,
                    yes_probability=yes_prob,
                    confidence=confidence,
                    market_midpoint=midpoint,
                    edge_pct=edge_pct,
                    traded=False,
                    skip_reason=f"risk_blocked_{verdict.block_reason.value if verdict.block_reason else 'unknown'}",
                )
            )
            return

        # Submit order
        order = self._paper_venue.submit_order(
            asset=asset,
            side=side,
            contracts=self._contracts_per_trade,
            ticker=market_ticker,
            midpoint_cents=midpoint,
            snapshot_version=snapshot.snapshot_version,
            model_version=model_name,
        )

        if order.status == "filled":
            self._risk.record_fill(asset, order.fill_cost_usd or 0.0)
            self._trade_count += 1
            self._session_trade_count += 1
            self._last_trade_window_by_asset[asset] = current_window
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name=model_name,
                    yes_probability=yes_prob,
                    confidence=confidence,
                    market_midpoint=midpoint,
                    edge_pct=edge_pct,
                    traded=True,
                    order_id=order.order_id,
                )
            )
            logger.info(
                "AUTO-TRADE: %s %s %d contracts @ %.1fc (edge=%.2f%%, model=%s)",
                asset,
                side,
                self._contracts_per_trade,
                order.fill_price_cents or 0,
                edge_pct,
                model_name,
            )
        else:
            self._skip_count += 1
            if order.status == "pending":
                self._last_trade_window_by_asset[asset] = current_window
            self._record_decision(
                AutoTradeDecision(
                    asset=asset,
                    market_ticker=market_ticker,
                    snapshot_version=snapshot.snapshot_version,
                    model_name=model_name,
                    yes_probability=yes_prob,
                    confidence=confidence,
                    market_midpoint=midpoint,
                    edge_pct=edge_pct,
                    traded=False,
                    skip_reason=f"order_{order.status}",
                )
            )

    def _record_decision(self, decision: AutoTradeDecision) -> None:
        self._decisions.append(decision)
        if len(self._decisions) > 200:
            self._decisions = self._decisions[-100:]

        try:
            with open(self._decision_log_path, "ab") as f:
                f.write(orjson.dumps(decision.to_dict()) + b"\n")
        except Exception as e:
            logger.error("Failed to write auto-trade decision to log: %s", e)
