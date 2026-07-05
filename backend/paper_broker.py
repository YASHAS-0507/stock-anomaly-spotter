"""
paper_broker.py
---------------
Virtual broker that simulates NSE trade execution in paper-trading mode.
No real money. No real broker API. Commission and slippage are modelled
at realistic NSE rates.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))

INITIAL_CAPITAL = 100_000.0   # ₹1,00,000 starting capital


def _ist_now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _parse_ist(ts: str) -> Optional[datetime]:
    try:
        return datetime.strptime(ts.replace(" IST", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    except Exception:
        return None


def _order_id(symbol: str) -> str:
    ts = datetime.now(IST).strftime("%Y%m%d-%H%M%S%f")[:19]
    return f"ORD-{symbol.upper().replace('.', '_')}-{ts}"


class PaperBroker:
    def __init__(self):
        self.commission_rate = 0.0003   # 0.03% per side (realistic NSE)
        self.slippage_rate   = 0.0001   # 0.01% slippage simulation
        self._reset_state()

    def _reset_state(self):
        self.portfolio = {
            "cash":         INITIAL_CAPITAL,
            "positions":    {},      # symbol → position dict
            "orders":       [],      # all orders ever placed
            "trades":       [],      # completed trades
            "equity_curve": [],      # daily snapshots (Phase 2.5+)
            "created_at":   _ist_now(),
        }

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        stop_loss: float,
        take_profit: float,
        trade_id: str,
        reason: str = "",
    ) -> dict:
        """Simulate order placement with slippage and commission."""
        ts = _ist_now()
        oid = _order_id(symbol)

        # ── Basic validation
        if quantity <= 0 or price <= 0:
            rejection = "Invalid quantity or price"
            order = self._build_order(oid, symbol, action, quantity, price, price,
                                      "rejected", rejection, 0.0, 0.0, ts, trade_id)
            self.portfolio["orders"].append(order)
            return {"success": False, "rejection_reason": rejection, "order": order}

        if action == "BUY":
            fill_price  = round(price * (1 + self.slippage_rate), 4)
            commission  = round(fill_price * quantity * self.commission_rate, 2)
            total_cost  = round(fill_price * quantity + commission, 2)

            if self.portfolio["cash"] < total_cost:
                rejection = (f"Insufficient cash: need ₹{total_cost:.2f}, "
                             f"have ₹{self.portfolio['cash']:.2f}")
                order = self._build_order(oid, symbol, action, quantity, price, fill_price,
                                          "rejected", rejection, commission, fill_price - price, ts, trade_id)
                self.portfolio["orders"].append(order)
                return {"success": False, "rejection_reason": rejection, "order": order}

            self.portfolio["cash"] = round(self.portfolio["cash"] - total_cost, 2)

            position = {
                "symbol":             symbol.upper(),
                "action":             "BUY",
                "quantity":           quantity,
                "entry_price":        price,
                "fill_price":         fill_price,
                "stop_loss":          stop_loss,
                "take_profit":        take_profit,
                "current_price":      fill_price,
                "unrealized_pnl":     0.0,
                "unrealized_pnl_pct": 0.0,
                "commission_paid":    commission,
                "trade_id":           trade_id,
                "opened_at":          ts,
                "reason":             reason,
            }
            self.portfolio["positions"][symbol.upper()] = position

            order = self._build_order(oid, symbol, action, quantity, price, fill_price,
                                      "filled", None, commission, fill_price - price, ts, trade_id)
            self.portfolio["orders"].append(order)
            return {"success": True, "order": order, "position": position}

        elif action == "SELL":
            sym = symbol.upper()
            if sym not in self.portfolio["positions"]:
                rejection = f"No open position for {sym}"
                order = self._build_order(oid, symbol, action, quantity, price, price,
                                          "rejected", rejection, 0.0, 0.0, ts, trade_id)
                self.portfolio["orders"].append(order)
                return {"success": False, "rejection_reason": rejection, "order": order}

            pos = self.portfolio["positions"][sym]
            fill_price       = round(price * (1 - self.slippage_rate), 4)
            commission_close = round(fill_price * quantity * self.commission_rate, 2)
            commission_total = round(pos["commission_paid"] + commission_close, 2)

            gross_pnl = round((fill_price - pos["fill_price"]) * quantity, 2)
            pnl       = round(gross_pnl - commission_total, 2)
            pnl_pct   = round(pnl / (pos["fill_price"] * quantity) * 100, 4) if pos["fill_price"] * quantity else 0.0

            opened_dt  = _parse_ist(pos["opened_at"])
            closed_dt  = datetime.now(IST)
            dur_hours  = round((closed_dt - opened_dt).total_seconds() / 3600, 2) if opened_dt else 0.0

            trade_record = {
                "trade_id":         trade_id,
                "symbol":           sym,
                "action":           "BUY→SELL",
                "quantity":         quantity,
                "entry_price":      pos["entry_price"],
                "exit_price":       fill_price,
                "pnl":              pnl,
                "pnl_pct":          pnl_pct,
                "commission_total": commission_total,
                "duration_hours":   dur_hours,
                "close_reason":     "manual",
                "opened_at":        pos["opened_at"],
                "closed_at":        ts,
            }
            self.portfolio["trades"].append(trade_record)
            del self.portfolio["positions"][sym]

            proceeds = round(fill_price * quantity - commission_close, 2)
            self.portfolio["cash"] = round(self.portfolio["cash"] + proceeds, 2)

            order = self._build_order(oid, symbol, action, quantity, price, fill_price,
                                      "filled", None, commission_close, price - fill_price, ts, trade_id)
            self.portfolio["orders"].append(order)
            return {"success": True, "order": order, "trade": trade_record}

        rejection = f"Unknown action: {action}"
        order = self._build_order(oid, symbol, action, quantity, price, price,
                                  "rejected", rejection, 0.0, 0.0, ts, trade_id)
        self.portfolio["orders"].append(order)
        return {"success": False, "rejection_reason": rejection, "order": order}

    def check_positions(self, current_prices: dict) -> list:
        """Check open positions vs current prices; auto-close SL/TP hits."""
        auto_closed = []
        for sym, pos in list(self.portfolio["positions"].items()):
            cp = current_prices.get(sym)
            if cp is None:
                continue

            pos["current_price"]      = round(float(cp), 4)
            pos["unrealized_pnl"]     = round((float(cp) - pos["fill_price"]) * pos["quantity"], 2)
            pos["unrealized_pnl_pct"] = round(pos["unrealized_pnl"] / (pos["fill_price"] * pos["quantity"]) * 100, 4) \
                                         if pos["fill_price"] * pos["quantity"] else 0.0

            hit_sl = pos["action"] == "BUY" and float(cp) <= pos["stop_loss"]
            hit_tp = pos["action"] == "BUY" and float(cp) >= pos["take_profit"]

            if hit_sl or hit_tp:
                close_reason = "stop_loss" if hit_sl else "take_profit"
                result = self._auto_close(sym, float(cp), close_reason)
                if result:
                    auto_closed.append(result)

        return auto_closed

    def get_portfolio_snapshot(self, current_prices: dict = None) -> dict:
        """Return complete portfolio state with statistics."""
        if current_prices:
            for sym, pos in self.portfolio["positions"].items():
                cp = current_prices.get(sym, pos["current_price"])
                pos["current_price"]      = round(float(cp), 4)
                pos["unrealized_pnl"]     = round((float(cp) - pos["fill_price"]) * pos["quantity"], 2)
                pos["unrealized_pnl_pct"] = round(pos["unrealized_pnl"] / (pos["fill_price"] * pos["quantity"]) * 100, 4) \
                                             if pos["fill_price"] * pos["quantity"] else 0.0

        cash     = self.portfolio["cash"]
        invested = sum(p["fill_price"] * p["quantity"] for p in self.portfolio["positions"].values())
        mkt_val  = sum(p["current_price"] * p["quantity"] for p in self.portfolio["positions"].values())
        total    = round(cash + mkt_val, 2)
        total_pnl     = round(total - INITIAL_CAPITAL, 2)
        total_pnl_pct = round(total_pnl / INITIAL_CAPITAL * 100, 4)

        trades     = self.portfolio["trades"]
        wins       = [t for t in trades if t["pnl"] > 0]
        losses     = [t for t in trades if t["pnl"] <= 0]
        win_count  = len(wins)
        loss_count = len(losses)
        win_rate   = round(win_count / len(trades) * 100, 1) if trades else 0.0
        avg_profit = round(sum(t["pnl"] for t in wins) / win_count, 2) if wins else 0.0
        avg_loss   = round(sum(t["pnl"] for t in losses) / loss_count, 2) if losses else 0.0
        gross_wins = sum(t["pnl"] for t in wins) or 0
        gross_loss = abs(sum(t["pnl"] for t in losses)) or 1
        profit_factor = round(gross_wins / gross_loss, 2) if gross_loss else 0.0
        best  = max((t["pnl"] for t in trades), default=0.0)
        worst = min((t["pnl"] for t in trades), default=0.0)

        positions_list = list(self.portfolio["positions"].values())

        return {
            "cash":            round(cash, 2),
            "invested":        round(invested, 2),
            "market_value":    round(mkt_val, 2),
            "total_value":     total,
            "total_pnl":       total_pnl,
            "total_pnl_pct":   total_pnl_pct,
            "positions":       positions_list,
            "open_count":      len(positions_list),
            "total_trades":    len(trades),
            "win_count":       win_count,
            "loss_count":      loss_count,
            "win_rate":        win_rate,
            "avg_profit":      avg_profit,
            "avg_loss":        avg_loss,
            "profit_factor":   profit_factor,
            "best_trade":      round(best, 2),
            "worst_trade":     round(worst, 2),
            "initial_capital": INITIAL_CAPITAL,
            "created_at":      self.portfolio["created_at"],
        }

    def get_trade_history(self, limit: int = 50) -> list:
        """Return last N completed trades, newest first."""
        return list(reversed(self.portfolio["trades"]))[:limit]

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self._reset_state()

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _build_order(self, oid, symbol, action, quantity, requested_price, fill_price,
                     status, rejection_reason, commission, slippage, ts, trade_id) -> dict:
        return {
            "order_id":         oid,
            "symbol":           symbol.upper(),
            "action":           action,
            "quantity":         quantity,
            "requested_price":  round(requested_price, 4),
            "fill_price":       round(fill_price, 4),
            "status":           status,
            "rejection_reason": rejection_reason,
            "commission":       round(commission, 2),
            "slippage":         round(abs(slippage), 4),
            "timestamp":        ts,
            "trade_id":         trade_id,
        }

    def _auto_close(self, symbol: str, current_price: float, reason: str) -> Optional[dict]:
        """Auto-close a position that hit SL or TP."""
        pos = self.portfolio["positions"].get(symbol)
        if not pos:
            return None

        ts               = _ist_now()
        fill_price       = round(current_price * (1 - self.slippage_rate), 4)
        commission_close = round(fill_price * pos["quantity"] * self.commission_rate, 2)
        commission_total = round(pos["commission_paid"] + commission_close, 2)
        gross_pnl        = round((fill_price - pos["fill_price"]) * pos["quantity"], 2)
        pnl              = round(gross_pnl - commission_total, 2)
        pnl_pct          = round(pnl / (pos["fill_price"] * pos["quantity"]) * 100, 4) \
                           if pos["fill_price"] * pos["quantity"] else 0.0

        opened_dt  = _parse_ist(pos["opened_at"])
        dur_hours  = round((datetime.now(IST) - opened_dt).total_seconds() / 3600, 2) if opened_dt else 0.0

        trade_record = {
            "trade_id":         pos["trade_id"],
            "symbol":           symbol,
            "action":           "BUY→SELL",
            "quantity":         pos["quantity"],
            "entry_price":      pos["entry_price"],
            "exit_price":       fill_price,
            "pnl":              pnl,
            "pnl_pct":          pnl_pct,
            "commission_total": commission_total,
            "duration_hours":   dur_hours,
            "close_reason":     reason,
            "opened_at":        pos["opened_at"],
            "closed_at":        ts,
        }
        self.portfolio["trades"].append(trade_record)

        proceeds = round(fill_price * pos["quantity"] - commission_close, 2)
        self.portfolio["cash"] = round(self.portfolio["cash"] + proceeds, 2)
        del self.portfolio["positions"][symbol]

        return trade_record


# Singleton
paper_broker = PaperBroker()
