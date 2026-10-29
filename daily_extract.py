"""
daily_extract.py
----------------
Fetch and merge 5-minute NSE candles from Angel One and yfinance for a watchlist.

Usage:
    python daily_extract.py               # last 5 trading weekdays
    python daily_extract.py --date 2026-10-15
    python daily_extract.py --date 2026-10-15 --date 2026-10-16

Output:
    data/candles/<SYMBOL>/5m/<YYYY-MM-DD>.json
    data/reports/<YYYY-MM-DD>.md
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Heavy network deps imported lazily inside functions so that test_merge.py
# can import the pure merge logic without needing these packages installed.
def _import_network_deps():
    global pyotp, yf, load_dotenv, SmartConnect
    import pyotp                          # noqa: PLC0415
    import yfinance as yf                 # noqa: PLC0415
    from dotenv import load_dotenv        # noqa: PLC0415
    from SmartApi import SmartConnect     # noqa: PLC0415

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

WATCHLIST = ["RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "SUNPHARMA.NS", "TITAN.NS"]

# Expected session slots 09:15 .. 15:25 IST in "HH:MM" strings
SESSION_SLOTS: list[str] = []
_t = datetime(2000, 1, 1, 9, 15)
while _t.strftime("%H:%M") <= "15:25":
    SESSION_SLOTS.append(_t.strftime("%H:%M"))
    _t += timedelta(minutes=5)

KNOWN_GAP_SLOTS = ["15:20"]
DISAGREE_THRESHOLD = 0.0005  # 0.05 %


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_tokens() -> dict[str, str]:
    """Import token map from ticker_registry without side-effects."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    from feeds.ticker_registry import NIFTY_50_TOKENS  # noqa: PLC0415
    missing = [s for s in WATCHLIST if s not in NIFTY_50_TOKENS]
    if missing:
        raise SystemExit(f"Missing tokens for: {missing}")
    return {s: NIFTY_50_TOKENS[s] for s in WATCHLIST}


def _last_n_weekdays(n: int) -> list[date]:
    days, d = [], date.today() - timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def _angel_login():
    _import_network_deps()
    load_dotenv(os.path.join("backend", ".env"))
    api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
    totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
    session = api.generateSession(
        os.environ["ANGEL_CLIENT_ID"], os.environ["ANGEL_PASSWORD"], totp
    )
    if not session.get("status"):
        raise SystemExit(f"Angel login failed: {session.get('message')}")
    return api


def _fetch_angel(api, token: str, day: date) -> list:
    """Return list of [timestamp_str, o, h, l, c, v] rows, or []."""
    resp = api.getCandleData({
        "exchange": "NSE",
        "symboltoken": token,
        "interval": "FIVE_MINUTE",
        "fromdate": day.strftime("%Y-%m-%d 09:15"),
        "todate":   day.strftime("%Y-%m-%d 15:30"),
    })
    return resp.get("data") or []


def _angel_rows_to_dict(rows: list) -> dict[str, dict]:
    """Map IST slot "HH:MM" → bar dict from Angel rows."""
    out: dict[str, dict] = {}
    for r in rows:
        ts_str = r[0]  # "2026-10-15T09:15:00+05:30"
        try:
            ts = datetime.fromisoformat(ts_str).astimezone(IST)
        except ValueError:
            continue
        slot = ts.strftime("%H:%M")
        out[slot] = {"o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
                     "c": float(r[4]), "v": int(r[5])}
    return out


def _fetch_yfinance(symbol: str, day: date) -> dict[str, dict]:
    """Map IST slot "HH:MM" → bar dict from yfinance."""
    _import_network_deps()
    start = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST)
    end   = datetime(day.year, day.month, day.day, 15, 31, tzinfo=IST)
    ticker = yf.Ticker(symbol)
    df = ticker.history(interval="5m", start=start, end=end)
    out: dict[str, dict] = {}
    if df is None or df.empty:
        return out
    for ts_idx, row in df.iterrows():
        # yfinance index may be tz-aware
        if hasattr(ts_idx, "tzinfo") and ts_idx.tzinfo is not None:
            ts_ist = ts_idx.astimezone(IST)
        else:
            ts_ist = ts_idx.replace(tzinfo=UTC).astimezone(IST)
        slot = ts_ist.strftime("%H:%M")
        out[slot] = {
            "o": float(row["Open"]),
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
            "v": int(row["Volume"]),
        }
    return out


def _pct_diff(a: float, b: float) -> float:
    mid = (abs(a) + abs(b)) / 2
    return abs(a - b) / mid if mid else 0.0


# ---------------------------------------------------------------------------
# Core merge logic (also imported by test_merge.py)
# ---------------------------------------------------------------------------

def merge_bars(
    angel: dict[str, dict],
    yfin:  dict[str, dict],
    slots: list[str] = SESSION_SLOTS,
    threshold: float = DISAGREE_THRESHOLD,
) -> tuple[list[dict], list[str], list[str], list[dict]]:
    """
    Merge two slot-keyed bar dicts.

    Returns:
        candles        – list of merged bar dicts (ts field NOT set here)
        missing_slots  – IST "HH:MM" slots absent from both sources
        zero_vol_slots – IST slots with v == 0
        disagreements  – list of {slot, field, angel_val, yf_val, pct}
    """
    candles: list[dict] = []
    missing_slots: list[str] = []
    zero_vol_slots: list[str] = []
    disagreements: list[dict] = []

    for slot in slots:
        a_bar = angel.get(slot)
        y_bar = yfin.get(slot)

        if a_bar is None and y_bar is None:
            missing_slots.append(slot)
            continue

        if a_bar is not None and y_bar is not None:
            for field in ("o", "h", "l", "c"):
                pct = _pct_diff(a_bar[field], y_bar[field])
                if pct > threshold:
                    disagreements.append({
                        "slot": slot, "field": field,
                        "angel": a_bar[field], "yf": y_bar[field],
                        "pct": round(pct * 100, 4),
                    })

        bar = a_bar if a_bar is not None else y_bar
        src = "angel" if a_bar is not None else "yfinance"
        entry: dict = {"slot": slot, "src": src, **bar}

        if bar["v"] == 0:
            zero_vol_slots.append(slot)
            entry["zero_volume"] = True

        candles.append(entry)

    return candles, missing_slots, zero_vol_slots, disagreements


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _slot_to_utc_ts(slot: str, day: date) -> str:
    """Convert IST "HH:MM" on a given date to UTC ISO-8601 string ending in Z."""
    h, m = int(slot[:2]), int(slot[3:])
    dt_ist = datetime(day.year, day.month, day.day, h, m, tzinfo=IST)
    dt_utc = dt_ist.astimezone(UTC)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _save_candle_json(symbol: str, day: date, candles: list[dict],
                      missing: list[str], zero_vol_slots: list[str],
                      disagreements: list[dict],
                      angel_count: int, yf_count: int) -> None:
    out_dir = os.path.join("data", "candles", symbol, "5m")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{day}.json")

    records = []
    for bar in candles:
        slot = bar.pop("slot")
        rec: dict = {
            "ts": _slot_to_utc_ts(slot, day),
            "o": bar["o"], "h": bar["h"], "l": bar["l"],
            "c": bar["c"], "v": bar["v"],
            "src": bar["src"],
        }
        if bar.get("zero_volume"):
            rec["zero_volume"] = True
        records.append(rec)

    payload = {
        "symbol": symbol,
        "interval": "5m",
        "timezone": "UTC",
        "candles": records,
        "metadata": {
            "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bar_count": len(records),
            "missing_slots_ist": missing,
            "known_gap_slots_ist": KNOWN_GAP_SLOTS,
            "zero_volume_count": len(zero_vol_slots),
            "disagreements_over_0_05pct": len(disagreements),
            "sources_used": {"angel": angel_count, "yfinance": yf_count},
        },
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _append_report(day: date, symbol: str, candles: list[dict],
                   missing: list[str], zero_vol_slots: list[str],
                   disagreements: list[dict]) -> None:
    out_dir = os.path.join("data", "reports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{day}.md")

    top5 = sorted(disagreements, key=lambda x: x["pct"], reverse=True)[:5]
    top5_str = ", ".join(f"{d['slot']} {d['field']} {d['pct']}%" for d in top5) or "none"

    header_needed = not os.path.exists(path)
    with open(path, "a") as f:
        if header_needed:
            f.write(f"# Candle report {day}\n\n")
            f.write("| symbol | bars | missing | zero-vol | disagree | top-5 disagreements |\n")
            f.write("|--------|------|---------|----------|----------|---------------------|\n")
        f.write(
            f"| {symbol} | {len(candles)} | {missing or 'none'} "
            f"| {zero_vol_slots or 'none'} | {len(disagreements)} | {top5_str} |\n"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", dest="dates", action="append",
                        help="YYYY-MM-DD (repeatable)")
    args = parser.parse_args()

    if args.dates:
        days = sorted(date.fromisoformat(d) for d in args.dates)
    else:
        days = _last_n_weekdays(5)

    tokens = _load_tokens()
    api = _angel_login()

    for day in days:
        angel_raw: dict[str, list] = {}
        for symbol in WATCHLIST:
            time.sleep(1)
            rows = _fetch_angel(api, tokens[symbol], day)
            angel_raw[symbol] = rows
            # Save raw Angel response
            raw_dir = os.path.join("data", "compare", "angel", symbol)
            os.makedirs(raw_dir, exist_ok=True)
            with open(os.path.join(raw_dir, f"{day}.json"), "w") as f:
                json.dump(rows, f)

        for symbol in WATCHLIST:
            a_bars = _angel_rows_to_dict(angel_raw[symbol])
            y_bars = _fetch_yfinance(symbol, day)

            candles, missing, zero_vol_slots, disagreements = merge_bars(a_bars, y_bars)

            a_count = sum(1 for b in candles if b["src"] == "angel")
            y_count = sum(1 for b in candles if b["src"] == "yfinance")

            _save_candle_json(symbol, day, [dict(b) for b in candles],
                              missing, zero_vol_slots, disagreements,
                              a_count, y_count)
            _append_report(day, symbol, candles, missing, zero_vol_slots, disagreements)

            print(
                f"{day} {symbol:16s}  bars={len(candles):3d}"
                f"  missing={len(missing)}"
                f"  zero_vol={len(zero_vol_slots)}"
                f"  disagree={len(disagreements)}"
                f"  angel={a_count} yf={y_count}"
            )


if __name__ == "__main__":
    main()
