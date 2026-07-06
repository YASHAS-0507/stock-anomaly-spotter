"""
trade_analyzer.py
-----------------
Computes complete trade performance analytics.
Returns mock data when no real trades are available.
"""

import random
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

_NIFTY50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS",
    "TITAN.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "WIPRO.NS",
]
_SETUPS = ["ORB_BREAKOUT", "VWAP_BOUNCE", "TREND_CONTINUATION", "NEWS_CATALYST"]
_REASONS_WIN  = ["take_profit", "take_profit", "take_profit", "time_stop"]
_REASONS_LOSS = ["stop_loss", "stop_loss", "time_stop", "square_off"]


def generate_mock_trades(n: int = 47, seed: int = 42) -> list:
    """Deterministic mock trade history for 30 trading days."""
    rng = random.Random(seed)
    today = datetime.now(IST).date()

    # Build last 30 trading days
    days = []
    d = today
    while len(days) < 30:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()

    n_wins   = round(n * 0.54)   # 25
    n_losses = n - n_wins        # 22
    outcomes = [True] * n_wins + [False] * n_losses
    rng.shuffle(outcomes)

    trades = []
    for i, is_win in enumerate(outcomes):
        td        = rng.choice(days)
        open_h    = rng.randint(9, 13)
        open_m    = rng.randint(30 if open_h == 9 else 0, 59)
        hold_mins = rng.randint(15, 90)
        pnl_pct   = round(rng.uniform(0.8, 2.5), 2) if is_win else round(-rng.uniform(0.3, 1.2), 2)
        ticker    = rng.choice(_NIFTY50)
        setup     = rng.choice(_SETUPS)
        entry     = round(rng.uniform(300, 3500), 2)
        shares    = rng.randint(5, 40)
        exit_p    = round(entry * (1 + pnl_pct / 100), 2)
        commission = round(entry * shares * 0.0006, 2)
        pnl       = round((exit_p - entry) * shares - commission, 2)
        reason    = rng.choice(_REASONS_WIN if is_win else _REASONS_LOSS)

        opened_dt = datetime(td.year, td.month, td.day, open_h, open_m, rng.randint(0, 59), tzinfo=IST)
        closed_dt = opened_dt + timedelta(minutes=hold_mins)

        trades.append({
            "trade_id":         f"TRD-MOCK-{i+1:03d}",
            "ticker":           ticker,
            "setup_type":       setup,
            "shares":           shares,
            "entry_price":      entry,
            "fill_price":       entry,
            "exit_price":       exit_p,
            "pnl":              pnl,
            "pnl_pct":          pnl_pct,
            "commission_total": commission,
            "duration_minutes": hold_mins,
            "close_reason":     reason,
            "opened_at":        opened_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
            "closed_at":        closed_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        })
    return trades


def _pnl_pct(t: dict) -> float:
    """Compute or return pnl_pct for a trade."""
    if "pnl_pct" in t:
        return float(t["pnl_pct"])
    entry = float(t.get("entry_price") or t.get("fill_price") or 0)
    exit_ = float(t.get("exit_price") or 0)
    if entry > 0 and exit_ > 0:
        return (exit_ - entry) / entry * 100
    # Fallback via pnl / position_value
    pnl    = float(t.get("pnl", 0))
    shares = int(t.get("shares", 1)) or 1
    if entry > 0:
        return pnl / (entry * shares) * 100
    return 0.0


def _hold_minutes(t: dict) -> float:
    if "duration_minutes" in t and t["duration_minutes"]:
        return float(t["duration_minutes"])
    if "duration_hours" in t and t["duration_hours"]:
        return float(t["duration_hours"]) * 60
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        o = datetime.strptime(t["opened_at"].replace(" IST", ""), fmt)
        c = datetime.strptime(t["closed_at"].replace(" IST", ""), fmt)
        return (c - o).total_seconds() / 60
    except Exception:
        return 30.0


class TradeAnalyzer:

    def analyze(self, trades: list) -> dict:
        source = "real"
        if not trades:
            trades = generate_mock_trades()
            source = "mock"

        total  = len(trades)
        wins   = [t for t in trades if float(t.get("pnl", 0)) > 0]
        losses = [t for t in trades if float(t.get("pnl", 0)) <= 0]

        win_rate = len(wins) / total if total else 0.0

        gross_profit = sum(float(t["pnl"]) for t in wins)
        gross_loss   = abs(sum(float(t["pnl"]) for t in losses))
        total_pnl    = sum(float(t.get("pnl", 0)) for t in trades)
        total_comm   = sum(float(t.get("commission_total", 0)) for t in trades)

        avg_win_pct  = (sum(_pnl_pct(t) for t in wins)   / len(wins))   if wins   else 0.0
        avg_loss_pct = (sum(_pnl_pct(t) for t in losses) / len(losses)) if losses else 0.0

        profit_factor = (
            round(gross_profit / gross_loss, 4) if gross_loss > 0
            else (round(gross_profit, 4) if gross_profit > 0 else 0.0)
        )
        expectancy = total_pnl / total if total else 0.0

        avg_hold = (
            sum(_hold_minutes(t) for t in trades) / total if total else 0.0
        )

        sorted_trades = sorted(trades, key=lambda t: float(t.get("pnl", 0)))
        best  = sorted_trades[-1] if sorted_trades else {}
        worst = sorted_trades[0]  if sorted_trades else {}

        # Setup breakdown
        setup_map: dict = {}
        for t in trades:
            s = t.get("setup_type") or "UNKNOWN"
            if s not in setup_map:
                setup_map[s] = {"wins": 0, "losses": 0, "pnl_sum": 0.0, "count": 0}
            e = setup_map[s]
            e["count"]   += 1
            e["pnl_sum"] += float(t.get("pnl", 0))
            if float(t.get("pnl", 0)) > 0:
                e["wins"]   += 1
            else:
                e["losses"] += 1

        setup_breakdown = {
            s: {
                "wins":     d["wins"],
                "losses":   d["losses"],
                "win_rate": round(d["wins"] / d["count"], 4) if d["count"] else 0.0,
                "avg_pnl":  round(d["pnl_sum"] / d["count"], 2) if d["count"] else 0.0,
            }
            for s, d in setup_map.items()
        }

        # Exit reason breakdown
        exit_reasons: dict = {"take_profit": 0, "stop_loss": 0, "time_stop": 0, "square_off": 0}
        for t in trades:
            r = t.get("close_reason", "")
            exit_reasons[r] = exit_reasons.get(r, 0) + 1

        return {
            "total_trades":         total,
            "winning_trades":       len(wins),
            "losing_trades":        len(losses),
            "win_rate":             round(win_rate, 4),
            "avg_winner_pct":       round(avg_win_pct, 4),
            "avg_loser_pct":        round(avg_loss_pct, 4),
            "profit_factor":        profit_factor,
            "expectancy_per_trade": round(expectancy, 2),
            "total_pnl":            round(total_pnl, 2),
            "total_commission":     round(total_comm, 2),
            "net_pnl":              round(total_pnl, 2),
            "best_trade":           best,
            "worst_trade":          worst,
            "avg_hold_minutes":     round(avg_hold, 1),
            "setup_breakdown":      setup_breakdown,
            "exit_reason_breakdown": exit_reasons,
            "data_source":          source,
        }
