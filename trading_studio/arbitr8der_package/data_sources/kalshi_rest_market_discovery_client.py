"""Kalshi REST market discovery client.

Read-only: discovers active BTC/ETH 15-minute tickers, fetches market details
(status, close time, strike, bid/ask, depth, fee metadata). No order submission.

Rate limits: Kalshi REST is ~10 req/sec authenticated, lower unauthenticated.
Auth: Bearer token from environment. Markets endpoint is public; portfolio endpoints require auth.
Failure modes: network timeout, rate limit 429, auth expiry 401, market not found 404.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from arbitr8der_package.config.typed_configuration_settings_module import load_settings
from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
_KALSHI_MARKETS_URL = f"{_KALSHI_BASE_URL}/markets"
_KALSHI_SERIES_URL = f"{_KALSHI_BASE_URL}/series"

# Pattern for BTC/ETH 15-minute markets
_BTC_TICKER_PREFIXES = ("KXBTC15M",)
_ETH_TICKER_PREFIXES = ("KXETH15M",)

_REQUEST_TIMEOUT = 10.0  # seconds


class KalshiMarketDetail:
    """Parsed market detail from Kalshi REST API."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.ticker: str = raw.get("ticker", "")
        self.title: str = raw.get("title", "")
        self.status: str = raw.get("status", "unknown")  # open, closed, settled
        self.close_time: str | None = raw.get("close_time")
        self.expiration_time: str | None = raw.get("expiration_time")
        self.strike_type: str = raw.get("strike_type", "")
        self.reference_price: float | None = raw.get("reference_price")
        self.yes_bid: int | None = raw.get("yes_bid")
        self.yes_ask: int | None = raw.get("yes_ask")
        self.no_bid: int | None = raw.get("no_bid")
        self.no_ask: int | None = raw.get("no_ask")
        self.last_price: int | None = raw.get("last_price")
        self.volume: int = raw.get("volume", 0)
        self.open_interest: int = raw.get("open_interest", 0)
        self.tick_size: int = raw.get("tick_size", 1)
        self.series_ticker: str = raw.get("series_ticker", "")
        self.category: str = raw.get("category", "")
        self.sub_title: str = raw.get("sub_title", "")
        self.fee_rate_bps: float | None = None  # Populated from fee endpoint if available
        self.discovered_at: float = time.time()

    @property
    def is_active(self) -> bool:
        return self.status in ("open", "pending", "active")

    @property
    def midpoint_cents(self) -> int | None:
        if self.yes_bid is not None and self.yes_ask is not None:
            return (self.yes_bid + self.yes_ask) // 2
        if self.last_price is not None:
            return self.last_price
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "title": self.title,
            "status": self.status,
            "close_time": self.close_time,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "no_bid": self.no_bid,
            "no_ask": self.no_ask,
            "midpoint_cents": self.midpoint_cents,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "series_ticker": self.series_ticker,
            "discovered_at": self.discovered_at,
        }


class KalshiRestMarketDiscoveryClient:
    """Read-only Kalshi REST client for market discovery.

    Discovers active BTC/ETH 15-minute markets and fetches market details.
    Does not submit orders.
    """

    def __init__(self, api_key: str | None = None) -> None:
        settings = load_settings()
        self._api_key = api_key or settings.kalshi_api_key_id
        self._base_url = settings.kalshi_api_url.rstrip("/")
        self._markets_cache: dict[str, KalshiMarketDetail] = {}
        self._last_discovery_ts: float = 0
        self._headers: dict[str, str] = {}
        if self._api_key:
            self._headers["Authorization"] = f"Bearer {self._api_key}"

    async def discover_active_markets(self, client: httpx.AsyncClient | None = None) -> list[KalshiMarketDetail]:
        """Fetch all active BTC/ETH 15-minute markets from Kalshi.

        Returns list of KalshiMarketDetail for matching open/pending markets.
        """
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            markets = await self._fetch_all_markets(client)
            btc_eth_markets = [
                m for m in markets
                if m.is_active and self._is_btc_or_eth_15m(m.ticker)
            ]
            for m in btc_eth_markets:
                self._markets_cache[m.ticker] = m
            self._last_discovery_ts = time.time()
            logger.info("Discovered %d active BTC/ETH 15m markets", len(btc_eth_markets))
            return btc_eth_markets
        finally:
            if own_client:
                await client.aclose()

    async def get_market_detail(self, ticker: str, client: httpx.AsyncClient | None = None) -> KalshiMarketDetail | None:
        """Fetch detailed info for a specific market ticker."""
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{self._markets_url()}/{ticker}"
            response = await client.get(url, headers=self._headers)
            if response.status_code == 200:
                data = response.json()
                market_data = data.get("market", data)
                detail = KalshiMarketDetail(market_data)
                self._markets_cache[ticker] = detail
                return detail
            elif response.status_code == 404:
                logger.warning("Market not found: %s", ticker)
                return None
            else:
                logger.error("Failed to fetch market %s: HTTP %d", ticker, response.status_code)
                return None
        finally:
            if own_client:
                await client.aclose()

    def get_cached_market(self, ticker: str) -> KalshiMarketDetail | None:
        """Return cached market detail without network call."""
        return self._markets_cache.get(ticker)

    async def get_balance(self, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
        """Fetch account balance from Kalshi.

        Returns dict with 'balance' (cents), 'position_limit', etc.
        Requires authenticated API key.
        """
        if not self._api_key:
            logger.warning("Cannot fetch balance: no API key configured")
            return None

        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{self._base_url}/portfolio/balance"
            response = await client.get(url, headers=self._headers)

            if response.status_code == 200:
                data = response.json()
                balance_cents = data.get("balance", 0)
                balance_usd = balance_cents / 100.0
                logger.info("Kalshi balance: $%.2f (%d cents)", balance_usd, balance_cents)
                return data
            else:
                logger.error("Failed to fetch balance: HTTP %d", response.status_code)
                return None
        finally:
            if own_client:
                await client.aclose()

    @property
    def cached_markets(self) -> dict[str, KalshiMarketDetail]:
        return dict(self._markets_cache)

    async def _fetch_all_markets(self, client: httpx.AsyncClient) -> list[KalshiMarketDetail]:
        """Fetch BTC and ETH 15m markets using targeted series_ticker filters."""
        all_markets: list[KalshiMarketDetail] = []
        series_tickers = list(_BTC_TICKER_PREFIXES) + list(_ETH_TICKER_PREFIXES)

        for series in series_tickers:
            cursor: str | None = None
            while True:
                params: dict[str, Any] = {"limit": 100, "status": "open", "series_ticker": series}
                if cursor:
                    params["cursor"] = cursor

                url = self._markets_url()
                response = await client.get(url, headers=self._headers, params=params)

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    logger.warning("Rate limited on %s, waiting %.1fs", series, retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code != 200:
                    logger.error("Market discovery failed for %s: HTTP %d", series, response.status_code)
                    break

                data = response.json()
                markets_raw = data.get("markets", [])
                for raw in markets_raw:
                    all_markets.append(KalshiMarketDetail(raw))

                cursor = data.get("cursor")
                if not cursor or not markets_raw:
                    break

        return all_markets

    def _markets_url(self) -> str:
        return f"{self._base_url}/markets"

    @staticmethod
    def _is_btc_or_eth_15m(ticker: str) -> bool:
        """Check if ticker matches BTC/ETH 15-minute market pattern."""
        upper = ticker.upper()
        for prefix in _BTC_TICKER_PREFIXES + _ETH_TICKER_PREFIXES:
            if upper.startswith(prefix):
                return True
        return False

    @staticmethod
    def parse_fixture_market_response() -> dict[str, Any]:
        """Return a sanitized example Kalshi market response for testing.

        Based on observed Kalshi API v2 market response structure.
        """
        return {
            "market": {
                "ticker": "KXBTC15M-26JUL23-T15:00",
                "title": "Will Bitcoin be above $68,000 at 3:00 PM ET?",
                "status": "open",
                "close_time": "2026-07-23T19:00:00Z",
                "expiration_time": "2026-07-23T19:00:00Z",
                "strike_type": "above",
                "reference_price": 68000.0,
                "yes_bid": 55,
                "yes_ask": 58,
                "no_bid": 42,
                "no_ask": 45,
                "last_price": 56,
                "volume": 1234,
                "open_interest": 5678,
                "tick_size": 1,
                "series_ticker": "KXBTC15M",
                "category": "crypto",
                "sub_title": "15 Minute",
                "can_close_early": False,
                "expiration_value": None,
                "open_time": "2026-07-23T18:45:00Z",
            }
        }
