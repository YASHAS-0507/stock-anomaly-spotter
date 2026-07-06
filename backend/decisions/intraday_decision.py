"""
intraday_decision.py
--------------------
Intraday signal generator: combines regime, ML prediction, news intelligence,
and four named setups to produce a BUY / HOLD / BLOCKED decision.

Decision order (strict):
  1. regime.trading_permitted False  → BLOCKED
  2. open_positions >= max_positions → BLOCKED
  3. cooldown active                 → BLOCKED
  4. No setup matches features       → HOLD
  5. combined_score < 65             → HOLD
  6. ml_confidence < setup threshold → HOLD
  7. All pass                        → BUY
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

DECISION_CONFIG = {
    "weights": {
        "technical":   0.45,
        "news":        0.30,
        "market_mood": 0.25,
    },
    "min_combined_score": 65,
    "min_ml_confidence":  0.55,
    "max_positions":      3,
    "cooldown_minutes":   15,
    "no_new_after":       "14:45",
    "hard_square_off":    "15:15",
}

SETUPS: dict[str, dict] = {
    "ORB_BREAKOUT": {
        "required": {
            "orb_breakout":        True,
            "volume_ratio_min":    1.5,
            "trading_window":      "window1",
        },
        "min_ml_confidence": 0.58,
    },
    "VWAP_BOUNCE": {
        "required": {
            "price_above_vwap":        True,
            "price_vs_vwap_pct_max":   0.15,
            "volume_ratio_min":        1.2,
            "rsi_min":                 45,
        },
        "min_ml_confidence": 0.55,
    },
    "TREND_CONTINUATION": {
        "required": {
            "ema9_above_ema21": True,
            "higher_highs":     True,
            "higher_lows":      True,
            "rsi_range":        [40, 65],
        },
        "min_ml_confidence": 0.57,
    },
    "NEWS_CATALYST": {
        "required": {
            "news_action":      "BOOST",
            "volume_ratio_min": 2.0,
        },
        "min_ml_confidence": 0.50,
    },
}


class IntradayDecisionEngine:
    """Combines all signals into a single actionable decision."""

    def generate_signal(
        self,
        ticker: str,
        features: dict,
        regime: dict,
        ml_prediction: dict,
        intelligence: dict,
        open_positions: int,
        last_trade_time: Optional[datetime] = None,
    ) -> dict:
        """
        Generate a trading signal for the given ticker.

        Parameters
        ----------
        ticker          : e.g. "RELIANCE.NS"
        features        : output of IntradayFeatures.compute()
        regime          : output of IntradayRegimeDetector.detect()
        ml_prediction   : output of IntradayModel.predict()
        intelligence    : output of LLMAnalyzer.analyze()
        open_positions  : number of currently open paper positions
        last_trade_time : datetime of the last trade (tz-aware); None if no trades

        Returns
        -------
        dict with signal, setup_type, combined_score, score_breakdown,
        ml_confidence, execution_permitted, rejection_reason, reasoning
        """
        try:
            return self._generate(
                ticker, features, regime, ml_prediction,
                intelligence, open_positions, last_trade_time,
            )
        except Exception as exc:
            logger.warning("[decision] generate_signal() failed for %s: %s", ticker, exc)
            return _blocked("Internal error in decision engine", setup_type=None)

    # ──────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────

    def _generate(
        self,
        ticker: str,
        features: dict,
        regime: dict,
        ml_prediction: dict,
        intelligence: dict,
        open_positions: int,
        last_trade_time: Optional[datetime],
    ) -> dict:
        cfg = DECISION_CONFIG

        # ── 1. Regime gate ────────────────────────────────────────────────
        if not regime.get("trading_permitted", False):
            regime_name = regime.get("regime", "UNKNOWN")
            return _blocked(f"Regime {regime_name} — trading not permitted", setup_type=None)

        # ── 2. Max positions gate ─────────────────────────────────────────
        if open_positions >= cfg["max_positions"]:
            return _blocked(
                f"Max positions reached ({open_positions}/{cfg['max_positions']})",
                setup_type=None,
            )

        # ── 3. Cooldown gate ──────────────────────────────────────────────
        if last_trade_time is not None:
            now = datetime.now(IST)
            lt  = last_trade_time
            if lt.tzinfo is None:
                lt = lt.replace(tzinfo=IST)
            else:
                lt = lt.astimezone(IST)
            elapsed_minutes = (now - lt).total_seconds() / 60.0
            if elapsed_minutes < cfg["cooldown_minutes"]:
                remaining = int(cfg["cooldown_minutes"] - elapsed_minutes)
                return _blocked(
                    f"Cooldown active — {remaining}min remaining",
                    setup_type=None,
                )

        # ── 4. Setup identification ───────────────────────────────────────
        setup_type = _match_setup(features, intelligence)
        if setup_type is None:
            return _hold("No setup pattern matches current conditions", combined_score=0)

        # ── 5. Combined score ─────────────────────────────────────────────
        prob_up = float(ml_prediction.get("prob_up", 0.5) or 0.5)
        intel_score = float(intelligence.get("intelligence_score", 50) or 50)
        # Normalise intelligence_score: accept 0-1 or 0-100
        if intel_score > 1.0:
            intel_score = intel_score / 100.0

        vix_regime = regime.get("vix_regime") or ""
        mood_score = 0.75 if vix_regime in ("NORMAL", "LOW") else 0.40

        technical_score = prob_up * 100.0          # 0–100
        news_score      = intel_score * 100.0      # 0–100
        mood_score_100  = mood_score * 100.0       # 0–100

        w = cfg["weights"]
        combined = (
            technical_score * w["technical"]
            + news_score    * w["news"]
            + mood_score_100 * w["market_mood"]
        )
        combined = round(combined, 1)

        score_breakdown = {
            "technical":   round(technical_score, 2),
            "news":        round(news_score, 2),
            "market_mood": round(mood_score_100, 2),
        }

        # ── 6. Score gate ─────────────────────────────────────────────────
        if combined < cfg["min_combined_score"]:
            return _hold(
                f"Combined score {combined:.0f} < threshold {cfg['min_combined_score']}",
                combined_score=int(combined),
                setup_type=setup_type,
                score_breakdown=score_breakdown,
                ml_confidence=prob_up,
            )

        # ── 7. ML confidence gate ─────────────────────────────────────────
        setup_min_conf = SETUPS[setup_type]["min_ml_confidence"]
        if prob_up < setup_min_conf:
            return _hold(
                f"ML confidence {prob_up:.2f} < {setup_type} threshold {setup_min_conf}",
                combined_score=int(combined),
                setup_type=setup_type,
                score_breakdown=score_breakdown,
                ml_confidence=prob_up,
            )

        # ── BUY ───────────────────────────────────────────────────────────
        reasoning = (
            f"{setup_type} setup confirmed. "
            f"Score={combined:.0f}, ML prob_up={prob_up:.0%}, "
            f"VIX regime={vix_regime or 'NORMAL'}."
        )
        return {
            "signal":             "BUY",
            "setup_type":         setup_type,
            "combined_score":     int(combined),
            "score_breakdown":    score_breakdown,
            "ml_confidence":      round(prob_up, 4),
            "execution_permitted": True,
            "rejection_reason":   None,
            "reasoning":          reasoning,
        }


# ══════════════════════════════════════════════════════════════════
# Setup matching
# ══════════════════════════════════════════════════════════════════

def _match_setup(features: dict, intelligence: dict) -> Optional[str]:
    """
    Return the first matching setup name, or None.
    Evaluated in definition order: ORB_BREAKOUT → VWAP_BOUNCE →
    TREND_CONTINUATION → NEWS_CATALYST.
    """
    vol_ratio = float(features.get("volume_ratio", 0.0) or 0.0)
    rsi       = float(features.get("rsi_14", 50.0) or 50.0)
    pvwap_pct = abs(float(features.get("price_vs_vwap_pct", 999.0) or 999.0))

    # ── ORB_BREAKOUT ──────────────────────────────────────────────────────
    if (features.get("orb_breakout") is True
            and vol_ratio >= SETUPS["ORB_BREAKOUT"]["required"]["volume_ratio_min"]
            and features.get("trading_window") == SETUPS["ORB_BREAKOUT"]["required"]["trading_window"]):
        return "ORB_BREAKOUT"

    # ── VWAP_BOUNCE ───────────────────────────────────────────────────────
    vwap_req = SETUPS["VWAP_BOUNCE"]["required"]
    if (features.get("price_above_vwap") is True
            and pvwap_pct <= vwap_req["price_vs_vwap_pct_max"]
            and vol_ratio >= vwap_req["volume_ratio_min"]
            and rsi >= vwap_req["rsi_min"]):
        return "VWAP_BOUNCE"

    # ── TREND_CONTINUATION ────────────────────────────────────────────────
    tc_req = SETUPS["TREND_CONTINUATION"]["required"]
    rsi_range = tc_req["rsi_range"]
    if (features.get("ema9_above_ema21") is True
            and features.get("higher_highs") is True
            and features.get("higher_lows") is True
            and rsi_range[0] <= rsi <= rsi_range[1]):
        return "TREND_CONTINUATION"

    # ── NEWS_CATALYST ─────────────────────────────────────────────────────
    nc_req = SETUPS["NEWS_CATALYST"]["required"]
    news_action = intelligence.get("action", "") or ""
    if (news_action.upper() == nc_req["news_action"]
            and vol_ratio >= nc_req["volume_ratio_min"]):
        return "NEWS_CATALYST"

    return None


# ══════════════════════════════════════════════════════════════════
# Response builders
# ══════════════════════════════════════════════════════════════════

def _blocked(reason: str, setup_type: Optional[str]) -> dict:
    return {
        "signal":              "BLOCKED",
        "setup_type":          setup_type,
        "combined_score":      0,
        "score_breakdown":     {"technical": 0.0, "news": 0.0, "market_mood": 0.0},
        "ml_confidence":       0.0,
        "execution_permitted": False,
        "rejection_reason":    reason,
        "reasoning":           reason,
    }


def _hold(
    reason: str,
    combined_score: int = 0,
    setup_type: Optional[str] = None,
    score_breakdown: Optional[dict] = None,
    ml_confidence: float = 0.0,
) -> dict:
    return {
        "signal":              "HOLD",
        "setup_type":          setup_type,
        "combined_score":      combined_score,
        "score_breakdown":     score_breakdown or {"technical": 0.0, "news": 0.0, "market_mood": 0.0},
        "ml_confidence":       round(ml_confidence, 4),
        "execution_permitted": False,
        "rejection_reason":    reason,
        "reasoning":           reason,
    }


# Module-level singleton
intraday_decision_engine = IntradayDecisionEngine()
