"""
auto_paper_broker.py
--------------------
Autonomous paper broker: executes BUY signals from the decision engine,
monitors open positions for SL/TP/time-stop on every price tick, and
performs a hard square-off at 15:15 IST.

Thread-safe — all position mutations acquire self._lock.
"""

import logging
import threading
import uuid
from datetime import datetime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

_INITIAL_CAPITAL    = 100_000.0
_DEFAULT_HOLD_MINS  = 90          # fallback max_hold_minutes if sizing omits it


def _ist_now_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _parse_ist(ts: str) -> Optional[datetime]:
    try:
        return IST.localize(datetime.strptime(ts.replace(" IST", ""), "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None


class AutoPaperBroker:
    """Autonomous paper broker with SL/TP monitoring and daily risk limits."""

    def __init__(self):
        self.capital          = _INITIAL_CAPITAL
        self.positions: dict  = {}   # ticker → position dict
        self.trades:    list  = []   # completed trade dicts
        self.orders:    list  = []   # all order attempts
        self.daily_pnl        = 0.0
        self.daily_loss       = 0.0
        self.commission_rate  = 0.0003   # 0.03% per side
        self.slippage_rate    = 0.0001   # 0.01% slippage
        self.max_daily_loss       = 3_000.0
        self.emergency_stop_loss  = 5_000.0
        self._paused           = False
        self._emergency_stopped = False
        self._lock             = threading.Lock()

    # ──────────────────────────────────────────────────────
    # Order execution
    # ──────────────────────────────────────────────────────

    def execute_signal(
        self,
        signal: dict,
        entry_price: float,
        sizing: dict,
    ) -> dict:
        """
        Execute a BUY signal from IntradayDecisionEngine.

        Parameters
        ----------
        signal       : decision dict (keys: signal, setup_type, ticker, trade_id)
        entry_price  : current market price
        sizing       : dict with shares, stop_loss, take_profit_1/2, risk_amount,
                       max_hold_minutes (optional)

        Returns
        -------
        dict with status ("filled"|"rejected"), fill_price, trade_id, reason
        """
        ticker   = signal.get("ticker", "UNKNOWN")
        trade_id = signal.get("trade_id") or f"TRD-{uuid.uuid4().hex[:8].upper()}"

        # ── Pre-flight checks ──────────────────────────────────────────────
        if self._paused:
            return self._reject(trade_id, ticker, "Broker is paused")

        if self._emergency_stopped:
            return self._reject(trade_id, ticker, "Emergency stop active — no new trades")

        limit_check = self.check_daily_limits()
        if not limit_check["can_trade"]:
            return self._reject(trade_id, ticker, limit_check["reason"])

        shares = int(sizing.get("shares", 0))
        if shares <= 0 or entry_price <= 0:
            return self._reject(trade_id, ticker, "Invalid shares or entry price")

        fill_price    = round(entry_price * (1 + self.slippage_rate), 4)
        commission    = round(fill_price * shares * self.commission_rate, 2)
        total_cost    = round(fill_price * shares + commission, 2)

        with self._lock:
            if self.capital < total_cost:
                return self._reject(
                    trade_id, ticker,
                    f"Insufficient capital: need ₹{total_cost:.2f}, have ₹{self.capital:.2f}",
                )

            self.capital = round(self.capital - total_cost, 2)

            position = {
                "ticker":           ticker,
                "entry_price":      entry_price,
                "fill_price":       fill_price,
                "stop_loss":        float(sizing.get("stop_loss", entry_price * 0.98)),
                "take_profit_1":    float(sizing.get("take_profit_1", entry_price * 1.02)),
                "take_profit_2":    float(sizing.get("take_profit_2", entry_price * 1.04)),
                "shares":           shares,
                "position_value":   round(fill_price * shares, 2),
                "unrealized_pnl":   0.0,
                "commission_paid":  commission,
                "trade_id":         trade_id,
                "opened_at":        _ist_now_str(),
                "setup_type":       signal.get("setup_type", ""),
                "max_hold_minutes": int(sizing.get("max_hold_minutes", _DEFAULT_HOLD_MINS)),
            }
            self.positions[ticker] = position

            order = {
                "trade_id":    trade_id,
                "ticker":      ticker,
                "status":      "filled",
                "fill_price":  fill_price,
                "shares":      shares,
                "commission":  commission,
                "total_cost":  total_cost,
                "timestamp":   position["opened_at"],
            }
            self.orders.append(order)

        logger.info("[broker] Filled %s @ %.2f x%d (id=%s)", ticker, fill_price, shares, trade_id)
        return {"status": "filled", "fill_price": fill_price, "trade_id": trade_id, "reason": None}

    # ──────────────────────────────────────────────────────
    # Position monitoring
    # ──────────────────────────────────────────────────────

    def monitor_positions(self, current_prices: dict) -> list:
        """
        Check all open positions against current prices.

        Closes positions that hit SL, TP-1, or max hold time.
        Thread-safe.

        Returns list of closed trade dicts.
        """
        closed = []
        with self._lock:
            now = datetime.now(IST)
            for ticker in list(self.positions.keys()):
                pos   = self.positions[ticker]
                price = current_prices.get(ticker)
                if price is None:
                    continue

                price = float(price)
                pos["unrealized_pnl"] = round((price - pos["fill_price"]) * pos["shares"], 2)

                reason = None
                if price <= pos["stop_loss"]:
                    reason = "stop_loss"
                elif price >= pos["take_profit_1"]:
                    reason = "take_profit"
                else:
                    opened = _parse_ist(pos["opened_at"])
                    if opened:
                        held_mins = (now - opened).total_seconds() / 60.0
                        if held_mins >= pos["max_hold_minutes"]:
                            reason = "time_stop"

                if reason:
                    trade = self._close_position_locked(ticker, reason, price)
                    if trade:
                        closed.append(trade)

        return closed

    def close_position(self, ticker: str, reason: str, current_price: float) -> Optional[dict]:
        """Close a single position by ticker. Thread-safe."""
        with self._lock:
            return self._close_position_locked(ticker, reason, current_price)

    def square_off_all(self, current_prices: dict) -> list:
        """Close ALL open positions at market. Returns list of closed trades."""
        closed = []
        with self._lock:
            for ticker in list(self.positions.keys()):
                price = float(current_prices.get(ticker, self.positions[ticker]["fill_price"]))
                trade = self._close_position_locked(ticker, "square_off", price)
                if trade:
                    closed.append(trade)
        return closed

    # ──────────────────────────────────────────────────────
    # Risk controls
    # ──────────────────────────────────────────────────────

    def pause(self) -> None:
        self._paused = True
        logger.info("[broker] Paused — no new trades until resume()")

    def resume(self) -> None:
        self._paused = False
        logger.info("[broker] Resumed")

    def emergency_stop(self, current_prices: dict) -> list:
        """Square off everything and prevent any further trading."""
        logger.warning("[broker] EMERGENCY STOP triggered")
        closed = self.square_off_all(current_prices)
        self._emergency_stopped = True
        return closed

    def check_daily_limits(self) -> dict:
        """Return whether new trades are allowed given today's P&L."""
        if self.daily_loss >= self.emergency_stop_loss:
            return {
                "can_trade":  False,
                "reason":     f"Emergency stop loss hit (₹{self.daily_loss:.0f} >= ₹{self.emergency_stop_loss:.0f})",
                "daily_pnl":  self.daily_pnl,
                "daily_loss": self.daily_loss,
            }
        if self.daily_loss >= self.max_daily_loss:
            return {
                "can_trade":  False,
                "reason":     f"Daily loss limit hit (₹{self.daily_loss:.0f} >= ₹{self.max_daily_loss:.0f})",
                "daily_pnl":  self.daily_pnl,
                "daily_loss": self.daily_loss,
            }
        return {
            "can_trade":  True,
            "reason":     "Within daily limits",
            "daily_pnl":  self.daily_pnl,
            "daily_loss": self.daily_loss,
        }

    # ──────────────────────────────────────────────────────
    # Portfolio introspection
    # ──────────────────────────────────────────────────────

    def get_portfolio_snapshot(self, current_prices: dict = {}) -> dict:
        """Return full portfolio state."""
        with self._lock:
            # Refresh unrealized P&L if prices provided
            for ticker, pos in self.positions.items():
                price = current_prices.get(ticker, pos["fill_price"])
                pos["unrealized_pnl"] = round((float(price) - pos["fill_price"]) * pos["shares"], 2)

            invested    = sum(p["fill_price"] * p["shares"] for p in self.positions.values())
            unreal_pnl  = sum(p["unrealized_pnl"] for p in self.positions.values())
            total_value = round(self.capital + invested + unreal_pnl, 2)
            total_pnl   = round(total_value - _INITIAL_CAPITAL, 2)
            total_pnl_pct = round(total_pnl / _INITIAL_CAPITAL * 100, 4)

            wins   = [t for t in self.trades if t["pnl"] > 0]
            losses = [t for t in self.trades if t["pnl"] <= 0]
            win_rate = round(len(wins) / len(self.trades) * 100, 1) if self.trades else 0.0

            return {
                "cash":              round(self.capital, 2),
                "invested":          round(invested, 2),
                "total_value":       total_value,
                "total_pnl":         total_pnl,
                "total_pnl_pct":     total_pnl_pct,
                "open_positions":    list(self.positions.values()),
                "open_count":        len(self.positions),
                "total_trades":      len(self.trades),
                "win_count":         len(wins),
                "loss_count":        len(losses),
                "win_rate":          win_rate,
                "daily_pnl":         round(self.daily_pnl, 2),
                "paused":            self._paused,
                "emergency_stopped": self._emergency_stopped,
            }

    def get_trade_history(self, limit: int = 50) -> list:
        """Return last N completed trades, newest first."""
        return list(reversed(self.trades))[:limit]

    def reset(self) -> None:
        """Reset to initial state."""
        with self._lock:
            self.capital           = _INITIAL_CAPITAL
            self.positions         = {}
            self.trades            = []
            self.orders            = []
            self.daily_pnl         = 0.0
            self.daily_loss        = 0.0
            self._paused           = False
            self._emergency_stopped = False
        logger.info("[broker] Reset to initial state")

    # ──────────────────────────────────────────────────────
    # Internal helpers (call only while _lock is held)
    # ──────────────────────────────────────────────────────

    def _close_position_locked(
        self,
        ticker: str,
        reason: str,
        current_price: float,
    ) -> Optional[dict]:
        """Core close logic. Caller must hold self._lock."""
        pos = self.positions.get(ticker)
        if not pos:
            return None

        fill_price        = round(current_price * (1 - self.slippage_rate), 4)
        commission_close  = round(fill_price * pos["shares"] * self.commission_rate, 2)
        commission_total  = round(pos["commission_paid"] + commission_close, 2)
        gross_pnl         = round((fill_price - pos["fill_price"]) * pos["shares"], 2)
        pnl               = round(gross_pnl - commission_total, 2)

        opened_dt  = _parse_ist(pos["opened_at"])
        now        = datetime.now(IST)
        dur_mins   = round((now - opened_dt).total_seconds() / 60.0, 1) if opened_dt else 0.0

        trade = {
            "trade_id":         pos["trade_id"],
            "ticker":           ticker,
            "setup_type":       pos.get("setup_type", ""),
            "shares":           pos["shares"],
            "entry_price":      pos["entry_price"],
            "fill_price":       pos["fill_price"],
            "exit_price":       fill_price,
            "pnl":              pnl,
            "commission_total": commission_total,
            "duration_minutes": dur_mins,
            "close_reason":     reason,
            "opened_at":        pos["opened_at"],
            "closed_at":        _ist_now_str(),
        }
        self.trades.append(trade)

        proceeds = round(fill_price * pos["shares"] - commission_close, 2)
        self.capital = round(self.capital + proceeds, 2)

        # Update daily tracking
        self.daily_pnl = round(self.daily_pnl + pnl, 2)
        if pnl < 0:
            self.daily_loss = round(self.daily_loss + abs(pnl), 2)

        del self.positions[ticker]
        logger.info("[broker] Closed %s @ %.2f reason=%s pnl=%.2f", ticker, fill_price, reason, pnl)
        return trade

    @staticmethod
    def _reject(trade_id: str, ticker: str, reason: str) -> dict:
        logger.debug("[broker] Rejected %s (%s): %s", ticker, trade_id, reason)
        return {"status": "rejected", "fill_price": 0.0, "trade_id": trade_id, "reason": reason}


# Module-level singleton
auto_broker = AutoPaperBroker()
