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


def build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    """Runs the full feature pipeline in order. Returns a clean dataframe."""
    out = df.copy()
    out = add_returns(out)
    out = add_moving_averages(out)
    out = add_rsi(out)
    out = add_volatility(out)
    out = add_rolling_zscore(out)
    out = add_volume_features(out)

    # the label: did the NEXT day close higher than today? (1 = up, 0 = down)
    out["next_day_up"] = (out["close"].shift(-1) > out["close"]).astype(int)

    out = out.dropna().reset_index(drop=True)
    return out


FEATURE_COLUMNS = [
    "daily_return",
    "sma_cross",
    "rsi",
    "volatility",
    "return_zscore",
    "volume_ratio",
]
