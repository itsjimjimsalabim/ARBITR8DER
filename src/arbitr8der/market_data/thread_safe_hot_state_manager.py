"""Hot state — thread-safe in-memory snapshot of all live market data.

The AI reads one immutable ImmutableHotSnapshot per decision cycle.
No DB waits in the update path. Generation counter tracks freshness.

Per Theories_of_Operations: "RAM for hot data, SQLite for cold persistence."
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImmutableHotSnapshot:
    """Immutable snapshot of current market state. Read by AI each decision cycle.

    Frozen (frozen=True) so the AI can safely read while new updates arrive.
    """
    generation: int
    timestamp: float

    # Orderbook state per ticker: {ticker: {"yes_best": X, "no_best": Y, "spread": Z, ...}}
    orderbooks: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # Spot prices: {"BTC": 112345.67, "ETH": 3456.78}
    spot_prices: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # Sentiment: {"BTC": 0.55, "ETH": 0.48} (0-1 scale from Polymarket)
    sentiment: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # Macro: {"BTC_MCAP": "...", "BTC_24H_CHANGE": ...}
    macro: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # Active tickers: {"BTC": "KXBTC15M-...", "ETH": "KXETH15M-..."}
    active_tickers: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # Stream health: {"kalshi_rest": True, "kalshi_ws": True, "binance": True, ...}
    stream_health: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    # Latency measurements: {"binance_received_ms": 5, "snapshot_age_ms": 12, ...}
    latency: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    def is_stale(self, max_age_seconds: float = 10.0) -> bool:
        """Is this snapshot older than max_age?"""
        return (time.time() - self.timestamp) > max_age_seconds

    def to_dict(self) -> dict:
        """Convert to plain dict for serialization."""
        return {
            "generation": self.generation,
            "timestamp": self.timestamp,
            "orderbooks": dict(self.orderbooks),
            "spot_prices": dict(self.spot_prices),
            "sentiment": dict(self.sentiment),
            "macro": dict(self.macro),
            "active_tickers": dict(self.active_tickers),
            "stream_health": dict(self.stream_health),
            "latency": dict(self.latency),
        }


class ThreadSafeHotStateManager:
    """Thread-safe hot state manager.

    All updates go through this class. Readers get an immutable ImmutableHotSnapshot.
    A generation counter is bumped on every update so consumers can detect
    whether the state has changed since their last read.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._generation: int = 0
        self._last_update: float = 0.0

        # Mutable backing stores (protected by _lock)
        self._orderbooks: dict[str, dict[str, Any]] = {}
        self._spot_prices: dict[str, float] = {}
        self._sentiment: dict[str, float] = {}
        self._macro: dict[str, Any] = {}
        self._active_tickers: dict[str, str] = {}
        self._stream_health: dict[str, bool] = {}
        self._latency: dict[str, float] = {}

    @property
    def generation(self) -> int:
        return self._generation

    def snapshot(self) -> ImmutableHotSnapshot:
        """Get an immutable snapshot. Thread-safe, non-blocking read."""
        with self._lock:
            return ImmutableHotSnapshot(
                generation=self._generation,
                timestamp=self._last_update,
                orderbooks=MappingProxyType(dict(
                    {k: dict(v) for k, v in self._orderbooks.items()}
                )),
                spot_prices=MappingProxyType(dict(self._spot_prices)),
                sentiment=MappingProxyType(dict(self._sentiment)),
                macro=MappingProxyType(dict(self._macro)),
                active_tickers=MappingProxyType(dict(self._active_tickers)),
                stream_health=MappingProxyType(dict(self._stream_health)),
                latency=MappingProxyType(dict(self._latency)),
            )

    def update_orderbook(self, ticker: str, book_data: dict[str, Any]) -> None:
        """Update orderbook state for a ticker."""
        with self._lock:
            self._orderbooks[ticker] = dict(book_data)
            self._bump()

    def update_spot_price(self, asset: str, price: float) -> None:
        """Update spot price for an asset (BTC, ETH)."""
        with self._lock:
            self._spot_prices[asset] = price
            self._bump()

    def update_sentiment(self, asset: str, score: float) -> None:
        """Update sentiment score for an asset (0.0-1.0)."""
        with self._lock:
            self._sentiment[asset] = score
            self._bump()

    def update_macro(self, data: dict[str, Any]) -> None:
        """Update macro context data."""
        with self._lock:
            self._macro.update(data)
            self._bump()

    def update_active_ticker(self, asset: str, ticker: str) -> None:
        """Update the active ticker for an asset."""
        with self._lock:
            self._active_tickers[asset] = ticker
            self._bump()

    def update_stream_health(self, source: str, healthy: bool) -> None:
        """Update stream health status."""
        with self._lock:
            self._stream_health[source] = healthy
            self._bump()

    def update_latency(self, metric: str, value_ms: float) -> None:
        """Update a latency measurement."""
        with self._lock:
            self._latency[metric] = value_ms
            self._bump()

    def _bump(self) -> None:
        """Bump generation and timestamp. Must be called under _lock."""
        self._generation += 1
        self._last_update = time.time()

    def summary(self) -> dict:
        """Quick summary for status displays (no lock needed for reads)."""
        return {
            "generation": self._generation,
            "last_update": self._last_update,
            "tickers": dict(self._active_tickers),
            "spot_prices": dict(self._spot_prices),
            "streams": dict(self._stream_health),
        }
