"""CoinGecko macro context poller.

REST: https://api.coingecko.com/api/v3 — /simple/price, /coins/{id}/market_chart
Rate limits: 10-50 req/min (free tier). Slow polling (every 60-120s).
Auth: optional API key for higher limits.
Failure modes: rate limit 429, network timeout, coin not found.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine

import httpx

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
_REQUEST_TIMEOUT = 15.0
_POLL_INTERVAL = 60  # seconds between polls

_COIN_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
}


class CoinGeckoMacroObservation:
    """Parsed CoinGecko macro context observation."""

    def __init__(self, coin_id: str, asset: str, usd_price: float,
                 market_cap_usd: float | None, volume_24h_usd: float | None,
                 price_change_24h_pct: float | None,
                 price_change_1h_pct: float | None) -> None:
        self.coin_id = coin_id
        self.asset = asset
        self.usd_price = usd_price
        self.market_cap_usd = market_cap_usd
        self.volume_24h_usd = volume_24h_usd
        self.price_change_24h_pct = price_change_24h_pct
        self.price_change_1h_pct = price_change_1h_pct
        self.receive_ts = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "coin_id": self.coin_id,
            "asset": self.asset,
            "usd_price": self.usd_price,
            "market_cap_usd": self.market_cap_usd,
            "volume_24h_usd": self.volume_24h_usd,
            "price_change_24h_pct": self.price_change_24h_pct,
            "price_change_1h_pct": self.price_change_1h_pct,
            "receive_ts": self.receive_ts,
        }


class CoinGeckoMacroDataPoller:
    """Slow poller for CoinGecko macro context.

    Fetches BTC/ETH market data every 60 seconds:
    - Current USD price
    - 24h volume
    - Market cap
    - Price changes (1h, 24h)

    Read-only — no trading.
    """

    def __init__(self) -> None:
        self._last_observation: dict[str, CoinGeckoMacroObservation] = {}
        self._running = False
        self._callbacks: list[Callable[[CoinGeckoMacroObservation], Coroutine]] = []
        self._api_key: str | None = None

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key

    def on_macro_update(self, callback: Callable[[CoinGeckoMacroObservation], Coroutine]) -> None:
        self._callbacks.append(callback)

    @property
    def last_observations(self) -> dict[str, CoinGeckoMacroObservation]:
        return dict(self._last_observation)

    async def start_polling(self, assets: list[str] | None = None, interval: int = _POLL_INTERVAL) -> None:
        """Start polling CoinGecko for macro data."""
        if assets is None:
            assets = ["BTC", "ETH"]

        self._running = True
        logger.info("Starting CoinGecko poller for %s (every %ds)", assets, interval)

        while self._running:
            try:
                await self._poll_all(assets)
            except Exception as exc:
                logger.error("CoinGecko poll error: %s", exc)
            await asyncio.sleep(interval)

    async def _poll_all(self, assets: list[str]) -> None:
        """Poll all assets in a single API call."""
        coin_ids = [_COIN_ID_MAP.get(a, a.lower()) for a in assets]
        ids_str = ",".join(coin_ids)

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            headers = {}
            if self._api_key:
                headers["x-cg-demo-api-key"] = self._api_key

            url = f"{_COINGECKO_BASE_URL}/simple/price"
            params = {
                "ids": ids_str,
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            }

            response = await client.get(url, params=params, headers=headers)

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "60"))
                logger.warning("CoinGecko rate limited, backing off %.0fs", retry_after)
                await asyncio.sleep(retry_after)
                return

            if response.status_code != 200:
                logger.error("CoinGecko API failed: HTTP %d", response.status_code)
                return

            data = response.json()
            for coin_id, coin_data in data.items():
                asset = next((a for a, cid in _COIN_ID_MAP.items() if cid == coin_id), coin_id.upper())
                obs = CoinGeckoMacroObservation(
                    coin_id=coin_id,
                    asset=asset,
                    usd_price=coin_data.get("usd", 0),
                    market_cap_usd=coin_data.get("usd_market_cap"),
                    volume_24h_usd=coin_data.get("usd_24h_vol"),
                    price_change_24h_pct=coin_data.get("usd_24h_change"),
                    price_change_1h_pct=None,  # Not in simple/price endpoint
                )
                self._last_observation[asset] = obs
                for cb in self._callbacks:
                    try:
                        await cb(obs)
                    except Exception as exc:
                        logger.error("CoinGecko callback error: %s", exc)

            logger.debug("CoinGecko poll: %d coins updated", len(data))

    async def fetch_market_chart(self, asset: str, days: int = 1, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
        """Fetch historical market chart data for an asset."""
        coin_id = _COIN_ID_MAP.get(asset, asset.lower())
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{_COINGECKO_BASE_URL}/coins/{coin_id}/market_chart"
            params = {"vs_currency": "usd", "days": days}
            headers = {}
            if self._api_key:
                headers["x-cg-demo-api-key"] = self._api_key

            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                return response.json().get("prices", [])
            logger.warning("CoinGecko chart fetch failed: HTTP %d", response.status_code)
            return []
        finally:
            if own_client:
                await client.aclose()

    async def stop(self) -> None:
        self._running = False

    @staticmethod
    def parse_fixture_simple_price() -> dict[str, Any]:
        """Sanitized CoinGecko /simple/price response fixture."""
        return {
            "bitcoin": {
                "usd": 68123.45,
                "usd_market_cap": 1340000000000,
                "usd_24h_vol": 28500000000,
                "usd_24h_change": 2.34,
                "last_updated_at": 1721749200,
            },
            "ethereum": {
                "usd": 3567.89,
                "usd_market_cap": 428000000000,
                "usd_24h_vol": 15200000000,
                "usd_24h_change": -0.87,
                "last_updated_at": 1721749200,
            },
        }
