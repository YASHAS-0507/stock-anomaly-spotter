"""
app.py
------
FastAPI backend for the Stock Anomaly Spotter project.
Engineered with absolute global exception interception to guarantee frontend stability
and packed with real-time portfolio tracking, market regime filtering, and decision explainability.
"""

import shutil
import tempfile
from pathlib import Path
import os
import numpy as np
import pandas as pd
import math
from typing import Dict, Any, Union, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

# Core Research Pipeline Imports
from data_pipeline import get_price_data
from features import (
    build_feature_table, add_returns, add_moving_averages, add_rsi,
    add_volatility, add_rolling_zscore, add_volume_features, add_macd,
    add_bollinger_bands, add_lagged_features
)
from anomaly import detect_anomalies, summarize_anomalies
from chart_reader import extract_trend_line

# Multi-Stage Decision Intelligence Module Imports
from regime_detector import detect_market_regime
from explainability import generate_decision_reason
from risk_engine import calculate_position_size
from model import intelligence_core

# Explicit safe ML import checks
try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    CASCADING_ENGINES_AVAILABLE = True
except ImportError:
    CASCADING_ENGINES_AVAILABLE = False

app = FastAPI(title="Stock Anomaly Spotter API")

@app.on_event("startup")
def startup_event():
    """
    Warms up the ML engine by processing the raw data into the 
    required feature format before training.
    """
    from data_pipeline import get_price_data
    from features import build_feature_table # Ensure this is imported
    
    # 1. Get raw data
    historical_df, _ = get_price_data("RELIANCE.NS", period="1y")
    
    # 2. CRITICAL: Process the raw data into the required feature format
    # This matches the schema the model expects
    processed_df = build_feature_table(historical_df)
    
    # 3. Train using the processed features
    intelligence_core.initialize_production_model(processed_df)
    print("[app] ML Intelligence Core warmed up with processed features.")

# =====================================================================
# STAGE 6: STATE MANAGEMENT (IN-MEMORY PORTFOLIO TRACKER)
# =====================================================================
PORTFOLIO_STATE = {
    "available_cash": 5000.00,
    "total_equity": 5000.00,
    "open_trades": {},
    "daily_drawdown_limit": 500.00,
    "current_daily_loss": 0.00
}

# =====================================================================
# PYDANTIC PURE ROUTE DATA MODELS
# =====================================================================
class MarketDataRequest(BaseModel):
    prices: list

class RiskCalculationRequest(BaseModel):
    account_balance: float
    current_price: float
    win_probability: float
    risk_per_trade: float = 0.02

class DecisionRequest(BaseModel):
    probabilities: Dict[str, float]
    latest_features: Dict[str, float]

def clean_json_data(obj):
    """Recursively replaces NaN with None (which becomes 'null' in JSON)."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: clean_json_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_json_data(v) for v in obj]
    return obj

# CORS Configuration Matching Production
_frontend_url = os.environ.get("FRONTEND_URL")
_allowed_origins = [_frontend_url] if _frontend_url else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://selfless-intuition-production.up.railway.app"], 
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# THE IRONCLAD SAFETY NET: GLOBAL EXCEPTION HANDLERS
# =====================================================================
SAFE_FALLBACK_PAYLOAD = {
    "ticker": "SYSTEM-SAFE-MODE",
    "realtime_signal": {"action": "HOLD", "status": "PIPELINE RECALIBRATING", "color": "#FFB800"},
    "used_synthetic_data": True,
    "model_architecture": "Global Exception Fallback Shield",
    "pipeline_routing_execution": "Safety Catch Block Triggered",
    "configuration": {"horizon_days": 5, "spike_percentage_threshold": "5.0%"},
    "metrics": {"test_set_accuracy": 0.0, "baseline_majority_accuracy": 0.0},
    "probabilities": {
        "sideways": 1.0,
        "spike_up": 0.0,
        "spike_down": 0.0
    },
    "latest_day_forecast": {
        "date": "Live Matrix",
        "close_at_execution": 0.0,
        "probabilities": {
            "sideways": 1.0,
            "spike_up": 0.0,
            "spike_down": 0.0
        }
    },
    "stage_4_explainability": {
        "primary_signal": "HOLD",
        "confidence_rating": "0.0%",
        "reasoning_chain": ["Fallback protection mapping activated due to systemic interruption."]
    },
    "stage_5_risk_matrix": {
        "decision": "HOLD",
        "target_quantity": 0,
        "stop_loss_limit": None,
        "take_profit_limit": None,
        "allocated_risk_cash": 0.0,
        "risk_mitigation_reason": "Global Safety Interception"
    },
    "stage_6_portfolio_snapshot": {
        "free_cash": 5000.00,
        "total_portfolio_value": 5000.00,
        "active_asset_exposure": []
    },
    "disclaimer": "The pipeline encountered an interruption. Defaulting to safe neutral output to maintain UI stability."
}

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    print(f"CRITICAL SYSTEM ERROR INTERCEPTED: {str(exc)}")
    return JSONResponse(status_code=200, content=SAFE_FALLBACK_PAYLOAD)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    print(f"HTTP ERROR INTERCEPTED: {exc.detail}")
    return JSONResponse(status_code=200, content=SAFE_FALLBACK_PAYLOAD)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"VALIDATION ERROR INTERCEPTED: {exc.errors()}")
    return JSONResponse(status_code=200, content=SAFE_FALLBACK_PAYLOAD)

# =====================================================================
# CORE PIPELINE HELPER METHODS
# =====================================================================
def _load_features(ticker: str, period: str, horizon: int = 5):
    df, used_synthetic = get_price_data(ticker, period=period)
    if len(df) < 60:
        raise ValueError("Not enough data to analyze this ticker/period.")
    
    try:
        feature_df = build_feature_table(df, horizon=horizon)
    except TypeError:
        feature_df = build_feature_table(df)
         
    return feature_df, used_synthetic, df

# =====================================================================
# ENDPOINTS DEFINITIONS
# =====================================================================
@app.get("/")
def root():
    return {"status": "Quant Trading API operational", "portfolio": PORTFOLIO_STATE}

@app.get("/portfolio/state")
async def get_portfolio_state():
    return PORTFOLIO_STATE

@app.post("/portfolio/reset")
async def reset_portfolio():
    global PORTFOLIO_STATE
    PORTFOLIO_STATE = {
        "available_cash": 5000.00,
        "total_equity": 5000.00,
        "open_trades": {},
        "daily_drawdown_limit": 500.00,
        "current_daily_loss": 0.00
    }
    return {"status": "Portfolio reset", "portfolio": PORTFOLIO_STATE}

@app.post("/regime/detect")
async def detect_regime_endpoint(request: MarketDataRequest):
    if len(request.prices) < 200:
        raise HTTPException(status_code=400, detail="Minimum 200 price points required")
    df = pd.DataFrame({"Close": request.prices})
    return detect_market_regime(df)

@app.post("/decision/explain")
async def explain_decision_endpoint(request: DecisionRequest):
    return generate_decision_reason(probabilities=request.probabilities, latest_features=request.latest_features)

@app.post("/risk/position-size")
async def calculate_risk_endpoint(request: RiskCalculationRequest):
    return calculate_position_size(
        account_balance=request.account_balance,
        current_price=request.current_price,
        win_probability=request.win_probability,
        risk_per_trade=request.risk_per_trade
    )

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
        raise ValueError("XGBoost or dependencies missing on server environment.")

    # 1. Ingest Data Pipelines
    feature_df, used_synthetic, raw_df = _load_features(ticker, period, horizon=horizon)
    feature_df = feature_df.sort_values("date").reset_index(drop=True)
    
    if len(feature_df) < 45:
        raise ValueError("Insufficient dataset historical context.")

    # 2. Re-run indicators for validation datasets
    full_calculated_df = raw_df.copy().sort_values("date").reset_index(drop=True)
    full_calculated_df = add_returns(full_calculated_df)
    full_calculated_df = add_moving_averages(full_calculated_df)
    full_calculated_df = add_returns(full_calculated_df) if "daily_return" not in full_calculated_df.columns else full_calculated_df
    full_calculated_df = add_rsi(full_calculated_df)
    full_calculated_df = add_volatility(full_calculated_df)
    full_calculated_df["daily_return"] = full_calculated_df["daily_return"].fillna(0)
    full_calculated_df = add_rolling_zscore(full_calculated_df)
    full_calculated_df = add_volume_features(full_calculated_df)
    full_calculated_df = add_macd(full_calculated_df)
    full_calculated_df = add_bollinger_bands(full_calculated_df)
    full_calculated_df = add_lagged_features(full_calculated_df, columns=["daily_return", "rsi", "return_zscore"], lags=(1, 2, 3))

    # STAGE 2: MARKET REGIME VALVE CHECK
    regime_snapshot = detect_market_regime(full_calculated_df)

    feature_features = [
        "return_zscore", "rsi", "macd", "macd_signal", 
        "macd_histogram", "bollinger_bandwidth", "daily_return"
    ]

    for col in feature_features:
        if col not in feature_df.columns:
            feature_df[col] = 0.0
        if col not in full_calculated_df.columns:
            full_calculated_df[col] = 0.0

    X = feature_df[feature_features]
    y = feature_df["next_day_up"].astype(int)

    X_latest = full_calculated_df[feature_features].iloc[[-1]]
    latest_row_meta = full_calculated_df.iloc[[-1]]
    latest_close = float(latest_row_meta["close"].values[0])

    # Intercept Execution early if Market Intelligence Layer permits no active action
    if not regime_snapshot.get("action_permitted", True):
        probabilities_payload = {"sideways": 1.0, "spike_up": 0.0, "spike_down": 0.0}
        
        payload = {
            "ticker": ticker.upper(),
            "realtime_signal": {"action": "HOLD", "status": f"HALTED: {regime_snapshot['regime_type']}", "color": "#FFB800"},
            "used_synthetic_data": used_synthetic,
            "model_architecture": "XGBoost + TabPFN Cascading Network",
            "pipeline_routing_execution": f"Regime Shield Block [{regime_snapshot['regime_type']}]",
            "configuration": {"horizon_days": horizon, "spike_percentage_threshold": f"{round(spike_threshold * 100, 1)}%"},
            "metrics": {"test_set_accuracy": 0.0, "baseline_majority_accuracy": 0.0},
            "probabilities": probabilities_payload,
            "latest_day_forecast": {
                "date": str(latest_row_meta["date"].values[0]),
                "close_at_execution": latest_close,
                "probabilities": probabilities_payload
            },
            "stage_4_explainability": {
                "primary_signal": "HOLD",
                "confidence_rating": "100.0%",
                "reasoning_chain": [f"System locked execution circuit breaker due to market environment: {regime_snapshot['regime_type']}"]
            },
            "stage_5_risk_matrix": {
                "decision": "HOLD",
                "target_quantity": 0,
                "stop_loss_limit": None,
                "take_profit_limit": None,
                "allocated_risk_cash": 0.0,
                "risk_mitigation_reason": f"Execution gate disabled inside structural {regime_snapshot['regime_type']} macro footprint."
            },
            "stage_6_portfolio_snapshot": {
                "free_cash": round(PORTFOLIO_STATE["available_cash"], 2),
                "total_portfolio_value": round(PORTFOLIO_STATE["total_equity"], 2),
                "active_asset_exposure": list(PORTFOLIO_STATE["open_trades"].keys())
            },
            "disclaimer": "This model maps directional volatility probabilities based on live data. Project for educational use."
        }
        return clean_json_data(payload)

    # 3. Split data chronologically
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, shuffle=False)

    # 4. Train Model
    xgb_gatekeeper = xgb.XGBClassifier(
        max_depth=3, 
        learning_rate=0.1, 
        n_estimators=50, 
        random_state=42, 
        eval_metric="logloss"
    )
    xgb_gatekeeper.fit(X_train, y_train)

    # 5. Live Inference execution
    prob_price_up = float(xgb_gatekeeper.predict_proba(X_latest)[0][1])
    pipeline_routing = "XGBoost Core Engine"
    signal_action, signal_status, signal_color = "HOLD", "MARKET CONSOLIDATION REGIME", "#FFB800"

    if prob_price_up >= 0.58:
        signal_action, signal_status, signal_color = "BUY NOW", "STRONG UPWARD MOMENTUM DETECTED", "#00C48C"
        pipeline_routing = "XGBoost Trend Execution"
    elif prob_price_up <= 0.42:
        signal_action, signal_status, signal_color = "SHORT / STAY OUT", "BEARISH DOWNTREND REGIME", "#FF4560"
        pipeline_routing = "XGBoost Risk Execution"
    else:
        try:
            from tabpfn import TabPFNClassifier
            tabpfn_net = TabPFNClassifier(device='cpu', N_ensemble_configurations=2)
            tabpfn_net.fit(X_train, y_train)
            tabpfn_prob_up = float(tabpfn_net.predict_proba(X_latest)[0][1])
            
            if tabpfn_prob_up >= 0.62:
                signal_action, signal_status, signal_color = "BUY NOW", "BULLISH BREAKOUT (RESCUED BY TABPFN)", "#00C48C"
                pipeline_routing = "TabPFN In-Context Breakout Rescue"
                prob_price_up = tabpfn_prob_up
            elif tabpfn_prob_up <= 0.38:
                signal_action, signal_status, signal_color = "STAY OUT", "BEARISH TRAP (RESCUED BY TABPFN)", "#FF4560"
                pipeline_routing = "TabPFN In-Context Risk Rescue"
                prob_price_up = tabpfn_prob_up
        except Exception:
            pass

    if signal_action == "BUY NOW":
        f_up, f_down, f_sideways = prob_price_up, 1.0 - prob_price_up, 0.0
    elif "STAY OUT" in signal_action or "SHORT" in signal_action:
        f_up, f_down, f_sideways = prob_price_up, 1.0 - prob_price_up, 0.0
    else:
        f_up, f_down, f_sideways = prob_price_up * 0.5, (1.0 - prob_price_up) * 0.5, 0.5

    probabilities_payload = {
        "sideways": round(f_sideways, 4),
        "spike_up": round(f_up, 4),
        "spike_down": round(f_down, 4)
    }

    test_acc = float(accuracy_score(y_test, xgb_gatekeeper.predict(X_test))) if len(y_test) > 0 else 0.0
    baseline_acc = float(y_test.value_counts().max() / len(y_test)) if len(y_test) > 0 else 0.0

    # STAGE 4: GENERATE EXPLAINABILITY STRINGS
    latest_features_dict = X_latest.to_dict(orient="records")[0]
    explainability_snapshot = generate_decision_reason(probabilities_payload, latest_features_dict)

    # STAGE 5: COMPUTE POSITION SIZING METRIC
    risk_snapshot = calculate_position_size(
        account_balance=PORTFOLIO_STATE["available_cash"],
        current_price=latest_close,
        win_probability=probabilities_payload["spike_up"]
    )

    # STAGE 6: PORTFOLIO ENGINE SYSTEM OVERRIDE PRESERVATION
    if risk_snapshot["action"] == "ENTER":
        required_liquidity = risk_snapshot.get("total_transaction_value", 0.0)
        if required_liquidity > PORTFOLIO_STATE["available_cash"]:
            risk_snapshot["action"] = "HOLD"
            risk_snapshot["reason"] = "Portfolio Allocation Limit: Insufficient Free Liquid Cash"

    payload = {
        "ticker": ticker.upper(),
        "realtime_signal": {"action": signal_action, "status": signal_status, "color": signal_color},
        "used_synthetic_data": used_synthetic,
        "model_architecture": "XGBoost + TabPFN Cascading Network",
        "pipeline_routing_execution": pipeline_routing,
        "configuration": {
            "horizon_days": horizon,
            "spike_percentage_threshold": f"{round(spike_threshold * 100, 1)}%"
        },
        "metrics": {
            "test_set_accuracy": round(test_acc, 4),
            "baseline_majority_accuracy": round(baseline_acc, 4)
        },
        "probabilities": probabilities_payload,
        "latest_day_forecast": {
            "date": str(latest_row_meta["date"].values[0]),
            "close_at_execution": latest_close,
            "probabilities": probabilities_payload
        },
        "stage_4_explainability": explainability_snapshot,
        "stage_5_risk_matrix": {
            "decision": risk_snapshot["action"],
            "target_quantity": risk_snapshot.get("quantity", 0),
            "stop_loss_limit": risk_snapshot.get("stop_loss", None),
            "take_profit_limit": risk_snapshot.get("take_profit", None),
            "allocated_risk_cash": risk_snapshot.get("actual_risk", 0.0),
            "risk_mitigation_reason": risk_snapshot.get("reason", "Passed systemic risk metrics filters")
        },
        "stage_6_portfolio_snapshot": {
            "free_cash": round(PORTFOLIO_STATE["available_cash"], 2),
            "total_portfolio_value": round(PORTFOLIO_STATE["total_equity"], 2),
            "active_asset_exposure": list(PORTFOLIO_STATE["open_trades"].keys())
        },
        "disclaimer": "This model maps directional volatility probabilities based on live data. Project for educational use."
    }

    return clean_json_data(payload)

@app.post("/api/chart-trend")
async def chart_trend(file: UploadFile = File(...)):
    if file.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise ValueError("Please upload a PNG, JPG, or WEBP image.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = extract_trend_line(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not result.get("ok"):
        raise ValueError(result.get("reason", "Could not read chart."))

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)