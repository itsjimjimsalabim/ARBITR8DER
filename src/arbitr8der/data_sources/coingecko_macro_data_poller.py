"""CoinGecko macro data poller — BTC/ETH market cap, volume, 24h changes.

Polls CoinGecko free API for macro-level crypto data at slower cadence.
Used for context only, never as an entry/exit trigger.

Per Theories_of_Operations: "Coingecko is slow bigger-picture data like
volume/marketcap/longer changes. Context only, never an entry/exit trigger."
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

import httpx

from ..market_data.immutable_event_envelope_wrapper import EventEnvelope, EventType

logger = logging.getLogger(__name__)

COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
DEFAULT_POLL_INTERVAL_SECONDS = 60

# CoinGecko coin IDs for our target assets
COINGECKO_COIN_IDS = ["bitcoin", "ethereum"]

INITIAL_RECONNECT_DELAY_SECONDS = 1.0
MAX_RECONNECT_DELAY_SECONDS = 300


class CoinGeckoMacroDataPoller:
    """HTTP poller for CoinGecko macro-level crypto market data.

    Polls CoinGecko every N seconds for BTC/ETH market cap, volume, and
    24h price changes. Used as context overlay only — never a trade trigger.
    """

    def __init__(
        self,
        on_event_callback: Callable[[EventEnvelope], None],
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        api_base_url: str = COINGECKO_API_BASE,
    ):
        self.on_event_callback = on_event_callback
        self.poll_interval_seconds = poll_interval_seconds
        self.api_base_url = api_base_url

        self._is_running: bool = False
        self._last_poll_timestamp: float = 0.0
        self._last_successful_poll: float = 0.0
        self._macro_data: dict[str, Any] = {}
        self._error_count: int = 0
        self._rate_limit_until: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def latest_macro_data(self) -> dict[str, Any]:
        return dict(self._macro_data)

    async def _fetch_macro_data(self) -> dict[str, Any]:
        """Fetch macro data for BTC and ETH from CoinGecko.

        Returns mapping of asset -> macro metrics dict.
        """
        macro_mapping: dict[str, Any] = {}

        # Respect rate limit cooldown
        if time.time() < self._rate_limit_until:
            logger.debug("CoinGecko rate limited, skipping poll")
            return macro_mapping

        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(
                    f"{self.api_base_url}/coins/markets",
                    params={
                        "vs_currency": "usd",
                        "ids": ",".join(COINGECKO_COIN_IDS),
                        "order": "market_cap_desc",
                        "sparkline": "false",
                    },
                    timeout=15.0,
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    self._rate_limit_until = time.time() + retry_after
                    logger.warning(
                        "CoinGecko rate limited (429). Cooling down for %ds",
                        retry_after,
                    )
                    return macro_mapping

                response.raise_for_status()
                coins_data = response.json()

                for coin_record in coins_data:
                    coin_id = coin_record.get("id", "")

                    # Map CoinGecko ID to our asset name
                    asset_name = None
                    if coin_id == "bitcoin":
                        asset_name = "BTC"
                    elif coin_id == "ethereum":
                        asset_name = "ETH"

                    if not asset_name:
                        continue

                    macro_metrics = {
                        "price_usd": coin_record.get("current_price"),
                        "market_cap": coin_record.get("market_cap"),
                        "market_cap_rank": coin_record.get("market_cap_rank"),
                        "total_volume": coin_record.get("total_volume"),
                        "price_change_24h": coin_record.get("price_change_24h"),
                        "price_change_percentage_24h": coin_record.get(
                            "price_change_percentage_24h"
                        ),
                        "price_change_percentage_7d": coin_record.get(
                            "price_change_percentage_7d_in_currency"
                        ),
                        "circulating_supply": coin_record.get("circulating_supply"),
                        "ath": coin_record.get("ath"),
                        "ath_change_percentage": coin_record.get(
                            "ath_change_percentage"
                        ),
                    }

                    macro_mapping[asset_name] = macro_metrics
                    logger.debug(
                        "CoinGecko %s: price=$%s, mcap=$%s, vol=$%s",
                        asset_name,
                        macro_metrics["price_usd"],
                        macro_metrics["market_cap"],
                        macro_metrics["total_volume"],
                    )

        except httpx.HTTPStatusError as http_error:
            logger.warning(
                "CoinGecko API error %d: %s",
                http_error.response.status_code,
                http_error,
            )
            self._error_count += 1
        except Exception as unexpected_error:
            logger.warning("CoinGecko fetch error: %s", unexpected_error)
            self._error_count += 1

        return macro_mapping

    async def _polling_loop(self) -> None:
        """Main polling loop — runs at the configured interval."""
        while self._is_running:
            self._last_poll_timestamp = time.time()

            try:
                macro_data = await self._fetch_macro_data()

                if macro_data:
                    self._macro_data.update(macro_data)
                    self._last_successful_poll = time.time()

                    for asset_name, macro_metrics in macro_data.items():
                        event_envelope = EventEnvelope(
                            source="coingecko",
                            event_type=EventType.MACRO,
                            payload={
                                "asset": asset_name,
                                "macro": macro_metrics,
                                "provider": "coingecko",
                                "poll_timestamp": self._last_poll_timestamp,
                            },
                            ticker=f"{asset_name}_MACRO",
                        )
                        self.on_event_callback(event_envelope)

            except Exception as poll_error:
                logger.error("CoinGecko poll loop error: %s", poll_error)
                self._error_count += 1

            await asyncio.sleep(self.poll_interval_seconds)

    def start(self) -> None:
        """Start the polling loop in a background thread."""
        if self._is_running:
            logger.warning("CoinGecko poller already running")
            return

        self._is_running = True

        loop = asyncio.new_event_loop()
        self._loop = loop

        import threading

        def run_event_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._polling_loop())

        self._thread = threading.Thread(
            target=run_event_loop, daemon=True, name="coingecko-poller-loop"
        )
        self._thread.start()
        logger.info(
            "CoinGecko macro data poller started (interval=%ds)",
            self.poll_interval_seconds,
        )

    def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._is_running = False
        if hasattr(self, "_loop") and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("CoinGecko macro data poller stopped")

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
            "rate_limited_until": self._rate_limit_until,
            "latest_macro_data": dict(self._macro_data),
        }
