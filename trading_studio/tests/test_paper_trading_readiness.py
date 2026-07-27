from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from arbitr8der_package.execution.auto_trading_engine import AutoTradingEngine
from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
from arbitr8der_package.risk.risk_controls_module import OrderIntent, RiskBlockReason, RiskController


def test_order_intent_price_aware_risk():
    """Test that OrderIntent midpoint_cents correctly affects risk calculation."""
    # Base controller with $10 balance
    risk = RiskController(wallet_mode="paper")
    risk._balance = 10.0  # Force $10 balance

    # 1. Without midpoint_cents, falls back to 50c
    # 20 contracts @ 50c = $10.00 (Passes)
    intent1 = OrderIntent(asset="BTC", side="yes", contracts=20)
    verdict1 = risk.check(intent1, vessel_state="full_forward")
    assert verdict1.passed is True

    # 2. With midpoint_cents = 70c
    # 20 contracts @ 70c = $14.00 (Fails > $10)
    intent2 = OrderIntent(asset="BTC", side="yes", contracts=20, midpoint_cents=70.0)
    verdict2 = risk.check(intent2, vessel_state="full_forward")
    assert verdict2.passed is False
    assert verdict2.block_reason == RiskBlockReason.INSUFFICIENT_BALANCE
    assert "exceeds balance $10.00" in verdict2.block_detail

    # 3. Limit_cents takes priority over midpoint_cents
    # Limit = 40c -> 20 contracts @ 40c = $8.00 (Passes)
    intent3 = OrderIntent(asset="BTC", side="yes", contracts=20, limit_cents=40, midpoint_cents=70.0)
    verdict3 = risk.check(intent3, vessel_state="full_forward")
    assert verdict3.passed is True


def test_kill_switches():
    """Test that risk limits trigger correct blocks."""
    risk = RiskController(wallet_mode="paper", session_loss_cap=100.0)

    intent = OrderIntent(asset="BTC", side="yes", contracts=2)

    # Force session loss cap
    risk._session_pnl = -150.0
    verdict = risk.check(intent, vessel_state="full_forward")
    assert verdict.passed is False
    assert verdict.block_reason == RiskBlockReason.SESSION_LOSS_CAP

    # Reset and test daily loss cap
    risk._session_pnl = 0.0
    risk._daily_pnl = -600.0
    verdict2 = risk.check(intent, vessel_state="full_forward")
    assert verdict2.passed is False
    assert verdict2.block_reason == RiskBlockReason.DAILY_LOSS_CAP


@pytest.mark.asyncio
async def test_auto_trade_lifecycle_commands(tmp_path):
    """Test enable/disable/status lifecycle of AutoTradingEngine."""
    candle_store = MagicMock()
    scoring_engine = MagicMock()
    model_run_store = MagicMock()
    paper_venue = PaperVenueAdapter(db_path=tmp_path / "paper_wallet.db")
    risk_controller = RiskController()

    engine = AutoTradingEngine(
        candle_store=candle_store,
        scoring_engine=scoring_engine,
        model_run_store=model_run_store,
        snapshot_getter=lambda a: None,
        market_ticker_getter=lambda a: None,
        paper_venue=paper_venue,
        risk_controller=risk_controller,
        vessel_state_getter=lambda: "full_stop",
    )

    assert engine.enabled is False
    assert engine.get_status()["enabled"] is False

    engine.enable()
    assert engine.enabled is True
    assert engine.get_status()["enabled"] is True

    engine.disable()
    assert engine.enabled is False

    paper_venue.close()


@pytest.mark.asyncio
async def test_auto_trade_skip_paths(tmp_path):
    """Test auto-trade edge cases where trades should be skipped."""
    candle_store = AsyncMock()
    # Mock no candles
    candle_store.get_candles.return_value = []

    scoring_engine = MagicMock()
    model_run_store = AsyncMock()
    paper_venue = PaperVenueAdapter(db_path=tmp_path / "paper_wallet.db")
    risk_controller = RiskController()

    # State tracking
    mock_snapshot = SimpleNamespace(snapshot_version=100, created_ts=datetime.now(UTC), kalshi_midpoint_cents=None)

    def snapshot_getter(asset):
        if asset == "BTC":
            return mock_snapshot
        return None

    engine = AutoTradingEngine(
        candle_store=candle_store,
        scoring_engine=scoring_engine,
        model_run_store=model_run_store,
        snapshot_getter=snapshot_getter,
        market_ticker_getter=lambda a: "KXBTC",
        paper_venue=paper_venue,
        risk_controller=risk_controller,
        vessel_state_getter=lambda: "full_forward",
    )

    def no_op_compute(candles, window_ts):
        return {}

    def no_op_agg(candles):
        return []

    # Path 1: No kalshi_midpoint_cents
    await engine._evaluate_asset("BTC", no_op_compute, no_op_agg)
    assert engine.recent_decisions[-1].skip_reason == "no_kalshi_midpoint"

    # Path 2: Has midpoint, but no candles
    mock_snapshot.kalshi_midpoint_cents = 55.0
    await engine._evaluate_asset("BTC", no_op_compute, no_op_agg)
    assert engine.recent_decisions[-1].skip_reason == "no_candles"

    # Path 3: Candles available, but below threshold
    candle_store.get_candles.return_value = [{"close": 100}] * 10

    def dummy_agg(candles):
        return [{"close": 100}] * 5

    class FakeModel:
        def predict(self, features):
            return SimpleNamespace(yes_probability=0.55, confidence=0.8)  # 55% prob vs 55c midpoint = 0 edge

    scoring_engine.get_macro_model.return_value = FakeModel()

    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)
    assert engine.recent_decisions[-1].skip_reason == "edge_below_threshold"

    # Path 4: One trade per window (force a successful trade, then re-evaluate)
    class FakeModelHighEdge:
        def predict(self, features):
            return SimpleNamespace(yes_probability=0.85, confidence=0.8)  # 85% prob vs 55c midpoint = 30% edge

    scoring_engine.get_macro_model.return_value = FakeModelHighEdge()

    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)
    assert engine.recent_decisions[-1].traded is True

    # Second evaluation in same window
    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)
    assert engine.recent_decisions[-1].skip_reason == "window_already_traded"

    paper_venue.close()


@pytest.mark.asyncio
async def test_auto_settlement(tmp_path):
    """Test automated paper position settlement on expiration."""
    # 1. Initialize adapter
    adapter = PaperVenueAdapter(db_path=tmp_path / "paper_wallet.db", initial_balance=100.0)

    # 2. Place an order on an expired ticker
    # Target ticker has open time: 2026-07-26 12:00:00 Eastern Time (timestamp: 1785081600)
    # Using format: KXBTC15M-26JUL26T1200
    ticker = "KXBTC15M-26JUL26T1200"
    order = adapter.submit_order(
        asset="BTC",
        side="yes",
        contracts=10,
        ticker=ticker,
        midpoint_cents=40.0,
    )
    assert order.status == "filled"
    assert len(adapter.get_open_positions()) == 1

    # 3. Setup mock candle store with outcomes DB
    mock_db = AsyncMock()
    mock_cursor = AsyncMock()
    # Mock return value of outcomes query: direction = "UP" (YES wins)
    mock_cursor.fetchone.return_value = ("UP",)
    mock_db.execute.return_value = mock_cursor

    class FakeCandleStore:
        def __init__(self):
            self._db = mock_db

    candle_store = FakeCandleStore()

    # 4. Settle expired positions
    # Ticker has window open 1785081600, expires at 1785081600 + 900.
    # We mock time.time to be past expiration.
    from unittest.mock import patch

    with patch("time.time", return_value=1785081600 + 1000):
        settled_orders = await adapter.settle_expired_positions(candle_store=candle_store)

    assert len(settled_orders) == 1
    assert settled_orders[0].status == "settled"
    assert settled_orders[0].outcome == 1  # YES won because direction is "UP"
    # Payout is 100c ($1.00) per contract. We bought 10 contracts @ 40c ($4.00 total cost).
    # PnL should be $6.00. Balance should be initial $100.00 - $4.00 cost + $10.00 payout = $106.00.
    assert settled_orders[0].pnl == 6.0
    assert adapter.get_wallet().balance == 106.0
    assert len(adapter.get_open_positions()) == 0

    adapter.close()


@pytest.mark.asyncio
async def test_auto_settlement_rest_fallback(tmp_path):
    """Test automated paper position settlement falling back to Kalshi REST detail."""
    adapter = PaperVenueAdapter(db_path=tmp_path / "paper_wallet.db", initial_balance=100.0)

    ticker = "KXBTC15M-26JUL26T1200"
    order = adapter.submit_order(
        asset="BTC",
        side="no",  # We buy NO contracts @ 30c
        contracts=10,
        ticker=ticker,
        midpoint_cents=70.0,  # YES midpoint is 70c, so NO costs 30c
    )
    assert order.status == "filled"

    # Mock discovery client returning settled market with result "yes" (YES wins, so NO loses)
    mock_discovery = AsyncMock()
    mock_detail = MagicMock()
    mock_detail.status = "settled"
    mock_detail.reference_price = 60000.0
    mock_detail.raw = {"result": "yes"}
    mock_discovery.get_market_detail.return_value = mock_detail



    from unittest.mock import patch

    with patch("time.time", return_value=1785081600 + 1000):
        settled_orders = await adapter.settle_expired_positions(
            candle_store=None,
            discovery_client=mock_discovery,
        )

    assert len(settled_orders) == 1
    assert settled_orders[0].status == "settled"
    assert settled_orders[0].outcome == 1  # YES won
    # NO lost. We spent 10 contracts * 30c = $3.00. Balance should be $100.00 - $3.00 = $97.00.
    assert settled_orders[0].pnl == -3.0
    assert adapter.get_wallet().balance == 97.0
    assert len(adapter.get_open_positions()) == 0

    adapter.close()


@pytest.mark.asyncio
async def test_patient_limit_order_execution(tmp_path):
    """Test patient limit order submission and asynchronous filling."""
    # 1. Initialize adapter and engine with patient execution enabled
    adapter = PaperVenueAdapter(db_path=tmp_path / "paper_wallet.db", initial_balance=100.0)

    scoring_engine = MagicMock()
    model_run_store = AsyncMock()
    risk_controller = MagicMock()
    risk_verdict = MagicMock()
    risk_verdict.passed = True
    risk_controller.check.return_value = risk_verdict

    # Mock snapshots and ticker getters
    mock_snapshot_getter = MagicMock()
    # YES midpoint is 50c
    from datetime import datetime, timezone
    snap = SimpleNamespace(
        snapshot_version=10,
        kalshi_midpoint_cents=50.0,
        spot_avg_usd=60000.0,
        spot_disagreement_pct=0.01,
        created_ts=datetime.now(timezone.utc),
    )
    mock_snapshot_getter.return_value = snap

    mock_market_ticker_getter = MagicMock()
    mock_market_ticker_getter.return_value = "KXBTC15M-TEST"

    # Instantiate engine with patient_execution=True and 3c discount
    engine = AutoTradingEngine(
        candle_store=AsyncMock(),
        scoring_engine=scoring_engine,
        model_run_store=model_run_store,
        snapshot_getter=mock_snapshot_getter,
        market_ticker_getter=mock_market_ticker_getter,
        paper_venue=adapter,
        risk_controller=risk_controller,
        discovery_client=AsyncMock(),
        vessel_state_getter=lambda: "full_forward",
        patient_execution=True,
        limit_discount_cents=3,
        edge_threshold_pct=2.0,
    )

    # Mock high edge model prediction
    class FakeHighEdgeModel:
        def predict(self, features):
            return SimpleNamespace(yes_probability=0.75, confidence=0.8) # 75% YES prob vs 50c mid = 25% edge

    scoring_engine.get_macro_model.return_value = FakeHighEdgeModel()

    # Aggregator and feature extraction mocks
    no_op_compute = lambda candles, window_ts: {}
    dummy_agg = lambda candles: [{"close": 100}] * 5

    # 2. Evaluate asset - should submit a limit order at a discount
    # YES midpoint is 50c, discount is 3c. Limit price should be 50 - 3 = 47c.
    # Current midpoint (50c) is higher than limit (47c), so order stays pending.
    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)

    pending = adapter.get_pending_orders()
    assert len(pending) == 1
    assert pending[0].limit_cents == 47
    assert pending[0].status == "pending"
    assert engine._skip_count == 1
    assert engine._trade_count == 0

    # 3. Simulate new market data arriving: midpoint drops to 45c (<= 47c limit)
    # Call _evaluate_all_assets which runs update_pending_orders
    # Midpoint 45c is better than or equal to 47c limit, so it should fill!
    snap.kalshi_midpoint_cents = 45.0

    await engine._evaluate_all_assets()

    pending_after = adapter.get_pending_orders()
    assert len(pending_after) == 0

    filled = adapter.get_filled_orders()
    assert len(filled) == 1
    assert filled[0].status == "filled"
    assert filled[0].fill_price_cents == 45.0  # Fills at the better market price (midpoint)
    assert engine._trade_count == 1
    assert engine._skip_count == 0  # skip_count decremented!

    adapter.close()
