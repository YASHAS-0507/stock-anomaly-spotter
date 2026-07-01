"""
regime_detector.py
------------------
Stage 2 Market Regime Valve. Acts as an operational circuit breaker.
Intercepts lowercase feature matrices, tracks Bollinger compressions,
and enforces systematic data gates prior to downstream classification steps.
"""

import pandas as pd
import numpy as np
from typing import Dict, Union, Any


def detect_market_regime(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detects the current market regime based on technical indicators.
    Ensures complete JSON compliance for FastAPI serialization.

    Args:
        df: DataFrame containing lowercase 'close' column data.
            (minimum 60 rows required for reliable indicator operations)

    Returns:
        Dict with regime classification, trading permissions, and telemetry metrics.
    """
    # 1. Force structural validation check using pipeline lowercase standards
    if df is None or 'close' not in df.columns or len(df) < 60:
        return {
            "regime_type": "INSUFFICIENT_DATA",
            "action_permitted": False,
            "halt_required": True,
            "metrics": {"volatility_zscore": 0.0, "trend_strength": 0.0}
        }

    close = df['close']
    available_rows = len(df)

    # 2. Calculate SMAs (Trend Verification) - Adaptive windows based on data availability
    sma_long_window = min(200, max(50, available_rows - 10))  # At least 50, max 200, leave room for rolling
    sma_short_window = min(50, max(20, available_rows // 4))

    sma_short = close.rolling(window=sma_short_window).mean()
    sma_long = close.rolling(window=sma_long_window).mean()
    current_price = float(close.iloc[-1])

    trend_strength = 0.0
    bull_trend = False
    bear_trend = False

    if pd.notna(sma_short.iloc[-1]) and pd.notna(sma_long.iloc[-1]):
        last_sma_short = float(sma_short.iloc[-1])
        last_sma_long = float(sma_long.iloc[-1])

        if last_sma_long > 0:
            trend_strength = (last_sma_short - last_sma_long) / last_sma_long

        bull_trend = (current_price > last_sma_short) and (last_sma_short > last_sma_long)
        bear_trend = (current_price < last_sma_short) and (last_sma_short < last_sma_long)

    # 3. Volatility Calculation (Drop lookback NaNs to prevent type leaks)
    returns = close.pct_change()
    volatility_14d = (returns.rolling(window=14).std() * np.sqrt(252)).dropna()

    if not volatility_14d.empty:
        current_vol = float(volatility_14d.iloc[-1])
        vol_1y = volatility_14d.iloc[-252:]

        vol_mean = float(vol_1y.mean())
        vol_std = float(vol_1y.std())

        if vol_std > 0 and pd.notna(current_vol):
            vol_zscore = (current_vol - vol_mean) / vol_std
            high_volatility = vol_zscore > 0.842  # Top 20% distribution limit
        else:
            vol_zscore = 0.0
            high_volatility = False
    else:
        vol_zscore = 0.0
        high_volatility = False

    # 4. Bollinger Bandwidth (Squeeze Isolation) - Adaptive window based on data availability
    bb_window = min(20, max(10, available_rows // 5))  # Adaptive BB window
    bw_ma_window = min(30, max(10, available_rows // 3))  # Adaptive MA window

    sma_bb = close.rolling(window=bb_window).mean()
    std_bb = close.rolling(window=bb_window).std()

    bb_upper = sma_bb + (2 * std_bb)
    bb_lower = sma_bb - (2 * std_bb)

    # Wrap edge-case condition if moving average hits zero
    bb_bandwidth = (bb_upper - bb_lower) / sma_bb.replace(0, np.nan)
    bb_bw_ma = bb_bandwidth.rolling(window=bw_ma_window).mean()

    sideways_squeeze = False
    # Only check squeeze if we have enough data for reliable MA (at least 2x MA window)
    if available_rows >= bw_ma_window * 2:
        if pd.notna(bb_bandwidth.iloc[-1]) and pd.notna(bb_bw_ma.iloc[-1]):
            sideways_squeeze = float(bb_bandwidth.iloc[-1]) < float(bb_bw_ma.iloc[-1])
    else:
        # Not enough data for reliable squeeze detection
        sideways_squeeze = False

    # 5. Resolve Regime Cascades
    regime_type = "NORMAL"
    action_permitted = True

    if high_volatility:
        regime_type = "HIGH_VOLATILITY"
        action_permitted = False
    elif sideways_squeeze:
        regime_type = "SIDEWAYS_SQUEEZE"
        action_permitted = False
    elif bull_trend:
        regime_type = "BULL_TREND"
    elif bear_trend:
        regime_type = "BEAR_TREND"

    # Enforce clear mapping for app.py circuit breaker expectations
    halt_required = not action_permitted

    # Strict casting to native Python primitives for clean JSON parsing
    return {
        "regime_type": str(regime_type),
        "action_permitted": bool(action_permitted),
        "halt_required": bool(halt_required),
        "metrics": {
            "volatility_zscore": 0.0 if np.isnan(vol_zscore) else round(float(vol_zscore), 4),
            "trend_strength": 0.0 if np.isnan(trend_strength) else round(float(trend_strength), 4)
        }
    }


if __name__ == "__main__":
    # Internal execution verification using target schema frames
    dates = pd.date_range(start="2023-01-01", periods=300, freq="D")
    prices = np.cumprod(1 + np.random.normal(0.0005, 0.02, 300)) * 100

    df = pd.DataFrame({"close": prices}, index=dates)
    result = detect_market_regime(df)
    print(f"Sanitization Audit Result: {result}")