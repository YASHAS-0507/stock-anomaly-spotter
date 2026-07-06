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
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from wyckoff.wyckoff_detector import wyckoff_detector

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
    # Volume Profile (Day 18)
    "vp_poc":                  0.0,
    "vp_vah":                  0.0,
    "vp_val":                  0.0,
    "vp_prev_poc":             None,
    "vp_total_volume":         0,
    "price_vs_va":             "INSIDE_VA",
    "price_at_poc":            False,
    "price_at_vah":            False,
    "price_at_val":            False,
    "poc_distance_pct":        0.0,
    "prev_poc_distance_pct":   None,
    "at_prev_poc":             False,
    "volume_profile_strength": "NORMAL",
    # Fair Value Gaps (Day 19)
    "fvg_bullish_exists":        False,
    "fvg_bullish_top":           None,
    "fvg_bullish_bottom":        None,
    "fvg_bearish_exists":        False,
    "fvg_bearish_top":           None,
    "fvg_bearish_bottom":        None,
    "price_in_fvg":              False,
    "price_in_bullish_fvg":      False,
    "price_in_bearish_fvg":      False,
    "nearest_fvg_distance_pct":  0.0,
    "fvg_count":                 0,
    # Wyckoff (Day 20)
    "wyckoff_range_type":            "NONE",
    "wyckoff_in_range":              False,
    "wyckoff_range_support":         None,
    "wyckoff_range_resistance":      None,
    "wyckoff_spring_active":         False,
    "wyckoff_spring_depth_atr":      0.0,
    "wyckoff_spring_volume_ratio":   0.0,
    "wyckoff_spring_follow_through": False,
    "wyckoff_upthrust_active":       False,
    "wyckoff_upthrust_depth_atr":    0.0,
    "wyckoff_breakout_confirmed":    False,
    "wyckoff_breakdown_confirmed":   False,
    "wyckoff_breakout_strength":     0.0,
    "wyckoff_post_accumulation":     False,
    "wyckoff_post_distribution":     False,
    "wyckoff_cause_length_bars":     0,
    "wyckoff_vi_ratio":              1.0,
    "wyckoff_bias":                  "NEUTRAL",
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

        # ── Volume Profile (Day 18) ───────────────────────────────────────
        vp_features = self.add_volume_profile(candles_5min, price)
        result.update(vp_features)

        # ── Fair Value Gaps (Day 19) ──────────────────────────────────────
        fvg_features = self.add_fair_value_gaps(candles_5min, price)
        result.update(fvg_features)

        # ── Wyckoff analysis (Day 20) ────────────────────────────────────
        wyckoff_features = wyckoff_detector.detect(
            candles=candles_5min,
            current_price=price,
            atr=result.get("atr_14", 0.0),
            adx=result.get("adx", 20.0),
        )
        result.update(wyckoff_features)

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

    # ──────────────────────────────────────────────────────
    # Volume Profile (Day 18)
    # ──────────────────────────────────────────────────────

    def add_volume_profile(
        self,
        candles: list,
        current_price: float,
        price_bins: int = 50,
    ) -> dict:
        _defaults = {
            "vp_poc":                  current_price,
            "vp_vah":                  current_price * 1.005,
            "vp_val":                  current_price * 0.995,
            "vp_prev_poc":             None,
            "vp_total_volume":         0,
            "price_vs_va":             "INSIDE_VA",
            "price_at_poc":            False,
            "price_at_vah":            False,
            "price_at_val":            False,
            "poc_distance_pct":        0.0,
            "prev_poc_distance_pct":   None,
            "at_prev_poc":             False,
            "volume_profile_strength": "NORMAL",
        }
        try:
            return self._volume_profile(candles, current_price, price_bins)
        except Exception as exc:
            logger.warning("[features] add_volume_profile() failed: %s", exc)
            return _defaults

    def _volume_profile(
        self,
        candles: list,
        current_price: float,
        price_bins: int,
    ) -> dict:
        if len(candles) < 10:
            return {
                "vp_poc":                  current_price,
                "vp_vah":                  round(current_price * 1.005, 2),
                "vp_val":                  round(current_price * 0.995, 2),
                "vp_prev_poc":             None,
                "vp_total_volume":         0,
                "price_vs_va":             "INSIDE_VA",
                "price_at_poc":            False,
                "price_at_vah":            False,
                "price_at_val":            False,
                "poc_distance_pct":        0.0,
                "prev_poc_distance_pct":   None,
                "at_prev_poc":             False,
                "volume_profile_strength": "NORMAL",
            }

        min_low  = min(float(c.get("low",  current_price) or current_price) for c in candles)
        max_high = max(float(c.get("high", current_price) or current_price) for c in candles)
        if max_high <= min_low:
            max_high = min_low + 1.0

        bin_size = (max_high - min_low) / price_bins
        if bin_size <= 0:
            bin_size = 0.01

        volume_by_bin = [0.0] * price_bins
        total_volume  = 0.0

        for c in candles:
            h  = float(c.get("high",   0) or 0)
            l  = float(c.get("low",    0) or 0)
            cl = float(c.get("close",  0) or 0)
            v  = float(c.get("volume", 0) or 0)
            tp = (h + l + cl) / 3.0
            bi = int((tp - min_low) / bin_size)
            bi = max(0, min(price_bins - 1, bi))
            volume_by_bin[bi] += v
            total_volume       += v

        poc_bin = volume_by_bin.index(max(volume_by_bin))
        poc     = min_low + (poc_bin + 0.5) * bin_size

        # Value Area: expand from POC until 70% of total volume is covered
        va_target = total_volume * 0.70
        va_vol    = volume_by_bin[poc_bin]
        lo, hi    = poc_bin, poc_bin

        while va_vol < va_target and (lo > 0 or hi < price_bins - 1):
            vol_below = volume_by_bin[lo - 1] if lo > 0              else 0.0
            vol_above = volume_by_bin[hi + 1] if hi < price_bins - 1 else 0.0
            if vol_below == 0 and vol_above == 0:
                break
            if vol_above >= vol_below and hi < price_bins - 1:
                hi     += 1
                va_vol += volume_by_bin[hi]
            elif lo > 0:
                lo     -= 1
                va_vol += volume_by_bin[lo]
            else:
                hi     += 1
                va_vol += volume_by_bin[hi]

        vah = min_low + (hi + 1) * bin_size
        val = min_low + lo        * bin_size

        # Previous-day POC
        prev_poc = None
        try:
            candle_dates = []
            for c in candles:
                ts = c.get("timestamp")
                if ts:
                    try:
                        if isinstance(ts, (int, float)):
                            dt = datetime.fromtimestamp(float(ts), tz=IST)
                        else:
                            dt = datetime.fromisoformat(str(ts))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=IST)
                            else:
                                dt = dt.astimezone(IST)
                        candle_dates.append((c, dt.date()))
                    except Exception:
                        candle_dates.append((c, None))
                else:
                    candle_dates.append((c, None))

            known_dates = sorted(
                {d for _, d in candle_dates if d is not None}, reverse=True
            )
            if len(known_dates) >= 2:
                prev_date    = known_dates[1]
                prev_candles = [c for c, d in candle_dates if d == prev_date]
                if len(prev_candles) >= 5:
                    p_min = min(float(c.get("low",  0) or 0) for c in prev_candles)
                    p_max = max(float(c.get("high", 0) or 0) for c in prev_candles)
                    if p_max > p_min:
                        p_bs = (p_max - p_min) / price_bins
                        if p_bs > 0:
                            p_bins = [0.0] * price_bins
                            for c in prev_candles:
                                h  = float(c.get("high",   0) or 0)
                                l  = float(c.get("low",    0) or 0)
                                cl = float(c.get("close",  0) or 0)
                                v  = float(c.get("volume", 0) or 0)
                                tp = (h + l + cl) / 3.0
                                bi = int((tp - p_min) / p_bs)
                                bi = max(0, min(price_bins - 1, bi))
                                p_bins[bi] += v
                            p_poc_bin = p_bins.index(max(p_bins))
                            prev_poc  = round(p_min + (p_poc_bin + 0.5) * p_bs, 2)
        except Exception:
            prev_poc = None

        # Volume Profile strength
        vp_strength = "NORMAL"
        if len(candles) >= 20:
            all_vols  = [float(c.get("volume", 0) or 0) for c in candles]
            avg_vol   = sum(all_vols[-20:]) / 20.0
            today_avg = total_volume / len(candles)
            if today_avg > avg_vol * 1.5:
                vp_strength = "STRONG"
            elif today_avg < avg_vol * 0.7:
                vp_strength = "WEAK"

        tol         = 0.0025
        price_at_poc = abs(current_price - poc) / poc < tol if poc > 0 else False
        price_at_vah = abs(current_price - vah) / vah < tol if vah > 0 else False
        price_at_val = abs(current_price - val) / val < tol if val > 0 else False
        poc_dist     = round(abs(current_price - poc) / poc * 100, 4) if poc > 0 else 0.0

        prev_poc_dist = None
        at_prev_poc   = False
        if prev_poc and prev_poc > 0:
            prev_poc_dist = round(abs(current_price - prev_poc) / prev_poc * 100, 4)
            at_prev_poc   = prev_poc_dist < 0.3

        pva = (
            "ABOVE_VAH" if current_price > vah else
            "BELOW_VAL" if current_price < val else
            "INSIDE_VA"
        )

        return {
            "vp_poc":                  round(poc, 2),
            "vp_vah":                  round(vah, 2),
            "vp_val":                  round(val, 2),
            "vp_prev_poc":             prev_poc,
            "vp_total_volume":         int(total_volume),
            "price_vs_va":             pva,
            "price_at_poc":            price_at_poc,
            "price_at_vah":            price_at_vah,
            "price_at_val":            price_at_val,
            "poc_distance_pct":        poc_dist,
            "prev_poc_distance_pct":   prev_poc_dist,
            "at_prev_poc":             at_prev_poc,
            "volume_profile_strength": vp_strength,
        }

    # ──────────────────────────────────────────────────────
    # Fair Value Gaps (Day 19)
    # ──────────────────────────────────────────────────────

    def add_fair_value_gaps(
        self,
        candles: list,
        current_price: float,
        lookback: int = 20,
    ) -> dict:
        _defaults = {
            "fvg_bullish_exists":       False,
            "fvg_bullish_top":          None,
            "fvg_bullish_bottom":       None,
            "fvg_bearish_exists":       False,
            "fvg_bearish_top":          None,
            "fvg_bearish_bottom":       None,
            "price_in_fvg":             False,
            "price_in_bullish_fvg":     False,
            "price_in_bearish_fvg":     False,
            "nearest_fvg_distance_pct": 0.0,
            "fvg_count":                0,
        }
        try:
            return self._fair_value_gaps(candles, current_price, lookback)
        except Exception as exc:
            logger.warning("[features] add_fair_value_gaps() failed: %s", exc)
            return _defaults

    def _fair_value_gaps(
        self,
        candles: list,
        current_price: float,
        lookback: int,
    ) -> dict:
        _empty = {
            "fvg_bullish_exists":       False,
            "fvg_bullish_top":          None,
            "fvg_bullish_bottom":       None,
            "fvg_bearish_exists":       False,
            "fvg_bearish_top":          None,
            "fvg_bearish_bottom":       None,
            "price_in_fvg":             False,
            "price_in_bullish_fvg":     False,
            "price_in_bearish_fvg":     False,
            "nearest_fvg_distance_pct": 0.0,
            "fvg_count":                0,
        }
        if len(candles) < 3:
            return _empty

        scan_window = candles[-lookback:] if len(candles) > lookback else candles

        # (bottom, top) tuples for unfilled FVGs
        bullish_fvgs: list = []
        bearish_fvgs: list = []

        for i in range(len(scan_window) - 2):
            c1 = scan_window[i]
            c3 = scan_window[i + 2]

            h1 = float(c1.get("high", 0) or 0)
            l1 = float(c1.get("low",  0) or 0)
            h3 = float(c3.get("high", 0) or 0)
            l3 = float(c3.get("low",  0) or 0)

            # Bullish FVG: gap between candle1.high and candle3.low
            if h1 > 0 and l3 > 0 and h1 < l3:
                # Unfilled if price has not fallen back below the gap bottom
                if current_price > h1:
                    bullish_fvgs.append((h1, l3))

            # Bearish FVG: gap between candle3.high and candle1.low
            if l1 > 0 and h3 > 0 and l1 > h3:
                # Unfilled if price has not risen back above the gap top
                if current_price < l1:
                    bearish_fvgs.append((h3, l1))

        fvg_count = len(bullish_fvgs) + len(bearish_fvgs)

        price_in_bullish_fvg = any(b <= current_price <= t for b, t in bullish_fvgs)
        price_in_bearish_fvg = any(b <= current_price <= t for b, t in bearish_fvgs)
        price_in_fvg         = price_in_bullish_fvg or price_in_bearish_fvg

        # Nearest bullish FVG
        nearest_bull     = None
        bull_dist        = float("inf")
        for b, t in bullish_fvgs:
            if b <= current_price <= t:
                dist = 0.0
            elif current_price > t:
                dist = (current_price - t) / t * 100 if t > 0 else float("inf")
            else:
                dist = (b - current_price) / b * 100 if b > 0 else float("inf")
            if dist < bull_dist:
                bull_dist    = dist
                nearest_bull = (b, t)

        # Nearest bearish FVG
        nearest_bear = None
        bear_dist    = float("inf")
        for b, t in bearish_fvgs:
            if b <= current_price <= t:
                dist = 0.0
            elif current_price < b:
                dist = (b - current_price) / b * 100 if b > 0 else float("inf")
            else:
                dist = (current_price - t) / t * 100 if t > 0 else float("inf")
            if dist < bear_dist:
                bear_dist    = dist
                nearest_bear = (b, t)

        nearest_dist = min(bull_dist, bear_dist)
        if nearest_dist == float("inf"):
            nearest_dist = 0.0

        return {
            "fvg_bullish_exists":       len(bullish_fvgs) > 0,
            "fvg_bullish_top":          round(nearest_bull[1], 2) if nearest_bull else None,
            "fvg_bullish_bottom":       round(nearest_bull[0], 2) if nearest_bull else None,
            "fvg_bearish_exists":       len(bearish_fvgs) > 0,
            "fvg_bearish_top":          round(nearest_bear[1], 2) if nearest_bear else None,
            "fvg_bearish_bottom":       round(nearest_bear[0], 2) if nearest_bear else None,
            "price_in_fvg":             price_in_fvg,
            "price_in_bullish_fvg":     price_in_bullish_fvg,
            "price_in_bearish_fvg":     price_in_bearish_fvg,
            "nearest_fvg_distance_pct": round(nearest_dist, 4),
            "fvg_count":                fvg_count,
        }


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
