"""Settlement watcher — polls Kalshi REST for recently settled markets,
determines outcomes from candle data, and records them for auto-scoring.

This closes the feedback loop: predictions → outcomes → scoring → retraining.

Usage:
    watcher = SettlementWatcher(kalshi_client, candle_store)
    await watcher.start()  # runs in background
    await watcher.stop()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.durable_storage.candle_persistence_store import CandlePersistenceStore

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Settled market record
# ---------------------------------------------------------------------------

@dataclass
class SettledMarketRecord:
    """A Kalshi market that has settled, with outcome determined."""
    ticker: str
    asset: str
    strike_price: float
    close_time: float
    direction: str          # "UP" or "DOWN"
    close_price: float      # actual close from our candle data
    magnitude_pct: float
    window_open: float
    window_close: float
    recorded: bool = False


# ---------------------------------------------------------------------------
# Settlement watcher
# ---------------------------------------------------------------------------

class SettlementWatcher:
    """Polls Kalshi REST for settled markets and records outcomes.

    Runs as a background asyncio task. Periodically:
    1. Discovers recently settled KXBTC15M/KXETH15M markets from Kalshi REST
    2. Looks up the actual close price from our candle store
    3. Determines direction (UP if close > strike, DOWN if close < strike)
    4. Records the outcome in the outcomes table for auto-scoring

    Parameters
    ----------
    kalshi_discovery_client : KalshiRestMarketDiscoveryClient
        Market discovery client for Kalshi REST API.
    candle_store : CandlePersistenceStore
        Persistent candle store for looking up close prices.
    poll_interval_seconds : int
        Seconds between settlement polls (default 60).
    lookback_minutes : int
        How far back to look for settled markets (default 30).
    """

    def __init__(
        self,
        kalshi_discovery_client,
        candle_store: CandlePersistenceStore,
        poll_interval_seconds: int = 60,
        lookback_minutes: int = 30,
    ):
        self._kalshi = kalshi_discovery_client
        self._candle_store = candle_store
        self._poll_interval = poll_interval_seconds
        self._lookback_minutes = lookback_minutes
        self._running = False
        self._task: asyncio.Task | None = None
        self._settled_tickers: set[str] = set()  # avoid re-processing
        self._last_poll: float = 0.0
        self._settlement_count: int = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def settlement_count(self) -> int:
        return self._settlement_count

    async def start(self) -> None:
        """Start the settlement watcher loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="settlement-watcher")
        logger.info("Settlement watcher started (interval=%ds)", self._poll_interval)

    async def stop(self) -> None:
        """Stop the settlement watcher loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Settlement watcher stopped (recorded %d outcomes)", self._settlement_count)

    async def _poll_loop(self) -> None:
        """Main polling loop — checks for settled markets periodically."""
        while self._running:
            try:
                await self._check_settled_markets()
            except Exception as exc:
                logger.error("Settlement poll error: %s", exc, exc_info=True)

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def _check_settled_markets(self) -> int:
        """Check Kalshi for recently settled markets and record outcomes.

        Returns the number of new outcomes recorded.
        """
        recorded = 0
        try:
            # Discover markets — the client filters to open/pending/active,
            # but we also want to check recently closed/settled ones
            # We'll query with status=settled or closed
            settled_markets = await self._fetch_settled_markets()

            for market in settled_markets:
                if market["ticker"] in self._settled_tickers:
                    continue

                outcome = await self._determine_market_outcome(market)
                if outcome is not None:
                    self._settled_tickers.add(market["ticker"])
                    self._settlement_count += 1
                    recorded += 1

        except Exception as exc:
            logger.warning("Error checking settled markets: %s", exc)

        if recorded > 0:
            logger.info("Recorded %d new settlement outcomes (total: %d)", recorded, self._settlement_count)

        return recorded

    async def _fetch_settled_markets(self) -> list[dict]:
        """Fetch recently settled/closed Kalshi markets via REST API."""
        import os
        settings = self._kalshi._settings if hasattr(self._kalshi, '_settings') else None

        api_url = "https://api.elections.kalshi.com/trade-api/v2"
        if settings and hasattr(settings, 'kalshi_api_url'):
            api_url = settings.kalshi_api_url

        headers = {}
        api_key = self._kalshi._api_key if hasattr(self._kalshi, '_api_key') else None
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        settled_markets = []

        # Query for recently closed/settled markets
        for series_ticker in ["KXBTC15M", "KXETH15M"]:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    params = {
                        "series_ticker": series_ticker,
                        "status": "settled",
                        "limit": 20,
                    }
                    resp = await client.get(f"{api_url}/markets", params=params, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        markets = data.get("markets", [])
                        for m in markets:
                            # Filter to recently settled (within lookback window)
                            close_time_str = m.get("close_time") or m.get("expiration_time")
                            if close_time_str:
                                from datetime import datetime, timezone
                                try:
                                    close_dt = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                                    close_ts = close_dt.timestamp()
                                    age_minutes = (time.time() - close_ts) / 60
                                    if age_minutes <= self._lookback_minutes:
                                        settled_markets.append(m)
                                except (ValueError, TypeError):
                                    pass
            except Exception as exc:
                logger.warning("Error fetching settled %s markets: %s", series_ticker, exc)

        # Also check "closed" status (markets that just closed but haven't settled yet)
        for series_ticker in ["KXBTC15M", "KXETH15M"]:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    params = {
                        "series_ticker": series_ticker,
                        "status": "closed",
                        "limit": 20,
                    }
                    resp = await client.get(f"{api_url}/markets", params=params, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        markets = data.get("markets", [])
                        for m in markets:
                            close_time_str = m.get("close_time") or m.get("expiration_time")
                            if close_time_str:
                                from datetime import datetime, timezone
                                try:
                                    close_dt = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                                    close_ts = close_dt.timestamp()
                                    age_minutes = (time.time() - close_ts) / 60
                                    if age_minutes <= self._lookback_minutes:
                                        settled_markets.append(m)
                                except (ValueError, TypeError):
                                    pass
            except Exception as exc:
                logger.warning("Error fetching closed %s markets: %s", series_ticker, exc)

        return settled_markets

    async def _determine_market_outcome(self, market: dict) -> SettledMarketRecord | None:
        """Determine the outcome of a settled Kalshi market.

        Compares the strike price to the actual close price from our candle data.
        """
        ticker = market.get("ticker", "")
        strike_price = market.get("reference_price")
        if strike_price is None or not ticker:
            return None

        # Parse asset from ticker (KXBTC15M -> BTC, KXETH15M -> ETH)
        asset = "BTC" if "BTC" in ticker.upper() else "ETH"

        # Parse window time from ticker
        # Format: KXBTC15M-26JUL25T1430 or KXBTC15M-26JUL25-14:30
        window_open = self._parse_window_time(ticker)
        if window_open is None:
            logger.debug("Could not parse window time from ticker: %s", ticker)
            return None

        window_close = window_open + 900.0

        # Look up the actual close price from our candle store
        close_price = await self._get_close_price_at_time(asset, window_close)
        if close_price is None:
            # Try to get it from the window open + a few seconds
            close_price = await self._get_close_price_at_time(asset, window_open + 890)
        if close_price is None:
            logger.debug("No candle data for %s at window %s", asset, ticker)
            return None

        # Determine direction
        direction = "UP" if close_price > strike_price else "DOWN"
        magnitude_pct = abs(close_price - strike_price) / strike_price * 100 if strike_price > 0 else 0.0

        # Record the outcome
        outcome_id = await self._candle_store.record_outcome(
            asset=asset,
            ticker=ticker,
            window_open=window_open,
            window_close=window_close,
            open_price=strike_price,
            close_price=close_price,
            direction=direction,
            magnitude_pct=magnitude_pct,
        )

        record = SettledMarketRecord(
            ticker=ticker,
            asset=asset,
            strike_price=strike_price,
            close_time=window_close,
            direction=direction,
            close_price=close_price,
            magnitude_pct=magnitude_pct,
            window_open=window_open,
            window_close=window_close,
            recorded=True,
        )

        logger.info(
            "Settlement recorded: %s %s (strike=%.2f, close=%.2f, dir=%s, id=%d)",
            asset, ticker, strike_price, close_price, direction, outcome_id,
        )

        return record

    async def _get_close_price_at_time(self, asset: str, target_time: float) -> float | None:
        """Get the close price of the 1m candle closest to target_time."""
        candles = await self._candle_store.get_candles(
            asset=asset, source="binance", interval="1m", limit=5,
        )

        if not candles:
            return None

        # candles are newest-first; find the one closest to target_time
        best = None
        best_diff = float("inf")
        for c in candles:
            diff = abs(c["open_time"] - target_time)
            if diff < best_diff:
                best_diff = diff
                best = c

        # Only use if within 5 minutes of target
        if best and best_diff < 300:
            return best["close"]

        return None

    def _parse_window_time(self, ticker: str) -> float | None:
        """Parse the 15m window open time from a Kalshi ticker.

        Ticker format: KXBTC15M-26JUL25T1430 or KXBTC15M-26JUL25-14:30
        Returns Unix timestamp or None.
        """
        import re
        from datetime import datetime, timezone

        # Try various patterns
        patterns = [
            r"KX(BTC|ETH)15M-(\d{2})([A-Z]{3})(\d{2})T(\d{2})(\d{2})",  # 26JUL25T1430
            r"KX(BTC|ETH)15M-(\d{2})([A-Z]{3})(\d{2})-(\d{2}):(\d{2})",  # 26JUL25-14:30
            r"KX(BTC|ETH)15M-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})",      # 20250726T1430
        ]

        for pattern in patterns:
            m = re.search(pattern, ticker, re.IGNORECASE)
            if m:
                groups = m.groups()
                try:
                    if len(groups) == 6 and groups[2].isalpha():
                        # DD-MON-YYTHHMM format
                        day = int(groups[1])
                        month_map = {
                            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
                            "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
                            "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
                        }
                        month = month_map.get(groups[2].upper(), 0)
                        year = 2000 + int(groups[3])
                        hour = int(groups[4])
                        minute = int(groups[5])

                        dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                        return dt.timestamp()
                    elif len(groups) == 6:
                        # YYYYMMDDTHHMM format
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                        hour = int(groups[3])
                        minute = int(groups[4])

                        dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                        return dt.timestamp()
                except (ValueError, KeyError):
                    continue

        return None

    def get_status(self) -> dict:
        """Return watcher status for health monitoring."""
        return {
            "running": self._running,
            "settlement_count": self._settlement_count,
            "known_tickers": len(self._settled_tickers),
            "last_poll": self._last_poll,
            "poll_interval_seconds": self._poll_interval,
        }
