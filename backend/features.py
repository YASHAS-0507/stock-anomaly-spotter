"""
features.py
------------
Turns raw OHLCV data into the technical-indicator features used by both
the anomaly detector and the prediction model.

Everything here is standard, well-known technical analysis -- nothing
exotic, on purpose. The point of the project is to be honest about what
these features can and can't predict.
"""

import numpy as np
import pandas as pd


def add_returns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["daily_return"] = df["close"].pct_change()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    return df


def add_moving_averages(df: pd.DataFrame, short: int = 10, long: int = 30) -> pd.DataFrame:
    df = df.copy()
    df[f"sma_{short}"] = df["close"].rolling(short).mean()
    df[f"sma_{long}"] = df["close"].rolling(long).mean()
    df["sma_cross"] = (df[f"sma_{short}"] - df[f"sma_{long}"])
    return df


def add_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Relative Strength Index -- classic momentum oscillator, 0-100."""
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)
    return df


def add_volatility(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["volatility"] = df["daily_return"].rolling(window).std()
    return df


def add_rolling_zscore(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    Rolling z-score of daily return -- this is the anomaly signal.
    A day is "anomalous" if its return is many standard deviations away
    from the recent local mean/std, regardless of overall market direction.
    """
    df = df.copy()
    roll_mean = df["daily_return"].rolling(window).mean()
    roll_std = df["daily_return"].rolling(window).std().replace(0, np.nan)
    df["return_zscore"] = (df["daily_return"] - roll_mean) / roll_std
    df["return_zscore"] = df["return_zscore"].fillna(0)
    return df


def add_volume_features(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["volume_sma"] = df["volume"].rolling(window).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma"].replace(0, np.nan)
    df["volume_ratio"] = df["volume_ratio"].fillna(1.0)
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    MACD (Moving Average Convergence Divergence) -- a momentum indicator
    that captures the relationship between two EMAs of price. The
    histogram (macd - signal) often shifts sign before a trend change,
    which is information the simple SMA crossover doesn't fully capture.
    """
    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_histogram"] = macd_line - signal_line
    return df


def add_bollinger_bands(df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """
    Bollinger Bands -- mean-reversion signal. %B tells us where price
    sits within its recent volatility band: near 1 = near upper band
    (potentially overbought), near 0 = near lower band (potentially
    oversold). This is different information from trend-following
    indicators like SMA crossover or MACD.
    """
    df = df.copy()
    sma = df["close"].rolling(window).mean()
    std = df["close"].rolling(window).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    band_width = (upper - lower).replace(0, np.nan)
    df["bollinger_pct_b"] = ((df["close"] - lower) / band_width).fillna(0.5)
    df["bollinger_bandwidth"] = (band_width / sma.replace(0, np.nan)).fillna(0)
    return df


def add_lagged_features(df: pd.DataFrame, columns: list, lags: list = (1, 2, 3)) -> pd.DataFrame:
    """
    Adds lagged versions of selected columns (e.g. yesterday's RSI,
    2-days-ago return). Tree models like RandomForest don't see sequence
    on their own -- each row is treated independently -- so without
    lagged features the model only ever sees "today's snapshot" and has
    no way to learn from short-term momentum/reversal patterns.
    """
    df = df.copy()
    for col in columns:
        for lag in lags:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def build_feature_table(df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """Runs the full feature pipeline in order. Returns a clean dataframe."""
    out = df.copy()
    out = add_returns(out)
    out = add_moving_averages(out)
    out = add_rsi(out)
    out = add_volatility(out)
    out = out.assign(daily_return=out["daily_return"].fillna(0)) # safety patch for rolling calc
    out = add_rolling_zscore(out)
    out = add_volume_features(out)
    out = add_macd(out)
    out = add_bollinger_bands(out)
    out = add_lagged_features(out, columns=["daily_return", "rsi", "return_zscore"], lags=(1, 2, 3))

    # --- THIS IS THE LINE YOU ARE CHANGING ---
    # It replaces the old hardcoded shift with the dynamic horizon variable
    out["next_day_up"] = (out["close"].shift(-horizon) > out["close"]).astype(int)

    out = out.dropna().reset_index(drop=True)
    return out


FEATURE_COLUMNS = [
    "daily_return",
    "sma_cross",
    "rsi",
    "volatility",
    "return_zscore",
    "volume_ratio",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bollinger_pct_b",
    "bollinger_bandwidth",
    "daily_return_lag1",
    "daily_return_lag2",
    "daily_return_lag3",
    "rsi_lag1",
    "rsi_lag2",
    "rsi_lag3",
    "return_zscore_lag1",
    "return_zscore_lag2",
    "return_zscore_lag3",
]