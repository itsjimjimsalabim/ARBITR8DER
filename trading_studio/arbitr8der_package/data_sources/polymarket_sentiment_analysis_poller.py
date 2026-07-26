"""Polymarket sentiment analysis poller.

REST: https://gamma-api.polymarket.com — markets and price history
CLOB: https://clob.polymarket.com — order book data

Polymarket has no direct 15-minute BTC/ETH markets. This module maps Kalshi
15-minute markets to the closest Polymarket BTC price-level markets, or marks
the mapping unavailable if no relevant market exists.

Rate limits: ~10 req/sec. Auth: none for public endpoints.
Failure modes: no mapping found, rate limit, stale data.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine

import httpx

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)

_POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com"
_POLYMARKET_CLOB_URL = "https://clob.polymarket.com"
_REQUEST_TIMEOUT = 15.0


class PolymarketSentimentObservation:
    """Parsed Polymarket sentiment observation."""

    def __init__(self, market_slug: str, condition_id: str, question: str,
                 yes_price: float, no_price: float, volume_usd: float,
                 liquidity: float, end_date: str | None) -> None:
        self.market_slug = market_slug
        self.condition_id = condition_id
        self.question = question
        self.yes_price = yes_price
        self.no_price = no_price
        self.volume_usd = volume_usd
        self.liquidity = liquidity
        self.end_date = end_date
        self.receive_ts = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_slug": self.market_slug,
            "condition_id": self.condition_id,
            "question": self.question,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "volume_usd": self.volume_usd,
            "liquidity": self.liquidity,
            "end_date": self.end_date,
            "receive_ts": self.receive_ts,
        }


class PolymarketSentimentPoller:
    """Slow poller for Polymarket BTC/ETH sentiment.

    Maps Kalshi 15-minute markets to Polymarket price-level markets.
    Polls every 30-60 seconds. If no relevant market exists, marks as unavailable.
    Read-only — no trading.
    """

    def __init__(self) -> None:
        self._last_observation: dict[str, PolymarketSentimentObservation] = {}
        self._market_mapping: dict[str, str] = {}  # kalshi_ticker -> polymarket_slug
        self._callbacks: list[Callable[[PolymarketSentimentObservation], Coroutine]] = []

    def on_sentiment(self, callback: Callable[[PolymarketSentimentObservation], Coroutine]) -> None:
        self._callbacks.append(callback)

    @property
    def last_observations(self) -> dict[str, PolymarketSentimentObservation]:
        return dict(self._last_observation)

    def register_mapping(self, kalshi_ticker: str, polymarket_slug: str) -> None:
        """Register a manual mapping from Kalshi ticker to Polymarket market slug."""
        self._market_mapping[kalshi_ticker] = polymarket_slug
        logger.info("Registered Polymarket mapping: %s -> %s", kalshi_ticker, polymarket_slug)

    async def search_btc_markets(self, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
        """Search Polymarket for active BTC price-level markets.

        Returns list of matching markets with slug, question, and prices.
        """
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{_POLYMARKET_GAMMA_URL}/markets"
            params = {"active": "true", "closed": "false", "tag": "crypto"}
            response = await client.get(url, params=params)

            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "2"))
                logger.warning("Polymarket rate limited, waiting %.1fs", retry_after)
                await asyncio.sleep(retry_after)
                return []

            if response.status_code != 200:
                logger.error("Polymarket search failed: HTTP %d", response.status_code)
                return []

            data = response.json()
            btc_markets = []

            for market in data if isinstance(data, list) else data.get("data", []):
                question = market.get("question", "").lower()
                description = market.get("description", "").lower()
                if "bitcoin" in question or "btc" in question or "bitcoin" in description:
                    tokens = market.get("tokens", [])
                    yes_price = 0.5
                    no_price = 0.5
                    for token in tokens:
                        if token.get("outcome", "").lower() == "yes":
                            yes_price = float(token.get("price", 0.5))
                        elif token.get("outcome", "").lower() == "no":
                            no_price = float(token.get("price", 0.5))

                    btc_markets.append({
                        "slug": market.get("slug", ""),
                        "condition_id": market.get("conditionId", ""),
                        "question": market.get("question", ""),
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "volume_usd": float(market.get("volume", 0)),
                        "liquidity": float(market.get("liquidity", 0)),
                        "end_date": market.get("endDate"),
                    })

            logger.info("Found %d BTC markets on Polymarket", len(btc_markets))
            return btc_markets
        finally:
            if own_client:
                await client.aclose()

    async def poll_sentiment(self, kalshi_ticker: str, client: httpx.AsyncClient | None = None) -> PolymarketSentimentObservation | None:
        """Poll Polymarket for sentiment related to a Kalshi market.

        If a mapping exists, fetch that market. Otherwise search for a match.
        Returns None if no relevant market is found.
        """
        slug = self._market_mapping.get(kalshi_ticker)
        if not slug:
            # Search for matching BTC market
            markets = await self.search_btc_markets(client)
            if not markets:
                logger.debug("No Polymarket BTC market found for %s", kalshi_ticker)
                return None
            # Use the first matching market directly from search results
            mkt = markets[0]
            obs = PolymarketSentimentObservation(
                market_slug=mkt["slug"],
                condition_id=mkt["condition_id"],
                question=mkt["question"],
                yes_price=mkt["yes_price"],
                no_price=mkt["no_price"],
                volume_usd=mkt["volume_usd"],
                liquidity=mkt["liquidity"],
                end_date=mkt.get("end_date"),
            )
            self._last_observation[kalshi_ticker] = obs
            for cb in self._callbacks:
                try:
                    await cb(obs)
                except Exception as exc:
                    logger.error("Polymarket callback error: %s", exc)
            return obs

        obs = await self._fetch_market(slug, client)
        if obs:
            self._last_observation[kalshi_ticker] = obs
            for cb in self._callbacks:
                try:
                    await cb(obs)
                except Exception as exc:
                    logger.error("Polymarket callback error: %s", exc)
        return obs

    async def _fetch_market(self, slug: str, client: httpx.AsyncClient | None = None) -> PolymarketSentimentObservation | None:
        """Fetch a specific Polymarket market by slug."""
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{_POLYMARKET_GAMMA_URL}/markets/{slug}"
            response = await client.get(url)
            if response.status_code != 200:
                return None

            market = response.json()
            tokens = market.get("tokens", [])
            yes_price = 0.5
            no_price = 0.5
            for token in tokens:
                if token.get("outcome", "").lower() == "yes":
                    yes_price = float(token.get("price", 0.5))
                elif token.get("outcome", "").lower() == "no":
                    no_price = float(token.get("price", 0.5))

            return PolymarketSentimentObservation(
                market_slug=slug,
                condition_id=market.get("conditionId", ""),
                question=market.get("question", ""),
                yes_price=yes_price,
                no_price=no_price,
                volume_usd=float(market.get("volume", 0)),
                liquidity=float(market.get("liquidity", 0)),
                end_date=market.get("endDate"),
            )
        finally:
            if own_client:
                await client.aclose()

    @staticmethod
    def parse_fixture_market() -> dict[str, Any]:
        """Sanitized Polymarket market response fixture."""
        return {
            "slug": "will-bitcoin-exceed-68000-on-july-23",
            "conditionId": "0xabc123...",
            "question": "Will Bitcoin exceed $68,000 on July 23, 2026?",
            "description": "This market resolves to Yes if Bitcoin price exceeds $68,000 at any point on July 23, 2026.",
            "tokens": [
                {"outcome": "Yes", "price": 0.62, "winner": False},
                {"outcome": "No", "price": 0.38, "winner": False},
            ],
            "volume": "125000.00",
            "liquidity": "45000.00",
            "active": True,
            "closed": False,
            "endDate": "2026-07-24T04:00:00Z",
            "tags": ["crypto", "bitcoin"],
        }
