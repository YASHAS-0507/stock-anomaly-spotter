"""
intraday_features.py
--------------------
Computes intraday technical features from 1-min and 5-min OHLCV candle lists.

Input candle format (from CandleBuilder or synthetic):
    {"timestamp": float|str, "open": float, "high": float,
     "low": float, "close": float, "volume": int}

All computations are purely in Python/numpy — no yfinance, no network calls.
Never raises — returns defaults when data is insufficient.
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Market session times (IST)
_MARKET_OPEN_HOUR,  _MARKET_OPEN_MIN  = 9,  15
_MARKET_CLOSE_HOUR, _MARKET_CLOSE_MIN = 15, 30
_ORB_END_HOUR,      _ORB_END_MIN       = 9,  30   # Opening Range: 9:15 – 9:30

# Trading window boundaries (minutes since market open)
_WINDOW1_END  = 75   # 9:15 – 10:30 — best momentum window
_DEAD_ZONE_END = 135  # 10:30 – 11:30 — choppy/low-volume
_WINDOW2_END  = 255  # 11:30 – 13:30 — second momentum window

# Defaults returned when data is insufficient
_DEFAULTS: dict = {
    "vwap":               0.0,
    "price_vs_vwap_pct":  0.0,
    "price_above_vwap":   False,
    "ema9":               0.0,
    "ema21":              0.0,
    "ema9_above_ema21":   False,
    "price_vs_ema21_pct": 0.0,
    "rsi_14":             50.0,
    "rsi_slope":          0.0,
    "macd":               0.0,
    "macd_signal":        0.0,
    "macd_histogram":     0.0,
    "macd_crossover":     False,
    "atr_14":             0.0,
    "atr_pct":            0.0,
    "bollinger_upper":    0.0,
    "bollinger_lower":    0.0,
    "bollinger_pct_b":    0.5,
    "bollinger_squeeze":  False,
    "volume_ratio":       1.0,
    "volume_trend":       "neutral",
    "orb_high":           0.0,
    "orb_low":            0.0,
    "orb_range":          0.0,
    "price_vs_orb":       "inside",
    "orb_breakout":       False,
    "higher_highs":       False,
    "higher_lows":        False,
    "daily_return":       0.0,
    "return_zscore":      0.0,
    "minutes_since_open": 0,
    "time_of_day_score":  0.5,
    "trading_window":     "closed",
    # Supertrend (Day 17)
    "supertrend_direction": "neutral",
    "supertrend_value":     0.0,
    # ADX (Day 17)
    "adx":                  20.0,
    "adx_plus_di":          20.0,
    "adx_minus_di":         20.0,
    "adx_trending":         False,
    # Pivot Points (Day 17)
    "pivot":                0.0,
    "pivot_r1":             0.0,
    "pivot_r2":             0.0,
    "pivot_s1":             0.0,
    "pivot_s2":             0.0,
    "pivot_zone":           "between_s1_r1",
}


class IntradayFeatures:
    """Stateless feature computer — all state lives in candle lists."""

    def compute(
        self,
        candles_5min: list,
        candles_1min: list,
        current_price: float,
    ) -> dict:
        """
        Compute intraday technical features.

        Parameters
        ----------
        candles_5min  : list of 5-min OHLCV dicts (oldest first)
        candles_1min  : list of 1-min OHLCV dicts (oldest first)
        current_price : latest LTP

        Returns
        -------
        dict of features — never raises
        """
        try:
            return self._compute(candles_5min, candles_1min, current_price)
        except Exception as exc:
            logger.warning("[features] compute() failed: %s", exc)
            result = dict(_DEFAULTS)
            result["trading_window"] = self._trading_window_now()
            result["minutes_since_open"] = self._minutes_since_open_now()
            return result

    # ──────────────────────────────────────────────────────
    # Core computation
    # ──────────────────────────────────────────────────────

    def _compute(
        self,
        candles_5min: list,
        candles_1min: list,
        current_price: float,
    ) -> dict:
        result: dict = {}

        closes_5  = _col(candles_5min, "close")
        highs_5   = _col(candles_5min, "high")
        lows_5    = _col(candles_5min, "low")
        volumes_5 = _col(candles_5min, "volume")

        closes_1  = _col(candles_1min, "close")
        highs_1   = _col(candles_1min, "high")
        lows_1    = _col(candles_1min, "low")
        volumes_1 = _col(candles_1min, "volume")

        price = current_price if current_price and current_price > 0 else (closes_5[-1] if closes_5 else 1.0)

        # ── VWAP ──────────────────────────────────────────────────────────
        vwap = _vwap(candles_1min if candles_1min else candles_5min)
        if vwap <= 0 and price > 0:
            vwap = price
        result["vwap"]              = round(vwap, 2)
        result["price_vs_vwap_pct"] = round((price - vwap) / vwap * 100, 3) if vwap > 0 else 0.0
        result["price_above_vwap"]  = price > vwap

        # ── EMA ───────────────────────────────────────────────────────────
        ema9  = _ema(closes_5, 9)  if len(closes_5) >= 9  else price
        ema21 = _ema(closes_5, 21) if len(closes_5) >= 21 else price
        result["ema9"]               = round(ema9, 2)
        result["ema21"]              = round(ema21, 2)
        result["ema9_above_ema21"]   = ema9 > ema21
        result["price_vs_ema21_pct"] = round((price - ema21) / ema21 * 100, 3) if ema21 > 0 else 0.0

        # ── RSI-14 ────────────────────────────────────────────────────────
        if len(closes_5) >= 16:
            rsi_series = _rsi_series(closes_5, 14)
            rsi_val   = rsi_series[-1] if rsi_series else 50.0
            rsi_slope = (rsi_series[-1] - rsi_series[-3]) / 2.0 if len(rsi_series) >= 3 else 0.0
        else:
            rsi_val, rsi_slope = 50.0, 0.0
        result["rsi_14"]   = round(max(0.0, min(100.0, rsi_val)), 2)
        result["rsi_slope"] = round(rsi_slope, 4)

        # ── MACD (12, 26, 9) ──────────────────────────────────────────────
        macd_line, signal_line, histogram, crossover = _macd(closes_5)
        result["macd"]           = round(macd_line,   4)
        result["macd_signal"]    = round(signal_line, 4)
        result["macd_histogram"] = round(histogram,   4)
        result["macd_crossover"] = crossover

        # ── ATR-14 ────────────────────────────────────────────────────────
        atr = _atr(highs_5, lows_5, closes_5, 14)
        result["atr_14"]  = round(atr, 4)
        result["atr_pct"] = round(atr / price * 100, 3) if price > 0 else 0.0

        # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────
        bb_upper, bb_lower, pct_b, squeeze = _bollinger(closes_5, 20, 2.0, price)
        result["bollinger_upper"]   = round(bb_upper, 2)
        result["bollinger_lower"]   = round(bb_lower, 2)
        result["bollinger_pct_b"]   = round(pct_b, 4)
        result["bollinger_squeeze"] = squeeze

        # ── Volume ───────────────────────────────────────────────────────
        vol_ratio, vol_trend = _volume_analysis(volumes_5 if volumes_5 else volumes_1)
        result["volume_ratio"] = round(vol_ratio, 3)
        result["volume_trend"] = vol_trend

        # ── Opening Range (9:15–9:30) ─────────────────────────────────────
        orb_h, orb_l = _opening_range(candles_5min if candles_5min else candles_1min)
        orb_range = round(orb_h - orb_l, 4) if orb_h > orb_l else 0.0
        result["orb_high"]  = round(orb_h, 2)
        result["orb_low"]   = round(orb_l, 2)
        result["orb_range"] = orb_range
        if orb_h > orb_l:
            if price > orb_h:
                result["price_vs_orb"]  = "above"
                result["orb_breakout"]  = True
            elif price < orb_l:
                result["price_vs_orb"]  = "below"
                result["orb_breakout"]  = True
            else:
                result["price_vs_orb"]  = "inside"
                result["orb_breakout"]  = False
        else:
            result["price_vs_orb"]  = "inside"
            result["orb_breakout"]  = False

        # ── Price action (higher highs / higher lows) ─────────────────────
        h_highs, h_lows = _price_structure(highs_5[-6:], lows_5[-6:])
        result["higher_highs"] = h_highs
        result["higher_lows"]  = h_lows

        # ── Daily return + z-score ────────────────────────────────────────
        daily_ret, ret_zscore = _return_stats(closes_5, price)
        result["daily_return"]  = round(daily_ret, 4)
        result["return_zscore"] = round(ret_zscore, 4)

        # ── Supertrend (Day 17) ───────────────────────────────────────────
        st_dir, st_val = _supertrend(highs_5, lows_5, closes_5)
        result["supertrend_direction"] = st_dir
        result["supertrend_value"]     = round(st_val, 2)

        # ── ADX (Day 17) ──────────────────────────────────────────────────
        adx_val, plus_di, minus_di = _adx(highs_5, lows_5, closes_5)
        result["adx"]          = round(adx_val, 2)
        result["adx_plus_di"]  = round(plus_di, 2)
        result["adx_minus_di"] = round(minus_di, 2)
        result["adx_trending"] = adx_val >= 25.0

        # ── Pivot Points (Day 17) ─────────────────────────────────────────
        pivot, r1, r2, s1, s2 = _pivot_points(highs_5, lows_5, closes_5)
        result["pivot"]      = round(pivot, 2)
        result["pivot_r1"]   = round(r1, 2)
        result["pivot_r2"]   = round(r2, 2)
        result["pivot_s1"]   = round(s1, 2)
        result["pivot_s2"]   = round(s2, 2)
        result["pivot_zone"] = _pivot_zone(price, r1, r2, s1, s2)

        # ── Time context ──────────────────────────────────────────────────
        now_ist = datetime.now(IST)
        mins_open = _minutes_since_open(now_ist)
        result["minutes_since_open"] = mins_open
        result["trading_window"]     = _trading_window(mins_open)
        result["time_of_day_score"]  = round(_time_score(mins_open), 4)

        return result

    # ──────────────────────────────────────────────────────
    # Fallback helpers (used when top-level exception fires)
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _trading_window_now() -> str:
        return _trading_window(_minutes_since_open(datetime.now(IST)))

    @staticmethod
    def _minutes_since_open_now() -> int:
        return _minutes_since_open(datetime.now(IST))


# ══════════════════════════════════════════════════════════════════
# Pure-function helpers (no class state)
# ══════════════════════════════════════════════════════════════════

def _col(candles: list, key: str) -> list:
    """Extract a numeric column from candle dicts, skipping None/zero entries."""
    return [float(c[key]) for c in candles if c.get(key) is not None]


def _ema(values: list, span: int) -> float:
    """Exponential moving average — last value only."""
    if not values:
        return 0.0
    k = 2.0 / (span + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _ema_series(values: list, span: int) -> list:
    """Full EMA series."""
    if not values:
        return []
    k = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi_series(closes: list, period: int = 14) -> list:
    """RSI series using Wilder's smoothed average."""
    if len(closes) < period + 1:
        return [50.0]
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # Seed with simple average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_vals = []
    eps = 1e-9
    rs = avg_gain / (avg_loss + eps)
    rsi_vals.append(100.0 - 100.0 / (1.0 + rs))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / (avg_loss + eps)
        rsi_vals.append(100.0 - 100.0 / (1.0 + rs))

    return rsi_vals


def _macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram, crossover_bool)."""
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0, False

    ema_fast_s = _ema_series(closes, fast)
    ema_slow_s = _ema_series(closes, slow)
    # Align — both series have same length as closes
    macd_series = [f - s for f, s in zip(ema_fast_s, ema_slow_s)]

    if len(macd_series) < signal:
        return macd_series[-1], 0.0, macd_series[-1], False

    signal_series = _ema_series(macd_series, signal)
    macd_line   = macd_series[-1]
    signal_line = signal_series[-1]
    histogram   = macd_line - signal_line

    # Crossover: macd crossed above signal in the last 2 bars
    crossover = False
    if len(macd_series) >= 2 and len(signal_series) >= 2:
        prev_diff = macd_series[-2] - signal_series[-2]
        curr_diff = macd_series[-1] - signal_series[-1]
        crossover = prev_diff < 0 and curr_diff >= 0

    return macd_line, signal_line, histogram, crossover


def _atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Average True Range (last `period` bars)."""
    n = min(len(highs), len(lows), len(closes))
    if n < 2:
        return (highs[0] - lows[0]) if n == 1 else 0.0

    tr_vals = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        tr_vals.append(tr)

    use = tr_vals[-period:] if len(tr_vals) >= period else tr_vals
    return sum(use) / len(use) if use else 0.0


def _bollinger(closes: list, period: int = 20, num_std: float = 2.0, price: float = 0.0):
    """Returns (upper, lower, pct_b, squeeze_bool)."""
    if len(closes) < period:
        mid = price or (closes[-1] if closes else 0.0)
        return mid, mid, 0.5, False

    window = closes[-period:]
    mean   = sum(window) / period
    var    = sum((v - mean) ** 2 for v in window) / period
    std    = math.sqrt(var)

    upper  = mean + num_std * std
    lower  = mean - num_std * std
    band_w = upper - lower

    pct_b  = (price - lower) / band_w if band_w > 0 else 0.5

    # Squeeze: band width < 2% of mid price
    squeeze = (band_w / mean * 100 < 2.0) if mean > 0 else False

    return upper, lower, pct_b, squeeze


def _volume_analysis(volumes: list) -> tuple:
    """Returns (volume_ratio, volume_trend_str)."""
    if len(volumes) < 2:
        return 1.0, "neutral"

    avg  = sum(volumes[:-1]) / len(volumes[:-1])
    last = volumes[-1]
    ratio = last / avg if avg > 0 else 1.0

    if ratio >= 2.0:
        trend = "surge"
    elif ratio >= 1.2:
        trend = "above_avg"
    elif ratio <= 0.5:
        trend = "dry"
    elif ratio <= 0.8:
        trend = "below_avg"
    else:
        trend = "neutral"

    return ratio, trend


def _opening_range(candles: list) -> tuple:
    """
    Extract ORB high/low from candles whose timestamps fall in 9:15–9:30 IST.
    Falls back to first 3 candles if no timestamp parses into that range.
    """
    orb_candles = []

    for c in candles:
        ts = c.get("timestamp")
        if ts is None:
            continue
        try:
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(float(ts), tz=IST)
            else:
                # ISO string from CandleBuilder
                dt = datetime.fromisoformat(str(ts))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                else:
                    dt = dt.astimezone(IST)
            h, m = dt.hour, dt.minute
            if (h == _MARKET_OPEN_HOUR and m >= _MARKET_OPEN_MIN) or \
               (h == _ORB_END_HOUR     and m <  _ORB_END_MIN):
                orb_candles.append(c)
        except Exception:
            pass

    # Fallback: use earliest 3 candles as proxy for the opening range
    if not orb_candles:
        orb_candles = candles[:3]

    if not orb_candles:
        return 0.0, 0.0

    orb_high = max(_col(orb_candles, "high"))
    orb_low  = min(_col(orb_candles, "low"))
    return orb_high, orb_low


def _price_structure(highs: list, lows: list) -> tuple:
    """Return (higher_highs, higher_lows) from recent swing bars."""
    if len(highs) < 3:
        return False, False
    h_highs = all(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    h_lows  = all(lows[i]  > lows[i - 1]  for i in range(1, len(lows)))
    return h_highs, h_lows


def _return_stats(closes: list, price: float) -> tuple:
    """Return (daily_return_pct, z_score)."""
    if not closes:
        return 0.0, 0.0

    first_close  = closes[0]
    daily_return = (price - first_close) / first_close * 100 if first_close > 0 else 0.0

    if len(closes) < 3:
        return daily_return, 0.0

    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100
               for i in range(1, len(closes)) if closes[i - 1] > 0]
    if not returns:
        return daily_return, 0.0

    mean  = sum(returns) / len(returns)
    var   = sum((r - mean) ** 2 for r in returns) / len(returns)
    std   = math.sqrt(var)
    latest_ret = returns[-1]
    zscore = (latest_ret - mean) / std if std > 0 else 0.0

    return daily_return, max(-5.0, min(5.0, zscore))


def _vwap(candles: list) -> float:
    """Cumulative VWAP across all provided candles."""
    cum_tv = 0.0
    cum_v  = 0.0
    for c in candles:
        h = c.get("high",  0) or 0
        l = c.get("low",   0) or 0
        cl = c.get("close", 0) or 0
        v  = c.get("volume", 0) or 0
        tp = (h + l + cl) / 3.0
        cum_tv += tp * v
        cum_v  += v
    return cum_tv / cum_v if cum_v > 0 else 0.0


def _minutes_since_open(now_ist: datetime) -> int:
    """Minutes elapsed since 9:15 IST. Negative before open."""
    open_mins = _MARKET_OPEN_HOUR * 60 + _MARKET_OPEN_MIN
    now_mins  = now_ist.hour * 60 + now_ist.minute
    return now_mins - open_mins


def _trading_window(mins_since_open: int) -> str:
    """Classify current time into a named trading window."""
    if mins_since_open < 0:
        return "pre_open"
    total_mins = _MARKET_CLOSE_HOUR * 60 + _MARKET_CLOSE_MIN - \
                 (_MARKET_OPEN_HOUR * 60 + _MARKET_OPEN_MIN)
    if mins_since_open > total_mins:
        return "closed"
    if mins_since_open <= _WINDOW1_END:
        return "window1"
    if mins_since_open <= _DEAD_ZONE_END:
        return "dead_zone"
    if mins_since_open <= _WINDOW2_END:
        return "window2"
    return "closed"


def _supertrend(
    highs: list, lows: list, closes: list,
    period: int = 10, multiplier: float = 3.0,
) -> tuple:
    """Returns (direction_str, supertrend_value). direction: 'bullish'|'bearish'|'neutral'."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 2:
        return "neutral", (closes[-1] if closes else 0.0)

    # True Range
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        ))

    # Wilder's ATR (indexed same as candles; valid from index period-1)
    atr = [0.0] * n
    atr[period - 1] = sum(tr[:period]) / period
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    final_ub  = [0.0] * n
    final_lb  = [0.0] * n
    direction = ["neutral"] * n
    st_val    = [0.0] * n

    for i in range(period - 1, n):
        hl2      = (highs[i] + lows[i]) / 2.0
        basic_ub = hl2 + multiplier * atr[i]
        basic_lb = hl2 - multiplier * atr[i]

        if i == period - 1:
            final_ub[i] = basic_ub
            final_lb[i] = basic_lb
        else:
            final_ub[i] = (basic_ub
                           if basic_ub < final_ub[i - 1] or closes[i - 1] > final_ub[i - 1]
                           else final_ub[i - 1])
            final_lb[i] = (basic_lb
                           if basic_lb > final_lb[i - 1] or closes[i - 1] < final_lb[i - 1]
                           else final_lb[i - 1])

        if i == period - 1:
            direction[i] = "bullish" if closes[i] > final_ub[i] else "bearish"
        elif direction[i - 1] == "bearish":
            direction[i] = "bullish" if closes[i] > final_ub[i] else "bearish"
        else:
            direction[i] = "bearish" if closes[i] < final_lb[i] else "bullish"

        st_val[i] = final_lb[i] if direction[i] == "bullish" else final_ub[i]

    return direction[n - 1], st_val[n - 1]


def _adx(highs: list, lows: list, closes: list, period: int = 14) -> tuple:
    """Returns (adx, plus_di, minus_di) using Wilder's smoothing."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 2:
        return 20.0, 20.0, 20.0

    tr_list  = []
    pdm_list = []
    ndm_list = []

    for i in range(1, n):
        tr_list.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        ))
        up   = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        pdm_list.append(up   if up   > down and up   > 0 else 0.0)
        ndm_list.append(down if down > up   and down > 0 else 0.0)

    smooth_tr  = sum(tr_list[:period])
    smooth_pdm = sum(pdm_list[:period])
    smooth_ndm = sum(ndm_list[:period])

    eps = 1e-9
    dx_list = []

    def _calc_di(dm): return 100.0 * dm / (smooth_tr + eps)

    plus_di  = _calc_di(smooth_pdm)
    minus_di = _calc_di(smooth_ndm)
    dx_list.append(100.0 * abs(plus_di - minus_di) / (plus_di + minus_di + eps))

    for i in range(period, len(tr_list)):
        smooth_tr  = smooth_tr  - smooth_tr  / period + tr_list[i]
        smooth_pdm = smooth_pdm - smooth_pdm / period + pdm_list[i]
        smooth_ndm = smooth_ndm - smooth_ndm / period + ndm_list[i]
        plus_di  = 100.0 * smooth_pdm / (smooth_tr + eps)
        minus_di = 100.0 * smooth_ndm / (smooth_tr + eps)
        dx_list.append(100.0 * abs(plus_di - minus_di) / (plus_di + minus_di + eps))

    # ADX = Wilder smooth of DX series
    if len(dx_list) < period:
        adx_val = sum(dx_list) / len(dx_list) if dx_list else 20.0
    else:
        adx_val = sum(dx_list[:period]) / period
        for dx in dx_list[period:]:
            adx_val = (adx_val * (period - 1) + dx) / period

    return round(adx_val, 2), round(plus_di, 2), round(minus_di, 2)


def _pivot_points(highs: list, lows: list, closes: list) -> tuple:
    """Classic pivot points (P, R1, R2, S1, S2) from session high/low/last close."""
    if not highs or not lows or not closes:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    h = max(highs)
    l = min(lows)
    c = closes[-1]
    p  = (h + l + c) / 3.0
    r1 = 2 * p - l
    r2 = p + (h - l)
    s1 = 2 * p - h
    s2 = p - (h - l)
    return p, r1, r2, s1, s2


def _pivot_zone(price: float, r1: float, r2: float, s1: float, s2: float) -> str:
    """Classify current price relative to pivot levels."""
    if r2 > 0 and price >= r2:
        return "above_r2"
    if r1 > 0 and price >= r1:
        return "above_r1"
    if s2 > 0 and price <= s2:
        return "below_s2"
    if s1 > 0 and price <= s1:
        return "below_s1"
    return "between_s1_r1"


def _time_score(mins_since_open: int) -> float:
    """
    Score 0–1 representing how favourable the current time is for trading.
    Peaks in window1 (0.9) and window2 (0.7), lowest in dead_zone (0.2).
    """
    window = _trading_window(mins_since_open)
    if window == "window1":
        # Peaks mid-window, tapers near edges
        mid   = _WINDOW1_END / 2.0
        dist  = abs(mins_since_open - mid) / mid
        return round(max(0.6, 0.9 - dist * 0.3), 4)
    elif window == "window2":
        start = _DEAD_ZONE_END
        mid   = (start + _WINDOW2_END) / 2.0
        total = (_WINDOW2_END - start) / 2.0
        dist  = abs(mins_since_open - mid) / total if total > 0 else 0.0
        return round(max(0.4, 0.7 - dist * 0.3), 4)
    elif window == "dead_zone":
        return 0.2
    elif window == "pre_open":
        return 0.1
    else:  # closed
        return 0.0
