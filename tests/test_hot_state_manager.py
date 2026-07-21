"""Tests for the hot state manager — thread-safe market data snapshot."""
import threading
import time

from arbitr8der.market_data.thread_safe_hot_state_manager import ThreadSafeHotStateManager, ImmutableHotSnapshot


class TestHotStateUpdates:
    """Update and snapshot tests."""

    def test_initial_snapshot_is_empty(self):
        hot_state_manager = ThreadSafeHotStateManager()
        snap = hot_state_manager.snapshot()
        assert snap.generation == 0
        assert snap.timestamp == 0.0
        assert len(snap.orderbooks) == 0
        assert len(snap.spot_prices) == 0

    def test_update_spot_price(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_spot_price("BTC", 112345.67)
        snap = hot_state_manager.snapshot()
        assert snap.spot_prices["BTC"] == 112345.67
        assert snap.generation == 1

    def test_update_orderbook(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_orderbook("KXBTC15M-25JUL211200", {
            "yes_best": 0.55,
            "no_best": 0.45,
            "spread": 0.10,
        })
        snap = hot_state_manager.snapshot()
        assert snap.orderbooks["KXBTC15M-25JUL211200"]["yes_best"] == 0.55

    def test_update_sentiment(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_sentiment("BTC", 0.72)
        snap = hot_state_manager.snapshot()
        assert snap.sentiment["BTC"] == 0.72

    def test_update_macro(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_macro({"BTC_MCAP": "2.1T", "BTC_24H_CHANGE": "+3.2%"})
        snap = hot_state_manager.snapshot()
        assert snap.macro["BTC_MCAP"] == "2.1T"

    def test_update_stream_health(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_stream_health("binance_ws", True)
        hot_state_manager.update_stream_health("polymarket", False)
        snap = hot_state_manager.snapshot()
        assert snap.stream_health["binance_ws"] is True
        assert snap.stream_health["polymarket"] is False

    def test_update_active_ticker(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_active_ticker("BTC", "KXBTC15M-25JUL211200")
        snap = hot_state_manager.snapshot()
        assert snap.active_tickers["BTC"] == "KXBTC15M-25JUL211200"

    def test_update_latency(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_latency("binance_received_ms", 5.2)
        snap = hot_state_manager.snapshot()
        assert snap.latency["binance_received_ms"] == 5.2


class TestHotStateGenerations:
    """Generation counter and snapshot freshness tests."""

    def test_generation_increments_on_update(self):
        hot_state_manager = ThreadSafeHotStateManager()
        assert hot_state_manager.generation == 0
        hot_state_manager.update_spot_price("BTC", 100)
        assert hot_state_manager.generation == 1
        hot_state_manager.update_spot_price("ETH", 50)
        assert hot_state_manager.generation == 2

    def test_snapshot_is_immutable(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_spot_price("BTC", 100)
        snap1 = hot_state_manager.snapshot()
        hot_state_manager.update_spot_price("BTC", 200)
        snap2 = hot_state_manager.snapshot()
        assert snap1.spot_prices["BTC"] == 100  # Old snapshot unchanged
        assert snap2.spot_prices["BTC"] == 200  # New snapshot has new data

    def test_snapshot_to_dict(self):
        hot_state_manager = ThreadSafeHotStateManager()
        hot_state_manager.update_spot_price("BTC", 112000)
        snap = hot_state_manager.snapshot()
        d = snap.to_dict()
        assert d["spot_prices"]["BTC"] == 112000
        assert "generation" in d
        assert "timestamp" in d


class TestImmutableHotSnapshotStaleness:
    """Snapshot staleness detection tests."""

    def test_fresh_snapshot_not_stale(self):
        snap = ImmutableHotSnapshot(
            generation=1,
            timestamp=time.time(),
        )
        assert not snap.is_stale(max_age_seconds=10.0)

    def test_old_snapshot_is_stale(self):
        snap = ImmutableHotSnapshot(
            generation=1,
            timestamp=time.time() - 30.0,
        )
        assert snap.is_stale(max_age_seconds=10.0)


class TestHotStateConcurrency:
    """Thread safety tests."""

    def test_concurrent_updates_dont_crash(self):
        hot_state_manager = ThreadSafeHotStateManager()
        errors = []

        def updater(asset, price):
            try:
                for i in range(100):
                    hot_state_manager.update_spot_price(asset, price + i)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=updater, args=("BTC", 100000)),
            threading.Thread(target=updater, args=("ETH", 3000)),
            threading.Thread(target=updater, args=("SOL", 150)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        snap = hot_state_manager.snapshot()
        assert snap.generation == 300  # 3 threads * 100 updates each
