"""Kalshi order-book WebSocket client.

Stateful: applies snapshot + ordered deltas, detects sequence gaps,
records staleness, requires verified rebuild after a gap. Read-only — no order submission.

WebSocket: wss://api.elections.kalshi.com/trade-api/ws/v2
Messages: orderbook_snapshot, orderbook_delta, subscribed, error
Auth: RSA PSS signature via HTTP headers during WebSocket handshake.
  - KALSHI-ACCESS-KEY: API key ID (UUID)
  - KALSHI-ACCESS-TIMESTAMP: current epoch milliseconds
  - KALSHI-ACCESS-SIGNATURE: base64 RSA-PSS-SHA256 of timestamp_ms + "GET" + path
  - Salt length: SHA256().digest_size (32 bytes) — matches kalshi_client._sign()

Subscribe format (Kalshi API v2):
  {"id": 1, "cmd": "subscribe", "params": {
    "channels": ["orderbook_delta"],
    "market_tickers": ["TICKER"],
    "use_yes_price": true
  }}

Snapshot format:
  {"type": "orderbook_snapshot", "sid": 1, "seq": 1, "msg": {
    "market_ticker": "...", "market_id": "...",
    "yes_dollars_fp": [["0.5500", "100.00"], ...],
    "no_dollars_fp": [["0.4500", "80.00"], ...]
  }}

Delta format:
  {"type": "orderbook_delta", "sid": 1, "seq": N, "msg": {
    "market_ticker": "...", "market_id": "...",
    "price_dollars": "0.5500", "delta_fp": "-458.00",
    "side": "yes", "ts": "...", "ts_ms": ...
  }}

Prices are in dollars (strings). Internally stored as cents (ints).
Quantities use "fp" format (strings). Stored as floats.
Failure modes: connection drop, sequence gap, stale data, auth expiry.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Coroutine

import websockets
import websockets.exceptions

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from arbitr8der_package.config.cwd_independent_path_resolver import resolve_streams_path
from arbitr8der_package.config.typed_configuration_settings_module import load_settings
from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_KALSHI_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
_KALSHI_WS_PATH = "/trade-api/ws/v2"
_RECONNECT_DELAY = 2.0
_MAX_RECONNECT_DELAY = 30.0
_STALE_THRESHOLD_SECONDS = 30.0


def _dollars_to_cents(dollar_str: str) -> int:
    """Convert dollar string like '0.5500' to cents integer 55."""
    return round(float(dollar_str) * 100)


def _fp_to_float(fp_str: str) -> float:
    """Convert fp string like '100.00' to float."""
    return float(fp_str)


class KalshiOrderBookState:
    """Maintains a local order book from Kalshi WebSocket deltas.

    Tracks sequence numbers and detects gaps. After a gap, the book is
    marked stale and requires a full snapshot rebuild.

    Prices stored as cents (ints). Quantities stored as floats (fp format).
    """

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self.yes_bid: int | None = None
        self.yes_ask: int | None = None
        self.no_bid: int | None = None
        self.no_ask: int | None = None
        self.yes_depth: dict[int, float] = {}  # price_cents -> quantity (fp)
        self.no_depth: dict[int, float] = {}
        self.last_sequence: int | None = None
        self.last_update_ts: float = 0
        self.is_stale: bool = False
        self.gap_detected: bool = False
        self.rebuilds_completed: int = 0

    def apply_snapshot(self, data: dict[str, Any]) -> None:
        """Apply a full order-book snapshot.

        Expects Kalshi API v2 format with yes_dollars_fp/no_dollars_fp arrays.
        """
        self.yes_depth.clear()
        self.no_depth.clear()

        # Parse yes side: [["0.5500", "100.00"], ...]
        for price_str, qty_str in data.get("yes_dollars_fp", []):
            price_cents = _dollars_to_cents(price_str)
            qty = _fp_to_float(qty_str)
            self.yes_depth[price_cents] = qty

        # Parse no side: [["0.4500", "80.00"], ...]
        for price_str, qty_str in data.get("no_dollars_fp", []):
            price_cents = _dollars_to_cents(price_str)
            qty = _fp_to_float(qty_str)
            self.no_depth[price_cents] = qty

        self._update_top_of_book()
        self.last_sequence = data.get("seq")
        self.last_update_ts = time.time()
        self.is_stale = False
        self.gap_detected = False
        self.rebuilds_completed += 1
        logger.info("Order book snapshot applied for %s (seq=%s, yes_levels=%d, no_levels=%d)",
                     self.ticker, self.last_sequence, len(self.yes_depth), len(self.no_depth))

    def apply_delta(self, data: dict[str, Any]) -> bool:
        """Apply a delta update. Returns False if sequence gap detected.

        Expects Kalshi API v2 format with price_dollars, delta_fp, side fields.
        """
        new_seq = data.get("seq")
        if new_seq is not None and self.last_sequence is not None:
            if new_seq != self.last_sequence + 1:
                logger.warning("Sequence gap for %s: expected %d, got %d",
                               self.ticker, self.last_sequence + 1, new_seq)
                self.gap_detected = True
                self.is_stale = True
                return False
            self.last_sequence = new_seq

        price_dollars = data.get("price_dollars", "0")
        delta_fp = data.get("delta_fp", "0")
        side = data.get("side", "yes")

        price_cents = _dollars_to_cents(price_dollars)
        delta_qty = _fp_to_float(delta_fp)

        depth = self.yes_depth if side == "yes" else self.no_depth

        if price_cents in depth:
            new_qty = depth[price_cents] + delta_qty
            if new_qty <= 0:
                depth.pop(price_cents, None)
            else:
                depth[price_cents] = new_qty
        elif delta_qty > 0:
            depth[price_cents] = delta_qty

        self._update_top_of_book()
        self.last_update_ts = time.time()
        return True

    def _update_top_of_book(self) -> None:
        """Extract best bid/ask from depth maps."""
        if self.yes_depth:
            self.yes_bid = max(self.yes_depth.keys())
            self.yes_ask = min(self.yes_depth.keys())
        else:
            self.yes_bid = None
            self.yes_ask = None

        if self.no_depth:
            self.no_bid = max(self.no_depth.keys())
            self.no_ask = min(self.no_depth.keys())
        else:
            self.no_bid = None
            self.no_ask = None

    @property
    def age_seconds(self) -> float:
        if self.last_update_ts == 0:
            return float("inf")
        return time.time() - self.last_update_ts

    @property
    def midpoint_cents(self) -> int | None:
        if self.yes_bid is not None and self.yes_ask is not None:
            return (self.yes_bid + self.yes_ask) // 2
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "no_bid": self.no_bid,
            "no_ask": self.no_ask,
            "midpoint_cents": self.midpoint_cents,
            "last_sequence": self.last_sequence,
            "age_seconds": round(self.age_seconds, 2),
            "is_stale": self.is_stale,
            "gap_detected": self.gap_detected,
            "rebuilds_completed": self.rebuilds_completed,
            "yes_levels": len(self.yes_depth),
            "no_levels": len(self.no_depth),
        }


class KalshiOrderBookWebSocketClient:
    """Stateful Kalshi order-book WebSocket client.

    Subscribes to orderbook_delta channel for specific tickers.
    Maintains local book state with sequence tracking and staleness detection.
    Read-only — no order submission capability.

    Auth: RSA-PSS signed HTTP headers (API key + private key PEM).
    Subscribe: {"id": N, "cmd": "subscribe", "params": {"channels": ["orderbook_delta"],
               "market_tickers": [...], "use_yes_price": true}}
    """

    def __init__(self, ticker: str, api_key: str | None = None, private_key_path: str | None = None) -> None:
        settings = load_settings()
        self._ticker = ticker
        self._api_key = api_key or settings.kalshi_api_key_id
        configured_key_path = private_key_path or settings.kalshi_private_key_path
        try:
            resolved_key_path = resolve_streams_path(configured_key_path)
        except Exception:
            resolved_key_path = Path(configured_key_path)
        self._private_key = self._load_private_key(str(resolved_key_path))
        self._ws_url = _KALSHI_WS_URL
        self.state = KalshiOrderBookState(ticker)
        self._connected = False
        self._running = False
        self._callbacks: list[Callable[[KalshiOrderBookState], Coroutine]] = []
        self._reconnect_delay = _RECONNECT_DELAY
        self._cmd_id = 0
        self._sid: int | None = None

    @staticmethod
    def _load_private_key(path: str) -> Any:
        """Load RSA private key from PEM file for request signing."""
        key_path = Path(path)
        if not key_path.exists():
            logger.warning("Kalshi private key not found at %s — WS auth will fail", path)
            return None
        try:
            pem_data = key_path.read_bytes()
            return serialization.load_pem_private_key(pem_data, password=None)
        except Exception as exc:
            logger.error("Failed to load Kalshi private key: %s", exc)
            return None

    def _next_cmd_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    def _sign_request(self) -> dict[str, str]:
        """Generate RSA-PSS signed HTTP headers for Kalshi API authentication.

        Signs: timestamp_ms_str + "GET" + "/trade-api/ws/v2"
        Returns dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE.
        Salt length matches old kalshi_client._sign(): SHA256().digest_size (32 bytes).
        """
        if not self._private_key or not self._api_key:
            return {}

        timestamp_ms = str(int(time.time() * 1000))
        message = (timestamp_ms + "GET" + _KALSHI_WS_PATH).encode("utf-8")

        try:
            signature = self._private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=hashes.SHA256().digest_size,
                ),
                hashes.SHA256(),
            )
            signature_b64 = base64.b64encode(signature).decode("utf-8")
            return {
                "KALSHI-ACCESS-KEY": self._api_key,
                "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
                "KALSHI-ACCESS-SIGNATURE": signature_b64,
                "Content-Type": "application/json",
            }
        except Exception as exc:
            logger.error("Failed to sign Kalshi request: %s", exc)
            return {}

    def on_update(self, callback: Callable[[KalshiOrderBookState], Coroutine]) -> None:
        """Register a callback for order book updates."""
        self._callbacks.append(callback)

    async def connect_and_run(self) -> None:
        """Connect to Kalshi WebSocket and process messages until stopped."""
        self._running = True
        while self._running:
            try:
                await self._run_session()
            except (websockets.exceptions.ConnectionClosed, ConnectionError, OSError,
                    websockets.exceptions.InvalidStatusCode) as exc:
                if not self._running:
                    break
                logger.warning("WebSocket disconnected: %s — reconnecting in %.1fs", exc, self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, _MAX_RECONNECT_DELAY)

    async def _run_session(self) -> None:
        """Single WebSocket session with RSA-authenticated handshake."""
        auth_headers = self._sign_request()
        if auth_headers:
            logger.info("Authenticating Kalshi WebSocket with RSA-PSS signature")
        else:
            logger.warning("No RSA auth headers — connecting unauthenticated (will not receive data)")

        async with websockets.connect(self._ws_url, extra_headers=auth_headers) as ws:
            self._connected = True
            self._reconnect_delay = _RECONNECT_DELAY
            logger.info("Connected to Kalshi WebSocket for %s", self._ticker)

            # Subscribe using Kalshi API v2 format
            cmd_id = self._next_cmd_id()
            subscribe_msg = {
                "id": cmd_id,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": [self._ticker],
                    "use_yes_price": True,
                },
            }
            await ws.send(json.dumps(subscribe_msg))
            logger.info("Sent subscribe for %s (cmd_id=%d)", self._ticker, cmd_id)

            async for raw_msg in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw_msg)
                    await self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from Kalshi WebSocket")

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """Process a single WebSocket message."""
        msg_type = msg.get("type", "")

        if msg_type == "subscribed":
            channel_info = msg.get("msg", {})
            self._sid = channel_info.get("sid")
            logger.info("Subscribed to %s (sid=%s)", channel_info.get("channel"), self._sid)

        elif msg_type == "orderbook_snapshot":
            data = msg.get("msg", {})
            market_ticker = data.get("market_ticker", "")
            if market_ticker != self._ticker:
                return

            # Snapshot contains seq at top level
            data["seq"] = msg.get("seq")
            self.state.apply_snapshot(data)
            await self._notify_callbacks()

        elif msg_type == "orderbook_delta":
            data = msg.get("msg", {})
            market_ticker = data.get("market_ticker", "")
            if market_ticker != self._ticker:
                return

            # Delta contains seq at top level
            data["seq"] = msg.get("seq")
            ok = self.state.apply_delta(data)
            if not ok:
                logger.warning("Sequence gap detected for %s — book is stale, awaiting snapshot", self._ticker)

            await self._notify_callbacks()

        elif msg_type == "error":
            error_msg = msg.get("msg", {})
            logger.error("Kalshi WebSocket error: %s", error_msg)

    async def _notify_callbacks(self) -> None:
        for cb in self._callbacks:
            try:
                await cb(self.state)
            except Exception as exc:
                logger.error("Callback error: %s", exc)

    async def stop(self) -> None:
        """Stop the WebSocket loop."""
        self._running = False
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @staticmethod
    def parse_fixture_orderbook_snapshot() -> dict[str, Any]:
        """Return a sanitized example order-book snapshot matching Kalshi API v2 format."""
        return {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {
                "market_ticker": "KXBTC15M-26JUL232215-15",
                "market_id": "d6a55151-6376-4ea7-9683-8e86cc2f804d",
                "yes_dollars_fp": [
                    ["0.5500", "100.00"],
                    ["0.5400", "200.00"],
                    ["0.5300", "150.00"],
                ],
                "no_dollars_fp": [
                    ["0.4500", "80.00"],
                    ["0.4400", "120.00"],
                    ["0.4300", "90.00"],
                ],
            },
        }

    @staticmethod
    def parse_fixture_orderbook_delta() -> dict[str, Any]:
        """Return a sanitized example order-book delta matching Kalshi API v2 format."""
        return {
            "type": "orderbook_delta",
            "sid": 1,
            "seq": 2,
            "msg": {
                "market_ticker": "KXBTC15M-26JUL232215-15",
                "market_id": "d6a55151-6376-4ea7-9683-8e86cc2f804d",
                "price_dollars": "0.5600",
                "delta_fp": "50.00",
                "side": "yes",
                "ts": "2026-07-24T02:00:01.000000Z",
                "ts_ms": 1784858401000,
            },
        }
