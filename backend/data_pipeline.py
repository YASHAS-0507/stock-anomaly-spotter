"""
data_pipeline.py
-----------------
Fetches historical OHLCV data for a given ticker with zero-leakage padding support.
Fabs out a seeded synthetic fallback series if network disruptions trigger faults.
"""

import numpy as np
import pandas as pd
import datetime as dt
from typing import Tuple

# --- 1. CONFIGURATION REGISTRY FOR FEATURE ENGINEERING WARM-UP ---
ROLLING_WINDOWS = [14, 20, 26, 50]  # RSI, Bollinger Bands, MACD, and EMA profiles
LAG_WINDOWS = [1, 2, 3]            # Multi-day lookback lags
PREDICTION_HORIZON = 5             # Target forecasting horizon


def derive_required_bars(period: str) -> int:
    """
    Translates a period string into required core bars and adds a structural
    padding allocation to guarantee indicator stabilization.
    """
    # Core target window demands - ensure minimum 90 rows for ML pipeline
    target_days = {"1mo": 90, "3mo": 90, "6mo": 126, "1y": 252, "2y": 504}.get(period, 252)
    
    # Extract maximum lookback bounds across your indicators and lags
    max_warmup = max(max(ROLLING_WINDOWS), max(LAG_WINDOWS), PREDICTION_HORIZON)
    
    # Apply a 1.45x structural multiplier for weekend/holiday protection
    padded_warmup_bars = int(max_warmup * 1.45) + 15
    
    # Total nominal bars to pull from ingestion layer
    return target_days + padded_warmup_bars


def fetch_real_data(ticker: str, total_bars: int) -> pd.DataFrame:
    """Pull real OHLCV data using yfinance based on exact bar depth requirements."""
    import yfinance as yf

    # Calculate start date based on required bars
    # 1 trading day ≈ 1.4 calendar days (accounting for weekends/holidays)
    approx_calendar_days = int(total_bars * 1.5)
    end_date = dt.date.today()
    # Safety: ensure end_date is not in the future
    if end_date > dt.date.today():
        end_date = dt.date.today()
    start_date = (end_date - dt.timedelta(days=approx_calendar_days)).strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    df = yf.download(ticker, start=start_date, end=end_date_str, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'")

    # Flatten newer yfinance MultiIndex column schemas if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df = df.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    # Guard against duplicate structural anomalies across columns
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[["date", "open", "high", "low", "close", "volume"]]

    # Enforce chronological ascending indexation order
    df = df.sort_values("date", ascending=True).reset_index(drop=True)
    return df


def generate_synthetic_data(ticker: str, days: int = 252) -> pd.DataFrame:
    """
    Deterministic synthetic OHLCV series, seeded from the ticker name so
    the same ticker always produces the same series (reproducible demos).
    """
    seed = sum(ord(c) for c in ticker.upper()) + days
    rng = np.random.default_rng(seed)

    start_price = 80 + rng.random() * 120
    daily_returns = rng.normal(loc=0.0004, scale=0.018, size=days)

    # Sprinkle anomaly targets for processing validation stability
    shock_days = rng.choice(days, size=max(3, days // 40), replace=False)
    for d in shock_days:
        daily_returns[d] += rng.choice([-1, 1]) * rng.uniform(0.05, 0.12)

    prices = start_price * np.cumprod(1 + daily_returns)
    dates = pd.bdate_range(end=dt.date.today(), periods=days + 5)[-days:]

    closes = prices
    opens = np.concatenate([[start_price], closes[:-1]]) * (1 + rng.normal(0, 0.003, days))
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.006, days)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.006, days)))
    volume = rng.integers(200_000, 5_000_000, size=days)

    df = pd.DataFrame({
        "date": dates,
        "open": opens.round(2),
        "high": highs.round(2),
        "low": lows.round(2),
        "close": closes.round(2),
        "volume": volume,
    })
    return df


def compute_trailing_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes indicators on the un-truncated matrix using center=False to fully 
    immunize the operational core from future data contamination leaks.
    """
    df = df.copy().sort_values("date", ascending=True).reset_index(drop=True)
    close = df['close']
    
    # 1. Log Returns & Non-Centered Trailing Volatility Z-Scores
    df['returns'] = np.log(close / close.shift(1))
    df['returns_z_score'] = (
        (df['returns'] - df['returns'].rolling(window=20, center=False).mean()) / 
        (df['returns'].rolling(window=20, center=False).std() + 1e-9)
    )

    # 2. Non-Centered RSI-14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, center=False).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, center=False).mean()
    rs = gain / (loss + 1e-9)
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # 3. Trailing MACD (12, 26, 9)
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # 4. Non-Centered Bollinger Bands (20, 2)
    df['bb_mid'] = close.rolling(window=20, center=False).mean()
    df['bb_std'] = close.rolling(window=20, center=False).std()
    df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2)
    df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)

    # 5. Volatility Profile
    df['rolling_volatility'] = df['returns'].rolling(window=20, center=False).std()

    # 6. Non-Contaminated Multi-day Lag Engine
    for lag in LAG_WINDOWS:
        df[f'lag_{lag}'] = close.shift(lag)

    return df


def get_price_data(ticker: str, period: str = "1y", allow_synthetic_fallback: bool = True) -> Tuple[pd.DataFrame, bool]:
    """
    The main architectural entry point for data collection.
    Fetches the padded horizon, extracts features cleanly, and drops warm-up rows.
    """
    # 1. Compute dynamic total bars (Target + Buffer)
    total_required_bars = derive_required_bars(period)
    target_visible_rows = {"1mo": 90, "3mo": 90, "6mo": 126, "1y": 252, "2y": 504}.get(period, 252)
    
    try:
        # 2. Extract padded data
        raw_df = fetch_real_data(ticker, total_bars=total_required_bars)
        is_synthetic = False
    except Exception as e:
        if not allow_synthetic_fallback:
            raise
        print(f"[data_pipeline] LIVE FETCH FAILED for '{ticker}', falling back to synthetic framework...")
        raw_df = generate_synthetic_data(ticker, days=total_required_bars)
        is_synthetic = True

    # 3. Run feature computation across the whole padded landscape to handle warm-up dependencies
    hydrated_df = compute_trailing_features(raw_df)
    
    # 4. Post-Indicator Temporal Truncation Gate
    # Keep exactly the trailing visible rows the user requested, preserving fully formed features.
    final_df = hydrated_df.iloc[-target_visible_rows:].copy().reset_index(drop=True)
    
    # Clean up lingering boundary NaNs if any are generated on initial historical edges
    if final_df.isnull().any().any():
        final_df = final_df.dropna().reset_index(drop=True)

    return final_df, is_synthetic


if __name__ == "__main__":
    df, synthetic = get_price_data("AAPL", period="6mo")
    print(f"Using Synthetic Data Fallback? = {synthetic}")
    print(f"Total Rows Returned: {len(df)}")
    print(df.tail(3))