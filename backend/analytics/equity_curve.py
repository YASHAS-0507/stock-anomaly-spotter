"""
equity_curve.py
---------------
Builds a full equity curve from trade history.
"""

from analytics.trade_analyzer import generate_mock_trades


class EquityCurve:

    def build(self, trades: list, initial_capital: float = 100_000.0) -> dict:
        source = "real"
        if not trades:
            trades = generate_mock_trades()
            source = "mock"

        sorted_trades = sorted(
            trades,
            key=lambda t: t.get("closed_at", t.get("opened_at", "")),
        )

        equity = initial_capital
        peak   = initial_capital
        points = []
        count  = 0

        for t in sorted_trades:
            equity += float(t.get("pnl", 0))
            count  += 1
            if equity > peak:
                peak = equity
            dd = round((peak - equity) / peak * 100, 4) if peak > 0 else 0.0
            ts = t.get("closed_at") or t.get("opened_at") or ""
            points.append({
                "timestamp":    ts,
                "equity":       round(equity, 2),
                "drawdown_pct": dd,
                "trade_count":  count,
            })

        peak_eq    = max((p["equity"] for p in points), default=initial_capital)
        current_eq = points[-1]["equity"] if points else initial_capital
        total_ret  = round((current_eq - initial_capital) / initial_capital * 100, 4)

        return {
            "data_points":      points,
            "peak_equity":      round(peak_eq, 2),
            "current_equity":   round(current_eq, 2),
            "total_return_pct": total_ret,
            "data_source":      source,
        }
