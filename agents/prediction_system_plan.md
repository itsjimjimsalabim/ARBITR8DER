# Prediction System Plan: Dual-Horizon BTC/ETH Binary Market Predictor

## Goal

Predict UP/DOWN outcomes for Kalshi 15-minute BTC and ETH markets across 4 sequential windows (1 hour ahead). Build two complementary models and a persistent data battery to feed and score them continuously.

**Last updated**: 2026-07-24, after sub-agent review of codebase + internet research.

---

## Sub-Agent Findings That Shaped This Plan

### Pipeline Gaps (from pipeline review agent)
- **Candle data NEVER reaches prediction model** — `backfill_candles()` output is dead code from pipeline perspective
- Binance candle cache is in-memory only (`_candle_cache` dict), lost on restart
- No gap-fill recovery when WebSocket reconnects
- Feature extraction (`FeatureExtractionEngine`) only sees latest single tick from HotSnapshot — no historical candles
- No auto-restart of provider tasks when they crash
- Coinbase has no REST fallback (unlike Binance)
- No continuous candle accumulation — `backfill_candles` is one-shot, overwrites cache
- Prediction scoring loop exists but isn't wired end-to-end

### Library Recommendations (from internet research agent)
- **tsfresh**: Automated feature extraction from rolling windows (hypothesis-tested feature selection)
- **statsmodels**: SARIMAX/VAR for baseline statistical forecasting
- **LightGBM/XGBoost**: Primary classifiers for tabular financial features (beats deep learning)
- **pytorch-forecasting** (TFT): Deep learning model — only if LightGBM baseline proves signal exists
- **DuckDB + Parquet**: Analytical store for candle data (columnar, fast aggregations)
- **SQLite**: Operational state (wallet, orders, journal)
- **FreqAI architecture**: Design template — self-adaptive retraining, walk-forward validation
- **Skip Prophet**: Designed for daily/weekly business data, poor fit for 15m noise

### Code Architecture (from code review agent)
- Scoring infrastructure (`PredictionScorer`, `MarketOutcomeResolver`) is mature and model-agnostic
- `FeatureExtractor` needs expansion beyond snapshot-bound features
- Need new data path: candle store → feature engine → model
- `BaselinePredictionModel` is intentionally trivial — easy to replace

---

## Two Prediction Horizons

### Macro Model (72-hour, ~288 fifteen-minute candles)
**Question**: "What's the trend regime for the next 1-4 hours?"
- Inputs: 288 15m candles (OHLCV), CoinGecko macro, Polymarket sentiment
- Output: Regime classification + directional bias per 15-min window
- Update: Every 15 minutes (once per new candle)

### Micro Model (5-minute, ~20 one-minute candles)
**Question**: "What happens in THIS specific 15-minute window?"
- Inputs: Last 20 1m candles (OHLCV), live Kalshi order book, Coinbase spread
- Output: UP probability for current window + confidence
- Update: Every 30-60 seconds

### Ensemble
- Macro provides **baseline bias** (regime context)
- Micro provides **timing refinement** (order flow pressure)
- Final = weighted combination, weights learned from scoring history
- Strong disagreement → skip trade (low confidence)

---

## Data Architecture

### Storage Strategy (from research)

**DuckDB + Parquet** for candle/feature data:
- Columnar storage, fast aggregations, zero setup
- `runtime/market_data/BTCUSD_1m.parquet`, `ETHUSD_15m.parquet`, etc.
- DuckDB queries Parquet directly: `SELECT * FROM 'runtime/market_data/BTCUSD_15m.parquet' WHERE ts > now() - interval '24 hours'`

**SQLite** for operational state:
- Existing tables: `observations`, `raw_provider_events`, `snapshots`, `predictions`
- New tables needed: `candles`, `outcomes`, `features`, `model_runs`

### New SQLite Schema

```sql
-- Persistent candle store (survives restart)
CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,          -- 'BTC' or 'ETH'
    source TEXT NOT NULL,         -- 'binance', 'coinbase'
    interval TEXT NOT NULL,       -- '1m', '5m', '15m'
    open_time REAL NOT NULL,      -- epoch seconds
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    quote_volume REAL,
    trades INTEGER,
    created_at REAL DEFAULT (strftime('%s','now')),
    UNIQUE(asset, source, interval, open_time)
);

-- Market outcomes (what actually happened each 15-min window)
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    ticker TEXT NOT NULL,
    window_open REAL NOT NULL,
    window_close REAL NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    direction TEXT NOT NULL,       -- 'UP' or 'DOWN'
    magnitude_pct REAL,
    created_at REAL DEFAULT (strftime('%s','now'))
);

-- Feature store (computed features per prediction window)
CREATE TABLE IF NOT EXISTS features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    window_open REAL NOT NULL,
    feature_set TEXT NOT NULL,     -- 'macro', 'micro', 'cross_asset'
    features_json TEXT NOT NULL,
    computed_at REAL NOT NULL
);

-- Model runs (track which model produced which prediction)
CREATE TABLE IF NOT EXISTS model_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,      -- 'lgbm_macro_v1', 'freq_baseline_v1'
    asset TEXT NOT NULL,
    window_open REAL NOT NULL,
    yes_probability REAL NOT NULL,
    confidence REAL NOT NULL,
    features_json TEXT,
    predicted_at REAL NOT NULL,
    outcome_id INTEGER,
    correct INTEGER,              -- NULL = unresolved
    pnl_cents REAL,
    FOREIGN KEY (outcome_id) REFERENCES outcomes(id)
);
```

### Data Collection Battery (4 loops)

**Loop 1: Candle Collection (every 60s)**
```
For each asset in [BTC, ETH]:
  1. Fetch latest 1m candles from Binance REST (last 5)
  2. Fetch latest 1m candles from Coinbase REST (last 5)
  3. Upsert into candles table
  4. Every 15 min: aggregate 1m → 15m candles
  5. Record outcome if a Kalshi window just closed
```

**Loop 2: Live Market State (every 30s)**
```
For each active Kalshi ticker:
  1. Record midpoint, book depth imbalance
  2. Record Coinbase spread
  3. Store as micro features
```

**Loop 3: Macro Context (every 60s)**
```
  1. CoinGecko BTC/ETH price, 24h change, volume
  2. Polymarket BTC sentiment
  3. Store as macro features
```

**Loop 4: Prediction + Scoring (every 15 min)**
```
  At T-2 min before window opens:
    1. Load candles from DB
    2. Compute macro + micro features
    3. Run models → probability
    4. Store prediction in model_runs table
    5. If confidence > threshold → paper trade

  At T+0 (window closes):
    1. Record actual outcome
    2. Match to prediction, mark correct/incorrect
    3. Update running accuracy stats
```

---

## Feature Engineering

### Macro Features (from 288 15m candles)
| Feature | Description | Source |
|---------|-------------|--------|
| `streak_length` | Consecutive same-direction candles | candles |
| `streak_direction` | UP or DOWN | candles |
| `body_ratio` | \|close-open\| / (high-low) | candles |
| `volume_trend` | SMA(vol,6) / SMA(vol,24) | candles |
| `price_vs_sma_24` | price / SMA(close,24) - 1 | candles |
| `price_vs_sma_96` | price / SMA(close,96) - 1 | candles |
| `rsi_7` | RSI(7) from 15m candles | candles |
| `rsi_14` | RSI(14) from 15m candles | candles |
| `bollinger_pct` | Position within Bollinger Bands | candles |
| `atr_14` | ATR(14) | candles |
| `hour_of_day` | 0-23 | candles |
| `day_of_week` | 0-6 | candles |
| `regime` | trending_up / trending_down / ranging / volatile | computed |
| `macro_24h_change` | CoinGecko 24h % change | CoinGecko |
| `polymarket_yes_price` | Polymarket sentiment | Polymarket |
| `kalshi_midpoint` | Current Kalshi midpoint | Kalshi |

### Micro Features (from last 20 1m candles + live state)
| Feature | Description | Source |
|---------|-------------|--------|
| `last_5m_return` | Price change in last 5 candles | candles |
| `last_15m_return` | Price change in last 15 candles | candles |
| `momentum_acceleration` | Is momentum increasing? | candles |
| `volume_spike` | current_vol / avg_vol_20 | candles |
| `book_imbalance` | bid_depth / (bid_depth + ask_depth) | Kalshi WS |
| `coinbase_spread` | ask - bid | Coinbase WS |
| `recent_trade_direction` | net buy vs sell last 1min | Binance WS |

### Cross-Asset Features
| Feature | Description |
|---------|-------------|
| `btc_eth_correlation_1h` | Rolling correlation over 4 candles |
| `btc_lead_eth` | Did BTC move first in last 30min? |
| `eth_lead_btc` | Did ETH move first in last 30min? |

---

## Model Progression

### Phase 1: Frequency Lookup (baseline, testable in hours)
- Group historical windows by similar conditions (regime + streak + time_of_day)
- Count outcomes in each group
- Prediction = historical frequency
- **Purpose**: Establishes minimum viable accuracy

### Phase 2: LightGBM Classifier (primary model)
- LightGBM on all features (macro + micro + cross-asset)
- Walk-forward cross-validation (no future data leakage)
- Feature importance tells us which features matter
- **Purpose**: Main prediction engine

### Phase 3: SARIMAX Statistical Baseline
- SARIMAX with exogenous features for 4-step-ahead forecast
- Direction from sign of forecast
- **Purpose**: Independent baseline to ensemble with LightGBM

### Phase 4: Ensemble
- Weighted average of LightGBM + SARIMAX probabilities
- Weights learned from validation accuracy
- **Purpose**: More robust than any single model

### Phase 5: TFT Deep Learning (if needed)
- Only if LightGBM baseline shows signal
- Temporal Fusion Transformer via pytorch-forecasting
- **Purpose**: Captures temporal patterns that tree models miss

---

## Backtesting Framework

Walk-forward validation on historical data:
```
For each window in candles[288:]:
  train = candles[:window_start]        # only past data
  features = compute_features(train)
  prediction = model.predict(features)
  outcome = actual_direction[window_start:window_end]
  correct = (prediction > 0.5) == (outcome == 'UP')
  record_result(prediction, outcome, correct)
```

**Metrics**: accuracy (>52% = edge), Brier score, calibration, PnL at various thresholds, per-regime accuracy, feature importance stability.

---

## Implementation Phases

### Phase 8A: Persistent Candle Store + Gap Recovery
- SQLite candles table + indexes
- Candle collection loop (Binance + Coinbase REST, every 60s)
- Gap detection: track last-received timestamp, backfill gaps on reconnect
- 1m → 15m aggregation
- **Files**: `candle_persistence_store.py`, `candle_collection_battery.py`

### Phase 8B: Feature Engineering Engine
- Compute all macro/micro/cross-asset features from stored candles
- Use `ta` library for RSI, Bollinger, ATR (pip install ta)
- Feature validation (no NaN, no inf, reasonable ranges)
- Store in features table
- **Files**: `feature_engine_v2.py`

### Phase 8C: Backtest Engine
- Walk-forward validation framework
- Load historical candles from DB
- Record outcomes from Kalshi REST (settled markets)
- Accuracy tracking by model/version
- **Files**: `backtest_engine.py`

### Phase 8D: Macro Model (LightGBM + Frequency Lookup)
- Frequency-based baseline model
- LightGBM classifier on macro features
- **Files**: `macro_prediction_model.py`

### Phase 8E: Micro Model
- Live feature computation from order book + recent candles
- Short-horizon prediction model
- Integration with macro ensemble
- **Files**: `micro_prediction_model.py`

### Phase 8F: Scoring Engine + REPL Integration
- Automatic outcome recording after each window
- Prediction-to-outcome matching
- Running accuracy dashboard
- REPL: `predict`, `accuracy`, `backtest`, `features`
- **Files**: `scoring_engine_v2.py`, REPL commands

### Phase 8G: Persistent Battery
- Background data collection daemon
- Auto-restart on failure (circuit breaker: 3 retries, then degraded)
- Data integrity checks
- **Files**: `persistent_battery_daemon.py`

---

## Success Criteria

Before live paper trading:
1. Backtest accuracy > 52% over 100+ historical windows
2. Backtest PnL positive
3. Feature importance stable across retraining
4. Macro and micro models agree > 60% of the time
5. No data gaps > 24 hours

---

## Open Questions

1. Use DuckDB+Parquet or keep everything in SQLite? (DuckDB for analytics, SQLite for ops)
2. What's the minimum backtest period before trusting a model?
3. Should we aggregate 1m→15m in SQL or Python?
4. How often to retrain LightGBM? (Every 24h? Every 100 candles?)
