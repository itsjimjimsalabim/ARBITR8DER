"""Immutable data contracts for the trading studio.

Every provider event, observation, and snapshot carries full lineage:
  - provider_event_id: unique per-event identifier from the source
  - provider_ts: timestamp assigned by the provider (UTC)
  - receive_ts: timestamp when the local process received it (UTC)
  - source_status: health/state of the provider at receipt time
  - sequence: monotonic sequence number from the provider (if available)
  - asset: the traded asset (BTC, ETH)
  - market_ticker: Kalshi market ticker (e.g. KXBTC15M-26JUL23-T15:00)
  - snapshot_version: monotonically increasing version of the hot snapshot this belongs to
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Asset(str, enum.Enum):
    BTC = "BTC"
    ETH = "ETH"


class ProviderSource(str, enum.Enum):
    KALSHI = "kalshi"
    BINANCE = "binance"
    COINBASE = "coinbase"
    POLYMARKET = "polymarket"
    COINGECKO = "coingecko"


class SourceHealthStatus(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


class OrderSide(str, enum.Enum):
    YES = "yes"
    NO = "no"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class MarketStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    PAUSED = "paused"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Base event — every provider event carries this lineage
# ---------------------------------------------------------------------------

class ProviderEvent(BaseModel):
    """Base model for any event received from a data provider."""
    model_config = {"frozen": True}

    provider_event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    provider_ts: datetime = Field(description="Timestamp assigned by the provider (UTC)")
    receive_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_status: SourceHealthStatus = SourceHealthStatus.UNKNOWN
    sequence: int | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider health
# ---------------------------------------------------------------------------

class ProviderHealthEvent(ProviderEvent):
    """Health status update from a provider."""
    source: ProviderSource
    status: SourceHealthStatus
    latency_ms: float | None = None
    error_message: str | None = None
    stream_uptime_seconds: float | None = None


# ---------------------------------------------------------------------------
# Kalshi order book
# ---------------------------------------------------------------------------

class OrderBookLevel(BaseModel):
    """Single price level in the order book."""
    model_config = {"frozen": True}
    price_cents: int = Field(ge=0, le=100)
    quantity: int = Field(ge=0)


class KalshiOrderBookEvent(ProviderEvent):
    """Kalshi order book state (snapshot or delta)."""
    source: Literal[ProviderSource.KALSHI] = ProviderSource.KALSHI
    asset: Asset
    market_ticker: str
    market_status: MarketStatus = MarketStatus.UNKNOWN
    strike_price_cents: int | None = None
    yes_bid: int | None = Field(default=None, ge=0, le=100)
    yes_ask: int | None = Field(default=None, ge=0, le=100)
    no_bid: int | None = Field(default=None, ge=0, le=100)
    yes_depth: list[OrderBookLevel] | dict[int, float] | Any = Field(default_factory=list)
    no_depth: list[OrderBookLevel] | dict[int, float] | Any = Field(default_factory=list)
    last_sequence: int | None = None
    fee_rate_bps: float | None = None
    is_snapshot: bool = True


# ---------------------------------------------------------------------------
# Exchange price observation (Binance, Coinbase)
# ---------------------------------------------------------------------------

class PriceObservationEvent(ProviderEvent):
    """Spot price observation from an exchange."""
    source: ProviderSource
    asset: Asset
    spot_price_usd: float = Field(gt=0)
    bid_usd: float | None = Field(default=None, gt=0)
    ask_usd: float | None = Field(default=None, gt=0)
    volume_24h_usd: float | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Polymarket sentiment
# ---------------------------------------------------------------------------

class PolymarketSentimentEvent(ProviderEvent):
    """Sentiment observation from Polymarket."""
    source: Literal[ProviderSource.POLYMARKET] = ProviderSource.POLYMARKET
    asset: Asset
    market_slug: str | None = None
    yes_price: float | None = Field(default=None, ge=0, le=1)
    no_price: float | None = Field(default=None, ge=0, le=1)
    volume_usd: float | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# CoinGecko macro context
# ---------------------------------------------------------------------------

class CoinGeckoMacroEvent(ProviderEvent):
    """Macro context from CoinGecko (slow poll)."""
    source: Literal[ProviderSource.COINGECKO] = ProviderSource.COINGECKO
    asset: Asset
    market_cap_usd: float | None = Field(default=None, ge=0)
    price_change_24h_pct: float | None = None
    total_volume_usd: float | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Hot snapshot — immutable combined market picture
# ---------------------------------------------------------------------------

class HotSnapshot(BaseModel):
    """Single immutable point-in-time picture of all sources.

    Version is monotonically increasing. Never mutated after creation.
    """
    model_config = {"frozen": True}

    snapshot_version: int = Field(ge=0)
    created_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asset: Asset

    # Source states
    kalshi_book: KalshiOrderBookEvent | None = None
    binance_spot: PriceObservationEvent | None = None
    coinbase_spot: PriceObservationEvent | None = None
    polymarket_sentiment: PolymarketSentimentEvent | None = None
    coingecko_macro: CoinGeckoMacroEvent | None = None

    # Derived fields
    spot_avg_usd: float | None = None
    spot_disagreement_pct: float | None = None
    kalshi_midpoint_cents: int | None = None
    time_to_market_close_seconds: float | None = None

    # Health summary
    source_health: dict[str, SourceHealthStatus] = Field(default_factory=dict)
    stale_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

class Prediction(BaseModel):
    """Forecast output for a 15-minute market."""
    model_config = {"frozen": True}

    prediction_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    created_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asset: Asset
    market_ticker: str
    snapshot_version: int = Field(ge=0)

    # Forecast
    probability_yes: float = Field(ge=0, le=1, description="Estimated P(YES)")
    confidence: float = Field(ge=0, le=1, description="Confidence in the forecast")
    recommendation: Literal["BUY_YES", "BUY_NO", "NO_TRADE"] = "NO_TRADE"

    # Feature context
    features_used: dict[str, Any] = Field(default_factory=dict)
    model_version: str = "baseline-v0"

    # Outcome (filled after market resolves)
    actual_outcome: bool | None = None
    outcome_ts: datetime | None = None
    score: float | None = None


# ---------------------------------------------------------------------------
# Trade intent
# ---------------------------------------------------------------------------

class TradeIntent(BaseModel):
    """Operator's explicit trade intent. Requires snapshot_version match."""
    model_config = {"frozen": True}

    intent_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    created_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    asset: Asset
    market_ticker: str
    snapshot_version: int = Field(ge=0)
    side: OrderSide
    quantity: int = Field(ge=2, description="Minimum 2 contracts")
    limit_price_cents: int | None = Field(default=None, ge=0, le=100)
    prediction_id: str | None = None
    reason: str = ""

    # Execution outcome
    status: OrderStatus = OrderStatus.PENDING
    fill_price_cents: int | None = None
    fill_quantity: int | None = None
    fill_ts: datetime | None = None
    fee_cents: int | None = None
    venue_order_id: str | None = None


# ---------------------------------------------------------------------------
# Journal entry
# ---------------------------------------------------------------------------

class JournalEntry(BaseModel):
    """Structured journal entry linking evidence to reasoning."""
    model_config = {"frozen": True}

    entry_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    created_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot_version: int | None = None
    prediction_id: str | None = None
    intent_id: str | None = None
    entry_type: Literal["observation", "hypothesis", "action", "outcome", "review"] = "observation"
    text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Archive manifest
# ---------------------------------------------------------------------------

class ArchiveManifest(BaseModel):
    """Metadata for an archived data bundle."""
    model_config = {"frozen": True}

    archive_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    created_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    oldest_event_ts: datetime
    newest_event_ts: datetime
    event_count: int = Field(ge=0)
    source_files: list[str] = Field(default_factory=list)
    checksum_sha256: str = ""
    verified: bool = False
    asset: Asset | None = None
