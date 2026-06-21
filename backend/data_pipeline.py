"""
data_pipeline.py
-----------------
Fetches historical OHLCV data for a given ticker.

Tries yfinance first (real market data). If the network call fails
(no internet, ticker not found, rate-limited, etc.) it falls back to
a seeded synthetic series so the rest of the pipeline always has
something to run on -- this matters for demos and offline grading.
"""

import numpy as np
import pandas as pd
import datetime as dt


def fetch_real_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Pull real OHLCV data using yfinance. Raises on failure."""
    import yfinance as yf

    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'")

    df = df.reset_index()
    df = df.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df = df[["date", "open", "high", "low", "close", "volume"]]
    return df


def generate_synthetic_data(ticker: str, days: int = 252) -> pd.DataFrame:
    """
    Deterministic synthetic OHLCV series, seeded from the ticker name so
    the same ticker always produces the same series (reproducible demos).
    Uses a simple geometric random walk with occasional volatility shocks,
    which is a reasonable stand-in for real price behaviour.
    """
    seed = sum(ord(c) for c in ticker.upper()) + days
    rng = np.random.default_rng(seed)

    start_price = 80 + rng.random() * 120
    daily_returns = rng.normal(loc=0.0004, scale=0.018, size=days)

    # sprinkle in a handful of shock days so the anomaly detector has
    # something real to find
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


def get_price_data(ticker: str, period: str = "1y", allow_synthetic_fallback: bool = True) -> tuple[pd.DataFrame, bool]:
    """
    Returns (dataframe, used_synthetic_flag).

    This is the single entry point the rest of the app should call --
    it hides whether the data is real or synthetic, but tells the caller
    so the UI/report can be transparent about it.
    """
    try:
        df = fetch_real_data(ticker, period=period)
        return df, False
    except Exception as e:
        if not allow_synthetic_fallback:
            raise
        print(f"[data_pipeline] live fetch failed for '{ticker}' ({e}); using synthetic fallback")
        days = {"1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504}.get(period, 252)
        df = generate_synthetic_data(ticker, days=days)
        return df, True


if __name__ == "__main__":
    df, synthetic = get_price_data("RELIANCE.NS", period="6mo")
    print(f"synthetic={synthetic}")
    print(df.tail())
