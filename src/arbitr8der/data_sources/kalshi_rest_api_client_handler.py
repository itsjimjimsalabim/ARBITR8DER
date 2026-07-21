"""Kalshi REST client — JWT auth, market discovery, active ticker resolution.

Authenticates with Kalshi using RSA private key JWT signing.
Fetches active 15-minute BTC/ETH markets and resolves current trading tickers.

Per Theories_of_Operations: "Kalshi is the main data source and main execution.
Only BTC and ETH 15-minute yes/no markets (KXBTC15M*, KXETH15M*)."
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import jwt

logger = logging.getLogger(__name__)

# Kalshi API base URLs
KALSHI_API_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"

# Market series prefixes for our target markets
BTC_SERIES_PREFIX = "KXBTC15M"
ETH_SERIES_PREFIX = "KXETH15M"


class KalshiRestApiClientHandler:
    """REST client for Kalshi market discovery and JWT authentication.

    Generates short-lived JWT tokens signed with RSA private key.
    Fetches active markets and resolves current 15-minute trading tickers.
    """

    def __init__(
        self,
        api_key_id: str,
        private_key_path: str,
        base_url: str = KALSHI_API_BASE_URL,
    ):
        self.api_key_id = api_key_id
        self.private_key_path = Path(private_key_path)
        self.base_url = base_url.rstrip("/")

        self._private_key_pem: Optional[bytes] = None
        self._jwt_token: Optional[str] = None
        self._jwt_generated_at: float = 0.0
        self._http_client: Optional[httpx.AsyncClient] = None

        self._load_private_key()

    def _load_private_key(self) -> None:
        """Load the RSA private key from disk."""
        if self.private_key_path.exists():
            self._private_key_pem = self.private_key_path.read_bytes()
            logger.info(
                "Loaded Kalshi private key from %s (%d bytes)",
                self.private_key_path.name,
                len(self._private_key_pem),
            )
        else:
            logger.warning(
                "Kalshi private key not found at %s", self.private_key_path
            )

    def generate_jwt_token(self) -> str:
        """Generate a short-lived JWT token for Kalshi API auth.

        Tokens are valid for ~24h but we regenerate every 55 min for safety.
        """
        now = time.time()
        if self._jwt_token and (now - self._jwt_generated_at) < 3300:
            return self._jwt_token

        if not self._private_key_pem:
            raise RuntimeError("No private key loaded — cannot generate JWT")

        payload = {
            "iss": self.api_key_id,
            "sub": self.api_key_id,
            "iat": int(now),
            "exp": int(now) + 86400,
        }

        self._jwt_token = jwt.encode(
            payload, self._private_key_pem, algorithm="RS512"
        )
        self._jwt_generated_at = now

        logger.info("Generated new Kalshi JWT token (expires in 24h)")
        return self._jwt_token

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers for Kalshi API requests."""
        token = self.generate_jwt_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get_active_markets(self) -> list[dict[str, Any]]:
        """Fetch all active markets from Kalshi API.

        Returns list of market dicts. Filters for our 15-min BTC/ETH series.
        """
        headers = self._get_auth_headers()
        url = f"{self.base_url}/markets"

        params = {"status": "open", "limit": 100}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=headers, params=params, timeout=15.0
                )
                response.raise_for_status()

            data = response.json()
            all_markets = data.get("markets", [])

            # Filter for our target series
            target_markets = [
                mkt
                for mkt in all_markets
                if mkt.get("ticker", "").startswith(
                    (BTC_SERIES_PREFIX, ETH_SERIES_PREFIX)
                )
            ]

            logger.info(
                "Fetched %d active markets (%d target: BTC/ETH 15m)",
                len(all_markets),
                len(target_markets),
            )
            return target_markets

        except httpx.HTTPStatusError as http_error:
            logger.error(
                "Kalshi API error %d: %s", http_error.response.status_code, http_error
            )
            raise
        except Exception as unexpected_error:
            logger.error("Failed to fetch Kalshi markets: %s", unexpected_error)
            raise

    async def get_current_tickers(self) -> dict[str, str]:
        """Resolve current active trading tickers for BTC and ETH.

        Returns {"BTC": "KXBTC15M-...", "ETH": "KXETH15M-..."}.
        Picks the ticker closest to expiry (next rollover).
        """
        active_markets = await self.get_active_markets()
        active_ticker_mapping: dict[str, str] = {}

        btc_candidates: list[dict] = []
        eth_candidates: list[dict] = []

        for market_record in active_markets:
            ticker_name = market_record.get("ticker", "")
            if ticker_name.startswith(BTC_SERIES_PREFIX):
                btc_candidates.append(market_record)
            elif ticker_name.startswith(ETH_SERIES_PREFIX):
                eth_candidates.append(market_record)

        # Pick the one closest to expiry (smallest time to close)
        if btc_candidates:
            best_btc = min(
                btc_candidates,
                key=lambda m: abs(
                    m.get("close_time", 0) - time.time()
                ),
            )
            active_ticker_mapping["BTC"] = best_btc["ticker"]
            logger.info("Active BTC ticker: %s", best_btc["ticker"])

        if eth_candidates:
            best_eth = min(
                eth_candidates,
                key=lambda m: abs(
                    m.get("close_time", 0) - time.time()
                ),
            )
            active_ticker_mapping["ETH"] = best_eth["ticker"]
            logger.info("Active ETH ticker: %s", best_eth["ticker"])

        return active_ticker_mapping

    async def health_check(self) -> bool:
        """Simple health check — can we reach the Kalshi API?"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/exchange/status",
                    timeout=10.0,
                )
                is_healthy = response.status_code == 200
                logger.info("Kalshi health check: %s", "OK" if is_healthy else "FAIL")
                return is_healthy
        except Exception as health_check_error:
            logger.warning("Kalshi health check failed: %s", health_check_error)
            return False

    async def close(self) -> None:
        """Clean up HTTP client resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
