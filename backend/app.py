"""
app.py
------
FastAPI backend for the Stock Anomaly Spotter project.
Upgraded with Binary XGBoost and TabPFN In-Context Transformer Rescue Net.
Backward compatible with original multi-class frontend payload keys.
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
from features import (
    build_feature_table, add_returns, add_moving_averages, add_rsi,
    add_volatility, add_rolling_zscore, add_volume_features, add_macd,
    add_bollinger_bands, add_lagged_features
)
from anomaly import detect_anomalies, summarize_anomalies
from chart_reader import extract_trend_line

# Import explicit optional dependencies for the predictive pipeline
try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    CASCADING_ENGINES_AVAILABLE = True
except ImportError:
    CASCADING_ENGINES_AVAILABLE = False

app = FastAPI(title="Stock Anomaly Spotter API")

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
         
    return feature_df, used_synthetic, df


@app.get("/api/analyze")
def analyze(ticker: str = Query(...), period: str = Query("1y"), threshold: float = Query(2.2)):
    feature_df, used_synthetic, _ = _load_features(ticker, period)
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
    spike_threshold: float = Query(0.05)
):
    if not CASCADING_ENGINES_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="XGBoost and scikit-learn are required for this endpoint."
        )

    # 1. Load data and feature frame
    feature_df, used_synthetic, raw_df = _load_features(ticker, period, horizon=horizon)
    feature_df = feature_df.sort_values("date").reset_index(drop=True)
    
    if len(feature_df) < 45:
        raise HTTPException(status_code=400, detail="Insufficient chronological timeline context.")

    # 2. Re-run indicators on raw data to extract the live row BEFORE target drop truncation
    full_calculated_df = raw_df.copy().sort_values("date").reset_index(drop=True)
    full_calculated_df = add_returns(full_calculated_df)
    full_calculated_df = add_moving_averages(full_calculated_df)
    full_calculated_df = add_rsi(full_calculated_df)
    full_calculated_df = add_volatility(full_calculated_df)
    full_calculated_df["daily_return"] = full_calculated_df["daily_return"].fillna(0)
    full_calculated_df = add_rolling_zscore(full_calculated_df)
    full_calculated_df = add_volume_features(full_calculated_df)
    full_calculated_df = add_macd(full_calculated_df)
    full_calculated_df = add_bollinger_bands(full_calculated_df)
    full_calculated_df = add_lagged_features(full_calculated_df, columns=["daily_return", "rsi", "return_zscore"], lags=(1, 2, 3))

    # Features selected to feed into the classification algorithms
    feature_features = [
        "return_zscore", "rsi", "macd", "macd_signal", 
        "macd_histogram", "bollinger_bandwidth", "daily_return"
    ]

    X = feature_df[feature_features]
    y = feature_df["next_day_up"].astype(int)

    # Isolate live variables for the upcoming prediction execution
    X_latest = full_calculated_df[feature_features].iloc[[-1]]
    latest_row_meta = full_calculated_df.iloc[[-1]]

    # 3. Strict Chronological Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, shuffle=False)

    # 4. Train XGBoost Gatekeeper
    xgb_gatekeeper = xgb.XGBClassifier(
        max_depth=3, 
        learning_rate=0.1, 
        n_estimators=50, 
        random_state=42, 
        eval_metric="logloss"
    )
    xgb_gatekeeper.fit(X_train, y_train)

    # 5. Metrics Compilation
    y_pred = xgb_gatekeeper.predict(X_test)
    test_acc = float(accuracy_score(y_test, y_pred))
    majority_class_count = int(y_test.value_counts().max())
    baseline_acc = float(majority_class_count / len(y_test))

    # 6. Live Core Inference
    prob_price_up = float(xgb_gatekeeper.predict_proba(X_latest)[0][1])
    pipeline_routing = "XGBoost Core Engine"

    # 7. Execution Cascading + TabPFN Gray-Zone Filter Rescue Net
    if prob_price_up >= 0.60:
        signal_action, signal_status, signal_color = "BUY NOW", "STRONG UPWARD MOMENTUM DETECTED", "#00C48C"
        pipeline_routing = "XGBoost Trend Execution"
    elif prob_price_up <= 0.40:
        signal_action, signal_status, signal_color = "SHORT / STAY OUT", "BEARISH DOWNTREND REGIME", "#FF4560"
        pipeline_routing = "XGBoost Risk Execution"
    else:
        # Indecisive Middle Zone (41% - 59%) -> Trigger TabPFN In-Context Rescue Net!
        try:
            from tabpfn import TabPFNClassifier
            tabpfn_net = TabPFNClassifier(device='cpu', N_ensemble_configurations=2)
            tabpfn_net.fit(X_train, y_train)
            
            tabpfn_prob_up = float(tabpfn_net.predict_proba(X_latest)[0][1])
            
            if tabpfn_prob_up >= 0.65:
                signal_action, signal_status, signal_color = "BUY NOW", "BULLISH BREAKOUT (RESCUED BY TABPFN)", "#00C48C"
                pipeline_routing = "TabPFN In-Context Breakout Rescue"
                prob_price_up = tabpfn_prob_up
            elif tabpfn_prob_up <= 0.35:
                signal_action, signal_status, signal_color = "STAY OUT", "BEARISH TRAP (RESCUED BY TABPFN)", "#FF4560"
                pipeline_routing = "TabPFN In-Context Risk Rescue"
                prob_price_up = tabpfn_prob_up
            else:
                signal_action, signal_status, signal_color = "HOLD", "TRUE SIDEWAYS MARKET / NEUTRAL ZONE", "#FFB800"
                pipeline_routing = "XGBoost + TabPFN Consolidated Hold"
        except Exception:
            signal_action, signal_status, signal_color = "HOLD", "MARKET IS INDECISIVE", "#FFB800"
            pipeline_routing = "XGBoost Indecisive (Rescue Framework Fallback)"

    data_note = (
        "live market data" if not used_synthetic
        else "synthetic data (live fetch was unavailable for this request)"
    )

    # 8. Frontend Interface Compatibility Mapping Layer
    # We map our precise continuous probabilities back into the keys the frontend is rendering
    if signal_action == "BUY NOW":
        f_up = prob_price_up
        f_down = 1.0 - prob_price_up
        f_sideways = 0.0
    elif signal_action == "SHORT / STAY OUT" or signal_action == "STAY OUT":
        f_up = prob_price_up
        f_down = 1.0 - prob_price_up
        f_sideways = 0.0
    else:
        # Balanced or consolidation phase representation
        f_up = prob_price_up * 0.5
        f_down = (1.0 - prob_price_up) * 0.5
        f_sideways = 0.5

    return {
        "ticker": ticker.upper(),
        "realtime_signal": {
            "action": signal_action,
            "status": signal_status,
            "color": signal_color
        },
        "used_synthetic_data": used_synthetic,
        "model_architecture": "XGBoost + TabPFN In-Context Cascading Network",
        "pipeline_routing_execution": pipeline_routing,
        "configuration": {
            "horizon_days": horizon
        },
        "metrics": {
            "test_set_accuracy": round(test_acc, 4),
            "baseline_majority_accuracy": round(baseline_acc, 4)
        },
        "latest_day_forecast": {
            "date": str(latest_row_meta["date"].values[0]),
            "close_at_execution": float(latest_row_meta["close"].values[0]),
            # --- CRITICAL FRONTEND FIX: Restoring legacy keys to satisfy UI reading parameters ---
            "probabilities": {
                "sideways": round(f_sideways, 4),
                "spike_up": round(f_up, 4),
                "spike_down": round(f_down, 4)
            }
        },
        "disclaimer": f"This model maps directional volatility probabilities based on {data_note}. Project for educational use."
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