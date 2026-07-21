"""Data pipeline orchestrator — starts/stops all streams, routes events to HotState + DB.

Central coordinator that wires all 5 data sources to:
  1. HotState (in-memory snapshot for fast reads)
  2. EventRepository (SQLite persistence for cold storage)
  3. StreamHealthStatusMonitor (staleness tracking)

Per Theories_of_Operations: "The AI must not wait on DB writes in the hot path.
Events route to HotState synchronously, persist to DB asynchronously."
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .immutable_event_envelope_wrapper import EventEnvelope, EventType
from .thread_safe_hot_state_manager import ThreadSafeHotStateManager
from .stream_health_status_monitor import StreamHealthStatusMonitor
from ..config.typed_configuration_settings_module import Settings, load_settings
from ..storage.sqlite_database_connection_manager import SqliteDatabaseConnectionManager
from ..storage.event_persistence_repository_handler import EventPersistenceRepositoryHandler

logger = logging.getLogger(__name__)

# Stream source names used throughout the pipeline
KALSHI_REST_SOURCE = "kalshi_rest"
KALSHI_WS_SOURCE = "kalshi_ws"
BINANCE_WS_SOURCE = "binance_ws"
COINBASE_WS_SOURCE = "coinbase_ws"
POLYMARKET_SOURCE = "polymarket"
COINGECKO_SOURCE = "coingecko"


class DataPipelineOrchestrator:
    """Central coordinator for all data streams.

    Starts/stops all data sources, routes events to HotState (fast path)
    and EventRepository (async persistence), monitors stream health.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        database_manager: Optional[SqliteDatabaseConnectionManager] = None,
        hot_state_manager: Optional[ThreadSafeHotStateManager] = None,
        health_monitor: Optional[StreamHealthStatusMonitor] = None,
    ):
        self.settings = settings or load_settings()

        # Core components
        self._database_manager = database_manager or SqliteDatabaseConnectionManager(
            str(self.settings.database_path)
        )
        self._database_manager.connect()

        self._event_repository = EventPersistenceRepositoryHandler(self._database_manager)
        self._hot_state_manager = hot_state_manager or ThreadSafeHotStateManager()
        self._health_monitor = health_monitor or StreamHealthStatusMonitor()

        # Stream instances (created on start, not on init)
        self._kalshi_rest_client = None
        self._kalshi_websocket_client = None
        self._binance_spot_stream = None
        self._coinbase_spot_stream = None
        self._polymarket_sentiment_poller = None
        self._coingecko_macro_poller = None

        self._is_running: bool = False
        self._event_count: int = 0
        self._started_timestamp: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def event_count(self) -> int:
        return self._event_count

    def route_event(self, event_envelope: EventEnvelope) -> None:
        """Central event router — called by all data sources.

        Fast path: update HotState synchronously.
        Cold path: persist to DB (fire-and-forget for now, batch later).
        """
        self._event_count += 1
        source_name = event_envelope.source

        # Update stream health monitor
        self._health_monitor.record_message_received(source_name)

        # Route to HotState (fast path — synchronous)
        self._update_hot_state_from_event(event_envelope)

        # Persist to DB (cold path — we log it; batch/async can be added later)
        try:
            self._event_repository.insert(event_envelope)
        except Exception as persistence_error:
            logger.warning(
                "Failed to persist event from %s: %s",
                source_name,
                persistence_error,
            )

    def _update_hot_state_from_event(self, event_envelope: EventEnvelope) -> None:
        """Update the in-memory HotState based on event type."""
        payload = dict(event_envelope.payload)
        event_type = event_envelope.event_type

        if event_type in (EventType.ORDERBOOK_SNAPSHOT, EventType.ORDERBOOK_DELTA):
            self._hot_state_manager.update_orderbook(
                ticker=payload.get("ticker", ""),
                book_data={
                    "yes_best": payload.get("yes_best"),
                    "no_best": payload.get("no_best"),
                    "spread": payload.get("spread"),
                    "source": KALSHI_WS_SOURCE,
                },
            )

        elif event_type == EventType.SPOT_PRICE:
            asset_name = payload.get("asset", "")
            price_value = payload.get("price")
            if asset_name and price_value:
                self._hot_state_manager.update_spot_price(
                    asset=asset_name,
                    price=float(price_value),
                )

        elif event_type == EventType.SENTIMENT:
            asset_name = payload.get("asset", "")
            sentiment_value = payload.get("sentiment")
            if asset_name and sentiment_value is not None:
                self._hot_state_manager.update_sentiment(
                    asset=asset_name,
                    score=float(sentiment_value),
                )

        elif event_type == EventType.MACRO:
            macro_data = payload.get("macro", {})
            if macro_data:
                self._hot_state_manager.update_macro(data=macro_data)

    async def start_all_data_sources(self) -> None:
        """Start all data source streams."""
        if self._is_running:
            logger.warning("Data pipeline already running")
            return

        logger.info("Starting all data sources...")

        # 1. Kalshi REST — market discovery
        from ..data_sources.kalshi_rest_api_client_handler import KalshiRestApiClientHandler

        self._kalshi_rest_client = KalshiRestApiClientHandler(
            api_key_id=self.settings.kalshi_api_key_id,
            private_key_path=self.settings.kalshi_private_key_path,
        )
        try:
            active_tickers = await self._kalshi_rest_client.get_current_tickers()
            logger.info("Active Kalshi tickers: %s", active_tickers)

            # Update HotState with active tickers
            for asset_name, ticker_name in active_tickers.items():
                self._hot_state_manager.update_active_ticker(
                    asset=asset_name, ticker=ticker_name
                )
        except Exception as kalshi_rest_error:
            logger.warning("Kalshi REST failed to start: %s", kalshi_rest_error)
            self._health_monitor.record_error(
                KALSHI_REST_SOURCE, str(kalshi_rest_error)
            )

        # 2. Kalshi WebSocket — orderbook stream
        from ..data_sources.kalshi_orderbook_websocket_client import KalshiOrderbookWebSocketClient

        self._kalshi_websocket_client = KalshiOrderbookWebSocketClient(
            api_key_id=self.settings.kalshi_api_key_id,
            private_key_pem=self._kalshi_rest_client._private_key_pem,
            on_event_callback=self.route_event,
        )

        # Subscribe to all active tickers
        for ticker_name in active_tickers.values():
            self._kalshi_websocket_client.subscribe_ticker(ticker_name)

        self._kalshi_websocket_client.start()

        # 3. Binance WebSocket — spot prices
        from ..data_sources.binance_spot_price_stream import BinanceSpotPriceStream

        self._binance_spot_stream = BinanceSpotPriceStream(
            on_event_callback=self.route_event,
        )
        self._binance_spot_stream.start()

        # 4. Coinbase WebSocket — spot cross-check
        from ..data_sources.coinbase_spot_price_stream import CoinbaseSpotPriceStream

        self._coinbase_spot_stream = CoinbaseSpotPriceStream(
            on_event_callback=self.route_event,
        )
        self._coinbase_spot_stream.start()

        # 5. Polymarket — sentiment polling
        from ..data_sources.polymarket_sentiment_analysis_poller import PolymarketSentimentAnalysisPoller

        self._polymarket_sentiment_poller = PolymarketSentimentAnalysisPoller(
            on_event_callback=self.route_event,
            poll_interval_seconds=30,
        )
        self._polymarket_sentiment_poller.start()

        # 6. CoinGecko — macro data polling
        from ..data_sources.coingecko_macro_data_poller import CoinGeckoMacroDataPoller

        self._coingecko_macro_poller = CoinGeckoMacroDataPoller(
            on_event_callback=self.route_event,
            poll_interval_seconds=60,
        )
        self._coingecko_macro_poller.start()

        self._is_running = True
        self._started_timestamp = time.time()
        logger.info("All data sources started successfully")

    def stop_all_data_sources(self) -> None:
        """Stop all data source streams gracefully."""
        logger.info("Stopping all data sources...")

        stream_stoppers = [
            ("Kalshi WS", self._kalshi_websocket_client),
            ("Binance WS", self._binance_spot_stream),
            ("Coinbase WS", self._coinbase_spot_stream),
            ("Polymarket", self._polymarket_sentiment_poller),
            ("CoinGecko", self._coingecko_macro_poller),
        ]

        for stream_name, stream_instance in stream_stoppers:
            if stream_instance:
                try:
                    stream_instance.stop()
                    logger.info("Stopped %s", stream_name)
                except Exception as stop_error:
                    logger.warning("Error stopping %s: %s", stream_name, stop_error)

        self._is_running = False
        logger.info(
            "All data sources stopped (total events processed: %d)", self._event_count
        )

    async def shutdown(self) -> None:
        """Full shutdown — stop streams, close DB connection."""
        self.stop_all_data_sources()

        if self._kalshi_rest_client:
            await self._kalshi_rest_client.close()

        if self._database_manager:
            self._database_manager.close()

        logger.info("Data pipeline fully shut down")

    def get_status(self) -> dict[str, Any]:
        """Get full pipeline status for display."""
        uptime_seconds = 0.0
        if self._started_timestamp > 0:
            uptime_seconds = time.time() - self._started_timestamp

        return {
            "running": self._is_running,
            "uptime_seconds": uptime_seconds,
            "total_events_processed": self._event_count,
            "hot_state_generation": self._hot_state_manager.generation,
            "stream_health": self._health_monitor.get_health_summary(),
            "hot_state": self._hot_state_manager.snapshot().to_dict(),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.stop_all_data_sources()
        if self._database_manager:
            self._database_manager.close()
