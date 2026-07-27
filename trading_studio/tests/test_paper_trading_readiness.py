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
        vessel_state_getter=lambda: "full_stop"
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
    mock_snapshot = SimpleNamespace(
        snapshot_version=100,
        created_ts=datetime.now(UTC),
        kalshi_midpoint_cents=None
    )

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
        vessel_state_getter=lambda: "full_forward"
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
            return SimpleNamespace(yes_probability=0.55, confidence=0.8) # 55% prob vs 55c midpoint = 0 edge

    scoring_engine.get_macro_model.return_value = FakeModel()

    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)
    assert engine.recent_decisions[-1].skip_reason == "edge_below_threshold"

    # Path 4: One trade per window (force a successful trade, then re-evaluate)
    class FakeModelHighEdge:
        def predict(self, features):
            return SimpleNamespace(yes_probability=0.85, confidence=0.8) # 85% prob vs 55c midpoint = 30% edge

    scoring_engine.get_macro_model.return_value = FakeModelHighEdge()

    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)
    assert engine.recent_decisions[-1].traded is True

    # Second evaluation in same window
    await engine._evaluate_asset("BTC", no_op_compute, dummy_agg)
    assert engine.recent_decisions[-1].skip_reason == "window_already_traded"

    paper_venue.close()
