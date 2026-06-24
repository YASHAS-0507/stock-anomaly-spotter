"""
app.py
------
FastAPI backend upgraded with a Hierarchical Cascading Pipeline:
  - Stage 1: XGBoost maps and filters out the dominant "Sideways" noise.
  - Stage 2: LightGBM performs precision targeting on high-volatility spikes.
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

# Try importing the cascading engine dependencies
try:
    import xgboost as xgb
    import lightgbm as lgb
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
    spike_threshold: float = Query(0.05)
):
    if not CASCADING_ENGINES_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="XGBoost, LightGBM, and scikit-learn are all required. Please check your requirements.txt file."
        )

    # 1. Pipeline preparation
    feature_df, used_synthetic = _load_features(ticker, period, horizon=horizon)
    feature_df = feature_df.sort_values("date").reset_index(drop=True)
    
    if len(feature_df) < 45:
        raise HTTPException(status_code=400, detail="Insufficient chronological timeline context.")

    # 2. Build target labels (0: Sideways, 1: Spike Up, 2: Spike Down)
    feature_df["future_close"] = feature_df["close"].shift(-horizon)
    feature_df["future_return"] = (feature_df["future_close"] - feature_df["close"]) / feature_df["close"]

    def label_market_spike(future_ret):
        if pd.isna(future_ret):
            return np.nan
        if future_ret >= spike_threshold:
            return 1
        elif future_ret <= -spike_threshold:
            return 2
        else:
            return 0

    feature_df["target"] = feature_df["future_return"].apply(label_market_spike)

    # Cache latest execution row for live inference
    latest_row = feature_df.iloc[[-1]].copy()
    train_clean_df = feature_df.dropna(subset=["target"]).copy()
    
    if len(train_clean_df) < 25:
        raise HTTPException(status_code=400, detail="Not enough historical frames to build cross-validation filters.")

    # 3. Separate structural parameters
    all_cols = train_clean_df.columns.tolist()
    ignore_cols = ["date", "target", "future_close", "future_return", "open", "high", "low", "volume"]
    feature_features = [c for c in all_cols if c not in ignore_cols and not train_clean_df[c].dtype == object]

    X = train_clean_df[feature_features]
    y = train_clean_df["target"].astype(int)

    # Chronological Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, shuffle=False)

    # --- STAGE 1: XGBOOST GATEKEEPER ---
    # Convert labels into Binary: 0 = Sideways, 1 = Volatility Warning (Any Spike)
    y_train_binary = (y_train != 0).astype(int)
    y_test_binary = (y_test != 0).astype(int)

    xgb_gatekeeper = xgb.XGBClassifier(
        max_depth=3, learning_rate=0.1, n_estimators=50, random_state=42, eval_metric="logloss"
    )
    xgb_gatekeeper.fit(X_train, y_train_binary)
    
    # --- STAGE 2: LIGHTGBM PRECISION SNIPER ---
    # LightGBM trains specifically on historical non-sideways anomaly frames
    breakout_mask = (y_train != 0)
    X_train_breakout = X_train[breakout_mask]
    y_train_breakout = y_train[breakout_mask]

    # Fallback if historical spikes are completely empty in the train set split
    if len(y_train_breakout) < 2:
        X_train_breakout = X_train
        y_train_breakout = y_train

    lgb_sniper = lgb.LGBMClassifier(
        max_depth=4, learning_rate=0.08, n_estimators=40, random_state=42, verbosity=-1
    )
    lgb_sniper.fit(X_train_breakout, y_train_breakout)

    # --- PIPELINE EVALUATION ---
    # Test accuracy evaluation using the complete cascading logic pass
    pred_test_binary = xgb_gatekeeper.predict(X_test)
    final_test_preds = []
    
    for idx, is_breakout in enumerate(pred_test_binary):
        if is_breakout == 0:
            final_test_preds.append(0)  # Sent straight to sideways
        else:
            row_frame = X_test.iloc[[idx]]
            final_test_preds.append(int(lgb_sniper.predict(row_frame)[0]))

    pipeline_acc = float(accuracy_score(y_test, final_test_preds))
    baseline_acc = float(int(y_test.value_counts().max()) / len(y_test))

    # --- LIVE CASCADING INFERENCE ---
    X_latest = latest_row[feature_features]
    prob_any_breakout = float(xgb_gatekeeper.predict_proba(X_latest)[0][1])

    # Cascade execution sequence routing
    if prob_any_breakout < 0.40:
        p_sideways = 1.0 - prob_any_breakout
        p_up = prob_any_breakout * 0.5
        p_down = prob_any_breakout * 0.5
    else:
        lgb_probs = lgb_sniper.predict_proba(X_latest)[0]
        # Map class indexes cleanly back safely depending on fallback shapes
        if len(lgb_probs) == 3:
            p_sideways = float(lgb_probs[0]) * (1.0 - prob_any_breakout)
            p_up = float(lgb_probs[1])
            p_down = float(lgb_probs[2])
        else:
            p_sideways = 1.0 - prob_any_breakout
            p_up = float(lgb_probs[0]) if 1 in lgb_sniper.classes_ else 0.0
            p_down = float(lgb_probs[1]) if 2 in lgb_sniper.classes_ else (float(lgb_probs[0]) if 2 in lgb_sniper.classes_ else 0.0)

    # Re-normalize array layout weights to add up to exactly 100%
    total_w = p_sideways + p_up + p_down
    p_sideways, p_up, p_down = p_sideways / total_w, p_up / total_w, p_down / total_w

    # Determine real-time action status alerts
    if p_up >= 0.45:
        signal_action, signal_status, signal_color = "BUY NOW", "BULLISH BREAKOUT DETECTED", "#00C48C"
    elif p_down >= 0.45:
        signal_action, signal_status, signal_color = "STAY OUT / SHORT", "BEARISH RISK DETECTED", "#FF4560"
    else:
        signal_action, signal_status, signal_color = "HOLD", "MARKET IS SIDEWAYS / NEUTRAL", "#FFB800"

    distribution = y.value_counts().to_dict()
    mapped_dist = {"sideways": int(distribution.get(0, 0)), "spike_up": int(distribution.get(1, 0)), "spike_down": int(distribution.get(2, 0))}

    return {
        "ticker": ticker.upper(),
        "used_synthetic_data": used_synthetic,
        "model_architecture": f"Hierarchical Ensemble: XGBoost (Gatekeeper) + LightGBM (Sniper)",
        "configuration": {
            "horizon_days": horizon,
            "spike_percentage_threshold": f"{round(spike_threshold * 100, 1)}%"
        },
        "realtime_signal": {
            "action": signal_action,
            "status": signal_status,
            "color": signal_color
        },
        "historical_distribution": mapped_dist,
        "metrics": {
            "test_set_accuracy": round(pipeline_acc, 4),
            "baseline_majority_accuracy": round(baseline_acc, 4)
        },
        "latest_day_forecast": {
            "date": str(latest_row["date"].values[0]),
            "close_at_execution": float(latest_row["close"].values[0]),
            "probabilities": {
                "sideways": round(p_sideways, 4),
                "spike_up": round(p_up, 4),
                "spike_down": round(p_down, 4)
            }
        },
        "disclaimer": "Dual-engine statistical indicator cascade. Designed as an educational engineering blueprint."
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
    return {"status": "ok", "service": "cascading-anomaly-engine"}