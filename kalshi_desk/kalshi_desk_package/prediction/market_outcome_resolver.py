"""Market outcome resolver — resolves Kalshi market settlement outcomes.

Checks Kalshi market status after close time and records the actual outcome
(YES=1, NO=0) for scoring against predictions.

Uses Kalshi REST API to fetch market status:
  - "settled" with expiration_value = "yes" or "no"
  - "closed" but not yet settled = pending resolution
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from kalshi_desk_package.config.typed_configuration_settings_module import load_settings
from kalshi_desk_package.config.structured_logging_configuration_module import get_logger
from kalshi_desk_package.prediction.baseline_prediction_engine import PredictionRecord

logger = get_logger(__name__)

_KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
_REQUEST_TIMEOUT = 10.0


@dataclass
class MarketOutcome:
    """Resolved outcome for a Kalshi market."""
    ticker: str = ""
    resolved: bool = False
    actual_outcome: int | None = None  # 1 = YES, 0 = NO
    market_status: str = ""  # "settled", "closed", "open", etc.
    expiration_value: str | None = None  # "yes", "no", or None
    reference_price: float | None = None  # strike price
    resolved_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "resolved": self.resolved,
            "actual_outcome": self.actual_outcome,
            "market_status": self.market_status,
            "expiration_value": self.expiration_value,
            "reference_price": self.reference_price,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class MarketOutcomeResolver:
    """Resolves Kalshi market outcomes by querying the REST API.

    Checks market status and extracts settlement information.
    """

    def __init__(self, api_key: str | None = None) -> None:
        settings = load_settings()
        self._api_key = api_key or settings.kalshi_api_key_id
        self._base_url = settings.kalshi_api_url.rstrip("/")
        self._headers: dict[str, str] = {}
        if self._api_key:
            self._headers["Authorization"] = f"Bearer {self._api_key}"

    async def resolve_market(self, ticker: str, client: httpx.AsyncClient | None = None) -> MarketOutcome:
        """Fetch market status and resolve outcome if settled.

        Args:
            ticker: Kalshi market ticker (e.g. "KXBTC15M-26JUL23-T15:00")
            client: Optional shared httpx client

        Returns:
            MarketOutcome with resolution info
        """
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            url = f"{self._base_url}/markets/{ticker}"
            response = await client.get(url, headers=self._headers)

            if response.status_code == 200:
                data = response.json()
                market_data = data.get("market", data)
                return self._parse_outcome(ticker, market_data)
            elif response.status_code == 404:
                logger.warning("Market not found: %s", ticker)
                return MarketOutcome(ticker=ticker, resolved=False, market_status="not_found")
            else:
                logger.error("Failed to fetch market %s: HTTP %d", ticker, response.status_code)
                return MarketOutcome(ticker=ticker, resolved=False, market_status="error")
        finally:
            if own_client:
                await client.aclose()

    def _parse_outcome(self, ticker: str, data: dict[str, Any]) -> MarketOutcome:
        """Parse market data into a MarketOutcome."""
        status = data.get("status", "unknown")
        expiration_value = data.get("expiration_value")
        reference_price = data.get("reference_price")

        outcome = MarketOutcome(
            ticker=ticker,
            market_status=status,
            expiration_value=expiration_value,
            reference_price=reference_price,
            raw_data=data,
        )

        if status == "settled" and expiration_value:
            outcome.resolved = True
            outcome.resolved_at = datetime.now(timezone.utc)

            if expiration_value.lower() == "yes":
                outcome.actual_outcome = 1
            elif expiration_value.lower() == "no":
                outcome.actual_outcome = 0
            else:
                logger.warning("Unknown expiration_value for %s: %s", ticker, expiration_value)

        return outcome

    async def resolve_predictions(
        self,
        predictions: list[PredictionRecord],
        client: httpx.AsyncClient | None = None,
    ) -> list[PredictionRecord]:
        """Resolve outcomes for a list of predictions.

        Updates each PredictionRecord with actual_outcome and outcome_ts
        if the market has settled.

        Args:
            predictions: List of PredictionRecord to resolve
            client: Optional shared httpx client

        Returns:
            Same list with outcome fields populated where available
        """
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

        try:
            # Group by ticker to avoid duplicate API calls
            tickers_seen: set[str] = set()
            outcomes: dict[str, MarketOutcome] = {}

            for pred in predictions:
                if pred.ticker and pred.ticker not in tickers_seen:
                    tickers_seen.add(pred.ticker)
                    outcome = await self.resolve_market(pred.ticker, client)
                    outcomes[pred.ticker] = outcome

            # Update predictions with outcomes
            resolved_count = 0
            for pred in predictions:
                if pred.ticker in outcomes:
                    outcome = outcomes[pred.ticker]
                    if outcome.resolved:
                        pred.actual_outcome = outcome.actual_outcome
                        pred.outcome_ts = outcome.resolved_at
                        resolved_count += 1

            logger.info("Resolved %d/%d predictions", resolved_count, len(predictions))
            return predictions
        finally:
            if own_client:
                await client.aclose()

    @staticmethod
    def parse_fixture_settled_response() -> dict[str, Any]:
        """Return a fixture settled market response for testing."""
        return {
            "market": {
                "ticker": "KXBTC15M-26JUL23-T15:00",
                "status": "settled",
                "expiration_value": "yes",
                "reference_price": 68000.0,
                "close_time": "2026-07-23T19:00:00Z",
                "expiration_time": "2026-07-23T19:00:00Z",
            }
        }

    @staticmethod
    def parse_fixture_closed_response() -> dict[str, Any]:
        """Return a fixture closed (not yet settled) market response."""
        return {
            "market": {
                "ticker": "KXBTC15M-26JUL23-T16:00",
                "status": "closed",
                "expiration_value": None,
                "reference_price": 68500.0,
                "close_time": "2026-07-23T20:00:00Z",
                "expiration_time": "2026-07-23T20:00:00Z",
            }
        }
