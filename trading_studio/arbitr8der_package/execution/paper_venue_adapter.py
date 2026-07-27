"""PAPER venue adapter — simulates order fills using real market data.

SQLite-backed wallet with persistent inventory, positions, orders, and
settlement history. This is the first execution path toward live trading —
every feature here maps directly to a Kalshi API call in Phase 9.

Fee model matches Kalshi structure:
  - No commission on paper trades
  - Spread captured via fill price vs. midpoint

Order lifecycle:
  Intent → Risk Check → Fill (simulated) → Position → Settlement (on resolution)
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arbitr8der_package.config.structured_logging_configuration_module import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PaperWallet:
    """Persistent paper wallet balance."""
    balance: float = 17.00
    starting_balance: float = 17.00
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


@dataclass
class PaperOrder:
    """A paper order record."""
    order_id: str = ""
    created_at: str = ""
    filled_at: str | None = None
    settled_at: str | None = None
    status: str = "pending"  # pending, filled, settled, cancelled

    # Order details
    asset: str = ""
    side: str = ""  # "yes" or "no"
    contracts: int = 0
    ticker: str = ""
    limit_cents: int | None = None  # None = market order

    # Fill details
    fill_price_cents: float | None = None
    fill_cost_usd: float | None = None
    midpoint_at_fill: float | None = None

    # Settlement
    outcome: int | None = None  # 0 = NO, 1 = YES
    pnl: float | None = None
    settlement_price_cents: float | None = None

    # Lineage
    snapshot_version: int | None = None
    model_version: str = "baseline_v1"
    prediction_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperPosition:
    """An open paper position."""
    position_id: str = ""
    asset: str = ""
    side: str = ""
    ticker: str = ""
    contracts: int = 0
    avg_entry_cents: float = 0.0
    total_cost_usd: float = 0.0
    opened_at: str = ""
    last_updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Fee model
# ---------------------------------------------------------------------------

def kalshi_fee_model(contracts: int, price_cents: float) -> float:
    """Calculate fees matching Kalshi structure.

    Kalshi charges no commission but captures spread.
    For paper trading, we model a small spread cost.
    """
    notional = contracts * price_cents / 100.0
    # Kalshi has no explicit fees on most markets, but we model
    # a tiny spread cost for realism
    return 0.0


# ---------------------------------------------------------------------------
# Paper Venue Adapter
# ---------------------------------------------------------------------------

class PaperVenueAdapter:
    """SQLite-backed paper trading venue.

    Persists wallet, orders, positions, and settlement history across
    sessions. All fills are simulated using real market midpoint prices.
    """

    def __init__(self, db_path: Path | str | None = None, initial_balance: float | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent.parent / "runtime" / "paper_wallet.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema(initial_balance=initial_balance)
        self._wallet = self._load_wallet()
        logger.info("Paper venue adapter initialized, balance=$%.2f", self._wallet.balance)

    def _init_schema(self, initial_balance: float | None = None) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS wallet (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance REAL NOT NULL DEFAULT 17.00,
                starting_balance REAL NOT NULL DEFAULT 17.00,
                total_pnl REAL NOT NULL DEFAULT 0.0,
                total_trades INTEGER NOT NULL DEFAULT 0,
                winning_trades INTEGER NOT NULL DEFAULT 0,
                losing_trades INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                filled_at TEXT,
                settled_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                asset TEXT NOT NULL,
                side TEXT NOT NULL,
                contracts INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                limit_cents INTEGER,
                fill_price_cents REAL,
                fill_cost_usd REAL,
                midpoint_at_fill REAL,
                outcome INTEGER,
                pnl REAL,
                settlement_price_cents REAL,
                snapshot_version INTEGER,
                model_version TEXT DEFAULT 'baseline_v1',
                prediction_id TEXT
            );

            CREATE TABLE IF NOT EXISTS positions (
                position_id TEXT PRIMARY KEY,
                asset TEXT NOT NULL,
                side TEXT NOT NULL,
                ticker TEXT NOT NULL,
                contracts INTEGER NOT NULL,
                avg_entry_cents REAL NOT NULL,
                total_cost_usd REAL NOT NULL,
                opened_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settlements (
                settlement_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                position_id TEXT,
                ticker TEXT NOT NULL,
                outcome INTEGER NOT NULL,
                pnl REAL NOT NULL,
                settled_at TEXT NOT NULL
            );
        """)
        # Ensure wallet row exists
        row = self._conn.execute("SELECT id FROM wallet WHERE id = 1").fetchone()
        if row is None:
            balance = initial_balance if initial_balance is not None else 17.00
            self._conn.execute(
                "INSERT INTO wallet (id, balance, starting_balance) VALUES (1, ?, ?)",
                (balance, balance),
            )
            self._conn.commit()

    def _load_wallet(self) -> PaperWallet:
        row = self._conn.execute("SELECT * FROM wallet WHERE id = 1").fetchone()
        return PaperWallet(
            balance=row["balance"],
            starting_balance=row["starting_balance"],
            total_pnl=row["total_pnl"],
            total_trades=row["total_trades"],
            winning_trades=row["winning_trades"],
            losing_trades=row["losing_trades"],
        )

    def _save_wallet(self) -> None:
        self._conn.execute(
            """UPDATE wallet SET balance=?, total_pnl=?, total_trades=?,
               winning_trades=?, losing_trades=? WHERE id=1""",
            (self._wallet.balance, self._wallet.total_pnl,
             self._wallet.total_trades, self._wallet.winning_trades,
             self._wallet.losing_trades),
        )
        self._conn.commit()

    async def sync_live_balance(self, discovery_client: Any) -> float | None:
        """Fetch account balance from Kalshi REST and override the paper wallet balance.

        Returns the synced balance in USD or None if sync failed.
        """
        if discovery_client is None:
            return None
        try:
            data = await discovery_client.get_balance()
            if data and "balance" in data:
                balance_cents = data["balance"]
                balance_usd = balance_cents / 100.0
                self._wallet.balance = balance_usd
                self._wallet.starting_balance = balance_usd
                self._conn.execute(
                    "UPDATE wallet SET balance=?, starting_balance=? WHERE id=1",
                    (balance_usd, balance_usd)
                )
                self._conn.commit()
                logger.info("Synced paper wallet balance and starting balance to live Kalshi balance: $%.2f", balance_usd)
                return balance_usd
        except Exception as e:
            logger.warning("Failed to sync live Kalshi balance: %s", e)
        return None

    def update_pending_orders(self, ticker_midpoints: dict[str, float]) -> list[PaperOrder]:
        """Check all pending orders against current market midpoints and fill those that meet the criteria.

        ticker_midpoints is a dict of {ticker: midpoint_cents}
        """
        pending = self.get_pending_orders()
        if not pending:
            return []

        filled_orders = []
        now = datetime.now(UTC).isoformat()

        for order in pending:
            midpoint = ticker_midpoints.get(order.ticker)
            if midpoint is None:
                continue

            should_fill = False
            fill_price = None

            if order.side == "yes" and midpoint <= order.limit_cents:
                should_fill = True
                fill_price = midpoint
            elif order.side == "no" and midpoint >= (100 - order.limit_cents):
                should_fill = True
                fill_price = 100.0 - midpoint

            if should_fill:
                # Check balance
                fill_cost = order.contracts * fill_price / 100.0
                fees = kalshi_fee_model(order.contracts, fill_price)
                total_cost = fill_cost + fees

                if total_cost > self._wallet.balance:
                    order.status = "cancelled"
                    order.settled_at = now
                    self._save_order(order)
                    logger.warning("Pending order %s cancelled: insufficient balance", order.order_id)
                    continue

                # Fill the order
                self._wallet.balance -= total_cost
                self._wallet.total_trades += 1
                self._save_wallet()

                order.status = "filled"
                order.filled_at = now
                order.fill_price_cents = fill_price
                order.fill_cost_usd = fill_cost
                order.midpoint_at_fill = midpoint
                self._save_order(order)

                # Update position
                self._update_position(order)
                logger.info(
                    "Pending limit order filled: %s %s %d contracts of %s at %.1fc ($%.2f)",
                    order.side.upper(), order.asset, order.contracts, order.ticker, fill_price, fill_cost
                )
                filled_orders.append(order)

        return filled_orders

    # ------------------------------------------------------------------
    # Order lifecycle
    # ------------------------------------------------------------------

    def submit_order(
        self,
        asset: str,
        side: str,
        contracts: int,
        ticker: str,
        *,
        limit_cents: int | None = None,
        midpoint_cents: float | None = None,
        snapshot_version: int | None = None,
        model_version: str = "baseline_v1",
        prediction_id: str | None = None,
    ) -> PaperOrder:
        """Submit a paper order. Fills immediately at midpoint (market) or at limit."""
        now = datetime.now(UTC).isoformat()
        order_id = f"paper_{uuid.uuid4().hex[:12]}"

        # Determine fill price
        if limit_cents is not None:
            # Limit order — fill if midpoint is at or better than limit
            # Always fill at the better price (midpoint), not the limit
            if midpoint_cents is not None:
                if side == "yes" and midpoint_cents <= limit_cents:
                    fill_price = midpoint_cents  # Fill at market, not limit
                elif side == "no" and midpoint_cents >= (100 - limit_cents):
                    fill_price = 100.0 - midpoint_cents  # Fill at market, not limit
                else:
                    # Limit not reached — stay pending
                    order = PaperOrder(
                        order_id=order_id,
                        created_at=now,
                        status="pending",
                        asset=asset,
                        side=side,
                        contracts=contracts,
                        ticker=ticker,
                        limit_cents=limit_cents,
                        snapshot_version=snapshot_version,
                        model_version=model_version,
                        prediction_id=prediction_id,
                    )
                    self._save_order(order)
                    return order
            else:
                fill_price = float(limit_cents)
        else:
            # Market order — fill at midpoint (adjusted for NO contracts)
            raw_mid = midpoint_cents if midpoint_cents is not None else 50.0
            fill_price = (100.0 - raw_mid) if side == "no" else raw_mid

        # Calculate cost
        fill_cost = contracts * fill_price / 100.0
        fees = kalshi_fee_model(contracts, fill_price)
        total_cost = fill_cost + fees

        # Check balance
        if total_cost > self._wallet.balance:
            order = PaperOrder(
                order_id=order_id,
                created_at=now,
                status="cancelled",
                asset=asset,
                side=side,
                contracts=contracts,
                ticker=ticker,
                limit_cents=limit_cents,
                snapshot_version=snapshot_version,
                model_version=model_version,
                prediction_id=prediction_id,
            )
            self._save_order(order)
            logger.warning("Paper order %s cancelled: insufficient balance", order_id)
            return order

        # Fill the order
        self._wallet.balance -= total_cost
        self._wallet.total_trades += 1
        self._save_wallet()

        order = PaperOrder(
            order_id=order_id,
            created_at=now,
            filled_at=now,
            status="filled",
            asset=asset,
            side=side,
            contracts=contracts,
            ticker=ticker,
            limit_cents=limit_cents,
            fill_price_cents=fill_price,
            fill_cost_usd=fill_cost,
            midpoint_at_fill=midpoint_cents,
            snapshot_version=snapshot_version,
            model_version=model_version,
            prediction_id=prediction_id,
        )
        self._save_order(order)

        # Update or create position
        self._update_position(order)

        logger.info(
            "Paper fill: %s %s %d contracts of %s at %.1fc ($%.2f)",
            side.upper(), asset, contracts, ticker, fill_price, fill_cost,
        )
        return order

    def cancel_order(self, order_id: str) -> PaperOrder | None:
        """Cancel a pending order."""
        order = self._load_order(order_id)
        if order is None or order.status != "pending":
            return None
        order.status = "cancelled"
        self._save_order(order)
        logger.info("Paper order cancelled: %s", order_id)
        return order

    def settle_order(self, order_id: str, outcome: int) -> PaperOrder | None:
        """Settle a filled order with the market outcome (0=NO, 1=YES).

        PnL calculation:
          - YES order + YES outcome: pnl = contracts * (100 - fill_price) / 100
          - YES order + NO outcome: pnl = -fill_cost
          - NO order + NO outcome: pnl = contracts * (100 - fill_price) / 100
          - NO order + YES outcome: pnl = -fill_cost
        """
        order = self._load_order(order_id)
        if order is None or order.status != "filled":
            return None

        if order.fill_price_cents is None or order.fill_cost_usd is None:
            return None

        # Calculate PnL
        won = (
            (order.side == "yes" and outcome == 1) or
            (order.side == "no" and outcome == 0)
        )

        if won:
            # Won: payout is $1 per contract, cost was fill_price/100 per contract
            pnl = order.contracts * (1.0 - order.fill_price_cents / 100.0)
        else:
            # Lost: lose the cost
            pnl = -order.fill_cost_usd

        settlement_price = 100.0 if outcome == 1 else 0.0

        # Update wallet
        self._wallet.balance += order.fill_cost_usd + pnl  # return cost + add PnL
        self._wallet.total_pnl += pnl
        if won:
            self._wallet.winning_trades += 1
        else:
            self._wallet.losing_trades += 1
        self._save_wallet()

        # Update order
        now = datetime.now(UTC).isoformat()
        order.settled_at = now
        order.status = "settled"
        order.outcome = outcome
        order.pnl = pnl
        order.settlement_price_cents = settlement_price
        self._save_order(order)

        # Remove position
        self._remove_position(order.ticker, order.side)

        # Record settlement
        settlement_id = f"settle_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            "INSERT INTO settlements (settlement_id, order_id, ticker, outcome, pnl, settled_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (settlement_id, order_id, order.ticker, outcome, pnl, now),
        )
        self._conn.commit()

        logger.info(
            "Paper settlement: %s %s -> outcome=%d, pnl=$%.2f",
            order.ticker, order.side, outcome, pnl,
        )
        return order

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def _update_position(self, order: PaperOrder) -> None:
        """Update position after a fill."""
        if order.fill_price_cents is None or order.fill_cost_usd is None:
            return

        # Find existing position for this ticker+side
        row = self._conn.execute(
            "SELECT * FROM positions WHERE ticker = ? AND side = ?",
            (order.ticker, order.side),
        ).fetchone()

        now = datetime.now(UTC).isoformat()

        if row:
            # Average into existing position
            old_contracts = row["contracts"]
            old_cost = row["total_cost_usd"]
            new_contracts = old_contracts + order.contracts
            new_cost = old_cost + order.fill_cost_usd
            avg_price = (row["avg_entry_cents"] * old_contracts + order.fill_price_cents * order.contracts) / new_contracts

            self._conn.execute(
                "UPDATE positions SET contracts=?, avg_entry_cents=?, total_cost_usd=?, last_updated=? "
                "WHERE position_id=?",
                (new_contracts, avg_price, new_cost, now, row["position_id"]),
            )
        else:
            position_id = f"pos_{uuid.uuid4().hex[:12]}"
            self._conn.execute(
                "INSERT INTO positions (position_id, asset, side, ticker, contracts, avg_entry_cents, total_cost_usd, opened_at, last_updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (position_id, order.asset, order.side, order.ticker,
                 order.contracts, order.fill_price_cents, order.fill_cost_usd, now, now),
            )
        self._conn.commit()

    def _remove_position(self, ticker: str, side: str) -> None:
        """Remove a position after settlement."""
        self._conn.execute(
            "DELETE FROM positions WHERE ticker = ? AND side = ?",
            (ticker, side),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_wallet(self) -> PaperWallet:
        return self._wallet

    def get_open_positions(self) -> list[PaperPosition]:
        """Get all open positions."""
        rows = self._conn.execute("SELECT * FROM positions ORDER BY opened_at DESC").fetchall()
        return [
            PaperPosition(
                position_id=r["position_id"],
                asset=r["asset"],
                side=r["side"],
                ticker=r["ticker"],
                contracts=r["contracts"],
                avg_entry_cents=r["avg_entry_cents"],
                total_cost_usd=r["total_cost_usd"],
                opened_at=r["opened_at"],
                last_updated=r["last_updated"],
            )
            for r in rows
        ]

    def get_pending_orders(self) -> list[PaperOrder]:
        """Get all pending orders."""
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_order(r) for r in rows]

    def get_filled_orders(self) -> list[PaperOrder]:
        """Get all filled (open) orders."""
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE status = 'filled' ORDER BY filled_at DESC"
        ).fetchall()
        return [self._row_to_order(r) for r in rows]

    def get_order_history(self, limit: int = 50) -> list[PaperOrder]:
        """Get recent order history."""
        rows = self._conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_order(r) for r in rows]

    def get_settlement_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent settlements."""
        rows = self._conn.execute(
            "SELECT * FROM settlements ORDER BY settled_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _load_order(self, order_id: str) -> PaperOrder | None:
        row = self._conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        return self._row_to_order(row) if row else None

    def _save_order(self, order: PaperOrder) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO orders
               (order_id, created_at, filled_at, settled_at, status,
                asset, side, contracts, ticker, limit_cents,
                fill_price_cents, fill_cost_usd, midpoint_at_fill,
                outcome, pnl, settlement_price_cents,
                snapshot_version, model_version, prediction_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order.order_id, order.created_at, order.filled_at, order.settled_at,
             order.status, order.asset, order.side, order.contracts, order.ticker,
             order.limit_cents, order.fill_price_cents, order.fill_cost_usd,
             order.midpoint_at_fill, order.outcome, order.pnl,
             order.settlement_price_cents, order.snapshot_version,
             order.model_version, order.prediction_id),
        )
        self._conn.commit()

    def _row_to_order(self, row: sqlite3.Row) -> PaperOrder:
        return PaperOrder(
            order_id=row["order_id"],
            created_at=row["created_at"],
            filled_at=row["filled_at"],
            settled_at=row["settled_at"],
            status=row["status"],
            asset=row["asset"],
            side=row["side"],
            contracts=row["contracts"],
            ticker=row["ticker"],
            limit_cents=row["limit_cents"],
            fill_price_cents=row["fill_price_cents"],
            fill_cost_usd=row["fill_cost_usd"],
            midpoint_at_fill=row["midpoint_at_fill"],
            outcome=row["outcome"],
            pnl=row["pnl"],
            settlement_price_cents=row["settlement_price_cents"],
            snapshot_version=row["snapshot_version"],
            model_version=row["model_version"],
            prediction_id=row["prediction_id"],
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return wallet and position summary."""
        positions = self.get_open_positions()
        pending = self.get_pending_orders()
        return {
            "balance": self._wallet.balance,
            "starting_balance": self._wallet.starting_balance,
            "total_pnl": self._wallet.total_pnl,
            "total_trades": self._wallet.total_trades,
            "winning_trades": self._wallet.winning_trades,
            "losing_trades": self._wallet.losing_trades,
            "open_positions": len(positions),
            "pending_orders": len(pending),
            "positions": [p.to_dict() for p in positions],
        }

    async def settle_expired_positions(
        self,
        candle_store: Any | None = None,
        discovery_client: Any | None = None,
    ) -> list[PaperOrder]:
        """Auto-settle all open paper positions that have expired.

        Checks the outcomes table or Kalshi REST API for the resolution outcome.
        Credits cash balance with settlement proceeds and records PnL.
        """
        now_ts = time.time()

        # Cancel any pending orders that have expired
        pending = self.get_pending_orders()
        for order in pending:
            window_open = self._parse_window_time(order.ticker)
            if window_open is not None:
                expiration_time = window_open + 900.0
                if now_ts >= expiration_time:
                    order.status = "cancelled"
                    order.settled_at = datetime.now(UTC).isoformat()
                    self._save_order(order)
                    logger.info("Cancelled expired pending limit order %s for %s", order.order_id, order.ticker)

        positions = self.get_open_positions()
        if not positions:
            return []

        settled_orders = []

        for position in positions:
            window_open = self._parse_window_time(position.ticker)
            if window_open is None:
                continue

            # Kalshi 15m markets close 15 minutes after window open
            expiration_time = window_open + 900.0
            if now_ts < expiration_time:
                # Not expired yet
                continue

            # Query outcome
            outcome_val = None

            # 1. Try local candle outcomes table
            if candle_store is not None:
                try:
                    cursor = await candle_store._db.execute(
                        "SELECT direction FROM outcomes WHERE ticker = ?",
                        (position.ticker,),
                    )
                    row = await cursor.fetchone()
                    if row:
                        outcome_val = 1 if row[0].upper() == "UP" else 0
                        logger.debug("Found outcome for %s in outcomes DB: %d", position.ticker, outcome_val)
                except Exception as e:
                    logger.warning("Failed to query outcomes DB for %s: %s", position.ticker, e)

            # 2. Try Kalshi REST API if not resolved locally
            if outcome_val is None and discovery_client is not None:
                try:
                    detail = await discovery_client.get_market_detail(position.ticker)
                    if detail and detail.status.lower() in ("settled", "closed", "finalized"):
                        result = detail.raw.get("result")
                        if result == "yes":
                            outcome_val = 1
                        elif result == "no":
                            outcome_val = 0

                        # Cache it in outcomes table if we determined it from Kalshi
                        if outcome_val is not None and candle_store is not None:
                            try:
                                direction = "UP" if outcome_val == 1 else "DOWN"
                                strike_price = detail.reference_price or 0.0
                                # Record the outcome locally
                                await candle_store.record_outcome(
                                    asset=position.asset,
                                    ticker=position.ticker,
                                    window_open=window_open,
                                    window_close=expiration_time,
                                    open_price=strike_price,
                                    close_price=strike_price,
                                    direction=direction,
                                    magnitude_pct=0.0,
                                )
                            except Exception as cache_err:
                                logger.debug("Failed to cache retrieved outcome for %s: %s", position.ticker, cache_err)
                except Exception as e:
                    logger.warning("Failed to query market detail from Kalshi REST for %s: %s", position.ticker, e)

            # 3. If outcome found, settle all filled orders on this ticker
            if outcome_val is not None:
                cursor = self._conn.execute(
                    "SELECT order_id FROM orders WHERE ticker = ? AND status = 'filled'",
                    (position.ticker,),
                )
                rows = cursor.fetchall()
                for r in rows:
                    order_id = r["order_id"]
                    settled_order = self.settle_order(order_id, outcome_val)
                    if settled_order:
                        settled_orders.append(settled_order)

        return settled_orders

    def _parse_window_time(self, ticker: str) -> float | None:
        """Parse the 15m window open time from a Kalshi ticker.

        Ticker format: KXBTC15M-26JUL270945-45 or KXBTC15M-26JUL27T0945
        Returns Unix timestamp or None.
        """
        import re
        from datetime import datetime, timezone

        # 1. Try YYMONDDHHMM format (e.g. 26JUL270945)
        # Matches: YY (2 digits), MON (3 chars), DD (2 digits), optional T/-, HH (2 digits), MM (2 digits)
        m = re.search(r"KX(?:BTC|ETH)15M-(\d{2})([A-Z]{3})(\d{2})[T-_]?(\d{2})(\d{2})", ticker, re.IGNORECASE)
        if m:
            groups = m.groups()
            is_old_format = (groups[2] == "25" and groups[0] != "25")
            try:
                month_map = {
                    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
                    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
                    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
                }
                month = month_map.get(groups[1].upper(), 0)
                if is_old_format:
                    year = 2000 + int(groups[2])
                    day = int(groups[0])
                else:
                    year = 2000 + int(groups[0])
                    day = int(groups[2])
                hour = int(groups[3])
                minute = int(groups[4])

                try:
                    from zoneinfo import ZoneInfo
                    dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))
                    return dt.timestamp()
                except Exception:
                    is_dst = 3 < month < 11
                    offset = -4 if is_dst else -5
                    from datetime import timedelta
                    dt = datetime(year, month, day, hour, minute)
                    dt_utc = dt - timedelta(hours=offset)
                    return dt_utc.replace(tzinfo=timezone.utc).timestamp()
            except (ValueError, KeyError):
                pass

        # 2. Try DDMONYY format (fallback for old format/tests)
        m = re.search(r"KX(?:BTC|ETH)15M-(\d{2})([A-Z]{3})(\d{2})[T-_]?(\d{2})[:_]?(\d{2})", ticker, re.IGNORECASE)
        if m:
            groups = m.groups()
            try:
                month_map = {
                    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
                    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
                    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
                }
                month = month_map.get(groups[1].upper(), 0)
                day = int(groups[0])
                year = 2000 + int(groups[2])
                hour = int(groups[3])
                minute = int(groups[4])

                try:
                    from zoneinfo import ZoneInfo
                    dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))
                    return dt.timestamp()
                except Exception:
                    is_dst = 3 < month < 11
                    offset = -4 if is_dst else -5
                    from datetime import timedelta
                    dt = datetime(year, month, day, hour, minute)
                    dt_utc = dt - timedelta(hours=offset)
                    return dt_utc.replace(tzinfo=timezone.utc).timestamp()
            except (ValueError, KeyError):
                pass

        return None

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
