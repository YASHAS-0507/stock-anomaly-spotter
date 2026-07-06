"""
pattern_discovery.py
--------------------
Discovers which conditions produce the best trading results.
"""

from collections import defaultdict
from analytics.trade_analyzer import generate_mock_trades


def _parse_hour(ts: str) -> int:
    try:
        return int(ts.split(" ")[1].split(":")[0])
    except Exception:
        return 10


def _parse_weekday(ts: str) -> str:
    try:
        from datetime import datetime
        dt = datetime.strptime(ts.replace(" IST", ""), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%A")
    except Exception:
        return "Monday"


def _group_stats(trades: list, key_fn) -> list:
    groups: dict = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl_sum": 0.0})
    for t in trades:
        k = key_fn(t)
        g = groups[k]
        g["wins"]    += 1 if float(t.get("pnl", 0)) > 0 else 0
        g["losses"]  += 0 if float(t.get("pnl", 0)) > 0 else 1
        g["pnl_sum"] += float(t.get("pnl", 0))
    result = []
    for k, g in groups.items():
        count = g["wins"] + g["losses"]
        result.append({
            "key":      k,
            "trades":   count,
            "win_rate": round(g["wins"] / count, 4) if count else 0.0,
            "avg_pnl":  round(g["pnl_sum"] / count, 2) if count else 0.0,
        })
    return sorted(result, key=lambda x: x["win_rate"], reverse=True)


class PatternDiscovery:

    def discover(self, trades: list) -> dict:
        source = "real"
        if not trades:
            trades = generate_mock_trades()
            source = "mock"

        # Time windows: hour buckets
        time_stats = _group_stats(
            trades,
            lambda t: f"{_parse_hour(t.get('opened_at',''))//1:02d}:00-"
                      f"{_parse_hour(t.get('opened_at',''))//1+1:02d}:00"
        )

        # Setup breakdown
        setup_stats = _group_stats(trades, lambda t: t.get("setup_type", "UNKNOWN"))

        # Ticker breakdown
        ticker_stats = _group_stats(trades, lambda t: t.get("ticker", "UNKNOWN"))

        # Day of week
        dow_stats_raw = _group_stats(trades, lambda t: _parse_weekday(t.get("opened_at", "")))
        _DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        day_of_week = {
            s["key"]: {
                "win_rate": s["win_rate"],
                "avg_pnl":  s["avg_pnl"],
                "count":    s["trades"],
            }
            for s in dow_stats_raw
            if s["key"] in _DAY_ORDER
        }
        # Ensure all weekdays present
        for d in _DAY_ORDER:
            if d not in day_of_week:
                day_of_week[d] = {"win_rate": 0.0, "avg_pnl": 0.0, "count": 0}

        # Regime performance (from trade metadata if present)
        regime_map: dict = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl_sum": 0.0})
        for t in trades:
            r = t.get("regime", "UNKNOWN")
            g = regime_map[r]
            g["wins"]    += 1 if float(t.get("pnl", 0)) > 0 else 0
            g["losses"]  += 0 if float(t.get("pnl", 0)) > 0 else 1
            g["pnl_sum"] += float(t.get("pnl", 0))

        # If mock data has no regime field, synthesize from setup type
        if list(regime_map.keys()) == ["UNKNOWN"]:
            regime_map = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl_sum": 0.0})
            _SETUP_REGIME = {
                "ORB_BREAKOUT":        "BREAKOUT",
                "VWAP_BOUNCE":         "RANGING",
                "TREND_CONTINUATION":  "TRENDING_UP",
                "NEWS_CATALYST":       "HIGH_VOLATILITY",
            }
            for t in trades:
                r = _SETUP_REGIME.get(t.get("setup_type", ""), "TRENDING_UP")
                g = regime_map[r]
                g["wins"]    += 1 if float(t.get("pnl", 0)) > 0 else 0
                g["losses"]  += 0 if float(t.get("pnl", 0)) > 0 else 1
                g["pnl_sum"] += float(t.get("pnl", 0))

        regime_performance = {}
        for r, g in regime_map.items():
            count = g["wins"] + g["losses"]
            regime_performance[r] = {
                "win_rate": round(g["wins"] / count, 4) if count else 0.0,
                "avg_pnl":  round(g["pnl_sum"] / count, 2) if count else 0.0,
                "count":    count,
            }

        # VIX performance (mock: split by position in date-sorted trades)
        total = len(trades)
        vix_performance = {
            "LOW":    {"win_rate": 0.0, "avg_pnl": 0.0, "count": 0},
            "NORMAL": {"win_rate": 0.0, "avg_pnl": 0.0, "count": 0},
            "HIGH":   {"win_rate": 0.0, "avg_pnl": 0.0, "count": 0},
        }
        if total:
            buckets = [
                ("LOW",    trades[:total // 3]),
                ("NORMAL", trades[total // 3: 2 * total // 3]),
                ("HIGH",   trades[2 * total // 3:]),
            ]
            for vix_label, bucket in buckets:
                if not bucket:
                    continue
                bwins = sum(1 for t in bucket if float(t.get("pnl", 0)) > 0)
                bpnl  = sum(float(t.get("pnl", 0)) for t in bucket)
                vix_performance[vix_label] = {
                    "win_rate": round(bwins / len(bucket), 4),
                    "avg_pnl":  round(bpnl / len(bucket), 2),
                    "count":    len(bucket),
                }

        # Generate top 3 actionable insights
        insights = self._generate_insights(time_stats, setup_stats, ticker_stats, trades)

        return {
            "best_time_windows":  [
                {"window": s["key"], "trades": s["trades"],
                 "win_rate": s["win_rate"], "avg_pnl": s["avg_pnl"]}
                for s in time_stats[:5]
            ],
            "best_setups":  [
                {"setup": s["key"], "trades": s["trades"],
                 "win_rate": s["win_rate"], "avg_pnl": s["avg_pnl"]}
                for s in setup_stats
            ],
            "best_tickers": [
                {"ticker": s["key"], "trades": s["trades"],
                 "win_rate": s["win_rate"], "avg_pnl": s["avg_pnl"]}
                for s in ticker_stats[:10]
            ],
            "regime_performance": regime_performance,
            "vix_performance":    vix_performance,
            "day_of_week":        day_of_week,
            "insights":           insights,
            "data_source":        source,
        }

    def _generate_insights(self, time_stats, setup_stats, ticker_stats, trades) -> list:
        insights = []

        if time_stats:
            best_tw = time_stats[0]
            insights.append(
                f"{best_tw['key']} window has {best_tw['win_rate']:.0%} win rate "
                f"({best_tw['trades']} trades, avg ₹{best_tw['avg_pnl']:+.0f})"
            )

        if setup_stats:
            best_s = setup_stats[0]
            insights.append(
                f"{best_s['key'].replace('_', ' ').title()} setups lead with "
                f"{best_s['win_rate']:.0%} win rate across {best_s['trades']} trades"
            )

        if ticker_stats:
            best_t = ticker_stats[0]
            name = str(best_t.get("key", best_t.get("ticker", ""))).replace(".NS", "")
            insights.append(
                f"{name} is the top performer: {best_t['win_rate']:.0%} win rate, "
                f"avg ₹{best_t['avg_pnl']:+.0f} per trade"
            )

        # Fallback if data is sparse
        while len(insights) < 3:
            insights.append("Accumulating more trade data to surface deeper patterns.")

        return insights[:3]
