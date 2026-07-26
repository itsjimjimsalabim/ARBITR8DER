"""Coinbase BTC/ETH spot price ingestion.

WebSocket: wss://ws-feed.exchange.coinbase.com — ticker channel
REST: https://api.exchange.coinbase.com — candles for backfill

No auth required for public market data. Rate limits: 10 req/sec REST.
Failure modes: connection drop, rate limit, symbol not found.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Coroutine

import httpx
import websockets
import websockets.exceptions

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
_COINBASE_REST_BASE = "https://api.exchange.coinbase.com"
_REQUEST_TIMEOUT = 10.0
_RECONNECT_DELAY = 2.0
_MAX_RECONNECT_DELAY = 30.0


class CoinbasePriceObservation:
    """Parsed Coinbase ticker observation."""

    def __init__(self, product_id: str, price: float, bid: float | None, ask: float | None,
                 volume_24h: float | None, timestamp: str) -> None:
        self.product_id = product_id
        self.price = price
        self.bid = bid
        self.ask = ask
        self.volume_24h = volume_24h
        self.timestamp = timestamp
        self.receive_ts = time.time()

    @property
    def age_seconds(self) -> float:
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            return self.receive_ts - ts.timestamp()
        except Exception:
            return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "volume_24h": self.volume_24h,
            "timestamp": self.timestamp,
            "age_seconds": round(self.age_seconds, 4),
        }


class CoinbaseSpotPriceStream:
    """Coinbase real-time spot price stream.

    Subscribes to ticker channel for BTC-USD and ETH-USD.
    Read-only — no order submission.
    """

    def __init__(self) -> None:
        self._last_observation: dict[str, CoinbasePriceObservation] = {}
        self._running = False
        self._connected = False
        self._callbacks: list[Callable[[CoinbasePriceObservation], Coroutine]] = []
        self._reconnect_delay = _RECONNECT_DELAY

    def on_ticker(self, callback: Callable[[CoinbasePriceObservation], Coroutine]) -> None:
        self._callbacks.append(callback)

    @property
    def last_observations(self) -> dict[str, CoinbasePriceObservation]:
        return dict(self._last_observation)

    async def connect_and_run(self, product_ids: list[str] | None = None) -> None:
        """Connect to Coinbase WebSocket and process ticker messages."""
        if product_ids is None:
            product_ids = ["BTC-USD", "ETH-USD"]

        self._running = True
        while self._running:
            try:
                async with websockets.connect(_COINBASE_WS_URL) as ws:
                    self._connected = True
                    self._reconnect_delay = _RECONNECT_DELAY
                    logger.info("Connected to Coinbase WebSocket")

                    subscribe_msg = {
                        "type": "subscribe",
                        "product_ids": product_ids,
                        "channels": ["ticker"],
                    }
                    await ws.send(json.dumps(subscribe_msg))

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg)
                            await self._handle_ticker(msg)
                        except json.JSONDecodeError:
                            pass

            except (websockets.exceptions.ConnectionClosed, ConnectionError, OSError) as exc:
                if not self._running:
                    break
                logger.warning("Coinbase WebSocket disconnected: %s — reconnecting in %.1fs", exc, self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, _MAX_RECONNECT_DELAY)

    async def _handle_ticker(self, msg: dict[str, Any]) -> None:
        if msg.get("type") != "ticker":
            return

        product_id = msg.get("product_id", "")
        price = float(msg.get("price", 0))
        bid = float(msg["bid"]) if "bid" in msg else None
        ask = float(msg["ask"]) if "ask" in msg else None
        vol = float(msg.get("volume_24h", 0)) if "volume_24h" in msg else None
        ts = msg.get("time", "")

        obs = CoinbasePriceObservation(
            product_id=product_id, price=price, bid=bid, ask=ask,
            volume_24h=vol, timestamp=ts,
        )
        self._last_observation[product_id] = obs

        for cb in self._callbacks:
            try:
                await cb(obs)
            except Exception as exc:
                logger.error("Coinbase callback error: %s", exc)

    async def fetch_candles(self, product_id: str, client: httpx.AsyncClient | None = None,
                            granularity: int = 60, count: int = 300) -> list[dict[str, Any]]:
        """Fetch candles from Coinbase REST API."""
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        try:
            url = f"{_COINBASE_REST_BASE}/products/{product_id}/candles"
            params = {"granularity": granularity, "start": "", "end": ""}
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.json()[:count]
            logger.warning("Coinbase candle fetch failed: HTTP %d", response.status_code)
            return []
        finally:
            if own_client:
                await client.aclose()

    async def stop(self) -> None:
        self._running = False
        self._connected = False

    @staticmethod
    def parse_fixture_ticker() -> dict[str, Any]:
        """Sanitized Coinbase ticker message."""
        return {
            "type": "ticker",
            "product_id": "BTC-USD",
            "price": "68123.45",
            "bid": "68120.00",
            "ask": "68127.00",
            "volume_24h": "12345.678",
            "time": "2026-07-23T18:50:00.123456Z",
            "trade_id": 987654321,
            "last_size": "0.001",
        }
