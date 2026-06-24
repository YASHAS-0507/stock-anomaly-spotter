"""
app.py
------
FastAPI backend for the Stock Anomaly Spotter project.
Upgraded with multi-class XGBoost predictive analysis for Spike forecasting.

Endpoints:
  GET  /api/analyze?ticker=XXX&period=1y      -> full feature table + anomalies + chart series
  GET  /api/predict?ticker=XXX&period=1y      -> multi-class XGBoost spike prediction (+5% / -5% breakouts)
  POST /api/chart-trend                      -> upload a chart screenshot, get trend extraction

Run locally:
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8000
"""

import shutil
import tempfile
from pathlib import Path
import os
import numpy as np
import pandas as pd

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from data_pipeline import get_price_data
from features import build_feature_table
from anomaly import detect_anomalies, summarize_anomalies
from chart_reader import extract_trend_line

# Import explicit optional dependencies for the predictive pipeline
try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, accuracy_score
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

app = FastAPI(title="Stock Anomaly Spotter API")

# Set FRONTEND_URL in Railway's env vars once you have your frontend's public domain.
_frontend_url = os.environ.get("FRONTEND_URL")
_allowed_origins = [_frontend_url] if _frontend_url else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_features(ticker: str, period: str, horizon: int = 5):
    df, used_synthetic = get_price_data(ticker, period=period)
    if len(df) < 60:
        raise HTTPException(status_code=400, detail="Not enough data to analyze this ticker/period.")
    
    try:
        feature_df = build_feature_table(df, horizon=horizon)
    except TypeError:
        feature_df = build_feature_table(df)
        
    return feature_df, used_synthetic


@app.get("/api/analyze")
def analyze(ticker: str = Query(...), period: str = Query("1y"), threshold: float = Query(2.2)):
    feature_df, used_synthetic = _load_features(ticker, period)
    flagged = detect_anomalies(feature_df, threshold=threshold)
    summary = summarize_anomalies(flagged)

    return {
        "ticker": ticker.upper(),
        "used_synthetic_data": used_synthetic,
        "data_points": len(feature_df),
        "anomaly_summary": summary,
        "anomalies": flagged.assign(date=flagged["date"].astype(str)).to_dict(orient="records"),
        "series": {
            "date": feature_df["date"].astype(str).tolist(),
            "close": feature_df["close"].round(2).tolist(),
            "return_zscore": feature_df["return_zscore"].round(3).tolist(),
        },
    }


@app.get("/api/predict")
def predict(
    ticker: str = Query(...), 
    period: str = Query("1y"), 
    horizon: int = Query(5),
    spike_threshold: float = Query(0.05)  # 0.05 means a 5% price change triggers a spike alert
):
    if not XGBOOST_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="XGBoost and scikit-learn are required for this endpoint. Please add them to requirements.txt"
        )

    # 1. Load data and feature frame
    feature_df, used_synthetic = _load_features(ticker, period, horizon=horizon)
    
    # Sort chronologically to make sure time-series indexing handles shifting properly
    feature_df = feature_df.sort_values("date").reset_index(drop=True)
    
    if len(feature_df) < 40:
        raise HTTPException(status_code=400, detail="Not enough historical dates to train the predictive model.")

    # 2. Build the Look-Ahead Target Variables (Future Return Window)
    # Calculate the percentage change looking forward into the future horizon window
    feature_df["future_close"] = feature_df["close"].shift(-horizon)
    feature_df["future_return"] = (feature_df["future_close"] - feature_df["close"]) / feature_df["close"]

    def label_market_spike(future_ret):
        if pd.isna(future_ret):
            return np.nan
        if future_ret >= spike_threshold:
            return 1  # Spike Up Coming
        elif future_ret <= -spike_threshold:
            return 2  # Spike Down Coming
        else:
            return 0  # Sideways / Stability

    feature_df["target"] = feature_df["future_return"].apply(label_market_spike)

    # Separate the very latest row for the live forward-looking inference
    latest_row = feature_df.iloc[[-1]].copy()
    
    # Drop rows where target is NaN (the final tail ends of the series because they don't have future data yet)
    train_clean_df = feature_df.dropna(subset=["target"]).copy()
    
    if len(train_clean_df) < 20:
        raise HTTPException(status_code=400, detail="Insufficient clean samples available to evaluate thresholds.")

    # 3. Dynamic Feature Selection
    # Extract structural engineering numeric columns from your features pipeline
    all_cols = train_clean_df.columns.tolist()
    ignore_cols = ["date", "target", "future_close", "future_return", "open", "high", "low", "volume"]
    feature_features = [c for c in all_cols if c not in ignore_cols and not train_clean_df[c].dtype == object]

    X = train_clean_df[feature_features]
    y = train_clean_df["target"].astype(int)

    # 4. Strict Chronological Time-Ordered Split to avoid data leakage
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, shuffle=False)

    # Ensure all target classes exist for the multiclass structural allocation
    unique_classes = np.unique(y_train)
    num_classes = 3  # 0: Sideways, 1: Spike Up, 2: Spike Down

    # 5. Train Multiclass XGBoost Classifier
    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=num_classes,
        max_depth=4,
        learning_rate=0.08,
        n_estimators=80,
        random_state=42,
        eval_metric="mlogloss"
    )
    
    model.fit(X_train, y_train)

    # 6. Generate Test Metric Evaluators
    y_pred = model.predict(X_test)
    test_acc = float(accuracy_score(y_test, y_pred))
    
    # Generate baseline accuracy (majority class predictor check)
    majority_class_count = int(y_test.value_counts().max())
    baseline_acc = float(majority_class_count / len(y_test))

    # Calculate global target distribution details to map patterns
    distribution = y.value_counts().to_dict()
    class_mapping = {0: "sideways", 1: "spike_up", 2: "spike_down"}
    mapped_dist = {class_mapping.get(k, str(k)): int(v) for k, v in distribution.items()}

    # 7. Real-time Inference on the most recent trading sequence
    # 7. Real-time Inference on the most recent trading sequence
    X_latest = latest_row[feature_features]
    probabilities = model.predict_proba(X_latest)[0]
    
    p_sideways = float(probabilities[0])
    p_up = float(probabilities[1])
    p_down = float(probabilities[2])

    # 8. Real-Time Action Decision Logic Engine
    if p_up >= 0.45:
        signal_action = "BUY NOW"
        signal_status = "BULLISH BREAKOUT DETECTED"
        signal_color = "#00C48C"
    elif p_down >= 0.45:
        signal_action = "STAY OUT / SHORT"
        signal_status = "BEARISH RISK DETECTED"
        signal_color = "#FF4560"
    else:
        signal_action = "HOLD"
        signal_status = "MARKET IS SIDEWAYS / NEUTRAL"
        signal_color = "#FFB800"

    data_note = (
        "live market data" if not used_synthetic
        else "synthetic data (live fetch was unavailable for this request)"
    )

    return {
        "ticker": ticker.upper(),
        "realtime_signal": {
            "action": signal_action,
            "status": signal_status,
            "color": signal_color
        },
        "used_synthetic_data": used_synthetic,
        "model_architecture": f"XGBoost Multi-Class · {horizon}-day Forecast Horizon",
        "configuration": {
            "horizon_days": horizon,
            "spike_percentage_threshold": f"{round(spike_threshold * 100, 1)}%"
        },
        "historical_distribution": mapped_dist,
        "metrics": {
            "test_set_accuracy": round(test_acc, 4),
            "baseline_majority_accuracy": round(baseline_acc, 4)
        },
        "latest_day_forecast": {
            "date": str(latest_row["date"].values[0]),
            "close_at_execution": float(latest_row["close"].values[0]),
            "probabilities": {
                "sideways": round(float(probabilities[0]), 4),
                "spike_up": round(float(probabilities[1]), 4),
                "spike_down": round(float(probabilities[2]), 4)
            }
        },
        "disclaimer": (
            f"This model maps directional volatility probabilities based on {data_note}. "
            "It is an educational project, not formal investment advice."
        )
    }


@app.post("/api/chart-trend")
async def chart_trend(file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise HTTPException(status_code=400, detail="Please upload a PNG, JPG, or WEBP image.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = extract_trend_line(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("reason", "Could not read chart."))

    return result


@app.get("/")
def root():
    return {"status": "ok", "service": "stock-anomaly-spotter"}