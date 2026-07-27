"""Walk-forward backtest engine — trains models on sliding historical windows,
predicts forward, and compares to actual candle outcomes.

Usage:
    engine = WalkForwardBacktester(store, asset="BTC")
    result = await engine.run()
    result.print_summary()
"""

from __future__ import annotations

import datetime as _dt
import math
import time
from dataclasses import dataclass, field

from arbitr8der_package.config.structured_logging_configuration_module import get_logger
from arbitr8der_package.durable_storage.candle_persistence_store import CandlePersistenceStore
from arbitr8der_package.prediction.feature_engine_v2 import (
    _sma, _rsi, _bollinger, _atr, _detect_regime,
)
from arbitr8der_package.prediction.macro_prediction_model import (
    FrequencyLookupModel, LightGBMClassifier, MacroEnsemble,
)
from arbitr8der_package.prediction.micro_prediction_model import (
    MomentumLookupModel, LogisticRegressionClassifier, MicroEnsemble,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1m → 15m candle aggregation (pure function — no store access)
# ---------------------------------------------------------------------------

def aggregate_1m_to_15m_candles(one_minute_candles: list[dict]) -> list[dict]:
    """Aggregate 1m candles into 15m candles aligned to 900-second boundaries.

    Input: list of 1m candle dicts (any order) with open_time, open, high, low,
           close, volume, quote_volume, trades.
    Output: list of 15m candle dicts (oldest-first) with the same fields.
             Each 15m candle aggregates 10-15 1m candles from one 900s window.
    """
    if not one_minute_candles:
        return []

    # Group by 15m boundary
    windows: dict[int, list[dict]] = {}
    for c in one_minute_candles:
        boundary = int(c["open_time"] / 900) * 900
        if boundary not in windows:
            windows[boundary] = []
        windows[boundary].append(c)

    result = []
    for boundary in sorted(windows):
        candles = sorted(windows[boundary], key=lambda x: x["open_time"])
        if len(candles) < 3:
            continue  # skip sparse windows

        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        quote_volumes = [c.get("quote_volume") or 0.0 for c in candles]
        trades_list = [c.get("trades") or 0 for c in candles]

        result.append({
            "asset": candles[0]["asset"],
            "source": candles[0]["source"],
            "interval": "15m",
            "open_time": float(boundary),
            "open": opens[0],
            "high": max(highs),
            "low": min(lows),
            "close": closes[-1],
            "volume": sum(volumes),
            "quote_volume": sum(quote_volumes),
            "trades": sum(trades_list),
        })

    return result


# ---------------------------------------------------------------------------
# Feature computation helpers (pure functions — no store access)
# ---------------------------------------------------------------------------

def compute_macro_features_from_candles(
    candles: list[dict],
    window_ts: float | None = None,
) -> dict:
    """Compute macro feature dict from a list of 15m candles (oldest-first).

    `candles` should contain at least 5 entries; ideally 288+ for full features.
    `window_ts` is the open_time of the candle being predicted (used for time features).
    Returns a dict suitable for passing to MacroEnsemble.predict().
    """
    if len(candles) < 5:
        return _empty_macro_dict()

    closes = [c["close"] for c in candles]
    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    # Streak detection (most recent candles)
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

    # Body ratios
    body_ratios = []
    for i in range(len(closes)):
        rng = highs[i] - lows[i]
        body_ratios.append(abs(closes[i] - opens[i]) / rng if rng > 0 else 0.0)

    # Returns
    def _ret(n: int) -> float:
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

    # Realized volatility
    def _realized_vol(window: int) -> float:
        if len(closes) < window + 1:
            return 0.0
        rets = [
            (closes[i] / closes[i - 1] - 1)
            for i in range(-window, 0)
            if closes[i - 1] > 0
        ]
        if not rets:
            return 0.0
        return (sum(r ** 2 for r in rets) / len(rets)) ** 0.5

    vol_1h = _realized_vol(4)
    vol_24h = _realized_vol(96)

    # Volume trend
    vol_sma_6 = _sma(volumes, 6)
    vol_sma_24 = _sma(volumes, 24)

    # Time features from window timestamp
    if window_ts:
        dt = _dt.datetime.fromtimestamp(window_ts, tz=_dt.timezone.utc)
        hour = dt.hour
        dow = dt.weekday()
        minutes_to_close = 15 - (dt.minute % 15)
    else:
        now = _dt.datetime.now(_dt.timezone.utc)
        hour = now.hour
        dow = now.weekday()
        minutes_to_close = 15 - (now.minute % 15)

    regime = _detect_regime(closes, highs, lows)

    return {
        "streak_length": streak_len,
        "streak_direction": streak_dir,
        "body_ratio": body_ratios[-1] if body_ratios else 0.0,
        "body_ratio_sma_6": _sma(body_ratios, 6) or 0.0,
        "return_1": _ret(1),
        "return_4": _ret(4),
        "return_16": _ret(16),
        "return_96": _ret(96),
        "price_vs_sma_24": (closes[-1] / sma_24 - 1) if sma_24 and sma_24 > 0 else 0.0,
        "price_vs_sma_96": (closes[-1] / sma_96 - 1) if sma_96 and sma_96 > 0 else 0.0,
        "sma_24_vs_sma_96": (sma_24 / sma_96 - 1) if sma_24 and sma_96 and sma_96 > 0 else 0.0,
        "rsi_7": rsi7,
        "rsi_14": rsi14,
        "bollinger_pct": bb_pct,
        "bollinger_width": bb_width,
        "atr_14": atr,
        "realized_vol_15m": _realized_vol(1),
        "realized_vol_1h": vol_1h,
        "realized_vol_24h": vol_24h,
        "vol_regime": (vol_1h / vol_24h) if vol_24h > 0 else 1.0,
        "volume_trend": (vol_sma_6 / vol_sma_24) if vol_sma_6 and vol_sma_24 and vol_sma_24 > 0 else 1.0,
        "volume_zscore": 0.0,
        "hour_of_day": hour,
        "day_of_week": dow,
        "minutes_to_15m_close": minutes_to_close,
        "regime": regime,
        "kalshi_midpoint": 50.0,
        "polymarket_yes": 0.5,
        "macro_24h_change": 0.0,
    }


def _empty_macro_dict() -> dict:
    """Minimal default macro feature dict (model will guess ~50%)."""
    return {
        "streak_length": 0, "streak_direction": 0,
        "body_ratio": 0.0, "body_ratio_sma_6": 0.0,
        "return_1": 0.0, "return_4": 0.0, "return_16": 0.0, "return_96": 0.0,
        "price_vs_sma_24": 0.0, "price_vs_sma_96": 0.0, "sma_24_vs_sma_96": 0.0,
        "rsi_7": 50.0, "rsi_14": 50.0,
        "bollinger_pct": 0.5, "bollinger_width": 0.0, "atr_14": 0.0,
        "realized_vol_15m": 0.0, "realized_vol_1h": 0.0, "realized_vol_24h": 0.0,
        "vol_regime": 1.0, "volume_trend": 1.0, "volume_zscore": 0.0,
        "hour_of_day": 0, "day_of_week": 0, "minutes_to_15m_close": 0,
        "regime": "unknown",
        "kalshi_midpoint": 50.0, "polymarket_yes": 0.5, "macro_24h_change": 0.0,
    }


def _derive_outcome(candle: dict) -> str:
    """Derive UP/DOWN direction from a candle's open and close."""
    return "UP" if candle["close"] > candle["open"] else "DOWN"


# ---------------------------------------------------------------------------
# Single prediction record
# ---------------------------------------------------------------------------

@dataclass
class BacktestPrediction:
    """One prediction made during the walk-forward backtest."""
    window_open: float
    model_name: str
    yes_probability: float
    confidence: float
    predicted: str          # "UP" or "DOWN"
    actual: str             # "UP" or "DOWN"
    correct: bool
    open_price: float
    close_price: float
    magnitude_pct: float
    pnl_cents: float        # Kalshi contract PnL in cents
    contract_side: str      # "YES" or "NO" — which contract was bought
    entry_price_cents: float  # cost of the contract in cents


# ---------------------------------------------------------------------------
# Aggregate result
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Aggregated metrics from a walk-forward backtest run."""
    asset: str
    source: str
    model_name: str
    total_predictions: int = 0
    correct_predictions: int = 0
    accuracy_pct: float = 0.0
    brier_score: float = 0.0
    total_pnl_cents: float = 0.0
    avg_pnl_per_trade_cents: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_cents: float = 0.0
    win_rate_pct: float = 0.0
    avg_win_cents: float = 0.0
    avg_loss_cents: float = 0.0
    profit_factor: float = 0.0
    up_predictions: int = 0
    down_predictions: int = 0
    up_accuracy_pct: float = 0.0
    down_accuracy_pct: float = 0.0
    regime_accuracy: dict = field(default_factory=dict)  # regime -> accuracy
    feature_importance: dict = field(default_factory=dict)  # feature -> importance
    predictions: list = field(default_factory=list)  # BacktestPrediction objects
    elapsed_seconds: float = 0.0
    candle_count: int = 0
    train_window_size: int = 0

    def print_summary(self) -> None:
        """Pretty-print the backtest summary."""
        lines = [
            f"\n{'='*60}",
            f"  BACKTEST RESULT: {self.model_name}",
            f"  Asset: {self.asset} | Source: {self.source}",
            f"{'='*60}",
            f"  Candles analyzed:       {self.candle_count}",
            f"  Train window:           {self.train_window_size} candles",
            f"  Total predictions:      {self.total_predictions}",
            f"  Accuracy:               {self.accuracy_pct:.1f}%",
            f"  Win rate:               {self.win_rate_pct:.1f}%",
            f"  Brier score:            {self.brier_score:.4f}",
            f"  Total PnL:              {self.total_pnl_cents:+.1f} cents",
            f"  Avg PnL/trade:          {self.avg_pnl_per_trade_cents:+.2f} cents",
            f"  Sharpe ratio:           {self.sharpe_ratio:.3f}",
            f"  Max drawdown:           {self.max_drawdown_cents:.1f} cents",
            f"  Profit factor:          {self.profit_factor:.2f}",
            f"  Avg win:                {self.avg_win_cents:+.1f} cents",
            f"  Avg loss:               {self.avg_loss_cents:+.1f} cents",
            f"  UP predictions:         {self.up_predictions} (accuracy: {self.up_accuracy_pct:.1f}%)",
            f"  DOWN predictions:       {self.down_predictions} (accuracy: {self.down_accuracy_pct:.1f}%)",
        ]
        if self.regime_accuracy:
            lines.append(f"  Regime accuracy:")
            for regime, acc in sorted(self.regime_accuracy.items()):
                lines.append(f"    {regime:20s} {acc:.1f}%")
        if self.feature_importance:
            lines.append(f"  Top features:")
            sorted_fi = sorted(self.feature_importance.items(), key=lambda x: -x[1])
            for fname, imp in sorted_fi[:10]:
                lines.append(f"    {fname:35s} {imp:.4f}")
        lines.append(f"  Elapsed:                {self.elapsed_seconds:.1f}s")
        lines.append(f"{'='*60}\n")
        print("\n".join(lines))

    def to_comparison_dict(self) -> dict:
        """Return a dict suitable for side-by-side model comparison."""
        return {
            "model_name": self.model_name,
            "total_predictions": self.total_predictions,
            "accuracy_pct": round(self.accuracy_pct, 2),
            "brier_score": round(self.brier_score, 4),
            "total_pnl_cents": round(self.total_pnl_cents, 1),
            "avg_pnl_per_trade_cents": round(self.avg_pnl_per_trade_cents, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_drawdown_cents": round(self.max_drawdown_cents, 1),
            "win_rate_pct": round(self.win_rate_pct, 2),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win_cents": round(self.avg_win_cents, 1),
            "avg_loss_cents": round(self.avg_loss_cents, 1),
        }


# ---------------------------------------------------------------------------
# Walk-forward backtester
# ---------------------------------------------------------------------------

class WalkForwardBacktester:
    """Walk-forward backtest engine.

    Loads historical 15m candles, slides a training window forward,
    trains models at each step (or periodically), predicts the next
    candle's direction, and compares to actual outcomes.

    Parameters
    ----------
    store : CandlePersistenceStore
        Initialized candle store with historical data.
    asset : str
        Asset to backtest (e.g. "BTC", "ETH").
    source : str
        Data source (default "binance").
    train_window_size : int
        Number of candles in the training window (default 288 = 72h).
    min_train_samples : int
        Minimum candles needed before predictions start.
    retrain_every : int
        Retrain models every N predictions (1 = every step, 0 = train once).
    """

    def __init__(
        self,
        store: CandlePersistenceStore,
        asset: str = "BTC",
        source: str = "binance",
        train_window_size: int = 288,
        min_train_samples: int = 50,
        retrain_every: int = 10,
    ):
        self._store = store
        self._asset = asset
        self._source = source
        self._train_window_size = train_window_size
        self._min_train_samples = min_train_samples
        self._retrain_every = retrain_every

    async def run(self, model_type: str = "macro") -> BacktestResult | list[BacktestResult]:
        """Execute the walk-forward backtest.

        Parameters
        ----------
        model_type : str
            "macro" for MacroEnsemble, "micro" for MicroEnsemble,
            or "both" to run both and return a list for comparison.

        Returns
        -------
        BacktestResult for single model, or list[BacktestResult] for "both".
        """
        t0 = time.time()
        model_type = model_type.lower()

        if model_type == "both":
            macro_result = await self._run_single("macro")
            micro_result = await self._run_single("micro")
            elapsed = time.time() - t0
            macro_result.elapsed_seconds = elapsed
            micro_result.elapsed_seconds = elapsed
            return [macro_result, micro_result]

        result = await self._run_single(model_type)
        result.elapsed_seconds = time.time() - t0
        return result

    async def _run_single(self, model_type: str) -> BacktestResult:
        """Run a single-model walk-forward backtest."""
        candles = await self._store.get_candles(
            self._asset, self._source, "15m", limit=10000
        )
        # get_candles returns newest-first; reverse to oldest-first
        candles = list(reversed(candles))

        if len(candles) < self._train_window_size + self._min_train_samples:
            logger.warning(
                "Insufficient candles for backtest: %d (need %d + %d)",
                len(candles), self._train_window_size, self._min_train_samples,
            )
            return BacktestResult(
                asset=self._asset,
                source=self._source,
                model_name=model_type,
                candle_count=len(candles),
                train_window_size=self._train_window_size,
            )

        logger.info(
            "Starting walk-forward backtest: %s | %d candles | train_window=%d | retrain_every=%d",
            model_type, len(candles), self._train_window_size, self._retrain_every,
        )

        # Pre-compute features for all candles
        all_features = []
        for i in range(len(candles)):
            start = max(0, i - self._train_window_size + 1)
            window_candles = candles[start:i + 1]
            features = compute_macro_features_from_candles(
                window_candles, window_ts=candles[i]["open_time"]
            )
            all_features.append(features)

        # Pre-compute outcomes
        all_outcomes = [_derive_outcome(c) for c in candles]

        # Build model
        macro_model: MacroEnsemble | None = None
        micro_model: MicroEnsemble | None = None
        if model_type == "macro":
            macro_model = MacroEnsemble()
        elif model_type == "micro":
            micro_model = MicroEnsemble()
        else:
            raise ValueError(f"Unknown model_type: {model_type!r}")

        # Walk forward
        predictions: list[BacktestPrediction] = []
        trained = False
        steps_since_train = self._retrain_every  # force train on first step
        feature_importance_accumulator: dict[str, float] = {}
        retrain_count = 0

        start_idx = self._train_window_size
        for test_idx in range(start_idx, len(candles)):
            steps_since_train += 1

            # Train or retrain
            if not trained or steps_since_train >= self._retrain_every:
                train_features = all_features[max(0, test_idx - self._train_window_size):test_idx]
                train_outcomes = all_outcomes[max(0, test_idx - self._train_window_size):test_idx]

                if len(train_features) >= self._min_train_samples:
                    if macro_model is not None:
                        macro_model.freq_model.train(train_features, train_outcomes)
                        macro_model.lgbm_model.train(train_features, train_outcomes)
                        # Accumulate feature importance from LightGBM
                        fi = macro_model.lgbm_model.get_feature_importance()
                        for k, v in fi.items():
                            feature_importance_accumulator[k] = feature_importance_accumulator.get(k, 0.0) + v
                    elif micro_model is not None:
                        micro_model.momentum_model.train(train_features, train_outcomes)
                        micro_model.lr_model.train(train_features, train_outcomes)
                    trained = True
                    steps_since_train = 0
                    retrain_count += 1

            if not trained:
                continue

            # Predict
            test_features = all_features[test_idx]
            if macro_model is not None:
                pred = macro_model.predict(test_features)
            else:
                pred = micro_model.predict(test_features)

            actual = all_outcomes[test_idx]
            correct = (pred.prediction == actual)

            # Kalshi contract PnL:
            # Buy the contract matching our prediction (YES if UP predicted, NO if DOWN predicted)
            # Contract costs yes_probability * 100 cents (YES) or (1-yes_probability)*100 cents (NO)
            # If outcome matches prediction: profit = 100 - entry_cost
            # If outcome doesn't match: loss = -entry_cost
            if pred.prediction == "UP":
                # Buying YES contract
                entry_cost = pred.yes_probability * 100.0
                if actual == "UP":
                    pnl = 100.0 - entry_cost  # contract pays out
                else:
                    pnl = -entry_cost  # contract expires worthless
                contract_side = "YES"
            else:
                # Buying NO contract
                entry_cost = (1.0 - pred.yes_probability) * 100.0
                if actual == "DOWN":
                    pnl = 100.0 - entry_cost  # contract pays out
                else:
                    pnl = -entry_cost  # contract expires worthless
                contract_side = "NO"

            # Cap PnL at Kalshi contract bounds: max win = 100 - min_price, max loss = -entry_cost
            pnl = max(-entry_cost, min(100.0 - entry_cost, pnl))

            candle = candles[test_idx]
            open_p = candle["open"]
            close_p = candle["close"]
            mag_pct = abs(close_p - open_p) / open_p * 100 if open_p > 0 else 0.0

            predictions.append(BacktestPrediction(
                window_open=candle["open_time"],
                model_name=pred.model_name,
                yes_probability=pred.yes_probability,
                confidence=pred.confidence,
                predicted=pred.prediction,
                actual=actual,
                correct=correct,
                open_price=open_p,
                close_price=close_p,
                magnitude_pct=mag_pct,
                pnl_cents=pnl,
                contract_side=contract_side,
                entry_price_cents=entry_cost,
            ))

        # Average feature importance across retrains
        avg_feature_importance = {}
        if retrain_count > 0 and feature_importance_accumulator:
            for k, v in feature_importance_accumulator.items():
                avg_feature_importance[k] = v / retrain_count

        # Aggregate metrics
        result = self._compute_result(predictions, model_type, len(candles))
        result.feature_importance = avg_feature_importance
        return result

    def _compute_result(
        self,
        predictions: list[BacktestPrediction],
        model_type: str,
        candle_count: int,
    ) -> BacktestResult:
        """Compute aggregate metrics from prediction list."""
        result = BacktestResult(
            asset=self._asset,
            source=self._source,
            model_name=model_type,
            candle_count=candle_count,
            train_window_size=self._train_window_size,
            predictions=predictions,
        )

        if not predictions:
            return result

        n = len(predictions)
        result.total_predictions = n
        result.correct_predictions = sum(1 for p in predictions if p.correct)
        result.accuracy_pct = result.correct_predictions / n * 100

        # Brier score: mean((predicted_prob - actual)^2)
        # actual = 1.0 if UP, 0.0 if DOWN
        brier_terms = []
        for p in predictions:
            actual_val = 1.0 if p.actual == "UP" else 0.0
            brier_terms.append((p.yes_probability - actual_val) ** 2)
        result.brier_score = sum(brier_terms) / n

        # PnL
        pnls = [p.pnl_cents for p in predictions]
        result.total_pnl_cents = sum(pnls)
        result.avg_pnl_per_trade_cents = result.total_pnl_cents / n

        # Win/loss stats
        wins = [p.pnl_cents for p in predictions if p.correct]
        losses = [p.pnl_cents for p in predictions if not p.correct]
        result.win_rate_pct = len(wins) / n * 100
        result.avg_win_cents = sum(wins) / len(wins) if wins else 0.0
        result.avg_loss_cents = sum(losses) / len(losses) if losses else 0.0

        # Profit factor
        gross_profit = sum(w for w in wins) if wins else 0.0
        gross_loss = abs(sum(l for l in losses)) if losses else 0.0
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Sharpe ratio (annualized, assuming 15m candles → 35040 per year)
        if len(pnls) > 1:
            mean_ret = sum(pnls) / n
            var_ret = sum((p - mean_ret) ** 2 for p in pnls) / (n - 1)
            std_ret = var_ret ** 0.5
            result.sharpe_ratio = (mean_ret / std_ret) * (35040 ** 0.5) if std_ret > 0 else 0.0

        # Max drawdown
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        result.max_drawdown_cents = max_dd

        # Directional accuracy
        up_preds = [p for p in predictions if p.predicted == "UP"]
        down_preds = [p for p in predictions if p.predicted == "DOWN"]
        result.up_predictions = len(up_preds)
        result.down_predictions = len(down_preds)
        result.up_accuracy_pct = (
            sum(1 for p in up_preds if p.correct) / len(up_preds) * 100
            if up_preds else 0.0
        )
        result.down_accuracy_pct = (
            sum(1 for p in down_preds if p.correct) / len(down_preds) * 100
            if down_preds else 0.0
        )

        # Regime accuracy
        regime_correct: dict[str, list[bool]] = {}
        for p in predictions:
            # Find the regime from the features at that window
            # We store it as part of the feature dict; approximate from candle data
            regime_key = _approximate_regime(p)
            if regime_key not in regime_correct:
                regime_correct[regime_key] = []
            regime_correct[regime_key].append(p.correct)

        result.regime_accuracy = {
            regime: sum(vals) / len(vals) * 100
            for regime, vals in regime_correct.items()
            if vals
        }

        return result


def _approximate_regime(pred: BacktestPrediction) -> str:
    """Rough regime classification from prediction magnitude."""
    if pred.magnitude_pct > 0.5:
        return "volatile"
    elif pred.magnitude_pct > 0.2:
        return "trending"
    else:
        return "ranging"


def print_comparison(macro_result: BacktestResult, micro_result: BacktestResult) -> None:
    """Print a side-by-side comparison of two backtest results."""
    print(f"\n{'='*70}")
    print(f"  MODEL COMPARISON: {macro_result.asset}")
    print(f"{'='*70}")
    print(f"  {'METRIC':30s} {'MACRO':>18s} {'MICRO':>18s}")
    print(f"  {'-'*66}")

    rows = [
        ("Total predictions", f"{macro_result.total_predictions}", f"{micro_result.total_predictions}"),
        ("Accuracy", f"{macro_result.accuracy_pct:.1f}%", f"{micro_result.accuracy_pct:.1f}%"),
        ("Win rate", f"{macro_result.win_rate_pct:.1f}%", f"{micro_result.win_rate_pct:.1f}%"),
        ("Brier score", f"{macro_result.brier_score:.4f}", f"{micro_result.brier_score:.4f}"),
        ("Total PnL (cents)", f"{macro_result.total_pnl_cents:+.1f}", f"{micro_result.total_pnl_cents:+.1f}"),
        ("Avg PnL/trade", f"{macro_result.avg_pnl_per_trade_cents:+.2f}c", f"{micro_result.avg_pnl_per_trade_cents:+.2f}c"),
        ("Sharpe ratio", f"{macro_result.sharpe_ratio:.3f}", f"{micro_result.sharpe_ratio:.3f}"),
        ("Max drawdown", f"{macro_result.max_drawdown_cents:.1f}c", f"{micro_result.max_drawdown_cents:.1f}c"),
        ("Profit factor", f"{macro_result.profit_factor:.2f}", f"{micro_result.profit_factor:.2f}"),
        ("Avg win", f"{macro_result.avg_win_cents:+.1f}c", f"{micro_result.avg_win_cents:+.1f}c"),
        ("Avg loss", f"{macro_result.avg_loss_cents:+.1f}c", f"{micro_result.avg_loss_cents:+.1f}c"),
        ("UP accuracy", f"{macro_result.up_accuracy_pct:.1f}%", f"{micro_result.up_accuracy_pct:.1f}%"),
        ("DOWN accuracy", f"{macro_result.down_accuracy_pct:.1f}%", f"{micro_result.down_accuracy_pct:.1f}%"),
    ]

    for label, macro_val, micro_val in rows:
        print(f"  {label:30s} {macro_val:>18s} {micro_val:>18s}")

    # Winner declaration
    print(f"\n  {'WINNER':30s}", end="")
    metrics = [
        ("accuracy_pct", True), ("brier_score", False), ("total_pnl_cents", True),
        ("sharpe_ratio", True), ("max_drawdown_cents", False),
    ]
    macro_wins = 0
    micro_wins = 0
    for metric, higher_better in metrics:
        mv = getattr(macro_result, metric)
        kv = getattr(micro_result, metric)
        if higher_better:
            if mv > kv:
                macro_wins += 1
            elif kv > mv:
                micro_wins += 1
        else:
            if mv < kv:
                macro_wins += 1
            elif kv < mv:
                micro_wins += 1

    if macro_wins > micro_wins:
        print(f"{'MACRO':>18s} ({macro_wins}-{micro_wins})")
    elif micro_wins > macro_wins:
        print(f"{'':18s}{'MICRO':>18s} ({micro_wins}-{macro_wins})")
    else:
        print(f"{'TIE':>18s} ({macro_wins}-{micro_wins})")

    print(f"{'='*70}\n")
