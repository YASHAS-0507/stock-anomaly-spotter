"""
anomaly.py
----------
Flags statistically unusual trading days using a rolling z-score on
daily returns. This is the "spotter" half of the project -- it does
NOT predict the future, it just flags days that were unusual relative
to their recent local volatility regime.
"""

import pandas as pd


def detect_anomalies(feature_df: pd.DataFrame, threshold: float = 2.2) -> pd.DataFrame:
    """
    Returns the subset of rows where |return_zscore| >= threshold,
    with a human-readable direction label attached.
    """
    df = feature_df.copy()
    flagged = df[df["return_zscore"].abs() >= threshold].copy()
    flagged["anomaly_direction"] = flagged["return_zscore"].apply(
        lambda z: "spike_up" if z > 0 else "spike_down"
    )
    return flagged[["date", "close", "daily_return", "return_zscore", "anomaly_direction"]]


def summarize_anomalies(flagged: pd.DataFrame) -> dict:
    if flagged.empty:
        return {"count": 0, "max_abs_zscore": 0.0, "spike_up": 0, "spike_down": 0}
    return {
        "count": int(len(flagged)),
        "max_abs_zscore": round(float(flagged["return_zscore"].abs().max()), 2),
        "spike_up": int((flagged["anomaly_direction"] == "spike_up").sum()),
        "spike_down": int((flagged["anomaly_direction"] == "spike_down").sum()),
    }
