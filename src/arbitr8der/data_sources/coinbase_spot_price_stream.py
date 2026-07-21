"""Coinbase WebSocket spot price stream — BTC/ETH cross-check pricing.

Connects to Coinbase WebSocket for real-time BTC-USD and ETH-USD trade feeds.
Used as a cross-reference against Binance to detect spread and disagreement.

Per Theories_of_Operations: "Coinbase is a slower probability/sentiment overlay"
— actually, Coinbase is a fast spot price cross-check. Polymarket is the sentiment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from ..market_data.immutable_event_envelope_wrapper import EventEnvelope, EventType

logger = logging.getLogger(__name__)

COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
COINBASE_TRADE_CHANNELS = ["ticker"]
COINBASE_PRODUCT_IDS = ["BTC-USD", "ETH-USD"]

INITIAL_RECONNECT_DELAY_SECONDS = 1.0
MAX_RECONNECT_DELAY_SECONDS = 30


class CoinbaseSpotPriceStream:
    """WebSocket client for real-time BTC/ETH spot prices from Coinbase.

    Subscribes to Coinbase ticker channel for BTC-USD and ETH-USD.
    Wraps each ticker update as EventEnvelope and routes via callback.
    Used as cross-check against Binance to detect price disagreement.
    """

    def __init__(
        self,
        on_event_callback: Callable[[EventEnvelope], None],
        ws_url: str = COINBASE_WS_URL,
        product_ids: list[str] | None = None,
    ):
        self.on_event_callback = on_event_callback
        self.ws_url = ws_url
        self.product_ids = product_ids or list(COINBASE_PRODUCT_IDS)

        self._is_connected: bool = False
        self._running: bool = False
        self._last_ticker_timestamp: float = 0.0
        self._latest_spot_prices: dict[str, float] = {}
        self._reconnect_delay: float = INITIAL_RECONNECT_DELAY_SECONDS

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def latest_spot_prices(self) -> dict[str, float]:
        return dict(self._latest_spot_prices)

    def _parse_ticker_message(self, ticker_data: dict) -> Optional[EventEnvelope]:
        """Parse a Coinbase ticker message into an EventEnvelope."""
        product_id = ticker_data.get("product_id", "")

        # Map product_id to our asset name
        asset_name = None
        if product_id == "BTC-USD":
            asset_name = "BTC"
        elif product_id == "ETH-USD":
            asset_name = "ETH"
        else:
            return None

        price = float(ticker_data.get("price", 0))
        trade_timestamp = time.time()

        self._latest_spot_prices[asset_name] = price

        return EventEnvelope(
            source="coinbase_ws",
            event_type=EventType.SPOT_PRICE,
            payload={
                "asset": asset_name,
                "price": price,
                "product_id": product_id,
                "provider": "coinbase",
                "bid": float(ticker_data.get("best_bid", 0)),
                "ask": float(ticker_data.get("best_ask", 0)),
                "volume_24h": float(ticker_data.get("volume_24h", 0)),
            },
            ticker=f"{asset_name}_SPOT",
            timestamp=trade_timestamp,
        )

    async def _connection_loop(self) -> None:
        """Main WebSocket connection loop with auto-reconnect."""
        while self._running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                ) as websocket_connection:
                    self._is_connected = True
                    self._reconnect_delay = INITIAL_RECONNECT_DELAY_SECONDS

                    # Subscribe to ticker channel for our products
                    subscribe_message = json.dumps({
                        "type": "subscribe",
                        "product_ids": self.product_ids,
                        "channels": COINBASE_TRADE_CHANNELS,
                    })
                    await websocket_connection.send(subscribe_message)

                    logger.info(
                        "Coinbase WS connected: products=%s", self.product_ids
                    )

                    async for raw_message in websocket_connection:
                        self._last_ticker_timestamp = time.time()

                        try:
                            message_data = json.loads(raw_message)
                        except json.JSONDecodeError:
                            continue

                        message_type = message_data.get("type", "")

                        if message_type == "ticker":
                            event_envelope = self._parse_ticker_message(message_data)
                            if event_envelope:
                                self.on_event_callback(event_envelope)

                        elif message_type == "subscriptions":
                            logger.info("Coinbase WS subscribed: %s", message_data)

                        elif message_type == "error":
                            logger.warning(
                                "Coinbase WS error: %s",
                                message_data.get("message", ""),
                            )

            except ConnectionClosed as ws_close_error:
                self._is_connected = False
                logger.warning(
                    "Coinbase WS closed (code=%s): %s",
                    ws_close_error.code,
                    ws_close_error.reason,
                )
            except OSError as network_error:
                self._is_connected = False
                logger.warning("Coinbase WS network error: %s", network_error)
            except Exception as unexpected_error:
                self._is_connected = False
                logger.error("Coinbase WS unexpected error: %s", unexpected_error)

            if not self._running:
                break

            logger.info(
                "Reconnecting Coinbase WS in %.1fs...", self._reconnect_delay
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, MAX_RECONNECT_DELAY_SECONDS
            )

    def start(self) -> None:
        """Start the Coinbase WebSocket connection in a background thread."""
        if self._running:
            logger.warning("Coinbase WS already running")
            return

        self._running = True

        loop = asyncio.new_event_loop()
        self._loop = loop

        import threading

        def run_event_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._connection_loop())

        self._thread = threading.Thread(
            target=run_event_loop, daemon=True, name="coinbase-ws-loop"
        )
        self._thread.start()
        logger.info("Coinbase spot price stream started")

    def stop(self) -> None:
        """Stop the WebSocket connection gracefully."""
        self._running = False
        if hasattr(self, "_loop") and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._is_connected = False
        logger.info("Coinbase spot price stream stopped")

    def get_health_info(self) -> dict[str, Any]:
        """Get current connection health information."""
        return {
            "connected": self._is_connected,
            "running": self._running,
            "last_ticker_age_s": (
                time.time() - self._last_ticker_timestamp
                if self._last_ticker_timestamp > 0
                else None
            ),
            "latest_spot_prices": dict(self._latest_spot_prices),
        }
