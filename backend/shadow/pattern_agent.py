"""
pattern_agent.py
----------------
Rule-based shadow agent that scores features against known bullish/bearish patterns.
Observes silently — never executes trades.
"""

import logging

logger = logging.getLogger(__name__)


class PatternAgent:
    """Rule-based pattern scorer that improves as outcomes accumulate."""

    def predict(
        self,
        features: dict,
        regime: dict,
        intelligence: dict,
    ) -> dict:
        """
        Score features against bullish/bearish patterns.

        Returns
        -------
        dict with signal ("BUY"|"HOLD"|"SKIP"), confidence (float), reasoning (str)
        """
        try:
            return self._predict(features, regime, intelligence)
        except Exception as exc:
            logger.debug("[pattern_agent] predict() failed: %s", exc)
            return {"signal": "HOLD", "confidence": 0.5, "reasoning": "Error — defaulting to HOLD"}

    def _predict(self, features: dict, regime: dict, intelligence: dict) -> dict:
        score  = 0.5
        notes  = []

        vol_ratio = float(features.get("volume_ratio", 1.0) or 1.0)
        rsi       = float(features.get("rsi_14", 50.0) or 50.0)
        macd_hist = float(features.get("macd_histogram", 0.0) or 0.0)
        zscore    = float(features.get("return_zscore", 0.0) or 0.0)
        news_act  = str(intelligence.get("action", "") or "").upper()

        if features.get("price_above_vwap"):
            score += 0.08; notes.append("above VWAP")

        if features.get("ema9_above_ema21"):
            score += 0.06; notes.append("EMA9>EMA21")

        if vol_ratio > 1.5:
            score += 0.05; notes.append(f"vol={vol_ratio:.1f}x")

        if 50.0 <= rsi <= 65.0:
            score += 0.07; notes.append(f"RSI={rsi:.0f} (bullish zone)")

        if macd_hist > 0:
            score += 0.06; notes.append("MACD positive")

        if features.get("orb_breakout"):
            score += 0.08; notes.append("ORB breakout")

        if zscore > 2.0:
            score -= 0.10; notes.append(f"z-score={zscore:.1f} (choppy)")

        if rsi > 70.0:
            score -= 0.07; notes.append(f"RSI={rsi:.0f} (overbought)")

        if vol_ratio < 0.8:
            score -= 0.05; notes.append(f"vol={vol_ratio:.1f}x (dry)")

        if news_act == "BOOST":
            score += 0.05; notes.append("news BOOST")

        if news_act == "BLOCK":
            score -= 0.08; notes.append("news BLOCK")

        score = round(max(0.0, min(1.0, score)), 4)

        if score > 0.62:
            signal = "BUY"
        elif score < 0.45:
            signal = "SKIP"
        else:
            signal = "HOLD"

        reasoning = f"score={score:.2f} | " + (", ".join(notes) if notes else "no signals")
        return {"signal": signal, "confidence": score, "reasoning": reasoning}
