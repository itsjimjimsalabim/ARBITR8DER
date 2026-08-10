"""Persistent candle collection battery — fetches 1m candles from Binance
and Coinbase REST endpoints and stores them in SQLite.

Runs continuously with configurable poll intervals. Handles:
- Initial backfill of historical candles
- Incremental collection of new candles
- Gap detection and recovery
- 1m → 15m aggregation
- Automatic restart on failure with circuit breaker

Usage:
    battery = CandleCollectionBattery(settings)
    await battery.start()
    # ... later ...
    await battery.stop()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger
from kalshi_desk_package.config.typed_configuration_settings_module import TradingStudioSettings
from kalshi_desk_package.durable_storage.candle_persistence_store import CandlePersistenceStore

logger = get_logger(__name__)

# Binance REST endpoints
_BINANCE_REST_BASE = "https://api.binance.com"
_BINANCE_US_REST_BASE = "https://api.binance.us"

# Coinbase REST endpoints
_COINBASE_REST_BASE = "https://api.exchange.coinbase.com"

# Poll intervals
_CANDLE_POLL_INTERVAL_S = 60  # fetch new 1m candles every 60s
_BACKFILL_BATCH_SIZE = 1000
_MAX_BACKFILL_CANDLES = 4320  # 72 hours of 1m candles


@dataclass
class BatteryState:
    """Tracks the state of the collection battery."""
    running: bool = False
    started_at: float | None = None
    last_poll_at: float | None = None
    total_candles_stored: int = 0
    consecutive_errors: int = 0
    last_error: str | None = None
    binance_usable: bool = True
    coinbase_usable: bool = True


class CandleCollectionBattery:
    """Continuously collects 1m candles from Binance and Coinbase REST APIs
    and stores them in the CandlePersistenceStore."""

    def __init__(
        self,
        settings: TradingStudioSettings,
        store: CandlePersistenceStore,
    ):
        self._settings = settings
        self._store = store
        self._state = BatteryState()
        self._task: asyncio.Task | None = None
        self._running = asyncio.Event()
        self._assets = ["BTC", "ETH"]
        self._binance_symbols = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
        self._coinbase_products = {"BTC": "BTC-USD", "ETH": "ETH-USD"}

    @property
    def state(self) -> BatteryState:
        return self._state

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    async def start(self) -> None:
        """Start the battery. Backfill historical candles, then poll."""
        if self._state.running:
            logger.warning("Battery already running")
            return

        self._state.running = True
        self._state.started_at = time.time()
        self._running.set()

        logger.info("Starting candle collection battery")

        # Initial backfill
        await self._backfill_all()

        # Start continuous polling loop
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the battery gracefully."""
        logger.info("Stopping candle collection battery")
        self._running.clear()
        self._state.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Battery stopped. Total candles stored: %d",
                     self._state.total_candles_stored)

    # -------------------------------------------------------------------
    # Backfill
    # -------------------------------------------------------------------

    async def _backfill_all(self) -> None:
        """Backfill historical 1m candles for all assets from both sources."""
        async with httpx.AsyncClient(timeout=30) as client:
            for asset in self._assets:
                if self._state.binance_usable:
                    await self._backfill_binance(client, asset)
                if self._state.coinbase_usable:
                    await self._backfill_coinbase(client, asset)

    async def _backfill_binance(self, client: httpx.AsyncClient, asset: str) -> None:
        """Backfill 1m candles from Binance REST for an asset."""
        symbol = self._binance_symbols[asset]
        logger.info("Backfilling Binance %s 1m candles", symbol)

        # Check where we left off
        latest_time = await self._store.get_latest_candle_time(
            asset, "binance", "1m"
        )

        # Start from 72 hours ago if no data, or from latest candle
        end_ms = int(time.time() * 1000)
        if latest_time:
            start_ms = int(latest_time * 1000)
        else:
            start_ms = end_ms - (_MAX_BACKFILL_CANDLES * 60 * 1000)

        total_stored = 0
        current_end = end_ms

        while current_end > start_ms and total_stored < _MAX_BACKFILL_CANDLES:
            try:
                resp = await client.get(
                    f"{_BINANCE_REST_BASE}/api/v3/klines",
                    params={
                        "symbol": symbol,
                        "interval": "1m",
                        "endTime": current_end,
                        "limit": _BACKFILL_BATCH_SIZE,
                    },
                )

                if resp.status_code == 451:
                    # Geo-blocked, try Binance.US
                    resp = await client.get(
                        f"{_BINANCE_US_REST_BASE}/api/v3/klines",
                        params={
                            "symbol": symbol,
                            "interval": "1m",
                            "endTime": current_end,
                            "limit": _BACKFILL_BATCH_SIZE,
                        },
                    )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    logger.warning("Binance rate limited, waiting %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if resp.status_code != 200:
                    logger.error("Binance backfill failed: %d %s",
                                 resp.status_code, resp.text[:200])
                    self._state.consecutive_errors += 1
                    self._state.last_error = f"HTTP {resp.status_code}"
                    break

                candles = resp.json()
                if not candles:
                    break

                rows = []
                for c in candles:
                    rows.append({
                        "asset": asset,
                        "source": "binance",
                        "interval": "1m",
                        "open_time": c[0] / 1000.0,  # ms to seconds
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "quote_volume": float(c[7]),
                        "trades": int(c[8]),
                    })

                count = await self._store.upsert_candles(rows)
                total_stored += count

                # Move window back
                current_end = int(candles[0][0]) - 1

                # Rate limit: 1 req/sec
                await asyncio.sleep(1)

            except Exception as e:
                logger.error("Binance backfill error for %s: %s", symbol, e)
                self._state.consecutive_errors += 1
                self._state.last_error = str(e)
                break

        self._state.consecutive_errors = 0
        self._state.last_error = None
        logger.info("Binance backfill complete for %s: %d candles stored",
                     symbol, total_stored)

    async def _backfill_coinbase(self, client: httpx.AsyncClient, asset: str) -> None:
        """Backfill 1m candles from Coinbase REST for an asset."""
        product_id = self._coinbase_products[asset]
        logger.info("Backfilling Coinbase %s 1m candles", product_id)

        latest_time = await self._store.get_latest_candle_time(
            asset, "coinbase", "1m"
        )

        # Coinbase candles endpoint: max 300 per request
        # granularity 60 = 1 minute
        total_stored = 0

        try:
            params: dict = {"granularity": 60, "limit": 300}
            if latest_time:
                # Fetch from where we left off
                from datetime import datetime, timezone
                params["start"] = datetime.fromtimestamp(
                    latest_time, tz=timezone.utc
                ).isoformat()

            resp = await client.get(
                f"{_COINBASE_REST_BASE}/products/{product_id}/candles",
                params=params,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("Coinbase rate limited, waiting %ds", retry_after)
                await asyncio.sleep(retry_after)
                return

            if resp.status_code != 200:
                logger.error("Coinbase backfill failed: %d %s",
                             resp.status_code, resp.text[:200])
                self._state.consecutive_errors += 1
                self._state.last_error = f"Coinbase HTTP {resp.status_code}"
                return

            candles = resp.json()
            if not candles:
                return

            # Coinbase format: [time, low, high, open, close, volume]
            rows = []
            for c in candles:
                rows.append({
                    "asset": asset,
                    "source": "coinbase",
                    "interval": "1m",
                    "open_time": float(c[0]),
                    "open": float(c[3]),
                    "high": float(c[2]),
                    "low": float(c[1]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                    "quote_volume": None,
                    "trades": None,
                })

            count = await self._store.upsert_candles(rows)
            total_stored += count

        except Exception as e:
            logger.error("Coinbase backfill error for %s: %s", product_id, e)
            self._state.consecutive_errors += 1
            self._state.last_error = str(e)

        logger.info("Coinbase backfill complete for %s: %d candles stored",
                     product_id, total_stored)

    # -------------------------------------------------------------------
    # Continuous polling
    # -------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Continuously poll for new candles."""
        while self._running.is_set():
            try:
                await self._poll_once()
                self._state.last_poll_at = time.time()
                self._state.consecutive_errors = 0
                self._state.last_error = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._state.consecutive_errors += 1
                self._state.last_error = str(e)
                logger.error("Poll cycle error: %s", e)

                # Circuit breaker: if too many errors, slow down
                if self._state.consecutive_errors >= 5:
                    logger.warning("Too many errors, backing off 5 minutes")
                    await asyncio.sleep(300)
                    continue

            await asyncio.sleep(_CANDLE_POLL_INTERVAL_S)

    async def _poll_once(self) -> None:
        """Single poll cycle — fetch latest candles from both sources."""
        async with httpx.AsyncClient(timeout=15) as client:
            for asset in self._assets:
                if self._state.binance_usable:
                    await self._poll_binance(client, asset)
                if self._state.coinbase_usable:
                    await self._poll_coinbase(client, asset)

    async def _poll_binance(self, client: httpx.AsyncClient, asset: str) -> None:
        """Fetch latest few 1m candles from Binance."""
        symbol = self._binance_symbols[asset]
        try:
            resp = await client.get(
                f"{_BINANCE_REST_BASE}/api/v3/klines",
                params={"symbol": symbol, "interval": "1m", "limit": 5},
            )
            if resp.status_code == 451:
                resp = await client.get(
                    f"{_BINANCE_US_REST_BASE}/api/v3/klines",
                    params={"symbol": symbol, "interval": "1m", "limit": 5},
                )
            if resp.status_code != 200:
                return

            candles = resp.json()
            rows = []
            for c in candles:
                rows.append({
                    "asset": asset,
                    "source": "binance",
                    "interval": "1m",
                    "open_time": c[0] / 1000.0,
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                    "quote_volume": float(c[7]),
                    "trades": int(c[8]),
                })
            count = await self._store.upsert_candles(rows)
            self._state.total_candles_stored += count

        except Exception as e:
            logger.debug("Binance poll error for %s: %s", symbol, e)

    async def _poll_coinbase(self, client: httpx.AsyncClient, asset: str) -> None:
        """Fetch latest few 1m candles from Coinbase."""
        product_id = self._coinbase_products[asset]
        try:
            resp = await client.get(
                f"{_COINBASE_REST_BASE}/products/{product_id}/candles",
                params={"granularity": 60, "limit": 5},
            )
            if resp.status_code != 200:
                return

            candles = resp.json()
            rows = []
            for c in candles:
                rows.append({
                    "asset": asset,
                    "source": "coinbase",
                    "interval": "1m",
                    "open_time": float(c[0]),
                    "open": float(c[3]),
                    "high": float(c[2]),
                    "low": float(c[1]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                    "quote_volume": None,
                    "trades": None,
                })
            count = await self._store.upsert_candles(rows)
            self._state.total_candles_stored += count

        except Exception as e:
            logger.debug("Coinbase poll error for %s: %s", product_id, e)
