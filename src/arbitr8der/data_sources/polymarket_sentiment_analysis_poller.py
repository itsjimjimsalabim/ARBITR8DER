"""Polymarket sentiment poller — BTC/ETH probability overlay.

Polls Polymarket CLOB API for BTC and ETH sentiment data at regular intervals.
Used as a slower sentiment overlay, NOT a fast price signal.

Per Theories_of_Operations: "Polymarket is a slower probability/sentiment overlay,
it does not mirror the Kalshi 15min markets and cannot make a Kalshi trade valid."
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

import httpx

from ..market_data.immutable_event_envelope_wrapper import EventEnvelope, EventType

logger = logging.getLogger(__name__)

POLYMARKET_API_BASE = "https://clob.polymarket.com"
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"

# BTC and ETH event slugs on Polymarket
DEFAULT_POLL_INTERVAL_SECONDS = 30

INITIAL_RECONNECT_DELAY_SECONDS = 1.0
MAX_RECONNECT_DELAY_SECONDS = 120


class PolymarketSentimentAnalysisPoller:
    """HTTP poller for Polymarket sentiment data.

    Polls the Polymarket API every N seconds for BTC/ETH sentiment.
    Wraps sentiment data as EventEnvelope and routes via callback.
    """

    def __init__(
        self,
        on_event_callback: Callable[[EventEnvelope], None],
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        api_base_url: str = POLYMARKET_API_BASE,
        gamma_base_url: str = POLYMARKET_GAMMA_BASE,
    ):
        self.on_event_callback = on_event_callback
        self.poll_interval_seconds = poll_interval_seconds
        self.api_base_url = api_base_url
        self.gamma_base_url = gamma_base_url

        self._is_running: bool = False
        self._last_poll_timestamp: float = 0.0
        self._last_successful_poll: float = 0.0
        self._sentiment_data: dict[str, float] = {}
        self._error_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def latest_sentiment(self) -> dict[str, float]:
        return dict(self._sentiment_data)

    async def _fetch_sentiment_data(self) -> dict[str, Any]:
        """Fetch current BTC and ETH sentiment from Polymarket.

        Returns mapping of asset -> sentiment score (0.0 to 1.0).
        """
        sentiment_mapping: dict[str, Any] = {}

        try:
            async with httpx.AsyncClient() as http_client:
                # Fetch active markets
                markets_response = await http_client.get(
                    f"{self.gamma_base_url}/markets",
                    params={"limit": 50, "active": True, "closed": False},
                    timeout=15.0,
                )
                markets_response.raise_for_status()
                markets_data = markets_response.json()

                # Look for BTC and ETH related markets
                for market_record in markets_data:
                    question_text = market_record.get("question", "").lower()
                    outcomes_json = market_record.get("outcomes", "[]")
                    outcome_prices = market_record.get("outcomePrices", "[]")

                    # Parse outcomes and prices
                    if isinstance(outcomes_json, str):
                        import json
                        try:
                            outcomes_list = json.loads(outcomes_json)
                        except (json.JSONDecodeError, TypeError):
                            outcomes_list = []
                    else:
                        outcomes_list = outcomes_json or []

                    if isinstance(outcome_prices, str):
                        import json
                        try:
                            prices_list = json.loads(outcome_prices)
                        except (json.JSONDecodeError, TypeError):
                            prices_list = []
                    else:
                        prices_list = outcome_prices or []

                    if not outcomes_list or not prices_list:
                        continue

                    # Extract "Yes" price as sentiment proxy (0-1 probability)
                    if "bitcoin" in question_text or "btc" in question_text:
                        yes_index = next(
                            (i for i, o in enumerate(outcomes_list) if "yes" in str(o).lower()),
                            0,
                        )
                        if yes_index < len(prices_list):
                            sentiment_mapping["BTC"] = float(prices_list[yes_index])
                            logger.debug(
                                "BTC sentiment from Polymarket: %.3f (market: %s)",
                                sentiment_mapping["BTC"],
                                market_record.get("question", "")[:60],
                            )

                    elif "ethereum" in question_text or "eth" in question_text:
                        yes_index = next(
                            (i for i, o in enumerate(outcomes_list) if "yes" in str(o).lower()),
                            0,
                        )
                        if yes_index < len(prices_list):
                            sentiment_mapping["ETH"] = float(prices_list[yes_index])
                            logger.debug(
                                "ETH sentiment from Polymarket: %.3f (market: %s)",
                                sentiment_mapping["ETH"],
                                market_record.get("question", "")[:60],
                            )

        except httpx.HTTPStatusError as http_error:
            logger.warning(
                "Polymarket API error %d: %s",
                http_error.response.status_code,
                http_error,
            )
            self._error_count += 1
        except Exception as unexpected_error:
            logger.warning("Polymarket fetch error: %s", unexpected_error)
            self._error_count += 1

        return sentiment_mapping

    async def _polling_loop(self) -> None:
        """Main polling loop — runs at the configured interval."""
        while self._is_running:
            self._last_poll_timestamp = time.time()

            try:
                sentiment_data = await self._fetch_sentiment_data()

                if sentiment_data:
                    self._sentiment_data.update(sentiment_data)
                    self._last_successful_poll = time.time()

                    for asset_name, sentiment_score in sentiment_data.items():
                        event_envelope = EventEnvelope(
                            source="polymarket",
                            event_type=EventType.SENTIMENT,
                            payload={
                                "asset": asset_name,
                                "sentiment": sentiment_score,
                                "provider": "polymarket",
                                "poll_timestamp": self._last_poll_timestamp,
                            },
                            ticker=f"{asset_name}_SENTIMENT",
                        )
                        self.on_event_callback(event_envelope)

            except Exception as poll_error:
                logger.error("Polymarket poll loop error: %s", poll_error)
                self._error_count += 1

            await asyncio.sleep(self.poll_interval_seconds)

    def start(self) -> None:
        """Start the polling loop in a background thread."""
        if self._is_running:
            logger.warning("Polymarket poller already running")
            return

        self._is_running = True

        loop = asyncio.new_event_loop()
        self._loop = loop

        import threading

        def run_event_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._polling_loop())

        self._thread = threading.Thread(
            target=run_event_loop, daemon=True, name="polymarket-poller-loop"
        )
        self._thread.start()
        logger.info(
            "Polymarket sentiment poller started (interval=%ds)",
            self.poll_interval_seconds,
        )

    def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._is_running = False
        if hasattr(self, "_loop") and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("Polymarket sentiment poller stopped")

    def get_health_info(self) -> dict[str, Any]:
        """Get current health information."""
        return {
            "running": self._is_running,
            "last_poll_age_s": (
                time.time() - self._last_successful_poll
                if self._last_successful_poll > 0
                else None
            ),
            "error_count": self._error_count,
            "latest_sentiment": dict(self._sentiment_data),
        }
