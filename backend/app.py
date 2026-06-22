"""
app.py
------
FastAPI backend for the Stock Anomaly Spotter project.

Endpoints:
  GET  /api/analyze?ticker=XXX&period=1y      -> full feature table + anomalies + chart series
  GET  /api/predict?ticker=XXX&period=1y      -> trained model accuracy report + latest direction probability
  POST /api/chart-trend                      -> upload a chart screenshot, get trend extraction

Run locally:
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8000
"""

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from data_pipeline import get_price_data
from features import build_feature_table
from anomaly import detect_anomalies, summarize_anomalies
from model import train_direction_model, predict_latest
from chart_reader import extract_trend_line

import os

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


# Added a horizon parameter here so it can pass downstream to your features module
def _load_features(ticker: str, period: str, horizon: int = 5):
    df, used_synthetic = get_price_data(ticker, period=period)
    if len(df) < 60:
        raise HTTPException(status_code=400, detail="Not enough data to analyze this ticker/period.")
    
    # Check if your build_feature_table accepts a horizon argument.
    # If features.py isn't modified yet to accept it, this will use its default shift logic.
    try:
        feature_df = build_feature_table(df, horizon=horizon)
    except TypeError:
        # Fallback if features.py hasn't been updated to accept horizon= yet
        feature_df = build_feature_table(df)
        
    return feature_df, used_synthetic


@app.get("/api/analyze")
def analyze(ticker: str = Query(...), period: str = Query("1y"), threshold: float = Query(2.2)):
    # Keep historical analysis clean with the default standard window framework
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
def predict(ticker: str = Query(...), period: str = Query("1y"), horizon: int = Query(5)):
    # Pass our frontend selected horizon directly into our backend feature constructor
    feature_df, used_synthetic = _load_features(ticker, period, horizon=horizon)
    if len(feature_df) < 80:
        raise HTTPException(status_code=400, detail="Not enough data to train a model on this period.")

    result = train_direction_model(feature_df)
    latest = predict_latest(result.model, feature_df, result.selected_features)

    data_note = (
        "live market data" if not used_synthetic
        else "synthetic data (live fetch was unavailable for this request)"
    )

    return {
        "ticker": ticker.upper(),
        "used_synthetic_data": used_synthetic,
        # The title string is now completely dynamic based on user selection!
        "model": f"RandomForestClassifier · {horizon}-day direction · time-ordered split",
        "test_set_accuracy": result.accuracy,
        "baseline_majority_class_accuracy": result.baseline_accuracy,
        "precision": result.precision,
        "recall": result.recall,
        "f1_score": result.f1,
        "n_train_days": result.n_train,
        "n_test_days": result.n_test,
        "feature_importances": result.feature_importances,
        "latest_day_prediction": latest,
        "disclaimer": (
            f"This predicts statistical direction probability based on {data_note} only. "
            "It is a learning project, not financial advice, and should not be used to make "
            "real trading decisions."
        ),
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