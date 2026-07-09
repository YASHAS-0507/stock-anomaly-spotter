"""
analytics.py (router)
---------------------
FastAPI router for analytics endpoints.
Auto-switches between real trade data and mock data.
Never crashes — returns empty/mock analytics on any error.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _get_trades() -> list:
    """Safely retrieve completed trades from the live broker."""
    try:
        from broker.auto_paper_broker import auto_broker
        return auto_broker.get_trade_history(limit=500)
    except Exception:
        return []


def _get_trades_today() -> list:
    """Completed trades for today's IST date."""
    try:
        from broker.auto_paper_broker import auto_broker
        from datetime import datetime, timezone, timedelta
        IST   = timezone(timedelta(hours=5, minutes=30))
        today = datetime.now(IST).strftime("%Y-%m-%d")
        return [
            t for t in auto_broker.trades
            if (t.get("closed_at") or t.get("opened_at") or "").startswith(today)
        ]
    except Exception:
        return []


def _get_portfolio() -> dict:
    try:
        from broker.auto_paper_broker import auto_broker
        return auto_broker.get_portfolio_snapshot()
    except Exception:
        return {}


# ─── endpoints ────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_analytics_summary():
    try:
        from analytics.trade_analyzer   import TradeAnalyzer
        from analytics.pattern_discovery import PatternDiscovery
        from analytics.risk_metrics      import RiskMetrics

        trades   = _get_trades()
        result   = TradeAnalyzer().analyze(trades)
        result["patterns"] = PatternDiscovery().discover(trades)
        result["risk"]     = RiskMetrics().calculate(trades)
        return result
    except Exception as exc:
        return {"error": str(exc), "data_source": "error", "total_trades": 0}


@router.get("/patterns")
def get_patterns():
    try:
        from analytics.pattern_discovery import PatternDiscovery
        trades = _get_trades()
        return PatternDiscovery().discover(trades)
    except Exception as exc:
        return {"error": str(exc), "data_source": "error", "insights": []}


@router.get("/risk")
def get_risk():
    try:
        from analytics.risk_metrics import RiskMetrics
        trades = _get_trades()
        return RiskMetrics().calculate(trades)
    except Exception as exc:
        return {"error": str(exc), "data_source": "error"}


@router.get("/equity-curve")
def get_equity_curve():
    try:
        from analytics.equity_curve import EquityCurve
        trades = _get_trades()
        return EquityCurve().build(trades)
    except Exception as exc:
        return {"error": str(exc), "data_source": "error", "data_points": []}


@router.get("/trades")
def get_trades(days: int = 30, limit: int = 500):
    """
    Return trade history from Supabase (falls back to in-memory broker trades).
    Query params:
      days  — how many calendar days back to fetch (default 30)
      limit — max rows (default 500, used for in-memory fallback)
    """
    try:
        from broker.supabase_persistence import fetch_trades_by_date_range, is_available
        if is_available():
            trades = fetch_trades_by_date_range(days=days)
            return {"source": "supabase", "count": len(trades), "trades": trades}
    except Exception:
        pass

    # Fall back to in-memory broker state
    trades = _get_trades()[:limit]
    return {"source": "memory", "count": len(trades), "trades": trades}


@router.get("/daily-report")
def get_daily_report():
    try:
        from analytics.trade_analyzer    import TradeAnalyzer
        from analytics.pattern_discovery import PatternDiscovery
        from analytics.risk_metrics      import RiskMetrics
        from analytics.daily_reporter    import DailyReporter

        trades_today = _get_trades_today()
        all_trades   = _get_trades()
        portfolio    = _get_portfolio()
        analytics    = TradeAnalyzer().analyze(all_trades)
        patterns     = PatternDiscovery().discover(all_trades)
        risk         = RiskMetrics().calculate(all_trades)
        return DailyReporter().generate_report(
            trades_today, portfolio, analytics, patterns, risk
        )
    except Exception as exc:
        return {"error": str(exc), "data_source": "error"}
