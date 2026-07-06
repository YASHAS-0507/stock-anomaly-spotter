"""
wyckoff_detector.py
-------------------
Detects Wyckoff accumulation/distribution ranges, springs, upthrusts,
and breakouts from intraday 5-min candle data.

Wyckoff phases detected:
  Accumulation — trading range preceded by downtrend; VI > 1.1; stable lows
  Distribution — trading range preceded by uptrend;  VI < 0.9; failing highs
  Spring       — false break below accumulation support with quick recovery
  Upthrust     — false break above distribution resistance with quick reversal
  Breakout     — confirmed exit from range with volume

All computations are purely in Python — no network calls, never raises.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WyckoffDetector:
    """
    Detects Wyckoff structures from a list of 5-min OHLCV candle dicts.

    Parameters (tunable)
    --------------------
    min_range_bars        : minimum bars to qualify as a Wyckoff range
    max_range_bars        : maximum bars considered in sliding window
    k_span                : price span <= k_span * ATR to qualify as range
    adx_range_threshold   : ADX must be below this to confirm ranging
    spring_alpha          : spring must pierce support by > alpha * ATR
    spring_beta           : (close-low)/(high-low) recovery ratio
    spring_gamma          : volume >= gamma * avg_range_volume
    breakout_delta        : breakout close must exceed range edge by delta*ATR
    breakout_eta          : volume >= eta * avg_range_volume for confirmation
    """

    def __init__(self):
        self.min_range_bars = 20
        self.max_range_bars = 60
        self.k_span = 1.5
        self.adx_range_threshold = 20
        self.spring_alpha = 0.5
        self.spring_beta = 0.6
        self.spring_gamma = 1.3
        self.breakout_delta = 0.4
        self.breakout_eta = 1.3

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def detect(
        self,
        candles: list,
        current_price: float,
        atr: float,
        adx: float,
    ) -> dict:
        """
        Run the full Wyckoff detection pipeline.

        Parameters
        ----------
        candles       : list of 5-min OHLCV dicts (ascending time order)
        current_price : latest traded price
        atr           : ATR-14 already computed by intraday_features
        adx           : ADX-14 already computed by intraday_features

        Returns
        -------
        dict with 18 wyckoff_ keys (see _default_features for full list)
        """
        try:
            if not candles or len(candles) < self.min_range_bars or atr <= 0:
                return self._default_features()

            ranges = self._detect_ranges(candles, atr, adx)
            if not ranges:
                return self._default_features()

            # Classify each detected range
            for r in ranges:
                self._classify_range(r, candles)

            active = self._get_active_range(ranges, candles)
            if active is None:
                return self._default_features()

            spring   = self._detect_spring(active, candles, atr)
            upthrust = self._detect_upthrust(active, candles, atr)
            breakout = self._detect_breakout(active, candles, atr)

            return self._build_features(active, spring, upthrust, breakout, current_price)

        except Exception as exc:
            logger.debug("[wyckoff] detect() error: %s", exc)
            return self._default_features()

    # ──────────────────────────────────────────────────────
    # Range detection
    # ──────────────────────────────────────────────────────

    def _detect_ranges(self, candles: list, atr: float, adx: float) -> list:
        """
        Sliding-window scan for Wyckoff ranges.

        A range qualifies when:
          - price span (high_max - low_min) <= k_span * ATR
          - ADX < adx_range_threshold (price is ranging, not trending)
        """
        n = len(candles)
        found = []
        step = max(1, self.min_range_bars // 4)

        start = 0
        while start + self.min_range_bars <= n:
            # Find the longest qualifying window starting at `start`
            best_end = None
            for end in range(
                min(start + self.max_range_bars, n),
                start + self.min_range_bars - 1,
                -1,
            ):
                window = candles[start:end]
                highs  = [c["high"]   for c in window]
                lows   = [c["low"]    for c in window]
                vols   = [c["volume"] for c in window]
                span   = max(highs) - min(lows)
                if span <= self.k_span * atr and adx < self.adx_range_threshold:
                    best_end = end
                    break

            if best_end is not None:
                window = candles[start:best_end]
                highs  = [c["high"]   for c in window]
                lows   = [c["low"]    for c in window]
                vols   = [c["volume"] for c in window]
                avg_vol = sum(vols) / len(vols) if vols else 1.0
                found.append({
                    "start_idx":    start,
                    "end_idx":      best_end,
                    "support":      min(lows),
                    "resistance":   max(highs),
                    "avg_volume":   avg_vol,
                    "duration_bars": best_end - start,
                    "type":         None,
                    "vi_ratio":     None,
                })
                # Advance past this range to avoid heavy overlap
                start = best_end
            else:
                start += step

        return found

    # ──────────────────────────────────────────────────────
    # Range classification
    # ──────────────────────────────────────────────────────

    def _classify_range(self, range_obj: dict, candles: list) -> None:
        """
        Classify a range as ACCUMULATION, DISTRIBUTION, or None.

        Mutates range_obj["type"] and range_obj["vi_ratio"] in place.

        Logic
        -----
        1. Compute VI = avg_volume_on_up_bars / avg_volume_on_down_bars
        2. Check the pre-range trend (bars before range start):
             downtrend → close fell > 2 * (resistance - support) before range
             uptrend   → close rose  > 2 * (resistance - support) before range
        3. ACCUMULATION: downtrend + VI > 1.1 + lower half lows stable
           DISTRIBUTION: uptrend   + VI < 0.9 + upper half highs failing
        """
        start = range_obj["start_idx"]
        end   = range_obj["end_idx"]
        window = candles[start:end]

        if not window:
            return

        support    = range_obj["support"]
        resistance = range_obj["resistance"]
        midpoint   = (support + resistance) / 2.0

        # Volume Imbalance (VI)
        up_vols   = [c["volume"] for c in window if c["close"] >= c["open"]]
        down_vols = [c["volume"] for c in window if c["close"] < c["open"]]
        avg_up    = sum(up_vols)   / len(up_vols)   if up_vols   else 0.0
        avg_down  = sum(down_vols) / len(down_vols) if down_vols else 1.0
        vi_ratio  = avg_up / (avg_down + 1e-9)
        range_obj["vi_ratio"] = round(vi_ratio, 3)

        # Pre-range trend check
        lookback = min(start, self.min_range_bars)
        pre_range_bars = candles[max(0, start - lookback):start]
        span = resistance - support
        preceded_by_downtrend = False
        preceded_by_uptrend   = False

        if len(pre_range_bars) >= 5:
            pre_closes = [c["close"] for c in pre_range_bars]
            price_change = pre_closes[-1] - pre_closes[0]
            if price_change < -2.0 * span:
                preceded_by_downtrend = True
            elif price_change > 2.0 * span:
                preceded_by_uptrend = True

        # Low stability check (for accumulation): lows shouldn't be making
        # new lows in the second half of the range
        lower_half_lows = [c["low"] for c in window if c["low"] < midpoint]
        lows_stable = True
        if len(lower_half_lows) >= 4:
            first_half = lower_half_lows[: len(lower_half_lows) // 2]
            second_half = lower_half_lows[len(lower_half_lows) // 2 :]
            if second_half and first_half:
                if min(second_half) < min(first_half) * 0.998:
                    lows_stable = False

        # High failure check (for distribution): highs failing in second half
        upper_half_highs = [c["high"] for c in window if c["high"] > midpoint]
        highs_failing = False
        if len(upper_half_highs) >= 4:
            first_half  = upper_half_highs[: len(upper_half_highs) // 2]
            second_half = upper_half_highs[len(upper_half_highs) // 2 :]
            if second_half and first_half:
                if max(second_half) < max(first_half) * 0.998:
                    highs_failing = True

        if preceded_by_downtrend and vi_ratio > 1.1 and lows_stable:
            range_obj["type"] = "ACCUMULATION"
        elif preceded_by_uptrend and vi_ratio < 0.9 and highs_failing:
            range_obj["type"] = "DISTRIBUTION"
        else:
            range_obj["type"] = None

    # ──────────────────────────────────────────────────────
    # Spring detection
    # ──────────────────────────────────────────────────────

    def _detect_spring(
        self, range_obj: dict, candles: list, atr: float
    ) -> Optional[dict]:
        """
        Detect a Wyckoff spring (bear trap below support) in an ACCUMULATION range.

        Spring conditions (all must be true):
          1. low < support - alpha * ATR          (penetrated support)
          2. close > support                      (recovered above support)
          3. (close - low) / (high - low) >= beta (strong close relative to range)
          4. volume >= gamma * avg_range_volume   (volume surge)

        Returns dict with spring details or None.
        """
        if range_obj.get("type") != "ACCUMULATION":
            return None

        support    = range_obj["support"]
        avg_vol    = range_obj["avg_volume"]
        start      = range_obj["start_idx"]
        end        = range_obj["end_idx"]

        # Look for spring bars within and just after the range
        search_end = min(end + 5, len(candles))
        spring     = None

        for i in range(start, search_end):
            c = candles[i]
            candle_range = c["high"] - c["low"]
            if candle_range <= 0:
                continue

            penetrates  = c["low"] < support - self.spring_alpha * atr
            recovers    = c["close"] > support
            strong_close = (c["close"] - c["low"]) / candle_range >= self.spring_beta
            vol_surge   = c["volume"] >= self.spring_gamma * avg_vol

            if penetrates and recovers and strong_close and vol_surge:
                depth_atr    = round((support - c["low"]) / atr, 3) if atr > 0 else 0.0
                vol_ratio    = round(c["volume"] / avg_vol, 3) if avg_vol > 0 else 0.0
                # Follow-through: next bar closes higher than this bar's close
                follow = False
                if i + 1 < len(candles):
                    follow = candles[i + 1]["close"] > c["close"]
                spring = {
                    "bar_idx":             i,
                    "spring_low":          c["low"],
                    "spring_depth_atr":    depth_atr,
                    "spring_volume_ratio": vol_ratio,
                    "follow_through":      follow,
                }

        return spring

    # ──────────────────────────────────────────────────────
    # Upthrust detection
    # ──────────────────────────────────────────────────────

    def _detect_upthrust(
        self, range_obj: dict, candles: list, atr: float
    ) -> Optional[dict]:
        """
        Detect a Wyckoff upthrust (bull trap above resistance) in a DISTRIBUTION range.

        Upthrust conditions (mirror of spring):
          1. high > resistance + alpha * ATR      (penetrated resistance)
          2. close < resistance                   (rejected back below)
          3. (high - close) / (high - low) >= beta (weak close)
          4. volume >= gamma * avg_range_volume   (volume surge)
        """
        if range_obj.get("type") != "DISTRIBUTION":
            return None

        resistance = range_obj["resistance"]
        avg_vol    = range_obj["avg_volume"]
        start      = range_obj["start_idx"]
        end        = range_obj["end_idx"]

        search_end = min(end + 5, len(candles))
        upthrust   = None

        for i in range(start, search_end):
            c = candles[i]
            candle_range = c["high"] - c["low"]
            if candle_range <= 0:
                continue

            penetrates   = c["high"] > resistance + self.spring_alpha * atr
            rejected     = c["close"] < resistance
            weak_close   = (c["high"] - c["close"]) / candle_range >= self.spring_beta
            vol_surge    = c["volume"] >= self.spring_gamma * avg_vol

            if penetrates and rejected and weak_close and vol_surge:
                depth_atr  = round((c["high"] - resistance) / atr, 3) if atr > 0 else 0.0
                vol_ratio  = round(c["volume"] / avg_vol, 3) if avg_vol > 0 else 0.0
                upthrust = {
                    "bar_idx":              i,
                    "upthrust_high":        c["high"],
                    "upthrust_depth_atr":   depth_atr,
                    "upthrust_volume_ratio": vol_ratio,
                }

        return upthrust

    # ──────────────────────────────────────────────────────
    # Breakout detection
    # ──────────────────────────────────────────────────────

    def _detect_breakout(
        self, range_obj: dict, candles: list, atr: float
    ) -> Optional[dict]:
        """
        Detect a confirmed Wyckoff breakout from the active range.

        Checks the most recent candles after range end.
        Bullish: close > resistance + delta*ATR  AND volume >= eta*avg_vol
        Bearish: close < support - delta*ATR     AND volume >= eta*avg_vol

        Returns dict with direction, strength, and confirmation status.
        """
        end        = range_obj["end_idx"]
        support    = range_obj["support"]
        resistance = range_obj["resistance"]
        avg_vol    = range_obj["avg_volume"]
        n          = len(candles)

        if end >= n:
            return None

        # Look at post-range candles (up to last 10)
        search_start = max(end, n - 10)
        for i in range(n - 1, search_start - 1, -1):
            c = candles[i]
            vol_ok = c["volume"] >= self.breakout_eta * avg_vol

            if c["close"] > resistance + self.breakout_delta * atr and vol_ok:
                strength = round(
                    (c["close"] - resistance) / atr, 3
                ) if atr > 0 else 0.0
                return {
                    "direction":         "BULLISH",
                    "confirmed":         True,
                    "breakout_strength": strength,
                    "volume_ratio":      round(c["volume"] / avg_vol, 3) if avg_vol > 0 else 0.0,
                    "bars_since_range_end": n - 1 - end,
                }

            if c["close"] < support - self.breakout_delta * atr and vol_ok:
                strength = round(
                    (support - c["close"]) / atr, 3
                ) if atr > 0 else 0.0
                return {
                    "direction":         "BEARISH",
                    "confirmed":         True,
                    "breakout_strength": strength,
                    "volume_ratio":      round(c["volume"] / avg_vol, 3) if avg_vol > 0 else 0.0,
                    "bars_since_range_end": n - 1 - end,
                }

        return None

    # ──────────────────────────────────────────────────────
    # Active range selection
    # ──────────────────────────────────────────────────────

    def _get_active_range(self, ranges: list, candles: list) -> Optional[dict]:
        """Return the most recently ended range (highest end_idx)."""
        if not ranges:
            return None
        return max(ranges, key=lambda r: r["end_idx"])

    # ──────────────────────────────────────────────────────
    # Feature assembly
    # ──────────────────────────────────────────────────────

    def _build_features(
        self,
        active_range: dict,
        spring: Optional[dict],
        upthrust: Optional[dict],
        breakout: Optional[dict],
        current_price: float,
    ) -> dict:
        """Assemble the 18 wyckoff_ feature keys from detected structures."""
        features = self._default_features()

        range_type = active_range.get("type")  # ACCUMULATION / DISTRIBUTION / None
        support    = active_range["support"]
        resistance = active_range["resistance"]
        vi_ratio   = active_range.get("vi_ratio", 1.0) or 1.0
        cause_bars = active_range["duration_bars"]

        # Basic range info
        in_range = support <= current_price <= resistance
        features["wyckoff_in_range"]       = in_range
        features["wyckoff_range_type"]     = range_type or "NONE"
        features["wyckoff_range_support"]  = round(support, 2)
        features["wyckoff_range_resistance"] = round(resistance, 2)
        features["wyckoff_cause_length_bars"] = cause_bars
        features["wyckoff_vi_ratio"]       = round(vi_ratio, 3)

        # Spring
        if spring is not None:
            features["wyckoff_spring_active"]        = True
            features["wyckoff_spring_depth_atr"]     = spring["spring_depth_atr"]
            features["wyckoff_spring_volume_ratio"]  = spring["spring_volume_ratio"]
            features["wyckoff_spring_follow_through"] = spring["follow_through"]

        # Upthrust
        if upthrust is not None:
            features["wyckoff_upthrust_active"]     = True
            features["wyckoff_upthrust_depth_atr"]  = upthrust["upthrust_depth_atr"]

        # Breakout / Breakdown
        if breakout is not None and breakout.get("confirmed"):
            strength = breakout.get("breakout_strength", 0.0)
            if breakout["direction"] == "BULLISH":
                features["wyckoff_breakout_confirmed"] = True
                features["wyckoff_breakout_strength"]  = strength
            else:
                features["wyckoff_breakdown_confirmed"] = True
                features["wyckoff_breakout_strength"]   = strength

        # Post-phase flags
        post_acc  = range_type == "ACCUMULATION" and features["wyckoff_breakout_confirmed"]
        post_dist = range_type == "DISTRIBUTION" and features["wyckoff_breakdown_confirmed"]
        features["wyckoff_post_accumulation"] = post_acc
        features["wyckoff_post_distribution"] = post_dist

        # Bias
        spring_active   = features["wyckoff_spring_active"]
        upthrust_active = features["wyckoff_upthrust_active"]

        if post_acc and spring_active:
            bias = "STRONG_BULL"
        elif post_acc:
            bias = "BULL"
        elif post_dist and upthrust_active:
            bias = "STRONG_BEAR"
        elif post_dist:
            bias = "BEAR"
        elif in_range:
            bias = "RANGING"
        else:
            bias = "NEUTRAL"

        features["wyckoff_bias"] = bias
        return features

    # ──────────────────────────────────────────────────────
    # Default features
    # ──────────────────────────────────────────────────────

    def _default_features(self) -> dict:
        return {
            "wyckoff_range_type":           "NONE",
            "wyckoff_in_range":             False,
            "wyckoff_range_support":        None,
            "wyckoff_range_resistance":     None,
            "wyckoff_spring_active":        False,
            "wyckoff_spring_depth_atr":     0.0,
            "wyckoff_spring_volume_ratio":  0.0,
            "wyckoff_spring_follow_through": False,
            "wyckoff_upthrust_active":      False,
            "wyckoff_upthrust_depth_atr":   0.0,
            "wyckoff_breakout_confirmed":   False,
            "wyckoff_breakdown_confirmed":  False,
            "wyckoff_breakout_strength":    0.0,
            "wyckoff_post_accumulation":    False,
            "wyckoff_post_distribution":    False,
            "wyckoff_cause_length_bars":    0,
            "wyckoff_vi_ratio":             1.0,
            "wyckoff_bias":                 "NEUTRAL",
        }


# Module-level singleton
wyckoff_detector = WyckoffDetector()
