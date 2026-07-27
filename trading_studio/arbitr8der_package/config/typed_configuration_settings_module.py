"""Typed configuration settings for ARBITR8DER trading studio.

Loads from environment variables and the single root .env file
(``ARBITR8DER/.env`` at the repo root) by absolute path resolved from the
package location. This keeps the same env regardless of CWD, OS, or whether
the operator ran ``arb`` from the repo root or from ``trading_studio/``.
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from arbitr8der_package.config.cwd_independent_path_resolver import get_package_root


def _resolve_root_env_file() -> Path | None:
    """Resolve `<repo_root>/.env` from the package location.

    Returns ``None`` if the file does not exist so pydantic-settings silently
    falls back to environment variables only.
    """
    package_root = get_package_root()  # .../trading_studio
    repo_root = package_root.parent    # .../ARBITR8DER
    candidate = repo_root / ".env"
    return candidate if candidate.exists() else None


class TradingStudioSettings(BaseSettings):
    """Central settings object — sourced from env vars and the root .env file."""

    model_config = {
        "env_prefix": "AR8_",
        "env_file": _resolve_root_env_file(),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # Database
    db_host: str = Field(default="localhost", description="PostgreSQL host")
    db_port: int = Field(default=5432, description="PostgreSQL port")
    db_name: str = Field(default="arbitr8der", description="PostgreSQL database name")
    db_user: str = Field(default="postgres", description="PostgreSQL user")
    db_password: str = Field(default="postgres", description="PostgreSQL password")

    # Kalshi
    kalshi_api_key_id: str = Field(default="", description="Kalshi API key ID")
    kalshi_private_key_path: str = Field(default="kalshi_private.pem", description="Filename of Kalshi private key PEM in streams/ directory")
    kalshi_username: str = Field(default="", description="Kalshi account email")
    kalshi_password: str = Field(default="", description="Kalshi account password")

    # Trading behavior
    wallet_mode: str = Field(default="paper", description="paper | live")
    trading_mode: str = Field(default="hold", description="hold | buy | sell")
    tick_interval: int = Field(default=60, description="Seconds between data ticks")

    @field_validator("wallet_mode", "trading_mode", mode="before")
    @classmethod
    def _normalize_mode_string(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    # Data sources
    polymarket_api_url: str = Field(default="https://gamma-api.polymarket.com", description="Polymarket API base URL")
    binance_ws_url: str = Field(default="wss://stream.binance.com:9443/ws", description="Binance WebSocket endpoint")
    coinbase_ws_url: str = Field(default="wss://ws-feed.exchange.coinbase.com", description="Coinbase WebSocket endpoint")
    coingecko_api_url: str = Field(default="https://api.coingecko.com/api/v3", description="CoinGecko API base URL")
    kalshi_api_url: str = Field(default="https://api.elections.kalshi.com/trade-api/v2", description="Kalshi REST API base URL")
    kalshi_ws_url: str = Field(default="wss://api.elections.kalshi.com/trade-api/ws/v2", description="Kalshi WebSocket endpoint")
    kalshi_markets_url: str = Field(default="https://trading-api.kalshi.com/trade-api/v2", description="Kalshi markets API")

    # Safety
    auto_arm: bool = Field(default=False, description="Auto-arm on startup (dangerous)")
    dry_run: bool = Field(default=True, description="Simulate trades without execution")


def load_settings(**kwargs) -> TradingStudioSettings:
    """Load settings from environment with optional overrides."""
    return TradingStudioSettings(**kwargs)
