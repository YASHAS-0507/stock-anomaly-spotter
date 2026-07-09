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

import pytz

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

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
            "price_vs_vwap_pct_max":   1.5,   # percentage scale (features compute /vwap*100)
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

        # ── New indicator signals (Day 17) ────────────────────────────────
        adx_val    = float(features.get("adx",          20.0) or 20.0)
        plus_di    = float(features.get("adx_plus_di",  20.0) or 20.0)
        minus_di   = float(features.get("adx_minus_di", 20.0) or 20.0)
        st_dir     = str(features.get("supertrend_direction", "neutral") or "neutral")
        pivot_zone = str(features.get("pivot_zone", "between_s1_r1") or "between_s1_r1")

        # ADX bonus: strong trending + bullish DI alignment (up to +10 pts)
        adx_bonus = 0.0
        if adx_val >= 25.0 and plus_di > minus_di:
            adx_bonus = min(10.0, (adx_val - 25.0) * 0.4)

        # Supertrend: bullish +8, bearish -8
        st_bonus = 8.0 if st_dir == "bullish" else (-8.0 if st_dir == "bearish" else 0.0)

        # Pivot zone: at resistance = penalty, at support = small bonus
        pivot_bonus = 0.0
        if pivot_zone == "above_r2":
            pivot_bonus = -10.0
        elif pivot_zone == "above_r1":
            pivot_bonus = -5.0
        elif pivot_zone == "below_s1":
            pivot_bonus = 3.0

        base = prob_up * 100.0 + adx_bonus + st_bonus + pivot_bonus

        # Volume Profile adjustments (Day 18)
        price_vs_va = str(features.get("price_vs_va", "INSIDE_VA") or "INSIDE_VA")
        vp_poc_val  = features.get("vp_poc")
        vp_strength = str(features.get("volume_profile_strength", "NORMAL") or "NORMAL")

        if features.get("at_prev_poc", False):
            base += 9
        if features.get("price_at_val", False):
            base += 7
        if features.get("price_at_poc", False):
            base += 5
        if features.get("price_at_vah", False):
            base -= 6
        if price_vs_va == "ABOVE_VAH":
            base += 4
        elif price_vs_va == "BELOW_VAL":
            base -= 6
        if vp_strength == "STRONG":
            base += 3
        elif vp_strength == "WEAK":
            base -= 3

        # Fair Value Gap adjustments (Day 19)
        if features.get("price_in_bullish_fvg", False):
            base += 10
        if features.get("price_in_bearish_fvg", False):
            base -= 12
        if features.get("fvg_bullish_exists", False):
            fvg_dist = features.get("nearest_fvg_distance_pct", 999)
            if fvg_dist < 0.5:
                base += 5
        if features.get("fvg_count", 0) > 5:
            base -= 4

        fvg_signal = (
            "BULLISH_FVG" if features.get("price_in_bullish_fvg", False)
            else "BEARISH_FVG" if features.get("price_in_bearish_fvg", False)
            else "NO_FVG"
        )

        # Wyckoff adjustments (Day 20)
        wyckoff_bias = features.get("wyckoff_bias", "NEUTRAL")
        if wyckoff_bias == "STRONG_BULL":
            base += 12
        elif wyckoff_bias == "BULL":
            base += 8
        elif wyckoff_bias == "BEAR":
            base -= 10
        elif wyckoff_bias == "STRONG_BEAR":
            base -= 14
        elif wyckoff_bias == "RANGING":
            base -= 3

        if features.get("wyckoff_spring_active", False):
            if features.get("wyckoff_spring_follow_through"):
                base += 8
            else:
                base += 4

        if features.get("wyckoff_upthrust_active", False):
            base -= 8

        cause_bars = features.get("wyckoff_cause_length_bars", 0)
        if cause_bars > 40:
            base += 3
        elif cause_bars > 25:
            base += 1

        technical_score = max(0.0, min(100.0, base))
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
            "technical":       round(technical_score, 2),
            "news":            round(news_score, 2),
            "market_mood":     round(mood_score_100, 2),
            "adx":             round(adx_val, 1),
            "supertrend":      st_dir,
            "pivot_zone":      pivot_zone,
            "vp_zone":         price_vs_va,
            "at_key_vp_level": (
                features.get("price_at_poc", False) or
                features.get("price_at_val", False) or
                features.get("at_prev_poc",  False)
            ),
        }

        # ── 6. Score gate ─────────────────────────────────────────────────
        if combined < cfg["min_combined_score"]:
            result = _hold(
                f"Combined score {combined:.0f} < threshold {cfg['min_combined_score']}",
                combined_score=int(combined),
                setup_type=setup_type,
                score_breakdown=score_breakdown,
                ml_confidence=prob_up,
            )
            result["fvg_signal"] = fvg_signal
            return result

        # ── 7. ML confidence gate ─────────────────────────────────────────
        setup_min_conf = SETUPS[setup_type]["min_ml_confidence"]
        try:
            from models.intraday_model import intraday_model as _model
            if not _model.is_trained():
                setup_min_conf = max(0.0, setup_min_conf - 0.08)
                logger.info("[decision] untrained model — ML confidence thresholds relaxed for cold start")
        except Exception:
            pass
        if prob_up < setup_min_conf:
            result = _hold(
                f"ML confidence {prob_up:.2f} < {setup_type} threshold {setup_min_conf}",
                combined_score=int(combined),
                setup_type=setup_type,
                score_breakdown=score_breakdown,
                ml_confidence=prob_up,
            )
            result["fvg_signal"] = fvg_signal
            return result

        # ── BUY ───────────────────────────────────────────────────────────
        reasoning = (
            f"{setup_type} setup confirmed. "
            f"Score={combined:.0f}, ML prob_up={prob_up:.0%}, "
            f"VIX regime={vix_regime or 'NORMAL'}, "
            f"ADX={adx_val:.0f} ({st_dir} trend), "
            f"pivot zone={pivot_zone}."
        )
        return {
            "signal":              "BUY",
            "setup_type":          setup_type,
            "combined_score":      int(combined),
            "score_breakdown":     score_breakdown,
            "ml_confidence":       round(prob_up, 4),
            "execution_permitted": True,
            "rejection_reason":    None,
            "reasoning":           reasoning,
            "adx":                 round(adx_val, 1),
            "supertrend":          st_dir,
            "pivot_zone":          pivot_zone,
            "vp_poc":              vp_poc_val,
            "vp_zone":             price_vs_va,
            "at_key_vp_level": (
                features.get("price_at_poc", False) or
                features.get("price_at_val", False) or
                features.get("at_prev_poc",  False)
            ),
            "fvg_signal":          fvg_signal,
            "wyckoff_bias":        features.get("wyckoff_bias", "NEUTRAL"),
            "wyckoff_spring":      features.get("wyckoff_spring_active"),
            "wyckoff_range_type":  features.get("wyckoff_range_type"),
            "features":            features,
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
    # Suppress if Wyckoff upthrust signals price is near resistance falsely
    if (features.get("orb_breakout") is True
            and vol_ratio >= SETUPS["ORB_BREAKOUT"]["required"]["volume_ratio_min"]
            and features.get("trading_window") == SETUPS["ORB_BREAKOUT"]["required"]["trading_window"]
            and not features.get("wyckoff_upthrust_active", False)):
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
