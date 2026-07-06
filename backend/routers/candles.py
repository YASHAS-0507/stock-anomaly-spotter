"""
candles.py
----------
FastAPI router for intraday OHLCV candle data.

GET /api/candles/{ticker}?interval=5min&limit=100

Returns live candles from candle_builder if available,
falls back to yfinance historical data if market is closed.
Computes VWAP, EMA9, EMA21 server-side.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Query, Path

IST = timezone(timedelta(hours=5, minutes=30))

router = APIRouter(prefix="/api/candles", tags=["candles"])

VALID_INTERVALS = {"1min", "5min", "15min"}

# Map internal interval keys to yfinance interval strings
_YF_INTERVAL = {
    "1min":  "1m",
    "5min":  "5m",
    "15min": "15m",
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _compute_ema(values: list, period: int) -> list:
    k = 2 / (period + 1)
    ema = None
    result = []
    for v in values:
        if v is None:
            result.append(None)
            continue
        ema = v if ema is None else v * k + ema * (1 - k)
        result.append(round(ema, 2))
    return result


def _compute_vwap(candles: list) -> list:
    cum_tp_vol = 0.0
    cum_vol    = 0.0
    result     = []
    for c in candles:
        vol  = c.get("volume") or 1
        tp   = (c["high"] + c["low"] + c["close"]) / 3
        cum_tp_vol += tp * vol
        cum_vol    += vol
        result.append(round(cum_tp_vol / cum_vol, 2) if cum_vol > 0 else None)
    return result


def _annotate(candles: list) -> list:
    """Add VWAP, EMA9, EMA21 to each candle dict."""
    if not candles:
        return candles
    vwap  = _compute_vwap(candles)
    closes = [c["close"] for c in candles]
    ema9  = _compute_ema(closes, 9)
    ema21 = _compute_ema(closes, 21)
    out = []
    for i, c in enumerate(candles):
        out.append({
            **c,
            "vwap":  vwap[i],
            "ema9":  ema9[i],
            "ema21": ema21[i],
        })
    return out


def _is_market_open() -> bool:
    now   = datetime.now(IST)
    day   = now.weekday()          # 0=Mon … 6=Sun
    total = now.hour * 60 + now.minute
    return day < 5 and 555 <= total <= 930  # 9:15–15:30 IST


def _candles_from_builder(ticker: str, interval: str, limit: int) -> list:
    """Try to pull completed candles from the in-process candle_builder."""
    try:
        from feeds.candle_builder import candle_builder
        # candle_builder uses '1min'/'5min' keys; '15min' not built live
        tf_key = interval if interval in ("1min", "5min") else "5min"
        raw = candle_builder.get_candles(ticker, tf_key, limit)
        return raw
    except Exception:
        return []


def _candles_from_yfinance(ticker: str, interval: str, limit: int) -> list:
    """Fetch historical candles via yfinance as fallback."""
    try:
        import yfinance as yf
        yf_iv  = _YF_INTERVAL.get(interval, "5m")
        period = "1d" if interval in ("1min", "5min") else "5d"
        df = yf.Ticker(ticker).history(period=period, interval=yf_iv)
        if df.empty:
            return []
        candles = []
        for ts, row in df.tail(limit).iterrows():
            ist_ts = ts.tz_convert(IST) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(IST)
            candles.append({
                "timestamp": ist_ts.isoformat(),
                "open":   round(float(row["Open"]),   2),
                "high":   round(float(row["High"]),   2),
                "low":    round(float(row["Low"]),    2),
                "close":  round(float(row["Close"]),  2),
                "volume": int(row["Volume"]),
            })
        return candles
    except Exception:
        return []


# ─── endpoint ─────────────────────────────────────────────────────────────────

@router.get("/{ticker}")
def get_candles(
    ticker:   str = Path(..., description="Ticker symbol, e.g. RELIANCE.NS"),
    interval: str = Query("5min", description="1min | 5min | 15min"),
    limit:    int = Query(100,    ge=1, le=500, description="Max candles to return"),
):
    if interval not in VALID_INTERVALS:
        interval = "5min"

    source  = "live"
    candles = []

    if _is_market_open():
        candles = _candles_from_builder(ticker, interval, limit)

    if not candles:
        source  = "historical"
        candles = _candles_from_yfinance(ticker, interval, limit)

    candles = _annotate(candles)

    return {
        "ticker":   ticker,
        "interval": interval,
        "candles":  candles,
        "count":    len(candles),
        "source":   source,
    }
