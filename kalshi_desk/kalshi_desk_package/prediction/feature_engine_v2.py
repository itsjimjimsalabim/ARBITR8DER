"""Feature engineering engine v2 — computes macro, micro, and cross-asset
features from persisted candle data for the prediction models.

Reads from CandlePersistenceStore (SQLite) and produces feature dicts
that can be fed directly into LightGBM, frequency lookup, or any other model.

Features are organized into three tiers:
  - Macro: from 288 fifteen-minute candles (72h trend regime)
  - Micro: from last 20 one-minute candles + live market state
  - Cross-asset: BTC↔ETH relationships
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict

import numpy as np

from kalshi_desk_package.config.structured_logging_configuration_module import get_logger
from kalshi_desk_package.durable_storage.candle_persistence_store import CandlePersistenceStore

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Feature vector dataclass
# ---------------------------------------------------------------------------

@dataclass
class MacroFeatures:
    """Features computed from 72h of 15-minute candles."""
    # Trend
    streak_length: int = 0
    streak_direction: int = 0  # +1 = UP, -1 = DOWN
    body_ratio: float = 0.0  # |close-open| / (high-low)
    body_ratio_sma_6: float = 0.0  # 6-candle average body ratio

    # Momentum
    return_1: float = 0.0  # 1-candle return %
    return_4: float = 0.0  # 4-candle (1h) return %
    return_16: float = 0.0  # 16-candle (4h) return %
    return_96: float = 0.0  # 96-candle (24h) return %

    # Moving averages
    price_vs_sma_24: float = 0.0  # price / SMA(close, 24) - 1
    price_vs_sma_96: float = 0.0  # price / SMA(close, 96) - 1
    sma_24_vs_sma_96: float = 0.0  # SMA(24) / SMA(96) - 1

    # Technical indicators
    rsi_7: float = 50.0
    rsi_14: float = 50.0
    bollinger_pct: float = 0.5  # position within bands [0,1]
    bollinger_width: float = 0.0  # (upper - lower) / middle
    atr_14: float = 0.0  # normalized ATR

    # Volatility
    realized_vol_15m: float = 0.0  # single candle vol
    realized_vol_1h: float = 0.0  # 4-candle avg vol
    realized_vol_24h: float = 0.0  # 96-candle avg vol
    vol_regime: float = 0.0  # 1h vol / 24h vol

    # Volume
    volume_trend: float = 1.0  # SMA(vol,6) / SMA(vol,24)
    volume_zscore: float = 0.0  # (vol - avg) / std

    # Time
    hour_of_day: int = 0
    day_of_week: int = 0
    minutes_to_15m_close: int = 0  # 0-14

    # Regime classification
    regime: str = "unknown"  # trending_up, trending_down, ranging, volatile

    # Market-implied
    kalshi_midpoint: float = 50.0
    polymarket_yes: float = 0.5
    macro_24h_change: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def feature_names(self) -> list[str]:
        return list(self.to_dict().keys())

    @property
    def feature_vector(self) -> list[float]:
        """Numeric-only feature vector for ML models."""
        d = self.to_dict()
        result = []
        for v in d.values():
            if isinstance(v, (int, float)):
                result.append(float(v))
            elif isinstance(v, str):
                # Encode regime as numeric
                regime_map = {
                    "trending_up": 1.0, "trending_down": -1.0,
                    "ranging": 0.0, "volatile": 2.0, "unknown": 0.0,
                }
                result.append(regime_map.get(v, 0.0))
        return result


@dataclass
class MicroFeatures:
    """Features computed from last 20 one-minute candles + live state."""
    # Short-term momentum
    return_1m: float = 0.0
    return_5m: float = 0.0
    return_15m: float = 0.0
    momentum_acceleration: float = 0.0  # recent vs earlier momentum

    # Volatility micro
    range_5m: float = 0.0  # avg high-low range over 5 candles
    range_expanding: float = 1.0  # recent range / earlier range
    volatility_spike: float = 0.0  # current vol / avg vol

    # Volume micro
    volume_spike: float = 1.0  # current volume / avg
    volume_direction: float = 0.0  # net buy vs sell pressure

    # Order book (from Kalshi/Exchange)
    book_imbalance: float = 0.5  # bid / (bid + ask)
    coinbase_spread: float = 0.0  # ask - bid normalized
    kalshi_midpoint_distance: float = 0.0  # (mid - 50) / 50

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def feature_vector(self) -> list[float]:
        return [float(v) for v in self.to_dict().values()]


@dataclass
class CrossAssetFeatures:
    """Features from BTC↔ETH relationships."""
    btc_eth_correlation_1h: float = 0.0  # rolling 4-candle correlation
    btc_eth_correlation_24h: float = 0.0  # rolling 96-candle correlation
    btc_lead_eth: bool = False  # did BTC move first recently?
    eth_lead_btc: bool = False
    btc_regime: str = "unknown"
    eth_regime: str = "unknown"
    regime_disagreement: bool = False  # different regimes

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items()}
        d["btc_lead_eth"] = 1.0 if self.btc_lead_eth else 0.0
        d["eth_lead_btc"] = 1.0 if self.eth_lead_btc else 0.0
        d["regime_disagreement"] = 1.0 if self.regime_disagreement else 0.0
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def feature_vector(self) -> list[float]:
        return [float(v) for v in self.to_dict().values()]


# ---------------------------------------------------------------------------
# Indicator helpers (pure math, no dependencies beyond numpy)
# ---------------------------------------------------------------------------

def _sma(values: list[float], period: int) -> float | None:
    """Simple Moving Average of last `period` values."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> float | None:
    """Exponential Moving Average."""
    if not values:
        return None
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> float:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0  # neutral default

    gains = []
    losses = []
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _bollinger(closes: list[float], period: int = 20, num_std: float = 2.0):
    """Bollinger Bands position and width."""
    if len(closes) < period:
        return 0.5, 0.0
    window = closes[-period:]
    mid = sum(window) / period
    std = (sum((x - mid) ** 2 for x in window) / period) ** 0.5
    upper = mid + num_std * std
    lower = mid - num_std * std
    if upper == lower:
        return 0.5, 0.0
    pct = (closes[-1] - lower) / (upper - lower)
    width = (upper - lower) / mid if mid > 0 else 0.0
    return pct, width


def _atr(highs: list[float], lows: list[float], closes: list[float],
         period: int = 14) -> float:
    """Average True Range, normalized by price."""
    if len(closes) < period + 1:
        return 0.0
    true_ranges = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        c_prev = closes[i - 1]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        true_ranges.append(tr)
    avg_tr = sum(true_ranges) / period
    price = closes[-1]
    return avg_tr / price if price > 0 else 0.0


def _detect_regime(closes: list[float], highs: list[float],
                   lows: list[float]) -> str:
    """Classify market regime from 15m candle data."""
    if len(closes) < 24:
        return "unknown"

    # Recent 4 candles (1h) vs longer term
    recent_return = (closes[-1] - closes[-5]) / closes[-5] if len(closes) >= 5 else 0
    long_return = (closes[-1] - closes[-25]) / closes[-25] if len(closes) >= 25 else 0

    # Volatility: recent vs long-term
    recent_ranges = [highs[i] - lows[i] for i in range(-4, 0) if i + len(highs) >= 0]
    long_ranges = [highs[i] - lows[i] for i in range(-24, 0) if i + len(highs) >= 0]

    if not recent_ranges or not long_ranges:
        return "unknown"

    recent_avg_range = sum(recent_ranges) / len(recent_ranges)
    long_avg_range = sum(long_ranges) / len(long_ranges)
    vol_ratio = recent_avg_range / long_avg_range if long_avg_range > 0 else 1.0

    if vol_ratio > 1.5:
        return "volatile"
    if abs(recent_return) > 0.003:  # >0.3% in 1h
        return "trending_up" if recent_return > 0 else "trending_down"
    if abs(long_return) > 0.005:  # >0.5% in 6h
        return "trending_up" if long_return > 0 else "trending_down"
    return "ranging"


def _correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x = x[-n:]
    y = y[-n:]
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / n
    sx = (sum((xi - mx) ** 2 for xi in x) / n) ** 0.5
    sy = (sum((yi - my) ** 2 for yi in y) / n) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


# ---------------------------------------------------------------------------
# FeatureEngine
# ---------------------------------------------------------------------------

class FeatureEngine:
    """Computes all features from persisted candle data."""

    def __init__(self, store: CandlePersistenceStore):
        self._store = store

    # -------------------------------------------------------------------
    # Macro features (from 15m candles)
    # -------------------------------------------------------------------

    async def compute_macro_features(
        self,
        asset: str,
        source: str = "binance",
        kalshi_midpoint: float = 50.0,
        polymarket_yes: float = 0.5,
        macro_24h_change: float = 0.0,
    ) -> MacroFeatures:
        """Compute macro features from stored 15m candles."""
        candles = await self._store.get_candles(asset, source, "15m", limit=288)

        if len(candles) < 5:
            logger.warning("Insufficient 15m candles for %s: %d", asset, len(candles))
            return MacroFeatures(kalshi_midpoint=kalshi_midpoint)

        closes = [c["close"] for c in candles]
        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]

        # Streak detection
        streak_len = 0
        streak_dir = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] > closes[i - 1]:
                if streak_dir == 0:
                    streak_dir = 1
                elif streak_dir == 1:
                    streak_len += 1
                else:
                    break
            elif closes[i] < closes[i - 1]:
                if streak_dir == 0:
                    streak_dir = -1
                elif streak_dir == -1:
                    streak_len += 1
                else:
                    break
            else:
                break

        # Body ratio
        body_ratios = []
        for i in range(len(closes)):
            rng = highs[i] - lows[i]
            if rng > 0:
                body_ratios.append(abs(closes[i] - opens[i]) / rng)
            else:
                body_ratios.append(0.0)

        # Returns at multiple horizons
        def _ret(n):
            if len(closes) > n and closes[-n - 1] > 0:
                return (closes[-1] / closes[-n - 1] - 1) * 100
            return 0.0

        # SMAs
        sma_24 = _sma(closes, 24)
        sma_96 = _sma(closes, 96)

        # Technical indicators
        rsi7 = _rsi(closes, 7)
        rsi14 = _rsi(closes, 14)
        bb_pct, bb_width = _bollinger(closes, 20)
        atr = _atr(highs, lows, closes, 14)

        # Volatility
        def _realized_vol(window):
            if len(closes) < window + 1:
                return 0.0
            rets = [(closes[i] / closes[i - 1] - 1)
                    for i in range(-window, 0) if closes[i - 1] > 0]
            if not rets:
                return 0.0
            return (sum(r ** 2 for r in rets) / len(rets)) ** 0.5

        # Volume trend
        vol_sma_6 = _sma(volumes, 6)
        vol_sma_24 = _sma(volumes, 24)

        # Time features
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        hour = now.hour
        dow = now.weekday()
        minutes_to_close = 15 - (now.minute % 15)

        # Regime
        regime = _detect_regime(closes, highs, lows)

        return MacroFeatures(
            streak_length=streak_len,
            streak_direction=streak_dir,
            body_ratio=body_ratios[-1] if body_ratios else 0.0,
            body_ratio_sma_6=_sma(body_ratios, 6) or 0.0,
            return_1=_ret(1),
            return_4=_ret(4),
            return_16=_ret(16),
            return_96=_ret(96),
            price_vs_sma_24=(closes[-1] / sma_24 - 1) if sma_24 and sma_24 > 0 else 0.0,
            price_vs_sma_96=(closes[-1] / sma_96 - 1) if sma_96 and sma_96 > 0 else 0.0,
            sma_24_vs_sma_96=(sma_24 / sma_96 - 1) if sma_24 and sma_96 and sma_96 > 0 else 0.0,
            rsi_7=rsi7,
            rsi_14=rsi14,
            bollinger_pct=bb_pct,
            bollinger_width=bb_width,
            atr_14=atr,
            realized_vol_15m=_realized_vol(1),
            realized_vol_1h=_realized_vol(4),
            realized_vol_24h=_realized_vol(96),
            vol_regime=(_realized_vol(4) / _realized_vol(96))
                       if _realized_vol(96) > 0 else 1.0,
            volume_trend=(vol_sma_6 / vol_sma_24)
                         if vol_sma_6 and vol_sma_24 and vol_sma_24 > 0 else 1.0,
            volume_zscore=0.0,  # computed below
            hour_of_day=hour,
            day_of_week=dow,
            minutes_to_15m_close=minutes_to_close,
            regime=regime,
            kalshi_midpoint=kalshi_midpoint,
            polymarket_yes=polymarket_yes,
            macro_24h_change=macro_24h_change,
        )

    # -------------------------------------------------------------------
    # Micro features (from 1m candles + live state)
    # -------------------------------------------------------------------

    async def compute_micro_features(
        self,
        asset: str,
        source: str = "binance",
        book_imbalance: float = 0.5,
        coinbase_spread: float = 0.0,
        kalshi_midpoint: float = 50.0,
    ) -> MicroFeatures:
        """Compute micro features from stored 1m candles."""
        candles = await self._store.get_candles(asset, source, "1m", limit=30)

        if len(candles) < 5:
            logger.warning("Insufficient 1m candles for %s: %d", asset, len(candles))
            return MicroFeatures(
                book_imbalance=book_imbalance,
                coinbase_spread=coinbase_spread,
                kalshi_midpoint_distance=(kalshi_midpoint - 50) / 50,
            )

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]

        # Returns
        def _ret(n):
            if len(closes) > n and closes[-n - 1] > 0:
                return (closes[-1] / closes[-n - 1] - 1) * 100
            return 0.0

        # Momentum acceleration
        recent_5m = _ret(5)
        earlier_5m = (_ret(10) - _ret(5)) if len(closes) > 10 else 0.0

        # Range metrics
        recent_ranges = [highs[i] - lows[i] for i in range(-5, 0)]
        earlier_ranges = [highs[i] - lows[i] for i in range(-10, -5)] if len(highs) >= 10 else recent_ranges
        avg_recent_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else 0
        avg_earlier_range = sum(earlier_ranges) / len(earlier_ranges) if earlier_ranges else 1

        # Volatility spike
        current_range = highs[-1] - lows[-1] if highs and lows else 0
        avg_range = sum(highs[i] - lows[i] for i in range(-20, 0)) / 20 if len(highs) >= 20 else avg_recent_range
        vol_spike = current_range / avg_range if avg_range > 0 else 1.0

        # Volume spike
        vol_now = volumes[-1] if volumes else 0
        vol_avg = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 1
        vol_spike_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

        return MicroFeatures(
            return_1m=_ret(1),
            return_5m=_ret(5),
            return_15m=_ret(15),
            momentum_acceleration=recent_5m - earlier_5m,
            range_5m=avg_recent_range / closes[-1] if closes and closes[-1] > 0 else 0,
            range_expanding=avg_recent_range / avg_earlier_range if avg_earlier_range > 0 else 1.0,
            volatility_spike=vol_spike,
            volume_spike=vol_spike_ratio,
            volume_direction=0.0,
            book_imbalance=book_imbalance,
            coinbase_spread=coinbase_spread,
            kalshi_midpoint_distance=(kalshi_midpoint - 50) / 50,
        )

    # -------------------------------------------------------------------
    # Cross-asset features
    # -------------------------------------------------------------------

    async def compute_cross_asset_features(
        self,
        btc_source: str = "binance",
        eth_source: str = "binance",
    ) -> CrossAssetFeatures:
        """Compute cross-asset features between BTC and ETH."""
        btc_15m = await self._store.get_candles("BTC", btc_source, "15m", limit=96)
        eth_15m = await self._store.get_candles("ETH", eth_source, "15m", limit=96)

        if len(btc_15m) < 5 or len(eth_15m) < 5:
            return CrossAssetFeatures()

        btc_closes = [c["close"] for c in btc_15m]
        eth_closes = [c["close"] for c in eth_15m]

        btc_returns = [(btc_closes[i] / btc_closes[i - 1] - 1)
                       for i in range(1, len(btc_closes))]
        eth_returns = [(eth_closes[i] / eth_closes[i - 1] - 1)
                       for i in range(1, len(eth_closes))]

        # Correlation
        corr_1h = _correlation(btc_returns[-4:], eth_returns[-4:])
        corr_24h = _correlation(btc_returns[-96:], eth_returns[-96:])

        # Lead-lag: did one asset move first in the last 30 min (2 candles)?
        btc_lead = False
        eth_lead = False
        if len(btc_returns) >= 2 and len(eth_returns) >= 2:
            btc_recent = sum(abs(r) for r in btc_returns[-2:])
            eth_recent = sum(abs(r) for r in eth_returns[-2:])
            btc_last_direction = btc_returns[-1]
            eth_last_direction = eth_returns[-1]
            # If BTC moved more aggressively, it likely led
            if btc_recent > eth_recent * 1.2 and btc_last_direction != 0:
                btc_lead = True
            elif eth_recent > btc_recent * 1.2 and eth_last_direction != 0:
                eth_lead = True

        # Regime per asset
        btc_regime = _detect_regime(
            btc_closes,
            [c["high"] for c in btc_15m],
            [c["low"] for c in btc_15m],
        )
        eth_regime = _detect_regime(
            eth_closes,
            [c["high"] for c in eth_15m],
            [c["low"] for c in eth_15m],
        )

        return CrossAssetFeatures(
            btc_eth_correlation_1h=corr_1h,
            btc_eth_correlation_24h=corr_24h,
            btc_lead_eth=btc_lead,
            eth_lead_btc=eth_lead,
            btc_regime=btc_regime,
            eth_regime=eth_regime,
            regime_disagreement=(btc_regime != eth_regime),
        )

    # -------------------------------------------------------------------
    # Combined feature vector
    # -------------------------------------------------------------------

    async def compute_all_features(
        self,
        asset: str,
        source: str = "binance",
        kalshi_midpoint: float = 50.0,
        polymarket_yes: float = 0.5,
        macro_24h_change: float = 0.0,
        book_imbalance: float = 0.5,
        coinbase_spread: float = 0.0,
    ) -> dict:
        """Compute all feature tiers and return combined dict."""
        macro = await self.compute_macro_features(
            asset, source, kalshi_midpoint, polymarket_yes, macro_24h_change
        )
        micro = await self.compute_micro_features(
            asset, source, book_imbalance, coinbase_spread, kalshi_midpoint
        )
        cross = await self.compute_cross_asset_features(source, source)

        combined = {}
        combined.update(macro.to_dict())
        combined.update(micro.to_dict())
        combined.update(cross.to_dict())
        return combined
