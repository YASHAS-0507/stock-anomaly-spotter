"""
intraday_sizer.py
-----------------
ATR-based position sizer for intraday trades.

Risk model:
  - Risk 1% of available capital per trade (adjusted by size_multiplier)
  - Max position = 20% of available capital
  - TP1 = entry + 1.5× stop_distance
  - TP2 = entry + 3.0× stop_distance
"""

import logging

logger = logging.getLogger(__name__)


class IntradaySizer:
    """Calculates shares and risk/reward levels for a single trade."""

    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        available_capital: float,
        size_multiplier: float = 1.0,
        expiry_multiplier: float = 1.0,
    ) -> dict:
        """
        Compute position size and TP/SL levels.

        Parameters
        ----------
        entry_price       : intended entry price (₹)
        stop_loss         : stop-loss price (₹)
        available_capital : cash available in the broker account (₹)
        size_multiplier   : regime/VIX multiplier from IntradayRegimeDetector
        expiry_multiplier : F&O expiry risk multiplier from ExpiryCalendar

        Returns
        -------
        dict with viable=True and sizing details, or viable=False with reason
        """
        try:
            return self._calculate(
                entry_price, stop_loss, available_capital,
                size_multiplier, expiry_multiplier,
            )
        except Exception as exc:
            logger.warning("[sizer] calculate() failed: %s", exc)
            return {"viable": False, "reason": f"Internal error: {exc}"}

    def _calculate(
        self,
        entry_price: float,
        stop_loss: float,
        available_capital: float,
        size_multiplier: float,
        expiry_multiplier: float = 1.0,
    ) -> dict:
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return {"viable": False, "reason": "Invalid SL"}

        final_multiplier = max(0.0, size_multiplier) * max(0.0, expiry_multiplier)
        base_risk     = available_capital * 0.01
        adjusted_risk = base_risk * final_multiplier

        shares = int(adjusted_risk / stop_distance)

        # Cap at 20% of available capital
        position_value = shares * entry_price
        max_position   = available_capital * 0.20
        if position_value > max_position:
            shares = int(max_position / entry_price)

        if shares < 1:
            return {"viable": False, "reason": "Too small"}

        atr_stop   = stop_distance
        tp1        = entry_price + (atr_stop * 1.5)
        tp2        = entry_price + (atr_stop * 3.0)

        return {
            "viable":             True,
            "shares":             shares,
            "position_value":     round(shares * entry_price, 2),
            "risk_amount":        round(shares * stop_distance, 2),
            "stop_loss":          round(stop_loss, 2),
            "take_profit_1":      round(tp1, 2),
            "take_profit_2":      round(tp2, 2),
            "expiry_multiplier":  expiry_multiplier,
            "final_multiplier":   round(final_multiplier, 4),
        }


# Module-level singleton
intraday_sizer = IntradaySizer()
