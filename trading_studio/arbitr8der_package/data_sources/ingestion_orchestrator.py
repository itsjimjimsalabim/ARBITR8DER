"""Five-source ingestion orchestrator — owns the stream lease, starts/stops providers.

Coordinates all five data providers (Kalshi, Binance, Coinbase, Polymarket,
CoinGecko), converts their observations into Pydantic data-contract events,
feeds them to the snapshot merger, and enqueues durable events to the
persistence queue.

Phase 8f additions:
  - CandleCollectionBattery for 24/7 candle collection and aggregation
  - AutoScoringEngine for automatic prediction outcome resolution
  - Exposes candle_store and scoring model_run_store for prediction pipeline

Phase 8i additions:
  - SettlementWatcher for recording settled market outcomes

Read-only — no order submission or trading decisions.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from arbitr8der_package.config.cwd_independent_path_resolver import LEASE_FILE_PATH, RUNTIME_DIR
from arbitr8der_package.config.stream_provider_runtime_lease_file_lock import RuntimeLease
from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.config.typed_configuration_settings_module import load_settings
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
from arbitr8der_package.data_sources.binance_spot_price_stream import BinancePriceObservation, BinanceSpotPriceStream
from arbitr8der_package.data_sources.candle_collection_battery import CandleCollectionBattery
from arbitr8der_package.data_sources.coinbase_spot_price_stream import CoinbasePriceObservation, CoinbaseSpotPriceStream
from arbitr8der_package.data_sources.coingecko_macro_data_poller import (
    CoinGeckoMacroDataPoller,
    CoinGeckoMacroObservation,
)
from arbitr8der_package.data_sources.kalshi_orderbook_websocket_client import (
    KalshiOrderBookState,
    KalshiOrderBookWebSocketClient,
)
from arbitr8der_package.data_sources.kalshi_rest_market_discovery_client import (
    KalshiMarketDetail,
    KalshiRestMarketDiscoveryClient,
)
from arbitr8der_package.data_sources.polymarket_sentiment_analysis_poller import (
    PolymarketSentimentObservation,
    PolymarketSentimentPoller,
)
from arbitr8der_package.data_sources.source_health_monitor import SourceHealthMonitor
from arbitr8der_package.durable_storage.candle_persistence_store import CandlePersistenceStore
from arbitr8der_package.execution.auto_trading_engine import AutoTradingEngine
from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
from arbitr8der_package.prediction.auto_scoring_engine import AutoScoringEngine
from arbitr8der_package.prediction.model_run_record_store import ModelRunRecordStore
from arbitr8der_package.prediction.settlement_watcher import SettlementWatcher
from arbitr8der_package.risk.risk_controls_module import RiskController

logger = get_logger(__name__)

_OWNER_ID = f"ingestion-{uuid.uuid4().hex[:8]}"
_LEASE = RuntimeLease(LEASE_FILE_PATH, ttl=5 * 60)

# Spot price assets to track
_SPOT_ASSETS = [Asset.BTC, Asset.ETH]
_KALSHI_SYMBOLS = ["btcusdt", "ethusdt"]
_COINBASE_PRODUCTS = ["BTC-USD", "ETH-USD"]


class IngestionOrchestrator:
    """Central coordinator for all five data sources.

    Acquires the stream lease, starts every provider as a background task,
    converts their observations into Pydantic events, feeds the snapshot
    merger, and optionally enqueues events for durable storage.

    Usage:
        orchestrator = IngestionOrchestrator()
        await orchestrator.start()
        snapshot = orchestrator.latest_snapshot()
        health = orchestrator.health_report()
        await orchestrator.stop()
    """

    def __init__(
        self,
        kalshi_api_key: str | None = None,
        coingecko_api_key: str | None = None,
        enqueue_events: bool = False,
    ) -> None:
        self._kalshi_api_key = kalshi_api_key
        self._coingecko_api_key = coingecko_api_key
        self._enqueue_events = enqueue_events

        # Providers
        self._kalshi_rest = KalshiRestMarketDiscoveryClient()
        self._kalshi_ws: dict[str, KalshiOrderBookWebSocketClient] = {}
        self._binance = BinanceSpotPriceStream()
        self._coinbase = CoinbaseSpotPriceStream()
        self._polymarket = PolymarketSentimentPoller()
        self._coingecko = CoinGeckoMacroDataPoller()

        # Core state
        self._merger = SnapshotMerger(now_fn=lambda: datetime.now(UTC))
        self._health = SourceHealthMonitor(now_fn=time.time)
        self._latest_snapshots: dict[Asset, Any] = {}
        self._active_markets: list[KalshiMarketDetail] = []

        # Phase 8f — candle battery + scoring engine (initialized in start())
        self._candle_db: aiosqlite.Connection | None = None
        self._candle_store: CandlePersistenceStore | None = None
        self._candle_battery: CandleCollectionBattery | None = None
        self._model_run_db: aiosqlite.Connection | None = None
        self._model_run_store: ModelRunRecordStore | None = None
        self._scoring_engine: AutoScoringEngine | None = None

        # Phase 8i — settlement watcher (initialized in start())
        self._settlement_watcher: SettlementWatcher | None = None

        # Phase 8l — auto-trading engine (initialized in start())
        self._auto_trader: AutoTradingEngine | None = None
        self._paper_venue: PaperVenueAdapter | None = None
        self._risk_controller: RiskController | None = None

        # Tasks
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def lease_acquired(self) -> bool:
        return _LEASE.current_owner is not None

    def latest_snapshot(self, asset: Asset | None = None) -> Any | None:
        """Return the latest HotSnapshot for an asset, or the first one."""
        if asset:
            return self._latest_snapshots.get(asset)
        if self._latest_snapshots:
            return next(iter(self._latest_snapshots.values()))
        return None

    def latest_snapshots(self) -> dict[Asset, Any]:
        """Return all latest HotSnapshots keyed by asset."""
        return dict(self._latest_snapshots)

    def health_report(self) -> str:
        """Human-readable health report for all sources."""
        return self._health.format_report()

    def health_summary(self) -> dict[str, Any]:
        """Structured health summary."""
        return self._health.summary()

    def active_markets(self) -> list[dict[str, Any]]:
        """List of currently active Kalshi markets."""
        return [m.to_dict() for m in self._active_markets]

    @property
    def candle_store(self) -> CandlePersistenceStore | None:
        """Persistent candle store for the prediction pipeline."""
        return self._candle_store

    @property
    def model_run_store(self) -> ModelRunRecordStore | None:
        """Model run record store for prediction scoring."""
        return self._model_run_store

    @property
    def scoring_engine(self) -> AutoScoringEngine | None:
        """Auto-scoring engine for prediction outcome resolution."""
        return self._scoring_engine

    @property
    def candle_battery(self) -> CandleCollectionBattery | None:
        """Candle collection battery for 24/7 candle aggregation."""
        return self._candle_battery

    @property
    def settlement_watcher(self) -> SettlementWatcher | None:
        """Settlement watcher for recording settled market outcomes."""
        return self._settlement_watcher

    @property
    def auto_trader(self) -> AutoTradingEngine | None:
        """Auto-trading engine (disabled by default, enable via `autotrade on`)."""
        return self._auto_trader

    @property
    def paper_venue(self) -> PaperVenueAdapter | None:
        """Paper trading venue adapter."""
        return self._paper_venue

    @property
    def discovery_client(self) -> Any:
        """Kalshi REST market discovery client."""
        return self._kalshi_rest

    @property
    def risk_controller(self) -> RiskController | None:
        """Shared risk controller used by paper and auto-trading."""
        return self._risk_controller

    def market_ticker_for_asset(self, asset: str) -> str | None:
        """Return the active Kalshi ticker for an asset if one is known."""
        asset_upper = asset.upper()
        for market in self._active_markets:
            if asset_upper in market.ticker.upper():
                return market.ticker
        return None

    async def start(self) -> bool:
        """Acquire lease and start all providers. Returns True if started."""
        if self._running:
            logger.warning("Orchestrator already running")
            return True

        # Acquire lease
        if not _LEASE.acquire(_OWNER_ID):
            logger.error("Cannot acquire stream lease — another instance owns it")
            return False

        self._running = True
        logger.info("Ingestion orchestrator starting (owner=%s)", _OWNER_ID)

        # Phase 8f — open shared prediction database and create stores
        # Both candle_store and model_run_store share the same DB so that
        # AutoScoringEngine can JOIN model_runs with outcomes/candles.
        db_dir = RUNTIME_DIR / "data"
        db_dir.mkdir(parents=True, exist_ok=True)

        shared_db_path = str(db_dir / "prediction.db")
        self._candle_db = await aiosqlite.connect(shared_db_path)
        await self._candle_db.execute("PRAGMA journal_mode=WAL")
        await self._candle_db.execute("PRAGMA foreign_keys=ON")

        self._candle_store = CandlePersistenceStore(self._candle_db)
        await self._candle_store.initialize()

        # model_run_store shares the same DB connection
        self._model_run_store = ModelRunRecordStore(self._candle_db)
        await self._model_run_store.initialize()

        self._model_run_db = None  # no separate DB — shared with candle_db

        # Phase 8f — create candle battery and scoring engine
        settings = load_settings()
        self._candle_battery = CandleCollectionBattery(
            settings=settings,
            store=self._candle_store,
        )
        self._scoring_engine = AutoScoringEngine(
            model_run_store=self._model_run_store,
            candle_store=self._candle_store,
        )

        # Phase 8i — create settlement watcher
        self._settlement_watcher = SettlementWatcher(
            kalshi_discovery_client=self._kalshi_rest,
            candle_store=self._candle_store,
            poll_interval_seconds=60,
            lookback_minutes=30,
        )

        # Register provider callbacks
        self._register_callbacks()

        # Start all providers as background tasks
        self._tasks = [
            asyncio.create_task(self._run_kalshi_discovery(), name="kalshi-discovery"),
            asyncio.create_task(self._binance.connect_and_run(_KALSHI_SYMBOLS), name="binance-ws"),
            asyncio.create_task(self._coinbase.connect_and_run(_COINBASE_PRODUCTS), name="coinbase-ws"),
            asyncio.create_task(self._run_polymarket_poller(), name="polymarket-poll"),
            asyncio.create_task(self._coingecko.start_polling(), name="coingecko-poll"),
        ]

        # Phase 8f — candle battery and scoring engine background tasks
        self._tasks.append(
            asyncio.create_task(self._candle_battery.start(), name="candle-battery")
        )
        self._tasks.append(
            asyncio.create_task(self._run_scoring_engine(), name="scoring-engine")
        )

        # Phase 8i — settlement watcher background task
        self._tasks.append(
            asyncio.create_task(self._settlement_watcher.start(), name="settlement-watcher")
        )

        # Phase 8l — auto-trading engine (disabled by default)
        self._paper_venue = PaperVenueAdapter()
        self._risk_controller = RiskController(wallet_mode="paper")
        self._auto_trader = AutoTradingEngine(
            candle_store=self._candle_store,
            scoring_engine=self._scoring_engine,
            model_run_store=self._model_run_store,
            snapshot_getter=self.latest_snapshot,
            market_ticker_getter=self.market_ticker_for_asset,
            paper_venue=self._paper_venue,
            risk_controller=self._risk_controller,
            discovery_client=self._kalshi_rest,
        )
        self._tasks.append(
            asyncio.create_task(self._auto_trader.start(), name="auto-trader")
        )

        # Snapshot refresh loop
        self._tasks.append(
            asyncio.create_task(self._snapshot_refresh_loop(), name="snapshot-refresh")
        )

        # Task health monitor — catches provider crashes
        self._tasks.append(
            asyncio.create_task(self._task_health_monitor(), name="task-health-monitor")
        )

        logger.info("All provider tasks launched (%d tasks)", len(self._tasks))
        return True

    async def stop(self) -> None:
        """Stop all providers and release the lease."""
        if not self._running:
            return

        self._running = False
        logger.info("Ingestion orchestrator stopping")

        # Phase 8f — stop candle battery and scoring engine
        if self._candle_battery is not None:
            await self._candle_battery.stop()
        if self._scoring_engine is not None:
            await self._scoring_engine.stop()

        # Phase 8i — stop settlement watcher
        if self._settlement_watcher is not None:
            await self._settlement_watcher.stop()

        # Phase 8l — stop auto-trader
        if self._auto_trader is not None:
            await self._auto_trader.stop()

        # Stop all providers
        await self._binance.stop()
        await self._coinbase.stop()
        await self._coingecko.stop()
        for ws_client in self._kalshi_ws.values():
            await ws_client.stop()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Phase 8f — close database connection (shared by candle and model_run stores)
        if self._candle_db is not None:
            await self._candle_db.close()
            self._candle_db = None
            self._candle_store = None
            self._model_run_store = None
        self._model_run_db = None
        self._candle_battery = None
        self._scoring_engine = None
        self._settlement_watcher = None
        if self._paper_venue is not None:
            self._paper_venue.close()
        self._auto_trader = None
        self._paper_venue = None
        self._risk_controller = None

        # Release lease
        _LEASE.release(_OWNER_ID)
        logger.info("Ingestion orchestrator stopped, lease released")

    # ------------------------------------------------------------------
    # Provider callback registration
    # ------------------------------------------------------------------

    def _register_callbacks(self) -> None:
        """Register callbacks on all providers to feed the merger."""
        self._binance.on_trade(self._on_binance_trade)
        self._coinbase.on_ticker(self._on_coinbase_ticker)
        self._polymarket.on_sentiment(self._on_polymarket_sentiment)
        self._coingecko.on_macro_update(self._on_coingecko_update)

    def _register_kalshi_ws_callback(self, ticker: str, client: KalshiOrderBookWebSocketClient) -> None:
        """Register callback for a specific Kalshi WS client."""
        client.on_update(lambda state: self._on_kalshi_update(ticker, state))

    # ------------------------------------------------------------------
    # Provider callbacks — convert to Pydantic events and feed merger
    # ------------------------------------------------------------------

    async def _on_binance_trade(self, obs: BinancePriceObservation) -> None:
        """Binance trade observation callback."""
        asset = Asset.BTC if obs.symbol.upper().startswith("BTC") else Asset.ETH
        now = datetime.now(UTC)
        event = PriceObservationEvent(
            provider_event_id=f"binance-{uuid.uuid4().hex[:8]}",
            provider_ts=datetime.fromtimestamp(obs.trade_ts, tz=UTC) if obs.trade_ts else now,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            source=ProviderSource.BINANCE,
            asset=asset,
            spot_price_usd=obs.price,
            bid_usd=None,
            ask_usd=None,
            volume_24h_usd=None,
        )
        self._merger.update_binance(asset, event)
        self._health.record_event(f"binance_{asset.value.lower()}")

    async def _on_coinbase_ticker(self, obs: CoinbasePriceObservation) -> None:
        """Coinbase ticker observation callback."""
        asset = Asset.BTC if "BTC" in obs.product_id.upper() else Asset.ETH
        now = datetime.now(UTC)
        try:
            ts = datetime.fromisoformat(obs.timestamp.replace("Z", "+00:00")) if obs.timestamp else now
        except Exception:
            ts = now
        event = PriceObservationEvent(
            provider_event_id=f"coinbase-{uuid.uuid4().hex[:8]}",
            provider_ts=ts,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            source=ProviderSource.COINBASE,
            asset=asset,
            spot_price_usd=obs.price,
            bid_usd=obs.bid,
            ask_usd=obs.ask,
            volume_24h_usd=obs.volume_24h,
        )
        self._merger.update_coinbase(asset, event)
        self._health.record_event(f"coinbase_{asset.value.lower()}")

    async def _on_kalshi_update(self, ticker: str, state: KalshiOrderBookState) -> None:
        """Kalshi order book update callback."""
        asset = Asset.BTC if "BTC" in ticker.upper() else Asset.ETH
        now = datetime.now(UTC)
        event = KalshiOrderBookEvent(
            provider_event_id=f"kalshi-ws-{uuid.uuid4().hex[:8]}",
            provider_ts=now,
            receive_ts=now,
            source_status=SourceHealthStatus.STALE if state.is_stale else SourceHealthStatus.HEALTHY,
            asset=asset,
            market_ticker=ticker,
            yes_bid=state.yes_bid,
            yes_ask=state.yes_ask,
            no_bid=state.no_bid,
            no_ask=state.no_ask,
            yes_depth=state.yes_depth,
            no_depth=state.no_depth,
            sequence=state.last_sequence,
            midpoint=state.midpoint_cents,
        )
        self._merger.update_kalshi(event)
        self._health.record_event(f"kalshi_{asset.value.lower()}", sequence=state.last_sequence)

    async def _on_polymarket_sentiment(self, obs: PolymarketSentimentObservation) -> None:
        """Polymarket sentiment observation callback."""
        asset = Asset.BTC if "btc" in obs.market_slug.lower() or "bitcoin" in obs.question.lower() else Asset.ETH
        now = datetime.now(UTC)
        event = PolymarketSentimentEvent(
            provider_event_id=f"polymarket-{uuid.uuid4().hex[:8]}",
            provider_ts=now,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            asset=asset,
            market_slug=obs.market_slug,
            yes_price=obs.yes_price,
            no_price=obs.no_price,
            volume_usd=obs.volume_usd,
        )
        self._merger.update_polymarket(obs.market_slug, event)
        self._health.record_event(f"polymarket_{asset.value.lower()}")

    async def _on_coingecko_update(self, obs: CoinGeckoMacroObservation) -> None:
        """CoinGecko macro observation callback."""
        asset = Asset.BTC if obs.asset.upper() == "BTC" else Asset.ETH
        now = datetime.now(UTC)
        event = CoinGeckoMacroEvent(
            provider_event_id=f"coingecko-{uuid.uuid4().hex[:8]}",
            provider_ts=now,
            receive_ts=now,
            source_status=SourceHealthStatus.HEALTHY,
            asset=asset,
            market_cap_usd=obs.market_cap_usd,
            price_change_24h_pct=obs.price_change_24h_pct,
            total_volume_usd=obs.volume_24h_usd,
        )
        self._merger.update_coingecko(asset, event)
        self._health.record_event(f"coingecko_{asset.value.lower()}")

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _run_kalshi_discovery(self) -> None:
        """Periodically discover active Kalshi markets and start WS clients."""
        while self._running:
            try:
                markets = await self._kalshi_rest.discover_active_markets()
                self._active_markets = markets
                logger.info("Discovered %d active Kalshi markets", len(markets))

                # Start WS client for each new ticker
                for market in markets:
                    if market.ticker not in self._kalshi_ws:
                        client = KalshiOrderBookWebSocketClient(
                            market.ticker, api_key=self._kalshi_api_key
                        )
                        self._register_kalshi_ws_callback(market.ticker, client)
                        self._kalshi_ws[market.ticker] = client
                        task = asyncio.create_task(
                            client.connect_and_run(),
                            name=f"kalshi-ws-{market.ticker}",
                        )
                        self._tasks.append(task)
                        logger.info("Started Kalshi WS for %s", market.ticker)

                # Stop WS for closed markets
                active_tickers = {m.ticker for m in markets}
                for ticker, client in list(self._kalshi_ws.items()):
                    if ticker not in active_tickers:
                        await client.stop()
                        del self._kalshi_ws[ticker]
                        self._merger.clear_ticker(ticker)
                        logger.info("Stopped Kalshi WS for closed market %s", ticker)

            except Exception as exc:
                logger.error("Kalshi discovery error: %s", exc)
                self._health.record_error("kalshi_rest")

            # Re-discover every 60 seconds
            await asyncio.sleep(60)

    async def _run_polymarket_poller(self) -> None:
        """Periodically poll Polymarket for sentiment data."""
        while self._running:
            try:
                for market in self._active_markets:
                    if not self._running:
                        break
                    obs = await self._polymarket.poll_sentiment(market.ticker)
                    # Polymarket callback already fires via on_sentiment
                    if obs is None:
                        self._health.record_error(
                            f"polymarket_{Asset.BTC.value.lower()}"
                            if "BTC" in market.ticker.upper()
                            else f"polymarket_{Asset.ETH.value.lower()}"
                        )
            except Exception as exc:
                logger.error("Polymarket poll error: %s", exc)

            await asyncio.sleep(30)

    async def _snapshot_refresh_loop(self) -> None:
        """Periodically build snapshots from the merger."""
        while self._running:
            try:
                snapshots = self._merger.build_snapshots()
                for snap in snapshots:
                    self._latest_snapshots[snap.asset] = snap
            except Exception as exc:
                logger.error("Snapshot refresh error: %s", exc)

            await asyncio.sleep(2)

    async def _task_health_monitor(self) -> None:
        """Watch for provider tasks that crash and record errors.

        Every 10 seconds, scan all tracked tasks.  If a provider task has
        finished (done or cancelled), log it and record the error so the
        health summary reflects the failure.  This prevents silent task
        death — previously the Binance task could crash with an unhandled
        exception and no one would notice.
        """
        # Map task names to health monitor source names
        _TASK_SOURCE_MAP = {
            "binance-ws": "binance_ws",
            "coinbase-ws": "coinbase_ws",
            "kalshi-discovery": "kalshi_rest",
            "polymarket-poll": "polymarket_poll",
            "coingecko-poll": "coingecko_poll",
            "candle-battery": "candle_battery",
            "scoring-engine": "scoring_engine",
            "settlement-watcher": "settlement_watcher",
        }

        while self._running:
            await asyncio.sleep(10)
            for task in list(self._tasks):
                if task.done():
                    task_name = task.get_name()
                    source = _TASK_SOURCE_MAP.get(task_name)
                    if source is None:
                        continue  # internal task (snapshot-refresh, etc.)

                    if task.cancelled():
                        logger.warning("Provider task '%s' was cancelled", task_name)
                        self._health.record_error(source)
                    else:
                        exc = task.exception()
                        if exc is not None:
                            logger.error(
                                "Provider task '%s' crashed: %s", task_name, exc,
                            )
                            self._health.record_error(source)
                        else:
                            logger.warning(
                                "Provider task '%s' exited normally (unexpected)",
                                task_name,
                            )
                            self._health.record_error(source)

                    # Remove from task list so we don't re-report
                    self._tasks.remove(task)

    async def _run_scoring_engine(self) -> None:
        """Run the auto-scoring engine periodically to resolve model runs."""
        cycles_since_retrain = 10
        while self._running:
            try:
                if self._scoring_engine is not None:
                    # Determine new outcomes from candles
                    for asset in ("BTC", "ETH"):
                        try:
                            await self._scoring_engine.determine_outcomes_from_candles(asset)
                        except Exception as e:
                            logger.warning("Failed to determine outcomes from candles for %s: %s", asset, e)

                    # Score pending predictions
                    scored = await self._scoring_engine.score_pending_model_runs()
                    if scored > 0:
                        logger.info("Scoring engine resolved %d model runs", scored)

                    # Retrain models every 10 cycles (150 seconds) if there are scored predictions
                    cycles_since_retrain += 1
                    if cycles_since_retrain >= 10:
                        cycles_since_retrain = 0
                        logger.info("Triggering periodic background model retraining...")
                        results = await self._scoring_engine.retrain_models()
                        for asset, info in results.items():
                            if info.get("trained"):
                                logger.info("Background retrained %s: OK (%d samples)", asset, info.get("samples", 0))
                            else:
                                logger.debug("Background retrained %s: SKIPPED (%s)", asset, info.get("reason", ""))
            except Exception as exc:
                logger.error("Scoring engine error: %s", exc)

            await asyncio.sleep(15)
