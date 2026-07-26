from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest


class FakeScoringEngine:
    def __init__(self, macro_model=None, micro_model=None) -> None:
        self._macro_model = macro_model
        self._micro_model = micro_model

    def get_macro_model(self, asset: str):
        return self._macro_model

    def get_micro_model(self, asset: str):
        return self._micro_model


class FakeModelRunStore:
    def __init__(self) -> None:
        self.recorded_predictions: list[dict[str, object]] = []

    async def record_prediction(
        self,
        model_name: str,
        asset: str,
        window_open: float,
        yes_probability: float,
        confidence: float,
        features_json: str | None = None,
    ) -> int:
        self.recorded_predictions.append(
            {
                "model_name": model_name,
                "asset": asset,
                "window_open": window_open,
                "yes_probability": yes_probability,
                "confidence": confidence,
                "features_json": features_json,
            }
        )
        return len(self.recorded_predictions)


class FakeMacroModel:
    def predict(self, features: dict[str, object]):
        return SimpleNamespace(yes_probability=0.82, confidence=0.77)


class FakeCandleStore:
    def __init__(self, candles: list[dict[str, object]]) -> None:
        self._candles = candles

    async def get_candles(self, asset: str, source: str, interval: str, limit: int = 5000):
        return list(self._candles)


def _build_one_minute_candle_series() -> list[dict[str, object]]:
    boundary = 1700000100.0
    candles: list[dict[str, object]] = []
    for offset in range(15):
        candles.append(
            {
                "asset": "BTC",
                "source": "binance",
                "interval": "1m",
                "open_time": boundary + offset * 60,
                "open": 68000.0,
                "high": 68010.0,
                "low": 67990.0,
                "close": 68005.0,
                "volume": 1.0,
                "quote_volume": 68000.0,
                "trades": 10,
            }
        )
    return candles


def test_auto_trader_uses_snapshot_midpoint_for_edge(monkeypatch, tmp_path):
    from arbitr8der_package.execution.auto_trading_engine import AutoTradingEngine
    from arbitr8der_package.execution.paper_venue_adapter import PaperVenueAdapter
    from arbitr8der_package.risk.risk_controls_module import RiskController

    fake_backtest_module = ModuleType("arbitr8der_package.prediction.backtest_engine")
    fake_backtest_module.aggregate_1m_to_15m_candles = lambda candles: [
        {
            "asset": "BTC",
            "source": "binance",
            "interval": "15m",
            "open_time": 1700000100.0 + offset * 900,
            "open": 68000.0 + offset,
            "high": 68010.0 + offset,
            "low": 67990.0 + offset,
            "close": 68005.0 + offset,
            "volume": 15.0,
            "quote_volume": 1020000.0,
            "trades": 150,
        }
        for offset in range(5)
    ]
    fake_backtest_module.compute_macro_features_from_candles = lambda candles, window_ts: {
        "regime": "trending_up",
        "rsi_7": 63.0,
        "return_4": 1.25,
    }
    monkeypatch.setitem(sys.modules, "arbitr8der_package.prediction.backtest_engine", fake_backtest_module)

    async def _run_test() -> None:
        snapshot = SimpleNamespace(
            snapshot_version=42,
            created_ts=datetime.now(timezone.utc),
            kalshi_midpoint_cents=40,
        )
        candles = _build_one_minute_candle_series()
        candle_store = FakeCandleStore(candles)
        scoring_engine = FakeScoringEngine(macro_model=FakeMacroModel())
        model_run_store = FakeModelRunStore()
        paper_venue = PaperVenueAdapter(db_path=tmp_path / "paper_wallet.db")
        risk_controller = RiskController(wallet_mode="paper")

        engine = AutoTradingEngine(
            candle_store=candle_store,
            scoring_engine=scoring_engine,
            model_run_store=model_run_store,
            snapshot_getter=lambda asset: snapshot if asset == "BTC" else None,
            market_ticker_getter=lambda asset: "KXBTC15M-TEST" if asset == "BTC" else None,
            paper_venue=paper_venue,
            risk_controller=risk_controller,
            vessel_state_getter=lambda: "full_forward",
            edge_threshold_pct=2.0,
            contracts_per_trade=2,
        )

        await engine._evaluate_asset(  # noqa: SLF001 - direct regression coverage
            "BTC",
            fake_backtest_module.compute_macro_features_from_candles,
            fake_backtest_module.aggregate_1m_to_15m_candles,
        )

        assert engine.trade_count == 1
        assert engine.skip_count == 0
        assert engine.recent_decisions[-1].traded is True
        assert engine.recent_decisions[-1].market_ticker == "KXBTC15M-TEST"
        assert engine.recent_decisions[-1].snapshot_version == 42
        assert paper_venue.get_wallet().total_trades == 1
        assert len(paper_venue.get_open_positions()) == 1
        assert len(model_run_store.recorded_predictions) == 1

        paper_venue.close()

    asyncio.run(_run_test())
