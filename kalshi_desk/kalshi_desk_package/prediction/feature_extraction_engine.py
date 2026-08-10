"""Prediction feature extraction engine.

Extracts numeric features from HotSnapshot + Binance candle history
for the baseline prediction model. All features are versioned with
the snapshot version for reproducibility.

Features:
  - 1/5/15-minute price direction (up/down/flat)
  - Realized volatility (high-low range over N candles)
  - Spot disagreement (cross-source price divergence)
  - Volume (recent trading volume)
  - Time to market close (seconds until Kalshi market settles)
  - Market-implied probability (Kalshi midpoint as YES probability)
  - Data freshness (age of latest data per source in seconds)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


@dataclass
class PredictionFeatures:
    """Immutable feature vector extracted from a snapshot + candle history.

    All fields are nullable — missing features are None, not zero.
    """

    # Metadata
    asset: str = ""
    snapshot_version: int = 0
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Price direction features (positive = up, negative = down, 0 = flat)
    direction_1m: float | None = None   # 1-minute price change pct
    direction_5m: float | None = None   # 5-minute price change pct
    direction_15m: float | None = None  # 15-minute price change pct

    # Volatility features
    realized_vol_5m: float | None = None   # 5-min realized vol (high-low range / price)
    realized_vol_15m: float | None = None  # 15-min realized vol

    # Cross-source features
    spot_disagreement_pct: float | None = None  # disagreement between spot providers

    # Volume features
    recent_volume_usd: float | None = None  # volume over recent candles
    market_cap_usd: float | None = None     # from CoinGecko

    # Market structure features
    time_to_close_seconds: float | None = None  # seconds until Kalshi market closes
    kalshi_midpoint_cents: float | None = None  # market-implied YES probability (0-100)
    kalshi_spread_cents: float | None = None    # yes_ask - yes_bid spread

    # Data freshness features (seconds since last update)
    freshness_binance: float | None = None
    freshness_coinbase: float | None = None
    freshness_coingecko: float | None = None
    freshness_kalshi: float | None = None
    freshness_polymarket: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize features to a flat dict for storage/inspection."""
        return {
            "asset": self.asset,
            "snapshot_version": self.snapshot_version,
            "extracted_at": self.extracted_at.isoformat(),
            "direction_1m": self.direction_1m,
            "direction_5m": self.direction_5m,
            "direction_15m": self.direction_15m,
            "realized_vol_5m": self.realized_vol_5m,
            "realized_vol_15m": self.realized_vol_15m,
            "spot_disagreement_pct": self.spot_disagreement_pct,
            "recent_volume_usd": self.recent_volume_usd,
            "market_cap_usd": self.market_cap_usd,
            "time_to_close_seconds": self.time_to_close_seconds,
            "kalshi_midpoint_cents": self.kalshi_midpoint_cents,
            "kalshi_spread_cents": self.kalshi_spread_cents,
            "freshness_binance": self.freshness_binance,
            "freshness_coinbase": self.freshness_coinbase,
            "freshness_coingecko": self.freshness_coingecko,
            "freshness_kalshi": self.freshness_kalshi,
            "freshness_polymarket": self.freshness_polymarket,
        }

    @property
    def feature_count(self) -> int:
        """Number of non-None features."""
        return sum(1 for v in self.to_dict().values() if v is not None and v != self.asset)

    @property
    def completeness_pct(self) -> float:
        """Percentage of features that are non-None (excluding metadata)."""
        total = 15  # number of numeric features
        non_none = sum(1 for v in [
            self.direction_1m, self.direction_5m, self.direction_15m,
            self.realized_vol_5m, self.realized_vol_15m,
            self.spot_disagreement_pct, self.recent_volume_usd, self.market_cap_usd,
            self.time_to_close_seconds, self.kalshi_midpoint_cents, self.kalshi_spread_cents,
            self.freshness_binance, self.freshness_coinbase, self.freshness_coingecko,
            self.freshness_kalshi,
        ] if v is not None)
        return non_none / total * 100


class FeatureExtractionEngine:
    """Extracts prediction features from snapshot + candle history.

    Stateless — each extract() call produces a fresh PredictionFeatures.
    """

    def extract(
        self,
        asset: str,
        snapshot_version: int,
        snapshot: Any | None = None,
        candles: list[Any] | None = None,
        kalshi_market: Any = None,
        coingecko_obs: Any = None,
    ) -> PredictionFeatures:
        """Extract features from available data.

        Args:
            asset: "BTC" or "ETH"
            snapshot_version: Monotonic snapshot version
            snapshot: HotSnapshot instance
            candles: List of BinanceCandle objects (most recent last), or None
            kalshi_market: KalshiMarketDetail or None
            coingecko_obs: CoinGeckoMacroObservation or None

        Returns:
            PredictionFeatures with as many fields populated as data allows.
        """
        features = PredictionFeatures(asset=asset, snapshot_version=snapshot_version)

        # Direction features from Binance candles
        if candles and len(candles) >= 2:
            self._extract_directions(features, candles)

        # Volatility features from Binance candles
        if candles and len(candles) >= 2:
            self._extract_volatility(features, candles)

        # Spot disagreement from snapshot
        if snapshot and snapshot.spot_disagreement_pct is not None:
            features.spot_disagreement_pct = snapshot.spot_disagreement_pct

        # Volume from recent candles
        if candles:
            self._extract_volume(features, candles)

        # Market cap from CoinGecko
        if coingecko_obs and coingecko_obs.market_cap_usd is not None:
            features.market_cap_usd = coingecko_obs.market_cap_usd

        # Market structure from Kalshi
        if kalshi_market:
            self._extract_market_structure(features, kalshi_market, datetime.now(timezone.utc))

        # Kalshi midpoint from snapshot (if Kalshi state was merged)
        if snapshot and hasattr(snapshot, 'kalshi_midpoint_cents') and snapshot.kalshi_midpoint_cents is not None:
            features.kalshi_midpoint_cents = float(snapshot.kalshi_midpoint_cents)

        # Data freshness from snapshot source health
        if snapshot:
            self._extract_freshness(features, snapshot)

        logger.info(
            "Extracted %d features for %s (v%d, %.0f%% complete)",
            features.feature_count,
            asset,
            snapshot_version,
            features.completeness_pct,
        )
        return features

    def _extract_directions(self, features: PredictionFeatures, candles: list[Any]) -> None:
        """Extract 1/5/15-minute price direction from candles."""
        closes = [c.close for c in candles]

        if len(closes) >= 2:
            prev = closes[-2]
            curr = closes[-1]
            if prev > 0:
                features.direction_1m = (curr - prev) / prev * 100

        if len(closes) >= 6:
            prev = closes[-6]
            curr = closes[-1]
            if prev > 0:
                features.direction_5m = (curr - prev) / prev * 100

        if len(closes) >= 16:
            prev = closes[-16]
            curr = closes[-1]
            if prev > 0:
                features.direction_15m = (curr - prev) / prev * 100

    def _extract_volatility(self, features: PredictionFeatures, candles: list[Any]) -> None:
        """Extract realized volatility from candle high-low ranges."""
        if len(candles) >= 6:
            recent_5m = candles[-5:]
            avg_price = sum(c.close for c in recent_5m) / len(recent_5m)
            if avg_price > 0:
                total_range = sum(c.high - c.low for c in recent_5m)
                features.realized_vol_5m = total_range / avg_price * 100

        if len(candles) >= 16:
            recent_15m = candles[-15:]
            avg_price = sum(c.close for c in recent_15m) / len(recent_15m)
            if avg_price > 0:
                total_range = sum(c.high - c.low for c in recent_15m)
                features.realized_vol_15m = total_range / avg_price * 100

    def _extract_volume(self, features: PredictionFeatures, candles: list[Any]) -> None:
        """Extract recent volume from candles."""
        if candles:
            recent = candles[-15:] if len(candles) >= 15 else candles
            total_volume = sum(c.quote_volume for c in recent if c.quote_volume > 0)
            if total_volume > 0:
                features.recent_volume_usd = total_volume

    def _extract_market_structure(
        self,
        features: PredictionFeatures,
        market: Any,
        now: datetime,
    ) -> None:
        """Extract market structure features from Kalshi market detail."""
        if market.midpoint_cents is not None:
            features.kalshi_midpoint_cents = float(market.midpoint_cents)

        if market.yes_bid is not None and market.yes_ask is not None:
            features.kalshi_spread_cents = float(market.yes_ask - market.yes_bid)

        if market.close_time:
            try:
                close_dt = datetime.fromisoformat(market.close_time.replace("Z", "+00:00"))
                remaining = (close_dt - now).total_seconds()
                if remaining > 0:
                    features.time_to_close_seconds = remaining
            except (ValueError, TypeError):
                pass

    def _extract_freshness(self, features: PredictionFeatures, snapshot: Any) -> None:
        """Extract data freshness from snapshot source health."""
        if not hasattr(snapshot, 'source_health') or not snapshot.source_health:
            return

        for source_name, health_status in snapshot.source_health.items():
            lower = source_name.lower()
            # Map source names to freshness fields
            if "binance" in lower:
                # Use stale_sources list to estimate freshness
                if source_name in getattr(snapshot, 'stale_sources', []):
                    features.freshness_binance = 999.0  # stale = high age
                else:
                    features.freshness_binance = 0.0  # healthy = fresh
            elif "coinbase" in lower:
                if source_name in getattr(snapshot, 'stale_sources', []):
                    features.freshness_coinbase = 999.0
                else:
                    features.freshness_coinbase = 0.0
            elif "coingecko" in lower:
                if source_name in getattr(snapshot, 'stale_sources', []):
                    features.freshness_coingecko = 999.0
                else:
                    features.freshness_coingecko = 0.0
            elif "kalshi" in lower:
                if source_name in getattr(snapshot, 'stale_sources', []):
                    features.freshness_kalshi = 999.0
                else:
                    features.freshness_kalshi = 0.0
            elif "polymarket" in lower:
                if source_name in getattr(snapshot, 'stale_sources', []):
                    features.freshness_polymarket = 999.0
                else:
                    features.freshness_polymarket = 0.0
