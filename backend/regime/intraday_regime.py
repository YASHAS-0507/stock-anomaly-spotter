"""
intraday_regime.py
------------------
Classifies current market conditions into one of 12 intraday regimes and
determines whether trading is permitted for that regime.

Detection order (hard blocks evaluated first):
  1. Time gates  — PRE_OPEN, FIRST_15_MIN, DEAD_ZONE, LAST_15_MIN, CLOSED
  2. VIX gates   — EXTREME_VOLATILITY, HIGH_VOLATILITY
  3. Technical   — CHOPPY, BREAKOUT, TRENDING_UP, TRENDING_DOWN, RANGING

Phase 1: no short-selling → TRENDING_DOWN has trading_permitted=False.
"""

import logging
from datetime import datetime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# ── Regime catalogue ──────────────────────────────────────────────────────────
# Each entry: (trading_permitted, size_multiplier)
_REGIME_PROPS: dict[str, tuple[bool, float]] = {
    "PRE_OPEN":           (False, 0.0),
    "FIRST_15_MIN":       (False, 0.0),
    "TRENDING_UP":        (True,  1.0),
    "TRENDING_DOWN":      (False, 0.0),   # Phase 1: no shorts
    "RANGING":            (True,  0.5),
    "BREAKOUT":           (True,  1.0),
    "CHOPPY":             (False, 0.0),
    "HIGH_VOLATILITY":    (True,  0.5),
    "EXTREME_VOLATILITY": (False, 0.0),
    "DEAD_ZONE":          (False, 0.0),
    "WINDOW2":            (True,  0.8),
    "LAST_15_MIN":        (False, 0.0),
    "CLOSED":             (False, 0.0),
}

# Market session boundaries (hour, minute) in IST
_OPEN_H,        _OPEN_M        = 9,  15
_ORB_END_H,     _ORB_END_M     = 9,  30
_DEAD_START_H,  _DEAD_START_M  = 11, 30
_DEAD_END_H,    _DEAD_END_M    = 14,  0
_LAST15_H,      _LAST15_M      = 15,  0
_CLOSE_H,       _CLOSE_M       = 15, 30


def _to_mins(h: int, m: int) -> int:
    return h * 60 + m


_OPEN_MINS       = _to_mins(_OPEN_H,       _OPEN_M)
_ORB_END_MINS    = _to_mins(_ORB_END_H,    _ORB_END_M)
_DEAD_START_MINS = _to_mins(_DEAD_START_H, _DEAD_START_M)
_DEAD_END_MINS   = _to_mins(_DEAD_END_H,   _DEAD_END_M)
_LAST15_MINS     = _to_mins(_LAST15_H,     _LAST15_M)
_CLOSE_MINS      = _to_mins(_CLOSE_H,      _CLOSE_M)


class IntradayRegimeDetector:
    """Stateless regime classifier — all state lives in inputs."""

    def detect(
        self,
        features: dict,
        market_mood: dict,
        current_time: Optional[datetime] = None,
    ) -> dict:
        """
        Detect the current intraday regime.

        Parameters
        ----------
        features     : dict from IntradayFeatures.compute()
        market_mood  : dict from MarketMood.get_mood()
        current_time : datetime (tz-aware); defaults to datetime.now(IST)

        Returns
        -------
        dict with keys:
            regime, trading_permitted, size_multiplier, reason, confidence
        """
        try:
            return self._detect(features, market_mood, current_time)
        except Exception as exc:
            logger.warning("[regime] detect() failed: %s", exc)
            return _build("CLOSED", "Exception in regime detection — defaulting to CLOSED", 0.5)

    # ──────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────

    def _detect(
        self,
        features: dict,
        market_mood: dict,
        current_time: Optional[datetime],
    ) -> dict:
        now = current_time if current_time is not None else datetime.now(IST)
        # Normalise to IST
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)

        now_mins = _to_mins(now.hour, now.minute)

        # ── 1. Hard time gates ────────────────────────────────────────────
        if now_mins < _OPEN_MINS:
            return _build("PRE_OPEN",
                          f"Before market open ({now.hour}:{now.minute:02d} IST)", 1.0)

        if _OPEN_MINS <= now_mins < _ORB_END_MINS:
            return _build("FIRST_15_MIN",
                          "Opening 15 minutes — waiting for ORB to form", 1.0)

        if _DEAD_START_MINS <= now_mins < _DEAD_END_MINS:
            return _build("DEAD_ZONE",
                          "Mid-session dead zone (11:30–14:00) — low alpha", 1.0)

        if _LAST15_MINS <= now_mins < _CLOSE_MINS:
            return _build("LAST_15_MIN",
                          "Last 15 minutes before close — avoid new entries", 1.0)

        if now_mins >= _CLOSE_MINS:
            return _build("CLOSED",
                          "Market closed (after 15:30 IST)", 1.0)

        # ── 2. VIX gates ─────────────────────────────────────────────────
        vix = float(market_mood.get("vix", 15.0) or 15.0)
        vix_regime = "HIGH" if vix > 20.0 else "NORMAL"

        if vix > 25.0:
            return _build("EXTREME_VOLATILITY",
                          f"India VIX={vix:.1f} (>25) — tail risk, no trading", 0.9,
                          vix_regime=vix_regime)

        if vix > 20.0:
            return _build("HIGH_VOLATILITY",
                          f"India VIX={vix:.1f} (20–25) — elevated fear, half size", 0.85,
                          vix_regime=vix_regime)

        # ── 3. Technical regime detection ────────────────────────────────
        zscore       = float(features.get("return_zscore", 0.0) or 0.0)
        orb_breakout = bool(features.get("orb_breakout", False))
        vol_ratio    = float(features.get("volume_ratio", 1.0) or 1.0)
        above_vwap   = bool(features.get("price_above_vwap", False))
        ema9_above   = bool(features.get("ema9_above_ema21", False))
        bb_squeeze   = bool(features.get("bollinger_squeeze", False))

        # Determine if we're in window2 (14:00–15:00) for WINDOW2 regime
        in_window2 = _DEAD_END_MINS <= now_mins < _LAST15_MINS

        if zscore > 2.0:
            return _build("CHOPPY",
                          f"Return z-score={zscore:.2f} (>2.0) — erratic price action", 0.75,
                          vix_regime=vix_regime)

        if orb_breakout and vol_ratio > 1.5:
            conf = min(0.95, 0.70 + (vol_ratio - 1.5) * 0.1)
            return _build("BREAKOUT",
                          f"ORB breakout confirmed, volume={vol_ratio:.1f}× avg", round(conf, 2),
                          vix_regime=vix_regime)

        if above_vwap and ema9_above and vol_ratio > 1.2:
            conf = min(0.90, 0.65 + (vol_ratio - 1.2) * 0.08)
            return _build("TRENDING_UP",
                          f"Price above VWAP & EMA9>EMA21, volume={vol_ratio:.1f}× avg",
                          round(conf, 2), vix_regime=vix_regime)

        if not above_vwap and not ema9_above:
            return _build("TRENDING_DOWN",
                          "Price below VWAP and EMA9<EMA21 — downtrend (no shorting Phase 1)",
                          0.70, vix_regime=vix_regime)

        if bb_squeeze:
            return _build("RANGING",
                          "Bollinger Bands squeezing — low-volatility range", 0.65,
                          vix_regime=vix_regime)

        if in_window2:
            return _build("WINDOW2",
                          "Afternoon session (14:00–15:00) — reduced size", 0.60,
                          vix_regime=vix_regime)

        # Default
        return _build("RANGING",
                      "No strong directional signal — ranging conditions", 0.50,
                      vix_regime=vix_regime)


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _build(regime: str, reason: str, confidence: float, vix_regime: str = "NORMAL") -> dict:
    permitted, multiplier = _REGIME_PROPS.get(regime, (False, 0.0))
    return {
        "regime":           regime,
        "trading_permitted": permitted,
        "size_multiplier":  multiplier,
        "reason":           reason,
        "confidence":       round(max(0.0, min(1.0, confidence)), 4),
        "vix_regime":       vix_regime,
    }
