"""
candles.py
----------
FastAPI router for intraday OHLCV candle data.

GET /api/candles/{ticker}?interval=5min&limit=100

Single source of truth: reads directly from the in-memory candle_builder
store that the Angel One WebSocket tick pipeline populates in real time.

No external data source (yfinance, Angel One historical API) is ever
called from this endpoint.  If the store is empty — pre-market, or before
the first Angel One tick arrives — the endpoint returns an empty list with
a human-readable message.  The frontend renders nothing rather than a
stale/wrong chart.

Response shape:
{
    ticker:      str,
    interval:    str,            # "1min" | "5min" | "15min"
    candles:     list[dict],     # [{timestamp, open, high, low, close,
                                 #   volume, vwap, ema9, ema21}, ...]
    count:       int,
    source:      str,            # "live_builder" | "builder_error"
    market_open: bool,
    message:     str | null,     # non-null only when candles is empty
}
"""

import logging
from datetime import datetime

import pytz
from fastapi import APIRouter, Query, Path

logger = logging.getLogger(__name__)

_IST = pytz.timezone("Asia/Kolkata")

router = APIRouter(prefix="/api/candles", tags=["candles"])

VALID_INTERVALS = {"1min", "5min", "15min"}


# ─── indicator helpers (stateless, no I/O) ────────────────────────────────────

def _compute_ema(values: list, period: int) -> list:
    k   = 2 / (period + 1)
    ema = None
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        ema = v if ema is None else v * k + ema * (1 - k)
        out.append(round(ema, 2))
    return out


def _compute_vwap(candles: list) -> list:
    cum_tp_vol = 0.0
    cum_vol    = 0.0
    out        = []
    for c in candles:
        vol         = c.get("volume") or 1
        tp          = (c["high"] + c["low"] + c["close"]) / 3
        cum_tp_vol += tp * vol
        cum_vol    += vol
        out.append(round(cum_tp_vol / cum_vol, 2) if cum_vol > 0 else None)
    return out


def _annotate(candles: list) -> list:
    """Attach VWAP, EMA9, EMA21 to each candle dict in-place (returns new list)."""
    if not candles:
        return []
    vwap   = _compute_vwap(candles)
    closes = [c["close"] for c in candles]
    ema9   = _compute_ema(closes, 9)
    ema21  = _compute_ema(closes, 21)
    return [
        {**c, "vwap": vwap[i], "ema9": ema9[i], "ema21": ema21[i]}
        for i, c in enumerate(candles)
    ]


# ─── endpoint ─────────────────────────────────────────────────────────────────

@router.get("/{ticker}")
def get_candles(
    ticker:   str = Path(..., description="Ticker symbol, e.g. RELIANCE.NS"),
    interval: str = Query("5min", description="1min | 5min | 15min"),
    limit:    int = Query(100,    ge=1, le=500, description="Max candles to return"),
):
    if interval not in VALID_INTERVALS:
        interval = "5min"

    # candle_builder aggregates 1min and 5min timeframes.
    # 15min requests are served from the 5min store (best available live data).
    tf_key = interval if interval in ("1min", "5min") else "5min"

    candles = []
    source  = "live_builder"

    try:
        from feeds.candle_builder import candle_builder
        candles = candle_builder.get_candles(ticker, tf_key, limit)
    except Exception as exc:
        logger.warning("[candles] builder read error %s/%s: %s", ticker, tf_key, exc)
        source = "builder_error"

    candles = _annotate(candles)

    print(f"[candles] {ticker} {interval} → {len(candles)} candles from live store")
    logger.info("[candles] %s %s → %d candles from live store", ticker, interval, len(candles))

    now_ist     = datetime.now(_IST)
    market_open = now_ist.weekday() < 5 and (9 * 60 + 15) <= (now_ist.hour * 60 + now_ist.minute) <= (15 * 60 + 30)

    message = None
    if not candles:
        if market_open:
            message = (
                f"No {interval} candles for {ticker} yet — "
                "Angel One ticks are live but the first candle completes at the next minute boundary"
            )
        else:
            message = (
                f"No {interval} candles for {ticker} — "
                "live store is empty outside market hours (09:15–15:30 IST weekdays)"
            )

    return {
        "ticker":      ticker,
        "interval":    interval,
        "candles":     candles,
        "count":       len(candles),
        "source":      source,
        "market_open": market_open,
        "message":     message,
    }
