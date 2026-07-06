"""
risk_metrics.py
---------------
Professional risk metrics: Sharpe, Sortino, max drawdown, VaR, etc.
"""

import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from analytics.trade_analyzer import generate_mock_trades

IST = timezone(timedelta(hours=5, minutes=30))
_RF_ANNUAL  = 0.065          # 6.5% risk-free rate
_RF_DAILY   = _RF_ANNUAL / 252


def _equity_series(trades: list, initial_capital: float) -> list:
    """Build chronological equity values from trade list."""
    sorted_trades = sorted(
        trades,
        key=lambda t: t.get("closed_at", t.get("opened_at", "")),
    )
    equity = initial_capital
    series = [equity]
    for t in sorted_trades:
        equity += float(t.get("pnl", 0))
        series.append(round(equity, 2))
    return series


def _daily_returns(trades: list, initial_capital: float) -> list:
    """Group P&L by date and return daily return fractions."""
    day_pnl: dict = defaultdict(float)
    for t in trades:
        ts = t.get("closed_at", t.get("opened_at", ""))
        day = ts[:10] if ts else "2026-01-01"
        day_pnl[day] += float(t.get("pnl", 0))
    equity = initial_capital
    returns = []
    for day in sorted(day_pnl):
        ret = day_pnl[day] / equity if equity > 0 else 0.0
        returns.append(ret)
        equity += day_pnl[day]
    return returns


def _sharpe(daily_returns: list) -> float:
    if len(daily_returns) < 2:
        return 0.0
    n    = len(daily_returns)
    mean = sum(daily_returns) / n
    var  = sum((r - mean) ** 2 for r in daily_returns) / (n - 1)
    std  = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    return round((mean - _RF_DAILY) / std * math.sqrt(252), 4)


def _sortino(daily_returns: list) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean  = sum(daily_returns) / len(daily_returns)
    downs = [min(r - _RF_DAILY, 0.0) for r in daily_returns]
    dvar  = sum(d ** 2 for d in downs) / len(downs)
    dstd  = math.sqrt(dvar) if dvar > 0 else 0.0
    if dstd == 0:
        return 0.0
    return round((mean - _RF_DAILY) / dstd * math.sqrt(252), 4)


def _max_drawdown(equity_series: list):
    if not equity_series:
        return 0.0, 0.0
    peak = equity_series[0]
    max_dd_pct = 0.0
    max_dd_amt = 0.0
    for eq in equity_series:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd_pct = (peak - eq) / peak * 100
            dd_amt = peak - eq
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_amt = dd_amt
    return round(max_dd_pct, 4), round(max_dd_amt, 2)


def _consecutive_runs(trades: list):
    max_wins = max_losses = cur_wins = cur_losses = 0
    for t in trades:
        if float(t.get("pnl", 0)) > 0:
            cur_wins  += 1
            cur_losses = 0
        else:
            cur_losses += 1
            cur_wins   = 0
        max_wins   = max(max_wins,   cur_wins)
        max_losses = max(max_losses, cur_losses)
    return max_wins, max_losses


def _var_95(daily_returns: list) -> float:
    if not daily_returns:
        return 0.0
    sorted_r = sorted(daily_returns)
    idx = max(0, int(len(sorted_r) * 0.05) - 1)
    return round(abs(sorted_r[idx]) * 100, 4)


def _risk_rating(sharpe: float, max_dd: float) -> str:
    if sharpe >= 1.5 and max_dd < 5:
        return "LOW"
    if sharpe >= 0.5 and max_dd < 15:
        return "MEDIUM"
    if sharpe >= 0.0 and max_dd < 30:
        return "HIGH"
    return "EXTREME"


class RiskMetrics:

    def calculate(self, trades: list, initial_capital: float = 100_000.0) -> dict:
        source = "real"
        if not trades:
            trades = generate_mock_trades()
            source = "mock"

        eq_series    = _equity_series(trades, initial_capital)
        daily_rets   = _daily_returns(trades, initial_capital)
        sharpe       = _sharpe(daily_rets)
        sortino      = _sortino(daily_rets)
        max_dd_pct, max_dd_amt = _max_drawdown(eq_series)
        max_wins, max_losses   = _consecutive_runs(trades)
        var_95 = _var_95(daily_rets)

        peak_eq    = max(eq_series) if eq_series else initial_capital
        final_eq   = eq_series[-1]  if eq_series else initial_capital
        total_ret  = (final_eq - initial_capital) / initial_capital * 100

        # Recovery factor: total_return / max_drawdown
        recovery_factor = (
            round(total_ret / max_dd_pct, 4) if max_dd_pct > 0 else 0.0
        )

        # Calmar ratio: annualized return / max drawdown
        n_days = len(daily_rets) or 1
        ann_ret = total_ret * (252 / n_days)
        calmar  = round(ann_ret / max_dd_pct, 4) if max_dd_pct > 0 else 0.0

        # Equity curve data points (summarised by date)
        eq_points = self._build_eq_points(trades, initial_capital)

        return {
            "sharpe_ratio":          sharpe,
            "sortino_ratio":         sortino,
            "max_drawdown_pct":      max_dd_pct,
            "max_drawdown_amount":   max_dd_amt,
            "max_consecutive_losses": max_losses,
            "max_consecutive_wins":  max_wins,
            "recovery_factor":       recovery_factor,
            "calmar_ratio":          calmar,
            "daily_var_95":          var_95,
            "equity_curve":          eq_points,
            "risk_rating":           _risk_rating(sharpe, max_dd_pct),
            "data_source":           source,
        }

    def _build_eq_points(self, trades: list, initial_capital: float) -> list:
        sorted_trades = sorted(
            trades,
            key=lambda t: t.get("closed_at", t.get("opened_at", "")),
        )
        equity = initial_capital
        peak   = initial_capital
        points = [{"date": "start", "equity": round(equity, 2), "drawdown_pct": 0.0}]
        count  = 0
        for t in sorted_trades:
            equity += float(t.get("pnl", 0))
            count  += 1
            if equity > peak:
                peak = equity
            dd = round((peak - equity) / peak * 100, 4) if peak > 0 else 0.0
            date = (t.get("closed_at") or t.get("opened_at") or "")[:10]
            points.append({
                "date":          date,
                "equity":        round(equity, 2),
                "drawdown_pct":  dd,
                "trade_count":   count,
            })
        return points
