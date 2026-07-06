"""
timing_agent.py
---------------
Time-of-day and day-of-week weighted shadow agent.
Observes silently — never executes trades.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class TimingAgent:
    """Shadow agent that weights signals by time-of-day and day-of-week."""

    def predict(
        self,
        features: dict,
        current_time: Optional[datetime] = None,
    ) -> dict:
        """
        Produce a time-weighted signal.

        Returns
        -------
        dict with signal ("BUY"|"HOLD"|"SKIP"), confidence (float), reasoning (str)
        """
        try:
            return self._predict(features, current_time)
        except Exception as exc:
            logger.debug("[timing_agent] predict() failed: %s", exc)
            return {"signal": "HOLD", "confidence": 0.5, "reasoning": "Error — defaulting to HOLD"}

    def _predict(self, features: dict, current_time: Optional[datetime]) -> dict:
        now = current_time if current_time is not None else datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)

        # ── Base signal from VWAP + EMA ──────────────────────────────────
        above_vwap = bool(features.get("price_above_vwap", False))
        ema_above  = bool(features.get("ema9_above_ema21", False))

        if above_vwap and ema_above:
            base_signal = 0.65
            base_note   = "VWAP+EMA aligned"
        elif above_vwap or ema_above:
            base_signal = 0.52
            base_note   = "partial VWAP/EMA"
        else:
            base_signal = 0.40
            base_note   = "below VWAP+EMA"

        # ── Time weight ──────────────────────────────────────────────────
        h, m        = now.hour, now.minute
        now_mins    = h * 60 + m
        _t          = lambda hh, mm: hh * 60 + mm

        if _t(9, 30) <= now_mins < _t(10, 0):
            time_w = 1.2; time_note = "open momentum window"
        elif _t(10, 0) <= now_mins < _t(11, 30):
            time_w = 1.0; time_note = "normal session"
        elif _t(11, 30) <= now_mins < _t(14, 0):
            time_w = 0.6; time_note = "dead zone"
        elif _t(14, 0) <= now_mins < _t(15, 0):
            time_w = 0.9; time_note = "afternoon window"
        else:
            time_w = 0.5; time_note = "outside core session"

        # ── Day weight ───────────────────────────────────────────────────
        weekday = now.weekday()   # 0=Mon … 6=Sun
        if weekday == 0:
            day_w = 0.9; day_note = "Monday"
        elif weekday == 4:
            day_w = 0.85; day_note = "Friday"
        elif weekday in (5, 6):
            day_w = 0.5; day_note = "weekend"
        else:
            day_w = 1.0; day_note = "mid-week"

        final     = round(max(0.0, min(1.0, base_signal * time_w * day_w)), 4)
        reasoning = f"score={final:.2f} | {base_note}, {time_note}, {day_note}"

        if final > 0.62:
            signal = "BUY"
        elif final < 0.45:
            signal = "SKIP"
        else:
            signal = "HOLD"

        return {"signal": signal, "confidence": final, "reasoning": reasoning}
