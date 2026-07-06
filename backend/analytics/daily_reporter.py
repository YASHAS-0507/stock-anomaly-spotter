"""
daily_reporter.py
-----------------
Generates the daily session summary report.
"""

from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


class DailyReporter:

    def generate_report(
        self,
        trades_today: list,
        portfolio: dict,
        analytics: dict,
        patterns: dict,
        risk: dict,
    ) -> dict:
        source    = "real" if trades_today else "mock"
        today_str = datetime.now(IST).strftime("%Y-%m-%d")

        # Today's metrics
        n_today = len(trades_today)
        wins_today   = [t for t in trades_today if float(t.get("pnl", 0)) > 0]
        pnl_today    = sum(float(t.get("pnl", 0)) for t in trades_today)
        wr_today     = len(wins_today) / n_today if n_today else 0.0

        sorted_today = sorted(trades_today, key=lambda t: float(t.get("pnl", 0)))
        best_today   = sorted_today[-1] if sorted_today else None
        worst_today  = sorted_today[0]  if sorted_today else None

        # Cumulative from analytics
        cum = {
            "total_trades":   analytics.get("total_trades",   0),
            "overall_win_rate": analytics.get("win_rate",     0.0),
            "total_pnl":      analytics.get("total_pnl",      0.0),
            "profit_factor":  analytics.get("profit_factor",  0.0),
        }

        # Top insight from patterns
        insights   = patterns.get("insights", [])
        top_insight = insights[0] if insights else "Keep following the system rules."

        # Tomorrow suggestion
        best_setups = patterns.get("best_setups", [])
        best_tw     = patterns.get("best_time_windows", [])
        if best_setups and best_tw:
            setup_name = best_setups[0].get("setup", "").replace("_", " ").title()
            window     = best_tw[0].get("window", "10:00-11:00")
            tomorrow   = f"Focus on {setup_name} setups in the {window} window — highest edge historically."
        else:
            tomorrow = "Stick to the plan; review setup filters if win rate falls below 45%."

        # Session summary sentence
        pnl_sign = "+" if pnl_today >= 0 else ""
        if n_today:
            summary = (
                f"Session {today_str}: {n_today} trades, "
                f"P&L {pnl_sign}₹{pnl_today:.0f}, "
                f"win rate {wr_today:.0%}"
            )
        else:
            summary = f"Session {today_str}: No trades executed today (mock data)."

        # Risk alert
        max_dd   = risk.get("max_drawdown_pct", 0.0)
        sharpe   = risk.get("sharpe_ratio", 1.0)
        risk_alert = None
        if max_dd > 15:
            risk_alert = f"Max drawdown {max_dd:.1f}% — consider reducing position size."
        elif sharpe < 0.5:
            risk_alert = f"Sharpe ratio {sharpe:.2f} is below threshold — review strategy."

        return {
            "date":               today_str,
            "session_summary":    summary,
            "trades_today":       n_today,
            "pnl_today":          round(pnl_today, 2),
            "win_rate_today":     round(wr_today, 4),
            "best_trade_today":   best_today,
            "worst_trade_today":  worst_today,
            "cumulative_stats":   cum,
            "top_insight":        top_insight,
            "tomorrow_suggestion": tomorrow,
            "risk_alert":         risk_alert,
            "data_source":        source,
        }
