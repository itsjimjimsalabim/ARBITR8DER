"""Binance WebSocket spot price stream — BTC/ETH real-time pricing.

Connects to Binance WebSocket API for BTC/USDT and ETH/USDT trade streams.
Wraps each trade in an EventEnvelope and routes to the pipeline.

Per Theories_of_Operations: "Binance + Coinbase are the fast spot price/check
streams. We use both so we can see movement, spread, and if they disagree."
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

BINANCE_WS_BASE_URL = "wss://stream.binance.com:9443/ws"
BINANCE_TRADE_STREAMS = "btcusdt@trade/ethusdt@trade"

# Reconnection settings
INITIAL_RECONNECT_DELAY_SECONDS = 1.0
MAX_RECONNECT_DELAY_SECONDS = 30


class BinanceSpotPriceStream:
    """WebSocket client for real-time BTC/ETH spot prices from Binance.

    Subscribes to Binance trade streams. Each trade updates the spot price
    for BTC and ETH. Wraps data as EventEnvelope and routes via callback.
    """

    def __init__(
        self,
        on_event_callback: Callable[[EventEnvelope], None],
        ws_url: str = BINANCE_WS_BASE_URL,
        streams: str = BINANCE_TRADE_STREAMS,
    ):
        self.on_event_callback = on_event_callback
        self.ws_url = ws_url
        self.streams = streams

        self._is_connected: bool = False
        self._running: bool = False
        self._last_trade_timestamp: float = 0.0
        self._latest_spot_prices: dict[str, float] = {}
        self._reconnect_delay: float = INITIAL_RECONNECT_DELAY_SECONDS

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def latest_spot_prices(self) -> dict[str, float]:
        return dict(self._latest_spot_prices)

    def _parse_trade_message(self, trade_data: dict) -> Optional[EventEnvelope]:
        """Parse a Binance trade message into an EventEnvelope."""
        symbol = trade_data.get("s", "")

        # Map symbol to our asset name
        asset_name = None
        if symbol == "BTCUSDT":
            asset_name = "BTC"
        elif symbol == "ETHUSDT":
            asset_name = "ETH"
        else:
            return None

        price = float(trade_data.get("p", 0))
        quantity = float(trade_data.get("q", 0))
        trade_timestamp = trade_data.get("T", time.time() * 1000) / 1000.0

        self._latest_spot_prices[asset_name] = price

        return EventEnvelope(
            source="binance_ws",
            event_type=EventType.SPOT_PRICE,
            payload={
                "asset": asset_name,
                "price": price,
                "quantity": quantity,
                "trade_id": trade_data.get("t"),
                "symbol": symbol,
                "trade_time": trade_timestamp,
                "provider": "binance",
            },
            ticker=f"{asset_name}_SPOT",
            timestamp=trade_timestamp,
        )

    async def _connection_loop(self) -> None:
        """Main WebSocket connection loop with auto-reconnect."""
        stream_url = f"{self.ws_url}/{self.streams}"

        while self._running:
            try:
                async with websockets.connect(
                    stream_url,
                    ping_interval=20,
                    ping_timeout=10,
                ) as websocket_connection:
                    self._is_connected = True
                    self._reconnect_delay = INITIAL_RECONNECT_DELAY_SECONDS

                    logger.info(
                        "Binance WS connected: streams=%s", self.streams
                    )

                    async for raw_message in websocket_connection:
                        self._last_trade_timestamp = time.time()

                        try:
                            trade_data = json.loads(raw_message)
                        except json.JSONDecodeError:
                            continue

                        event_envelope = self._parse_trade_message(trade_data)
                        if event_envelope:
                            self.on_event_callback(event_envelope)

            except ConnectionClosed as ws_close_error:
                self._is_connected = False
                logger.warning(
                    "Binance WS closed (code=%s): %s",
                    ws_close_error.code,
                    ws_close_error.reason,
                )
            except OSError as network_error:
                self._is_connected = False
                logger.warning("Binance WS network error: %s", network_error)
            except Exception as unexpected_error:
                self._is_connected = False
                logger.error("Binance WS unexpected error: %s", unexpected_error)

            if not self._running:
                break

            logger.info(
                "Reconnecting Binance WS in %.1fs...", self._reconnect_delay
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, MAX_RECONNECT_DELAY_SECONDS
            )

    def start(self) -> None:
        """Start the Binance WebSocket connection in a background thread."""
        if self._running:
            logger.warning("Binance WS already running")
            return

        self._running = True

        loop = asyncio.new_event_loop()
        self._loop = loop

        import threading

        def run_event_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._connection_loop())

        self._thread = threading.Thread(
            target=run_event_loop, daemon=True, name="binance-ws-loop"
        )
        self._thread.start()
        logger.info("Binance spot price stream started")

    def stop(self) -> None:
        """Stop the WebSocket connection gracefully."""
        self._running = False
        if hasattr(self, "_loop") and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._is_connected = False
        logger.info("Binance spot price stream stopped")

    def get_health_info(self) -> dict[str, Any]:
        """Get current connection health information."""
        return {
            "connected": self._is_connected,
            "running": self._running,
            "last_trade_age_s": (
                time.time() - self._last_trade_timestamp
                if self._last_trade_timestamp > 0
                else None
            ),
            "latest_spot_prices": dict(self._latest_spot_prices),
        }
