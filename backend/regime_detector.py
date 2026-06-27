import pandas as pd
import numpy as np
from typing import Dict, Union

def detect_market_regime(df: pd.DataFrame) -> Dict[str, Union[str, bool, Dict[str, float]]]:
    """
    Detects the current market regime based on technical indicators.
    Ensures complete JSON compliance for FastAPI serialization.

    Args:
        df: DataFrame with 'Close' column containing price data
            (minimum 200 rows for full analysis)

    Returns:
        Dict with regime classification and trading permissions
    """
    # Force structural validation check
    if df is None or 'Close' not in df.columns or len(df) < 200:
        return {
            "regime_type": "INSUFFICIENT_DATA",
            "action_permitted": False,
            "metrics": {"volatility_zscore": 0.0, "trend_strength": 0.0}
        }

    close = df['Close']

    # 1. Calculate SMAs (Trend Verification)
    sma_50 = close.rolling(window=50).mean()
    sma_200 = close.rolling(window=200).mean()
    current_price = float(close.iloc[-1])

    trend_strength = 0.0
    bull_trend = False
    bear_trend = False

    if pd.notna(sma_50.iloc[-1]) and pd.notna(sma_200.iloc[-1]):
        last_sma_50 = float(sma_50.iloc[-1])
        last_sma_200 = float(sma_200.iloc[-1])
        
        if last_sma_200 > 0:
            trend_strength = (last_sma_50 - last_sma_200) / last_sma_200
            
        bull_trend = (current_price > last_sma_50) and (last_sma_50 > last_sma_200)
        bear_trend = (current_price < last_sma_50) and (last_sma_50 < last_sma_200)

    # 2. Volatility Calculation (Drop lookback NaNs to prevent type leaks)
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

    # 3. Bollinger Bandwidth (Squeeze Isolation)
    sma_20 = close.rolling(window=20).mean()
    std_20 = close.rolling(window=20).std()

    bb_upper = sma_20 + (2 * std_20)
    bb_lower = sma_20 - (2 * std_20)
    
    # Wrap edge-case condition if moving average hits zero
    bb_bandwidth = (bb_upper - bb_lower) / sma_20.replace(0, np.nan)
    bb_bw_ma = bb_bandwidth.rolling(window=30).mean()

    sideways_squeeze = False
    if pd.notna(bb_bandwidth.iloc[-1]) and pd.notna(bb_bw_ma.iloc[-1]):
        sideways_squeeze = float(bb_bandwidth.iloc[-1]) < float(bb_bw_ma.iloc[-1])

    # 4. Resolve Regime Cascades
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

    # Strict casting to native Python primitives for JSON parsing
    return {
        "regime_type": str(regime_type),
        "action_permitted": bool(action_permitted),
        "metrics": {
            "volatility_zscore": 0.0 if np.isnan(vol_zscore) else round(float(vol_zscore), 4),
            "trend_strength": 0.0 if np.isnan(trend_strength) else round(float(trend_strength), 4)
        }
    }

if __name__ == "__main__":
    # Internal execution test with synthetic market trend data
    dates = pd.date_range(start="2023-01-01", periods=300, freq="D")
    prices = np.cumprod(1 + np.random.normal(0.0005, 0.02, 300)) * 100

    df = pd.DataFrame({"Close": prices}, index=dates)
    result = detect_market_regime(df)
    print(f"Sanitization Audit Result: {result}")