"""Tests for feature_engine_v2 — macro, micro, and cross-asset feature computation.

Uses in-memory SQLite with synthetic candle data to validate all indicator
calculations and feature extraction paths.
"""

from __future__ import annotations

import math

import pytest
import pytest_asyncio

from arbitr8der_package.durable_storage.sqlite_database_engine_manager import (
    initialize_database,
)
from arbitr8der_package.durable_storage.candle_persistence_store import (
    CandlePersistenceStore,
)
from arbitr8der_package.prediction.feature_engine_v2 import (
    FeatureEngine,
    MacroFeatures,
    MicroFeatures,
    CrossAssetFeatures,
    _sma,
    _ema,
    _rsi,
    _bollinger,
    _atr,
    _detect_regime,
    _correlation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db():
    connection = await initialize_database(":memory:")
    yield connection
    await connection.close()


@pytest_asyncio.fixture
async def store(db):
    return CandlePersistenceStore(db)


@pytest_asyncio.fixture
async def engine(store):
    return FeatureEngine(store)


def _seed_15m_candles(asset="BTC", source="binance", count=100,
                       base_price=68000.0, volatility=0.002):
    """Generate synthetic 15m candles with realistic-looking price movement."""
    import random

    random.seed(42)
    rows = []
    price = base_price
    for i in range(count):
        open_p = price
        change = price * random.gauss(0, volatility)
        close = price + change
        high = max(open_p, close) + abs(change) * 0.5
        low = min(open_p, close) - abs(change) * 0.5
        volume = random.uniform(100, 500)
        rows.append({
            "asset": asset,
            "source": source,
            "interval": "15m",
            "open_time": 1700000000.0 + i * 900,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "quote_volume": volume * close,
            "trades": int(random.uniform(100, 1000)),
        })
        price = close
    return rows


def _seed_1m_candles(asset="BTC", source="binance", count=30,
                      base_price=68000.0, volatility=0.001):
    """Generate synthetic 1m candles."""
    import random

    random.seed(99)
    rows = []
    price = base_price
    for i in range(count):
        open_p = price
        change = price * random.gauss(0, volatility)
        close = price + change
        high = max(open_p, close) + abs(change) * 0.3
        low = min(open_p, close) - abs(change) * 0.3
        volume = random.uniform(10, 50)
        rows.append({
            "asset": asset,
            "source": source,
            "interval": "1m",
            "open_time": 1700000000.0 + i * 60,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "quote_volume": volume * close,
            "trades": int(random.uniform(10, 100)),
        })
        price = close
    return rows


# ---------------------------------------------------------------------------
# Indicator helper unit tests
# ---------------------------------------------------------------------------

class TestIndicatorHelpers:
    def test_sma_basic(self):
        assert _sma([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)

    def test_sma_insufficient_data(self):
        assert _sma([1, 2], 5) is None

    def test_ema_basic(self):
        values = [10.0] * 20
        result = _ema(values, 10)
        assert result is not None
        assert abs(result - 10.0) < 0.01

    def test_ema_empty(self):
        assert _ema([], 10) is None

    def test_rsi_all_gains(self):
        closes = [100 + i for i in range(20)]
        assert _rsi(closes, 14) == 100.0

    def test_rsi_all_losses(self):
        closes = [200 - i for i in range(20)]
        assert _rsi(closes, 14) == 0.0

    def test_rsi_insufficient_data(self):
        assert _rsi([100, 101], 14) == 50.0  # neutral default

    def test_bollinger_basic(self):
        closes = [100.0] * 25
        pct, width = _bollinger(closes, 20)
        assert pct == pytest.approx(0.5)
        assert width == pytest.approx(0.0)

    def test_bollinger_insufficient(self):
        pct, width = _bollinger([100.0] * 10, 20)
        assert pct == 0.5
        assert width == 0.0

    def test_atr_basic(self):
        highs = [101.0] * 20
        lows = [99.0] * 20
        closes = [100.0] * 20
        result = _atr(highs, lows, closes, 14)
        assert result > 0
        assert result < 0.1  # normalized, should be small

    def test_detect_regime_insufficient(self):
        assert _detect_regime([100.0] * 10, [101.0] * 10, [99.0] * 10) == "unknown"

    def test_detect_regime_ranging(self):
        closes = [100.0] * 30
        highs = [100.5] * 30
        lows = [99.5] * 30
        assert _detect_regime(closes, highs, lows) == "ranging"

    def test_correlation_perfect(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert _correlation(x, y) == pytest.approx(1.0)

    def test_correlation_insufficient(self):
        assert _correlation([1.0], [2.0]) == 0.0


# ---------------------------------------------------------------------------
# Dataclass feature vector tests
# ---------------------------------------------------------------------------

class TestFeatureDataclasses:
    def test_macro_features_to_dict(self):
        f = MacroFeatures()
        d = f.to_dict()
        assert "streak_length" in d
        assert "rsi_7" in d
        assert "regime" in d
        assert len(d) == 29

    def test_macro_feature_vector_numeric(self):
        f = MacroFeatures(regime="trending_up")
        vec = f.feature_vector
        assert all(isinstance(v, float) for v in vec)
        assert len(vec) == 29

    def test_micro_features_to_dict(self):
        f = MicroFeatures()
        d = f.to_dict()
        assert "return_1m" in d
        assert "book_imbalance" in d
        assert len(d) == 12

    def test_cross_asset_features_to_dict(self):
        f = CrossAssetFeatures(btc_lead_eth=True, regime_disagreement=True)
        d = f.to_dict()
        assert d["btc_lead_eth"] == 1.0
        assert d["regime_disagreement"] == 1.0


# ---------------------------------------------------------------------------
# FeatureEngine: macro features
# ---------------------------------------------------------------------------

class TestFeatureEngineMacro:
    @pytest.mark.asyncio
    async def test_compute_macro_insufficient_candles(self, engine, store):
        """With fewer than 5 candles, returns defaults."""
        rows = _seed_15m_candles(count=3)
        await store.upsert_candles(rows)

        features = await engine.compute_macro_features("BTC")
        assert isinstance(features, MacroFeatures)
        assert features.kalshi_midpoint == 50.0  # default

    @pytest.mark.asyncio
    async def test_compute_macro_with_data(self, engine, store):
        """With 100 candles, produces valid non-default features."""
        rows = _seed_15m_candles(count=100)
        await store.upsert_candles(rows)

        features = await engine.compute_macro_features(
            "BTC", kalshi_midpoint=55.0
        )
        assert isinstance(features, MacroFeatures)
        assert features.kalshi_midpoint == 55.0
        # RSI should be computed (not default 50.0 necessarily)
        assert 0 <= features.rsi_7 <= 100
        assert 0 <= features.rsi_14 <= 100
        assert features.regime in ("trending_up", "trending_down", "ranging", "volatile", "unknown")

    @pytest.mark.asyncio
    async def test_compute_macro_full_288(self, engine, store):
        """With 288 candles (72h), all features should be fully populated."""
        rows = _seed_15m_candles(count=288)
        await store.upsert_candles(rows)

        features = await engine.compute_macro_features("BTC")
        assert features.return_96 != 0.0  # 96-candle return should exist
        assert features.realized_vol_24h > 0.0
        assert features.bollinger_width >= 0.0
        assert features.atr_14 > 0.0


# ---------------------------------------------------------------------------
# FeatureEngine: micro features
# ---------------------------------------------------------------------------

class TestFeatureEngineMicro:
    @pytest.mark.asyncio
    async def test_compute_micro_insufficient(self, engine, store):
        rows = _seed_1m_candles(count=3)
        await store.upsert_candles(rows)

        features = await engine.compute_micro_features("BTC")
        assert isinstance(features, MicroFeatures)
        assert features.book_imbalance == 0.5  # default

    @pytest.mark.asyncio
    async def test_compute_micro_with_data(self, engine, store):
        rows = _seed_1m_candles(count=30)
        await store.upsert_candles(rows)

        features = await engine.compute_micro_features(
            "BTC", book_imbalance=0.65, coinbase_spread=0.001
        )
        assert isinstance(features, MicroFeatures)
        assert features.book_imbalance == 0.65
        assert features.coinbase_spread == 0.001
        assert features.range_5m >= 0.0
        assert features.volume_spike > 0.0


# ---------------------------------------------------------------------------
# FeatureEngine: cross-asset features
# ---------------------------------------------------------------------------

class TestFeatureEngineCrossAsset:
    @pytest.mark.asyncio
    async def test_compute_cross_insufficient(self, engine, store):
        btc = _seed_15m_candles(asset="BTC", count=3)
        eth = _seed_15m_candles(asset="ETH", count=3, base_price=3500.0)
        await store.upsert_candles(btc + eth)

        features = await engine.compute_cross_asset_features()
        assert isinstance(features, CrossAssetFeatures)
        assert features.btc_regime == "unknown"

    @pytest.mark.asyncio
    async def test_compute_cross_with_data(self, engine, store):
        btc = _seed_15m_candles(asset="BTC", count=50)
        eth = _seed_15m_candles(asset="ETH", count=50, base_price=3500.0)
        await store.upsert_candles(btc + eth)

        features = await engine.compute_cross_asset_features()
        assert isinstance(features, CrossAssetFeatures)
        assert -1.0 <= features.btc_eth_correlation_1h <= 1.0
        assert -1.001 <= features.btc_eth_correlation_24h <= 1.001
        assert features.btc_regime in ("trending_up", "trending_down", "ranging", "volatile", "unknown")


# ---------------------------------------------------------------------------
# FeatureEngine: combined features
# ---------------------------------------------------------------------------

class TestFeatureEngineCombined:
    @pytest.mark.asyncio
    async def test_compute_all_features(self, engine, store):
        btc_15m = _seed_15m_candles(asset="BTC", count=100)
        btc_1m = _seed_1m_candles(asset="BTC", count=30)
        eth_15m = _seed_15m_candles(asset="ETH", count=50, base_price=3500.0)
        await store.upsert_candles(btc_15m + btc_1m + eth_15m)

        combined = await engine.compute_all_features(
            "BTC", kalshi_midpoint=55.0, book_imbalance=0.6
        )
        assert isinstance(combined, dict)
        # Should have keys from all three tiers
        assert "rsi_7" in combined  # macro
        assert "return_1m" in combined  # micro
        assert "btc_eth_correlation_1h" in combined  # cross-asset
        # Total features: 29 macro + 12 micro + 7 cross = 48
        assert len(combined) == 48
