"""Hot snapshot merger — combines provider states into immutable HotSnapshots.

Merges the latest observation from each provider (Kalshi, Binance, Coinbase,
Polymarket, CoinGecko) into per-asset frozen HotSnapshots with a monotonically
increasing version number. Identifies missing or stale sources rather than
silently omitting them.

Read-only — no trading decisions here.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from arbitr8der_package.data_contracts.event_data_models import (
    Asset,
    CoinGeckoMacroEvent,
    HotSnapshot,
    KalshiOrderBookEvent,
    PolymarketSentimentEvent,
    PriceObservationEvent,
    SourceHealthStatus,
)


# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

_HEALTHY_MAX_AGE_S = 10.0
_DEGRADED_MAX_AGE_S = 30.0
_STALE_MAX_AGE_S = 120.0


# ---------------------------------------------------------------------------
# Health classification
# ---------------------------------------------------------------------------

def _classify_age(age_seconds: float | None) -> SourceHealthStatus:
    """Classify source health based on how recently it was updated."""
    if age_seconds is None:
        return SourceHealthStatus.DISCONNECTED
    if age_seconds <= _HEALTHY_MAX_AGE_S:
        return SourceHealthStatus.HEALTHY
    if age_seconds <= _DEGRADED_MAX_AGE_S:
        return SourceHealthStatus.DEGRADED
    if age_seconds <= _STALE_MAX_AGE_S:
        return SourceHealthStatus.STALE
    return SourceHealthStatus.DISCONNECTED


def _age_from_events(a: datetime | None, b: datetime | None) -> float | None:
    """Compute age in seconds between two datetimes (b is newer)."""
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds())


# ---------------------------------------------------------------------------
# Snapshot merger
# ---------------------------------------------------------------------------

class SnapshotMerger:
    """Merges all five provider states into per-asset HotSnapshots.

    Maintains a monotonic version counter. Every merge call increments it.
    Missing sources are reported as DISCONNECTED in source_health, not dropped.

    The merger holds the latest event from each provider, keyed by asset.
    Call ``build_snapshots()`` to produce one frozen HotSnapshot per active asset.

    Usage:
        merger = SnapshotMerger()
        merger.update_kalshi(book_event)
        merger.update_binance(btc_obs)
        merger.update_coinbase(btc_obs)
        merger.update_polymarket(ticker, sentiment_event)
        merger.update_coingecko(btc_macro)
        snapshots = merger.build_snapshots()
    """

    def __init__(self, now_fn: Any = None) -> None:
        self._version: int = 0
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        # Per-ticker Kalshi books
        self._kalshi: dict[str, KalshiOrderBookEvent] = {}
        # Per-asset spot prices
        self._binance: dict[Asset, PriceObservationEvent] = {}
        self._coinbase: dict[Asset, PriceObservationEvent] = {}
        # Per-ticker Polymarket sentiment
        self._polymarket: dict[str, PolymarketSentimentEvent] = {}
        # Per-asset CoinGecko macro
        self._coingecko: dict[Asset, CoinGeckoMacroEvent] = {}
        # Sequence tracking for Kalshi gap detection
        self._last_kalshi_seq: dict[str, int] = {}

    @property
    def version(self) -> int:
        return self._version

    def update_kalshi(self, event: KalshiOrderBookEvent) -> None:
        """Update Kalshi order book state for a ticker."""
        self._kalshi[event.market_ticker] = event

    def update_binance(self, asset: Asset, event: PriceObservationEvent) -> None:
        """Update Binance spot price for an asset."""
        self._binance[asset] = event

    def update_coinbase(self, asset: Asset, event: PriceObservationEvent) -> None:
        """Update Coinbase spot price for an asset."""
        self._coinbase[asset] = event

    def update_polymarket(self, ticker: str, event: PolymarketSentimentEvent) -> None:
        """Update Polymarket sentiment for a Kalshi ticker."""
        self._polymarket[ticker] = event

    def update_coingecko(self, asset: Asset, event: CoinGeckoMacroEvent) -> None:
        """Update CoinGecko macro data for an asset."""
        self._coingecko[asset] = event

    def clear_ticker(self, ticker: str) -> None:
        """Remove all state for a closed Kalshi ticker."""
        self._kalshi.pop(ticker, None)
        self._polymarket.pop(ticker, None)

    def active_tickers(self) -> list[str]:
        """Return all tracked Kalshi tickers, sorted."""
        return sorted(self._kalshi.keys())

    def active_assets(self) -> list[Asset]:
        """Return assets that have at least one data source active."""
        assets: set[Asset] = set()
        for ev in self._kalshi.values():
            assets.add(ev.asset)
        for a in self._binance:
            assets.add(a)
        for a in self._coinbase:
            assets.add(a)
        for ev in self._coingecko.values():
            assets.add(ev.asset)
        if not assets:
            assets = {Asset.BTC, Asset.ETH}
        return sorted(assets, key=lambda a: a.value)

    def _resolve_polymarket_for_asset(self, asset: Asset) -> PolymarketSentimentEvent | None:
        """Find the Polymarket sentiment for the first ticker matching this asset."""
        for ticker, poly in self._polymarket.items():
            if ticker.upper().startswith(f"KX{asset.value}"):
                return poly
        return None

    def build_snapshots(self) -> list[HotSnapshot]:
        """Build one frozen HotSnapshot per active asset.

        Increments the version counter once for all assets.
        Each snapshot is independent and immutable.
        """
        self._version += 1
        now = self._now_fn()
        snapshots: list[HotSnapshot] = []

        for asset in self.active_assets():
            # --- Source lookup ---
            kalshi_event = self._find_kalshi_for_asset(asset)
            binance_event = self._binance.get(asset)
            coinbase_event = self._coinbase.get(asset)
            polymarket_event = self._resolve_polymarket_for_asset(asset)
            coingecko_event = self._coingecko.get(asset)

            # --- Derived spot fields ---
            spot_avg: float | None = None
            spot_disagreement: float | None = None
            if binance_event and coinbase_event:
                spot_avg = round((binance_event.spot_price_usd + coinbase_event.spot_price_usd) / 2, 4)
                spot_disagreement = round(abs(binance_event.spot_price_usd - coinbase_event.spot_price_usd) / spot_avg * 100, 6)
            elif binance_event:
                spot_avg = binance_event.spot_price_usd
            elif coinbase_event:
                spot_avg = coinbase_event.spot_price_usd

            # --- Midpoint ---
            midpoint: int | None = None
            if kalshi_event:
                if kalshi_event.yes_bid is not None and kalshi_event.yes_ask is not None:
                    midpoint = round((kalshi_event.yes_bid + kalshi_event.yes_ask) / 2)
                elif polymarket_event:
                    midpoint = round(polymarket_event.yes_price * 100)

            # --- Health classification ---
            source_health: dict[str, SourceHealthStatus] = {}
            stale_sources: list[str] = []
            missing_sources: list[str] = []

            # Kalshi
            kalshi_source_name = f"kalshi_{asset.value.lower()}"
            if kalshi_event:
                age = _age_from_events(kalshi_event.receive_ts, now)
                status = _classify_age(age)
                source_health[kalshi_source_name] = status
                if status in (SourceHealthStatus.STALE, SourceHealthStatus.DISCONNECTED):
                    stale_sources.append(kalshi_source_name)
            else:
                source_health[kalshi_source_name] = SourceHealthStatus.DISCONNECTED
                missing_sources.append(kalshi_source_name)

            # Binance
            binance_source_name = f"binance_{asset.value.lower()}"
            if binance_event:
                age = _age_from_events(binance_event.receive_ts, now)
                status = _classify_age(age)
                source_health[binance_source_name] = status
                if status in (SourceHealthStatus.STALE, SourceHealthStatus.DISCONNECTED):
                    stale_sources.append(binance_source_name)
            else:
                source_health[binance_source_name] = SourceHealthStatus.DISCONNECTED
                missing_sources.append(binance_source_name)

            # Coinbase
            coinbase_source_name = f"coinbase_{asset.value.lower()}"
            if coinbase_event:
                age = _age_from_events(coinbase_event.receive_ts, now)
                status = _classify_age(age)
                source_health[coinbase_source_name] = status
                if status in (SourceHealthStatus.STALE, SourceHealthStatus.DISCONNECTED):
                    stale_sources.append(coinbase_source_name)
            else:
                source_health[coinbase_source_name] = SourceHealthStatus.DISCONNECTED
                missing_sources.append(coinbase_source_name)

            # Polymarket
            polymarket_source_name = f"polymarket_{asset.value.lower()}"
            if polymarket_event:
                age = _age_from_events(polymarket_event.receive_ts, now)
                status = _classify_age(age)
                source_health[polymarket_source_name] = status
                if status in (SourceHealthStatus.STALE, SourceHealthStatus.DISCONNECTED):
                    stale_sources.append(polymarket_source_name)
            else:
                source_health[polymarket_source_name] = SourceHealthStatus.DISCONNECTED
                missing_sources.append(polymarket_source_name)

            # CoinGecko
            coingecko_source_name = f"coingecko_{asset.value.lower()}"
            if coingecko_event:
                age = _age_from_events(coingecko_event.receive_ts, now)
                status = _classify_age(age)
                source_health[coingecko_source_name] = status
                if status in (SourceHealthStatus.STALE, SourceHealthStatus.DISCONNECTED):
                    stale_sources.append(coingecko_source_name)
            else:
                source_health[coingecko_source_name] = SourceHealthStatus.DISCONNECTED
                missing_sources.append(coingecko_source_name)

            snapshot = HotSnapshot(
                snapshot_version=self._version,
                created_ts=now,
                asset=asset,
                kalshi_book=kalshi_event,
                binance_spot=binance_event,
                coinbase_spot=coinbase_event,
                polymarket_sentiment=polymarket_event,
                coingecko_macro=coingecko_event,
                spot_avg_usd=spot_avg,
                spot_disagreement_pct=spot_disagreement,
                kalshi_midpoint_cents=midpoint,
                source_health=source_health,
                stale_sources=stale_sources,
                missing_sources=missing_sources,
            )
            snapshots.append(snapshot)

        return snapshots

    def _find_kalshi_for_asset(self, asset: Asset) -> KalshiOrderBookEvent | None:
        """Find the first Kalshi book event for a given asset."""
        for ev in self._kalshi.values():
            if ev.asset == asset:
                return ev
        return None
