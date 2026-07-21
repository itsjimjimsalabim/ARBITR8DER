"""Typed configuration for ARBITR8DER via pydantic-settings.

All settings are loaded from environment variables with the AR8_ prefix.
Example: AR8_VESSEL_STATE, AR8_KALSHI_API_KEY_ID, etc.
"""
from __future__ import annotations

import enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WalletMode(str, enum.Enum):
    """Wallet mode enum — case-insensitive."""

    @classmethod
    def _missing_(cls, value: str):
        """Allow case-insensitive matching."""
        for member in cls:
            if member.value.upper() == value.upper():
                return member
        return None
    PAPER = "PAPER"
    ARMED = "ARMED"


class TradingVesselState(str, enum.Enum):
    """Vessel state enum — case-insensitive."""

    @classmethod
    def _missing_(cls, value: str):
        """Allow case-insensitive matching."""
        for member in cls:
            if member.value.upper() == value.upper():
                return member
        return None
    FULL_STOP = "FULL_STOP"
    BATTERY = "BATTERY"
    FULL_FORWARD = "FULL_FORWARD"


# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DATA_DIR = RUNTIME_DIR / "data"
LOGS_DIR = RUNTIME_DIR / "logs"
JOURNALS_DIR = RUNTIME_DIR / "journals"
STATE_DIR = RUNTIME_DIR / "state"


class Settings(BaseSettings):
    """Application settings — loaded from .env with AR8_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="AR8_",
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Vessel ──────────────────────────────────────────────────────────
    vessel_state: TradingVesselState = TradingVesselState.FULL_STOP

    # ── Kalshi credentials ─────────────────────────────────────────────
    kalshi_api_key_id: str = ""
    kalshi_private_key_path: str = str(PROJECT_ROOT / "streams" / "kalshi_private.pem")
    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"

    # ── Trading mode ───────────────────────────────────────────────────
    wallet_mode: WalletMode = WalletMode.PAPER

    # ── Risk management ────────────────────────────────────────────────
    session_floor_pct: float = Field(default=0.20, description="Caution at -20%")
    rolling_floor_pct: float = Field(default=0.30, description="Pause at -30%")
    daily_loss_cap_pct: float = Field(default=0.50, description="Hard stop at -50%")
    lane_cooldown_periods: int = Field(default=2, description="Periods to wait after loss")
    max_position_pct: float = Field(default=0.30, description="Max balance in single position")

    # ── Execution thresholds ───────────────────────────────────────────
    min_edge_cents: float = Field(default=2.0, description="Minimum expected edge in cents")
    slippage_bps: float = Field(default=15.0, description="Assumed slippage in basis points")

    # ── Markets ────────────────────────────────────────────────────────
    target_assets: list[str] = Field(default=["BTC", "ETH"])
    btc_ticker_prefix: str = "KXBTC15M"
    eth_ticker_prefix: str = "KXETH15M"

    # ── Data sources ───────────────────────────────────────────────────
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    coinbase_ws_url: str = "wss://ws-feed.exchange.coinbase.com"
    polymarket_api_url: str = "https://gamma-api.polymarket.com"
    coingecko_api_url: str = "https://api.coingecko.com/api/v3"

    # ── Paths ──────────────────────────────────────────────────────────
    db_path: str = str(DATA_DIR / "arbitr8der.db")
    state_file: str = str(STATE_DIR / "vessel_state.json")

    # ── Timing ─────────────────────────────────────────────────────────
    poll_interval_coingecko_s: int = 300
    poll_interval_polymarket_s: int = 60
    stream_staleness_warn_s: int = 10
    stream_staleness_kill_s: int = 30

    @field_validator("kalshi_private_key_path")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        path = Path(v)
        if path.exists():
            return str(path.resolve())
        return v  # Allow missing at config time; fail at auth time

    @property
    def kalshi_auth_configured(self) -> bool:
        """True if we have both API key ID and a valid private key file."""
        return bool(self.kalshi_api_key_id) and Path(self.kalshi_private_key_path).exists()

    @property
    def armed_allowed(self) -> bool:
        """True if ARMED mode can be activated."""
        return self.kalshi_auth_configured and self.wallet_mode == WalletMode.ARMED


def load_settings() -> Settings:
    """Load settings from environment/.env. Called once at startup."""
    return Settings()
