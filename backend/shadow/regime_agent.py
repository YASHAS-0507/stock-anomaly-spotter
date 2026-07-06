"""
regime_agent.py
---------------
Regime-aware shadow agent: scores market conditions more granularly than
the binary trading_permitted flag in IntradayRegimeDetector.
Observes silently — never executes trades.
"""

import logging

logger = logging.getLogger(__name__)


class RegimeAgent:
    """Shadow agent that learns regime edge-cases the rule system misses."""

    def predict(
        self,
        features: dict,
        regime: dict,
        market_mood: dict,
    ) -> dict:
        """
        Score regime + macro conditions.

        Returns
        -------
        dict with signal ("BUY"|"HOLD"|"SKIP"), confidence (float), reasoning (str)
        """
        try:
            return self._predict(features, regime, market_mood)
        except Exception as exc:
            logger.debug("[regime_agent] predict() failed: %s", exc)
            return {"signal": "HOLD", "confidence": 0.5, "reasoning": "Error — defaulting to HOLD"}

    def _predict(self, features: dict, regime: dict, market_mood: dict) -> dict:
        score = 0.5
        notes = []

        regime_name = str(regime.get("regime", "") or "").upper()
        vix         = float(market_mood.get("vix", 15.0) or 15.0)
        vol_ratio   = float(features.get("volume_ratio", 1.0) or 1.0)

        # ── Regime adjustments ────────────────────────────────────────────
        _regime_deltas = {
            "TRENDING_UP":     +0.15,
            "BREAKOUT":        +0.12,
            "RANGING":         -0.05,
            "CHOPPY":          -0.20,
            "HIGH_VOLATILITY": -0.10,
        }
        if regime_name in _regime_deltas:
            delta = _regime_deltas[regime_name]
            score += delta
            notes.append(f"{regime_name}({delta:+.2f})")

        # ── VIX adjustments ───────────────────────────────────────────────
        if vix < 13.0:
            score += 0.08; notes.append(f"VIX={vix:.1f} (low fear)")
        elif vix <= 20.0:
            pass                # neutral
        elif vix <= 25.0:
            score -= 0.10; notes.append(f"VIX={vix:.1f} (elevated)")
        else:
            score -= 0.25; notes.append(f"VIX={vix:.1f} (extreme)")

        # ── Volume ────────────────────────────────────────────────────────
        if vol_ratio > 2.0:
            score += 0.07; notes.append(f"vol={vol_ratio:.1f}x (surge)")
        elif vol_ratio < 0.8:
            score -= 0.07; notes.append(f"vol={vol_ratio:.1f}x (dry)")

        # ── Price structure ───────────────────────────────────────────────
        if features.get("higher_highs") and features.get("higher_lows"):
            score += 0.06; notes.append("HH+HL")

        score = round(max(0.0, min(1.0, score)), 4)
        reasoning = f"score={score:.2f} | " + (", ".join(notes) if notes else "neutral")

        if score > 0.62:
            signal = "BUY"
        elif score < 0.45:
            signal = "SKIP"
        else:
            signal = "HOLD"

        return {"signal": signal, "confidence": score, "reasoning": reasoning}
