"""
decision_engine.py
------------------
Phase 2.2 AI Decision Engine. Synthesises regime, prediction, and risk
signals into a single institutional-grade trade decision.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# CONFIGURATION  (all tunable weights live here – nowhere else)
# ─────────────────────────────────────────────────────────────
DECISION_CONFIG = {
    "weights": {
        "trend":      0.25,
        "momentum":   0.20,
        "volume":     0.15,
        "regime":     0.15,
        "prediction": 0.15,
        "risk":       0.10,
    },
    "min_confidence_threshold": 0.60,
    "min_score_threshold":      55,
    "max_risk_rating":          "HIGH",   # EXTREME → blocked
}

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "EXTREME": 3}


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _is_market_open() -> bool:
    now = _ist_now()
    total = now.hour * 60 + now.minute
    return now.weekday() < 5 and 555 <= total <= 930  # 9:15–15:30


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _atr(feature_df: pd.DataFrame, latest_close: float) -> float:
    """14-day ATR from high/low if available, else volatility proxy."""
    if "high" in feature_df.columns and "low" in feature_df.columns:
        hl = (feature_df["high"] - feature_df["low"]).tail(14)
        if not hl.empty and hl.mean() > 0:
            return float(hl.mean())
    vol = float(feature_df["volatility"].iloc[-1]) if "volatility" in feature_df.columns else 0.02
    return vol * latest_close


def _score_breakdown(feature_row: dict, regime_type: str, prob_up: float) -> dict:
    """Compute 0-100 sub-scores for each factor."""

    # ── Trend: sma_cross relative to price
    sma_cross = float(feature_row.get("sma_cross", 0.0))
    latest_close = float(feature_row.get("close", 1.0)) or 1.0
    cross_pct = sma_cross / latest_close
    trend_score = _clamp(50.0 + cross_pct * 2500.0, 0.0, 100.0)

    # ── Momentum: RSI (60%) + MACD histogram sign (40%)
    rsi = float(feature_row.get("rsi", 50.0))
    macd_hist = float(feature_row.get("macd_histogram", 0.0))
    macd_sign_score = 70.0 if macd_hist > 0 else 30.0
    momentum_score = _clamp(rsi * 0.60 + macd_sign_score * 0.40, 0.0, 100.0)

    # ── Volume: volume_ratio (1.0 = average = 50 pts)
    volume_ratio = float(feature_row.get("volume_ratio", 1.0))
    volume_score = _clamp(volume_ratio * 50.0, 0.0, 100.0)

    # ── Regime: fixed mapping
    regime_map = {
        "BULL_TREND":        100.0,
        "NORMAL":             60.0,
        "BEAR_TREND":         30.0,
        "SIDEWAYS_SQUEEZE":   20.0,
        "HIGH_VOLATILITY":     0.0,
    }
    regime_score = regime_map.get(regime_type, 40.0)

    # ── Prediction: prob_up scaled to 0-100
    prediction_score = _clamp(prob_up * 100.0, 0.0, 100.0)

    # ── Risk: inverse of absolute return z-score magnitude
    return_zscore = abs(float(feature_row.get("return_zscore", 0.0)))
    risk_score = _clamp(100.0 - return_zscore * 25.0, 0.0, 100.0)

    return {
        "trend":      round(trend_score, 1),
        "momentum":   round(momentum_score, 1),
        "volume":     round(volume_score, 1),
        "regime":     round(regime_score, 1),
        "prediction": round(prediction_score, 1),
        "risk":       round(risk_score, 1),
    }


def _weighted_score(breakdown: dict) -> int:
    weights = DECISION_CONFIG["weights"]
    total = sum(breakdown[k] * weights[k] for k in weights)
    return int(round(total))


def _risk_rating(return_zscore: float) -> str:
    z = abs(return_zscore)
    if z > 3.0:
        return "EXTREME"
    if z > 2.0:
        return "HIGH"
    if z > 1.0:
        return "MEDIUM"
    return "LOW"


def _confidence(prob_up: float, signal: str, regime_type: str, return_zscore: float) -> float:
    if signal == "BUY":
        base = prob_up
    elif signal == "SELL":
        base = 1.0 - prob_up
    else:
        base = 0.5

    boost = 0.0
    if regime_type == "BULL_TREND" and signal == "BUY":
        boost += 0.10
    if regime_type == "SIDEWAYS_SQUEEZE":
        boost -= 0.15
    if abs(return_zscore) > 1.5:
        boost -= 0.10

    return round(_clamp(base + boost, 0.0, 1.0), 4)


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def generate_decision(
    feature_df: pd.DataFrame,
    prediction_payload: dict,
    regime_snapshot: dict,
    portfolio_state: dict,
    latest_close: float,
    ticker: str,
    horizon: int = 5,
) -> dict:
    """
    Synthesise a single institutional trade decision from all pipeline stages.
    """
    cfg = DECISION_CONFIG
    ts = _ist_now().strftime("%H:%M:%S IST")

    # Latest feature row as plain dict for safe access
    feature_row = feature_df.iloc[-1].to_dict()

    prob_up   = float(prediction_payload.get("probabilities", {}).get("spike_up", 0.5))
    regime_type = regime_snapshot.get("regime_type", "NORMAL")
    return_zscore = float(feature_row.get("return_zscore", 0.0))
    available_cash = float(portfolio_state.get("available_cash", 5000.0))

    # ── ATR (needed for all price levels)
    atr = _atr(feature_df, latest_close)
    atr_pct = atr / latest_close if latest_close > 0 else 0.02

    # ── Regime gate
    if not regime_snapshot.get("action_permitted", True):
        return _blocked_payload(
            ticker, latest_close, atr, ts,
            rejection_reason=f"Regime shield blocked execution: {regime_type}",
            score_breakdown=_score_breakdown(feature_row, regime_type, prob_up),
        )

    # ── Market hours gate
    if not _is_market_open():
        return _blocked_payload(
            ticker, latest_close, atr, ts,
            rejection_reason="Market is closed (outside NSE hours 9:15–15:30 IST Mon–Fri)",
            score_breakdown=_score_breakdown(feature_row, regime_type, prob_up),
        )

    # ── Raw signal from prob_up
    if prob_up >= 0.58:
        raw_signal = "BUY"
    elif prob_up <= 0.42:
        raw_signal = "SELL"
    else:
        raw_signal = "HOLD"

    # ── Scores
    breakdown = _score_breakdown(feature_row, regime_type, prob_up)
    score = _weighted_score(breakdown)
    risk = _risk_rating(return_zscore)
    confidence = _confidence(prob_up, raw_signal, regime_type, return_zscore)

    # ── Threshold and risk gates → may downgrade to HOLD/BLOCKED
    rejection_reason = None

    max_risk = cfg["max_risk_rating"]
    if _RISK_ORDER.get(risk, 0) > _RISK_ORDER.get(max_risk, 2):
        return _blocked_payload(
            ticker, latest_close, atr, ts,
            rejection_reason=f"Risk level {risk} exceeds maximum allowed {max_risk}",
            score_breakdown=breakdown,
        )

    if confidence < cfg["min_confidence_threshold"]:
        rejection_reason = f"Confidence {confidence:.1%} below threshold {cfg['min_confidence_threshold']:.0%}"
        raw_signal = "HOLD"

    if score < cfg["min_score_threshold"]:
        rejection_reason = (rejection_reason or
            f"Institutional score {score}/100 below threshold {cfg['min_score_threshold']}")
        raw_signal = "HOLD"

    final_signal = raw_signal

    # ── Position sizing (2% fixed-fractional, capped at 20% of portfolio)
    risk_budget = available_cash * 0.02
    position_value = risk_budget / max(atr_pct, 0.005)
    position_value = min(position_value, available_cash * 0.20)

    # Reduce for elevated volatility
    if risk == "HIGH":
        position_value *= 0.50
    elif risk == "EXTREME":
        position_value *= 0.25

    shares = max(0, int(position_value // latest_close)) if latest_close > 0 else 0
    actual_value = round(shares * latest_close, 2)
    risk_amount  = round(shares * atr * 1.5, 2)

    # ── Price levels (ATR-based)
    entry_price = round(latest_close, 2)
    stop_loss   = round(latest_close - atr * 1.5, 2)
    tp1 = round(latest_close + atr * 1.5, 2)
    tp2 = round(latest_close + atr * 3.0, 2)
    tp3 = round(latest_close + atr * 4.5, 2)

    expected_return   = round((tp2 - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0
    expected_drawdown = round((stop_loss - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0.0
    rr_ratio = round(abs(expected_return) / abs(expected_drawdown), 2) if expected_drawdown != 0 else 0.0

    # ── Holding period
    if horizon <= 1:
        holding_period = "Intraday"
    elif horizon <= 3:
        holding_period = "1-3 days"
    elif horizon <= 7:
        holding_period = "2-5 days (Swing)"
    else:
        holding_period = "1-2 weeks (Positional)"

    # ── Human-readable explanation
    rsi = float(feature_row.get("rsi", 50.0))
    if final_signal == "BUY":
        explanation = (
            f"Strong upward momentum. Score {score}/100. "
            f"RSI {rsi:.1f}, regime {regime_type}. "
            f"TP2 target {expected_return:+.2f}% vs SL {expected_drawdown:.2f}% ({rr_ratio:.1f}:1 R/R)."
        )
    elif final_signal == "SELL":
        explanation = (
            f"Bearish signal. Score {score}/100. "
            f"RSI {rsi:.1f}, regime {regime_type}. "
            f"Downside exposure {expected_drawdown:.2f}%."
        )
    else:
        explanation = rejection_reason or (
            f"Score {score}/100 and confidence {confidence:.1%}. "
            f"No high-conviction setup — waiting for clearer signal."
        )

    execution_permitted = final_signal in ("BUY", "SELL") and shares > 0

    print(
        f"[decision] {ticker} | {final_signal} | score={score} | "
        f"confidence={confidence:.2%} | risk={risk} | {ts}"
    )

    return {
        "decision":          final_signal,
        "signal":            final_signal,
        "confidence":        confidence,
        "score":             score,
        "risk":              risk,
        "expected_return":   expected_return,
        "expected_drawdown": expected_drawdown,
        "rr_ratio":          rr_ratio,
        "position_size": {
            "shares":        shares,
            "value":         actual_value,
            "risk_amount":   risk_amount,
            "sizing_method": "fixed_fractional_2pct",
        },
        "entry_price": entry_price,
        "stop_loss":   stop_loss,
        "take_profit": {"tp1": tp1, "tp2": tp2, "tp3": tp3},
        "holding_period":     holding_period,
        "explanation":        explanation,
        "rejection_reason":   rejection_reason,
        "score_breakdown":    breakdown,
        "execution_permitted": execution_permitted,
        "timestamp":          ts,
    }


# ─────────────────────────────────────────────────────────────
# BLOCKED PAYLOAD FACTORY
# ─────────────────────────────────────────────────────────────

def _blocked_payload(
    ticker: str,
    latest_close: float,
    atr: float,
    ts: str,
    rejection_reason: str,
    score_breakdown: dict,
) -> dict:
    print(f"[decision] {ticker} | BLOCKED | {rejection_reason} | {ts}")
    entry = round(latest_close, 2)
    sl    = round(latest_close - atr * 1.5, 2)
    tp1   = round(latest_close + atr * 1.5, 2)
    tp2   = round(latest_close + atr * 3.0, 2)
    tp3   = round(latest_close + atr * 4.5, 2)
    return {
        "decision":          "BLOCKED",
        "signal":            "BLOCKED",
        "confidence":        0.0,
        "score":             0,
        "risk":              "EXTREME",
        "expected_return":   0.0,
        "expected_drawdown": 0.0,
        "rr_ratio":          0.0,
        "position_size": {
            "shares":        0,
            "value":         0.0,
            "risk_amount":   0.0,
            "sizing_method": "blocked",
        },
        "entry_price": entry,
        "stop_loss":   sl,
        "take_profit": {"tp1": tp1, "tp2": tp2, "tp3": tp3},
        "holding_period":     "—",
        "explanation":        rejection_reason,
        "rejection_reason":   rejection_reason,
        "score_breakdown":    score_breakdown,
        "execution_permitted": False,
        "timestamp":          ts,
    }
