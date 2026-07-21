"""Kalshi WebSocket client — real-time orderbook snapshots and deltas.

Maintains a persistent WebSocket connection to Kalshi's trade API stream.
Emits EventEnvelope events for orderbook updates.

Per Theories_of_Operations: "If the book gets stale, gaps, reconnects, or loses
its snapshot, it is not trusted and the AI cannot trade it until it is good again."
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional

import jwt
import websockets
from websockets.exceptions import ConnectionClosed

from ..market_data.immutable_event_envelope_wrapper import EventEnvelope, EventType

logger = logging.getLogger(__name__)

KALSHI_WS_BASE_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"

# Reconnection settings
MAX_RECONNECT_DELAY_SECONDS = 60
INITIAL_RECONNECT_DELAY_SECONDS = 1.0
WS_PING_INTERVAL_SECONDS = 30


class KalshiOrderbookWebSocketClient:
    """WebSocket client for Kalshi real-time orderbook data.

    Subscribes to orderbook channels for specified tickers.
    Emits EventEnvelope events (ORDERBOOK_SNAPSHOT, ORDERBOOK_DELTA) via callback.

    Handles automatic reconnection with exponential backoff.
    """

    def __init__(
        self,
        api_key_id: str,
        private_key_pem: bytes,
        on_event_callback: Callable[[EventEnvelope], None],
        ws_url: str = KALSHI_WS_BASE_URL,
    ):
        self.api_key_id = api_key_id
        self.private_key_pem = private_key_pem
        self.on_event_callback = on_event_callback
        self.ws_url = ws_url

        self._websocket_connection: Optional[Any] = None
        self._is_connected: bool = False
        self._running: bool = False
        self._subscribed_tickers: set[str] = set()
        self._reconnect_delay: float = INITIAL_RECONNECT_DELAY_SECONDS
        self._last_message_timestamp: float = 0.0
        self._sequence_number: int = 0

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def last_message_timestamp(self) -> float:
        return self._last_message_timestamp

    def _generate_jwt_token(self) -> str:
        """Generate JWT for WebSocket authentication."""
        now = time.time()
        payload = {
            "iss": self.api_key_id,
            "sub": self.api_key_id,
            "iat": int(now),
            "exp": int(now) + 86400,
        }
        return jwt.encode(payload, self.private_key_pem, algorithm="RS512")

    async def _connect_and_subscribe(self) -> None:
        """Establish WebSocket connection and subscribe to tickers."""
        token = self._generate_jwt_token()
        auth_message = json.dumps({"type": "login", "token": token})

        connect_url = f"{self.ws_url}?token={token}"

        self._websocket_connection = await websockets.connect(
            connect_url,
            ping_interval=WS_PING_INTERVAL_SECONDS,
            ping_timeout=10,
            close_timeout=5,
        )

        self._is_connected = True
        self._reconnect_delay = INITIAL_RECONNECT_DELAY_SECONDS

        logger.info("Kalshi WebSocket connected")

        # Send auth message
        await self._websocket_connection.send(auth_message)

        # Subscribe to orderbook channels for all tracked tickers
        for ticker_symbol in self._subscribed_tickers:
            subscribe_message = json.dumps({
                "type": "subscribe",
                "channel": "orderbook_delta",
                "tickers": [ticker_symbol],
            })
            await self._websocket_connection.send(subscribe_message)
            logger.info("Subscribed to orderbook for ticker: %s", ticker_symbol)

    async def _handle_incoming_message(self, raw_message: str) -> None:
        """Parse and emit an EventEnvelope from a raw WebSocket message."""
        self._last_message_timestamp = time.time()

        try:
            message_data = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Kalshi WS message: %s", raw_message[:200])
            return

        message_type = message_data.get("type", "")
        message_payload = message_data.get("payload", {})

        if message_type == "orderbook_snapshot":
            ticker_symbol = message_payload.get("ticker", "")
            event_envelope = EventEnvelope(
                source="kalshi_ws",
                event_type=EventType.ORDERBOOK_SNAPSHOT,
                payload={
                    "ticker": ticker_symbol,
                    "yes_best": message_payload.get("yes_best"),
                    "no_best": message_payload.get("no_best"),
                    "spread": message_payload.get("spread"),
                    "yes_volume": message_payload.get("yes_volume"),
                    "no_volume": message_payload.get("no_volume"),
                    "market_status": message_payload.get("market_status"),
                },
                ticker=ticker_symbol,
            )
            logger.debug("Orderbook snapshot for %s", ticker_symbol)
            self.on_event_callback(event_envelope)

        elif message_type == "orderbook_delta":
            ticker_symbol = message_payload.get("ticker", "")
            self._sequence_number += 1
            event_envelope = EventEnvelope(
                source="kalshi_ws",
                event_type=EventType.ORDERBOOK_DELTA,
                payload={
                    "ticker": ticker_symbol,
                    "yes_best": message_payload.get("yes_best"),
                    "no_best": message_payload.get("no_best"),
                    "spread": message_payload.get("spread"),
                    "delta_type": message_payload.get("delta_type"),
                    "sequence": self._sequence_number,
                },
                ticker=ticker_symbol,
            )
            self.on_event_callback(event_envelope)

        elif message_type == "error":
            logger.warning("Kalshi WS error: %s", message_payload.get("message", ""))

        elif message_type == "subscribed":
            logger.info("Kalshi WS subscribed to channel: %s", message_payload.get("channel"))

        else:
            logger.debug("Kalshi WS unhandled message type: %s", message_type)

    async def _connection_loop(self) -> None:
        """Main reconnection loop — reconnects on any disconnect."""
        while self._running:
            try:
                await self._connect_and_subscribe()
                async for raw_message in self._websocket_connection:
                    await self._handle_incoming_message(raw_message)

            except ConnectionClosed as ws_close_error:
                self._is_connected = False
                logger.warning(
                    "Kalshi WS closed (code=%s): %s",
                    ws_close_error.code,
                    ws_close_error.reason,
                )
            except OSError as network_error:
                self._is_connected = False
                logger.warning("Kalshi WS network error: %s", network_error)
            except Exception as unexpected_error:
                self._is_connected = False
                logger.error("Kalshi WS unexpected error: %s", unexpected_error)

            if not self._running:
                break

            logger.info(
                "Reconnecting Kalshi WS in %.1fs...", self._reconnect_delay
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, MAX_RECONNECT_DELAY_SECONDS
            )

    def subscribe_ticker(self, ticker_symbol: str) -> None:
        """Add a ticker to the subscription list (before or after connect)."""
        self._subscribed_tickers.add(ticker_symbol)

    def start(self) -> None:
        """Start the WebSocket connection in a background thread."""
        if self._running:
            logger.warning("Kalshi WS already running")
            return

        self._running = True

        loop = asyncio.new_event_loop()
        self._loop = loop

        import threading

        def run_event_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._connection_loop())

        self._thread = threading.Thread(
            target=run_event_loop, daemon=True, name="kalshi-ws-loop"
        )
        self._thread.start()
        logger.info("Kalshi WebSocket background thread started")

    def stop(self) -> None:
        """Stop the WebSocket connection gracefully."""
        self._running = False
        if hasattr(self, "_loop") and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._is_connected = False
        logger.info("Kalshi WebSocket stopped")

    def get_health_info(self) -> dict[str, Any]:
        """Get current connection health information."""
        return {
            "connected": self._is_connected,
            "running": self._running,
            "subscribed_tickers": list(self._subscribed_tickers),
            "last_message_age_s": (
                time.time() - self._last_message_timestamp
                if self._last_message_timestamp > 0
                else None
            ),
            "sequence_number": self._sequence_number,
        }
