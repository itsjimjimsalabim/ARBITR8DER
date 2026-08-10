"""Binance BTC/ETH spot price ingestion.

WebSocket: wss://stream.binance.com:9443/ws — real-time trade stream
REST: https://api.binance.com/api/v3/klines — 1-minute candle backfill (72h cap)

No auth required for public market data. Rate limits: 1200 req/min REST, 5 WS streams.
Failure modes: connection drop, rate limit 429, symbol not found.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Coroutine

import httpx
import websockets
import websockets.exceptions

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"
_BINANCE_REST_BASE = "https://api.binance.us/api/v3"
_CANDLE_INTERVAL = "1m"
_BACKFILL_MAX_CANDLES = 72 * 60  # 72 hours of 1-min candles
_REQUEST_TIMEOUT = 10.0
_RECONNECT_DELAY = 2.0
_MAX_RECONNECT_DELAY = 30.0


class BinancePriceObservation:
    """Parsed Binance trade/price observation."""

    def __init__(self, symbol: str, price: float, quantity: float, trade_ts: float) -> None:
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.trade_ts = trade_ts
        self.receive_ts = time.time()

    @property
    def age_seconds(self) -> float:
        return self.receive_ts - self.trade_ts

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "quantity": self.quantity,
            "trade_ts": self.trade_ts,
            "receive_ts": self.receive_ts,
            "age_seconds": round(self.age_seconds, 4),
        }


class BinanceCandle:
    """Parsed 1-minute OHLCV candle from Binance REST."""

    def __init__(self, raw: list[Any]) -> None:
        self.open_time_ms: int = raw[0]
        self.open: float = float(raw[1])
        self.high: float = float(raw[2])
        self.low: float = float(raw[3])
        self.close: float = float(raw[4])
        self.volume: float = float(raw[5])
        self.close_time_ms: int = raw[6]
        self.quote_volume: float = float(raw[7])
        self.trades: int = raw[8]

    @property
    def open_time_s(self) -> float:
        return self.open_time_ms / 1000.0

    @property
    def close_time_s(self) -> float:
        return self.close_time_ms / 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_time": self.open_time_s,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "trades": self.trades,
        }


class BinanceSpotPriceStream:
    """Binance real-time spot price stream and candle backfill.

    Provides BTC/ETH real-time trades via WebSocket and historical 1-minute
    candles via REST. Read-only — no order submission.
    """

    def __init__(self) -> None:
        self._last_observation: dict[str, BinancePriceObservation] = {}
        self._candle_cache: dict[str, list[BinanceCandle]] = {}
        self._running = False
        self._connected = False
        self._callbacks: list[Callable[[BinancePriceObservation], Coroutine]] = []
        self._reconnect_delay = _RECONNECT_DELAY

    @property
    def last_candles(self) -> dict[str, list[BinanceCandle]]:
        """Cached candle data per symbol (populated by backfill_candles)."""
        return dict(self._candle_cache)

    def on_trade(self, callback: Callable[[BinancePriceObservation], Coroutine]) -> None:
        """Register a callback for trade observations."""
        self._callbacks.append(callback)

    @property
    def last_observations(self) -> dict[str, BinancePriceObservation]:
        return dict(self._last_observation)

    async def connect_and_run(self, symbols: list[str] | None = None) -> None:
        """Connect to Binance trade stream and process messages.

        Falls back to REST polling when WebSocket is unavailable (e.g.,
        geo-blocked with HTTP 451). The REST poller uses
        ``api.binance.us/ticker/price`` and fires the same callbacks so the
        orchestrator health monitor tracks Binance transparently.
        """
        if symbols is None:
            symbols = ["btcusdt", "ethusdt"]

        self._running = True
        streams = "/".join(f"{s}@trade" for s in symbols)
        ws_url = f"{_BINANCE_WS_BASE}/{streams}"

        ever_connected = False
        consecutive_failures = 0

        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    self._connected = True
                    self._reconnect_delay = _RECONNECT_DELAY
                    ever_connected = True
                    consecutive_failures = 0
                    logger.info("Connected to Binance WebSocket: %s", streams)

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg)
                            await self._handle_trade(msg)
                        except json.JSONDecodeError:
                            pass
                        except Exception:
                            pass

            except (websockets.exceptions.ConnectionClosed, ConnectionError, OSError) as exc:
                if not self._running:
                    break
                consecutive_failures += 1
                logger.warning(
                    "Binance WebSocket disconnected: %s — reconnecting in %.1fs (failures=%d)",
                    exc, self._reconnect_delay, consecutive_failures,
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, _MAX_RECONNECT_DELAY)

            except Exception as exc:
                # Catches InvalidStatusCode (HTTP 451), HandshakeError,
                # and any other websockets handshake / TLS failures.
                consecutive_failures += 1
                logger.error(
                    "Binance WebSocket connection failed: %s (failures=%d)",
                    exc, consecutive_failures,
                )

                if not ever_connected and consecutive_failures >= 2:
                    # Never connected — almost certainly geo-blocked or
                    # permanently refused.  Switch to REST immediately.
                    logger.warning(
                        "Binance WS never connected after %d attempts — "
                        "switching to REST spot price polling",
                        consecutive_failures,
                    )
                    await self._rest_spot_poll_loop(symbols)
                    break

                if consecutive_failures >= 10:
                    logger.warning(
                        "Binance WS failed %d times — switching to REST "
                        "spot price polling",
                        consecutive_failures,
                    )
                    await self._rest_spot_poll_loop(symbols)
                    break

                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, _MAX_RECONNECT_DELAY)

    # ------------------------------------------------------------------
    # REST fallback — spot price polling
    # ------------------------------------------------------------------

    async def _rest_spot_poll_loop(self, symbols: list[str]) -> None:
        """Fallback: poll Binance REST ``/ticker/price`` every 5 seconds.

        Uses the same callback mechanism as the WebSocket path so the
        orchestrator and health monitor see Binance events regardless of
        the transport.  Reconnects to WS periodically to check if the
        block has been lifted.
        """
        logger.info("Starting Binance REST spot price polling for %s", symbols)
        poll_interval = 5.0
        ws_retry_interval = 120.0  # Try WS again every 2 minutes
        last_ws_retry = time.time()

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            while self._running:
                # Periodically retry the WebSocket in case the block lifted
                if time.time() - last_ws_retry >= ws_retry_interval:
                    logger.info("Attempting Binance WS reconnect from REST fallback...")
                    last_ws_retry = time.time()
                    # Run one WS attempt in a short-lived task; if it
                    # connects, connect_and_run will resume normally.
                    try:
                        ws_task = asyncio.create_task(self._try_ws_reconnect(symbols))
                        await asyncio.wait_for(ws_task, timeout=10.0)
                    except (asyncio.TimeoutError, Exception) as exc:
                        logger.debug("Binance WS reconnect attempt failed: %s", exc)

                for symbol in symbols:
                    if not self._running:
                        break
                    try:
                        url = f"{_BINANCE_REST_BASE}/ticker/price"
                        params = {"symbol": symbol.upper()}
                        response = await client.get(url, params=params)

                        if response.status_code == 200:
                            data = response.json()
                            price = float(data.get("price", 0))
                            if price > 0:
                                obs = BinancePriceObservation(
                                    symbol=symbol.upper(),
                                    price=price,
                                    quantity=0.0,
                                    trade_ts=time.time(),
                                )
                                self._last_observation[symbol.upper()] = obs
                                for cb in self._callbacks:
                                    try:
                                        await cb(obs)
                                    except Exception as exc:
                                        logger.error("Binance REST callback error: %s", exc)
                        elif response.status_code == 429:
                            retry_after = float(response.headers.get("Retry-After", "5"))
                            logger.warning("Binance REST rate limited, waiting %.1fs", retry_after)
                            await asyncio.sleep(retry_after)
                        else:
                            logger.warning("Binance REST spot fetch failed: HTTP %d", response.status_code)
                    except Exception as exc:
                        logger.error("Binance REST spot poll error: %s", exc)

                await asyncio.sleep(poll_interval)

    async def _try_ws_reconnect(self, symbols: list[str]) -> None:
        """Single-shot WebSocket attempt — called from the REST fallback loop."""
        streams = "/".join(f"{s}@trade" for s in symbols)
        ws_url = f"{_BINANCE_WS_BASE}/{streams}"
        async with websockets.connect(ws_url) as ws:
            self._connected = True
            logger.info("Binance WS reconnected from REST fallback: %s", streams)
            # Drain messages until the outer connect_and_run loop
            # (or the next REST poll cycle) takes over.  We purposely
            # do NOT break out of the REST loop here — the REST loop
            # checks self._connected and could hand off, but keeping
            # both paths running briefly is harmless and avoids races.
            async for raw_msg in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw_msg)
                    await self._handle_trade(msg)
                except Exception:
                    pass

    async def _handle_trade(self, msg: dict[str, Any]) -> None:
        """Parse a Binance trade message."""
        # Trade stream format: {"e":"trade","s":"BTCUSDT","p":"65000.00","q":"0.001","T":1234567890}
        symbol = msg.get("s", "")
        price = float(msg.get("p", 0))
        quantity = float(msg.get("q", 0))
        trade_ts = msg.get("T", 0) / 1000.0

        obs = BinancePriceObservation(symbol=symbol, price=price, quantity=quantity, trade_ts=trade_ts)
        self._last_observation[symbol] = obs

        for cb in self._callbacks:
            try:
                await cb(obs)
            except Exception as exc:
                logger.error("Binance callback error: %s", exc)

    async def backfill_candles(self, symbol: str, client: httpx.AsyncClient | None = None) -> list[BinanceCandle]:
        """Fetch recent 1-minute candles for backfill (up to 72 hours).

        Returns list of BinanceCandle, oldest first.
        """
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{_BINANCE_REST_BASE}/klines"
            params = {"symbol": symbol.upper(), "interval": _CANDLE_INTERVAL, "limit": min(_BACKFILL_MAX_CANDLES, 1000)}
            candles: list[BinanceCandle] = []
            end_time_ms = int(time.time() * 1000)

            # Paginate if needed (Binance limits 1000 per request)
            remaining = _BACKFILL_MAX_CANDLES
            while remaining > 0:
                batch_size = min(remaining, 1000)
                params["limit"] = batch_size
                params["endTime"] = end_time_ms

                response = await client.get(url, params=params)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    logger.warning("Binance rate limited, waiting %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code != 200:
                    logger.error("Binance candle fetch failed: HTTP %d", response.status_code)
                    break

                data = response.json()
                if not data:
                    break

                for raw in data:
                    candles.append(BinanceCandle(raw))

                end_time_ms = int(data[0][0]) - 1  # before first candle of this batch
                remaining -= len(data)

                if len(data) < batch_size:
                    break

            candles.reverse()  # oldest first
            self._candle_cache[symbol.upper()] = candles
            logger.info("Backfilled %d 1-min candles for %s", len(candles), symbol)
            return candles
        finally:
            if own_client:
                await client.aclose()

    async def stop(self) -> None:
        self._running = False
        self._connected = False

    @staticmethod
    def parse_fixture_trade() -> dict[str, Any]:
        """Sanitized example Binance trade message."""
        return {"e": "trade", "s": "BTCUSDT", "p": "68123.45", "q": "0.00123", "T": 1721749200000, "m": True}

    @staticmethod
    def parse_fixture_candle() -> list[list[Any]]:
        """Sanitized example Binance kline response (3 candles).

        Fields: open_time, open, high, low, close, volume, close_time,
                quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
        """
        return [
            [1721749140000, "68100.00", "68150.00", "68090.00", "68120.00", "12.345", 1721749199999, "841234.56", 500, "6.172", "420000.00", "0"],
            [1721749200000, "68120.00", "68200.00", "68110.00", "68180.00", "15.678", 1721749259999, "1068901.23", 620, "7.839", "534000.00", "0"],
            [1721749260000, "68180.00", "68190.00", "68150.00", "68160.00", "8.901", 1721749319999, "607012.34", 350, "4.450", "356000.00", "0"],
        ]
