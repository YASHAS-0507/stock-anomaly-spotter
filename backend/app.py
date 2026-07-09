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
from typing import Dict, Any, Union, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
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

# Phase 2.1: WebSocket streaming
from services.websocket_manager import websocket_manager
# Market Data Layer (Phase 1)
from services.market_data import market_data_manager, Interval
from services.redis_manager import redis_manager
from services.market_status import market_status_service
from routers.market import router as market_router
from routers.candles   import router as candles_router
from routers.analytics import router as analytics_router

# Phase 2.2: AI Decision Engine
from decision_engine import generate_decision

# Phase 2.3: Execution Queue + Decision Logging
from execution_queue import execution_queue
from decision_logger import decision_logger

# Phase 2.4: Paper Trading Engine
from paper_broker import paper_broker

# Phase 3: Autonomous Scheduler + Live Trading
import threading as _threading
from scheduler.market_scheduler import market_scheduler
from broker.auto_paper_broker import auto_broker
from shadow.shadow_manager import shadow_manager
from tv_signals_store import tv_signals as _tv_signals

# System telemetry
try:
    import psutil
except ImportError:
    psutil = None

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
    import datetime as _dt, pytz as _pytz, sys as _sys

    _IST = _pytz.timezone("Asia/Kolkata")
    _utc_now  = _dt.datetime.now(_pytz.utc)
    _ist_now  = _dt.datetime.now(_IST)
    _server_tz = _dt.datetime.now(_IST).tzname()
    _mins     = _ist_now.hour * 60 + _ist_now.minute

    def is_market_open() -> bool:
        return (9 * 60 + 15) <= _mins <= (15 * 60 + 30) and _ist_now.weekday() < 5

    print("=" * 60)
    print(f"[TZ_AUDIT] Server clock TZ   : {_server_tz}")
    print(f"[TZ_AUDIT] Server UTC time   : {_utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"[TZ_AUDIT] Converted IST time: {_ist_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"[TZ_AUDIT] Offset UTC→IST    : +5:30 (Asia/Kolkata)")
    print(f"[TZ_AUDIT] Market open now   : {is_market_open()}")
    print("=" * 60)
    _sys.stdout.flush()

    try:
        from data_pipeline import get_price_data
        from features import build_feature_table

        historical_df, _ = get_price_data("RELIANCE.NS", period="1y")
        processed_df = build_feature_table(historical_df)
        intelligence_core.initialize_production_model(processed_df)
        print("[app] ML Intelligence Core warmed up with processed features.")
    except Exception as _e:
        print(f"[app] ML warmup skipped (yfinance unavailable on this host): {_e}")

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

# Add localhost for development
if _frontend_url and "localhost" not in _frontend_url:
    _allowed_origins.append("http://localhost:3000")
    _allowed_origins.append("http://127.0.0.1:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Market Data router (Phase 1)
app.include_router(market_router, tags=["market"])
# Phase 3: Intraday candle data router
app.include_router(candles_router, tags=["candles"])
# Analytics layer
app.include_router(analytics_router, tags=["analytics"])

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
        "reasoning_chain": ["Fallback protection mapping activated due to systemic interruption."],
        "summary": "HOLD (0.0% confidence). Fallback protection mapping activated due to systemic interruption."
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
        "portfolio_value": 5000.00,
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
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"VALIDATION ERROR INTERCEPTED: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# =====================================================================
# CORE PIPELINE HELPER METHODS
# =====================================================================
def _load_features(ticker: str, period: str, horizon: int = 5):
    df, used_synthetic = get_price_data(ticker, period=period)
    if len(df) < 45:
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

    # STAGE 2: MARKET REGIME VALVE CHECK (use already-computed feature_df)
    regime_snapshot = detect_market_regime(feature_df)

    feature_features = [
        "return_zscore", "rsi", "macd", "macd_signal", 
        "macd_histogram", "bollinger_bandwidth", "daily_return"
    ]

    for col in feature_features:
        if col not in feature_df.columns:
            feature_df[col] = 0.0

    X = feature_df[feature_features]
    y = feature_df["next_day_up"].astype(int)

    X_latest = feature_df[feature_features].iloc[[-1]]
    latest_row_meta = feature_df.iloc[[-1]]
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
                "confidence_rating": "0.0%",  # NO FALSE CONFIDENCE
                "reasoning_chain": [f"Analysis halted by regime detection: {regime_snapshot['regime_type']}"],
                "summary": f"Analysis halted: {regime_snapshot['regime_type']}. Model did not execute."
            },
            "stage_5_risk_matrix": {
                "decision": "HOLD",
                "target_quantity": 0,
                "stop_loss_limit": None,
                "take_profit_limit": None,
                "allocated_risk_cash": 0.0,
                "entry_price": None,
                "risk_reward_ratio": None,
                "risk_mitigation_reason": f"Execution blocked by regime: {regime_snapshot['regime_type']}"
            },
            "stage_6_portfolio_snapshot": {
                "free_cash": round(PORTFOLIO_STATE["available_cash"], 2),
                "portfolio_value": round(PORTFOLIO_STATE["total_equity"], 2),
                "active_asset_exposure": list(PORTFOLIO_STATE["open_trades"].keys())
            },
            "execution_status": "halted",  # NEW FIELD: halted|completed|failed
            "halt_reason": regime_snapshot['regime_type'],
            "disclaimer": "Analysis halted by regime detection. Model did not execute."
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
    
    # Add summary field for frontend compatibility
    explainability_snapshot["summary"] = f"{explainability_snapshot['primary_signal']} ({explainability_snapshot['confidence_rating']} confidence). " + " ".join(explainability_snapshot['reasoning_chain'])

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
            "entry_price": risk_snapshot.get("entry_price", None),
            "risk_reward_ratio": risk_snapshot.get("risk_reward_ratio", None),
            "risk_mitigation_reason": risk_snapshot.get("reason", "Passed systemic risk metrics filters")
        },
        "stage_6_portfolio_snapshot": {
            "free_cash": round(PORTFOLIO_STATE["available_cash"], 2),
            "portfolio_value": round(PORTFOLIO_STATE["total_equity"], 2),
            "active_asset_exposure": list(PORTFOLIO_STATE["open_trades"].keys())
        },
        "execution_status": "completed",  # NEW FIELD: completed|halted|failed
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

@app.get("/api/decision")
def get_decision(
    ticker: str = Query(...),
    period: str = Query("1y"),
    horizon: int = Query(5),
    spike_threshold: float = Query(0.05),
):
    """
    Phase 2.2: AI Decision Engine endpoint.
    Runs the same XGBoost pipeline as /api/predict, then synthesises
    an institutional trade decision via decision_engine.generate_decision().
    /api/predict is NOT modified — this endpoint is additive only.
    """
    try:
        if not CASCADING_ENGINES_AVAILABLE:
            raise ValueError("XGBoost or sklearn not available on this server.")

        feature_df, used_synthetic, raw_df = _load_features(ticker, period, horizon=horizon)
        feature_df = feature_df.sort_values("date").reset_index(drop=True)

        if len(feature_df) < 45:
            raise ValueError("Insufficient historical data.")

        regime_snapshot = detect_market_regime(feature_df)

        # XGBoost inference (identical feature set to /api/predict)
        _xgb_cols = [
            "return_zscore", "rsi", "macd", "macd_signal",
            "macd_histogram", "bollinger_bandwidth", "daily_return",
        ]
        for col in _xgb_cols:
            if col not in feature_df.columns:
                feature_df[col] = 0.0

        X = feature_df[_xgb_cols]
        y = feature_df["next_day_up"].astype(int)
        X_latest = feature_df[_xgb_cols].iloc[[-1]]
        latest_close = float(feature_df["close"].iloc[-1])

        X_train, _, y_train, _ = train_test_split(X, y, test_size=0.25, shuffle=False)

        xgb_model = xgb.XGBClassifier(
            max_depth=3, learning_rate=0.1, n_estimators=50,
            random_state=42, eval_metric="logloss",
        )
        xgb_model.fit(X_train, y_train)
        prob_price_up = float(xgb_model.predict_proba(X_latest)[0][1])

        prediction_payload = {
            "probabilities": {
                "spike_up":   prob_price_up,
                "spike_down": round(1.0 - prob_price_up, 4),
                "sideways":   0.0,
            }
        }

        decision = generate_decision(
            feature_df=feature_df,
            prediction_payload=prediction_payload,
            regime_snapshot=regime_snapshot,
            portfolio_state=PORTFOLIO_STATE,
            latest_close=latest_close,
            ticker=ticker,
            horizon=horizon,
        )

        # Phase 2.3: queue + log
        queue_entry = execution_queue.add(decision, ticker)
        decision_logger.log(
            ticker=ticker,
            decision_payload=decision,
            queue_entry=queue_entry,
            inference_time_ms=decision.get("inference_time_ms", 0),
        )
        decision["queue"] = {
            "trade_id":   queue_entry["trade_id"],
            "status":     queue_entry["status"],
            "queue_size": len(execution_queue.get_all()),
        }

        return clean_json_data(decision)

    except Exception as exc:
        from datetime import datetime, timezone, timedelta
        import pytz as _pytz; ts = datetime.now(_pytz.timezone("Asia/Kolkata")).strftime("%H:%M:%S IST")
        return {
            "decision":          "BLOCKED",
            "signal":            "BLOCKED",
            "confidence":        0.0,
            "score":             0,
            "risk":              "EXTREME",
            "expected_return":   0.0,
            "expected_drawdown": 0.0,
            "rr_ratio":          0.0,
            "position_size": {
                "shares": 0, "value": 0.0,
                "risk_amount": 0.0, "sizing_method": "error_fallback",
            },
            "entry_price": 0.0,
            "stop_loss":   0.0,
            "take_profit": {"tp1": 0.0, "tp2": 0.0, "tp3": 0.0},
            "holding_period":      "—",
            "explanation":         "Decision engine encountered an error.",
            "rejection_reason":    str(exc),
            "score_breakdown":     {"trend": 0, "momentum": 0, "volume": 0,
                                    "regime": 0, "prediction": 0, "risk": 0},
            "execution_permitted": False,
            "timestamp":           ts,
        }


@app.get("/api/queue")
def get_queue():
    try:
        return {
            "entries": execution_queue.get_all(),
            "stats":   execution_queue.get_stats(),
        }
    except Exception as exc:
        return {"entries": [], "stats": {}, "error": str(exc)}


@app.get("/api/queue/stats")
def get_queue_stats():
    try:
        return execution_queue.get_stats()
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/logs/recent")
def get_logs_recent(n: int = Query(20)):
    try:
        return {"decisions": decision_logger.get_recent(n)}
    except Exception as exc:
        return {"decisions": [], "error": str(exc)}


@app.get("/api/logs/stats")
def get_logs_stats():
    try:
        return decision_logger.get_stats()
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/system/telemetry")
def get_system_telemetry():
    telemetry: Dict[str, Any] = {
        "cpu_usage_percent":    "Unavailable",
        "memory_usage_percent": "Unavailable",
        "memory_used_mb":       "Unavailable",
        "memory_total_mb":      "Unavailable",
        "disk_usage_percent":   "Unavailable",
        "disk_used_gb":         "Unavailable",
        "disk_total_gb":        "Unavailable",
        "redis_status":         "Unavailable",
        "psutil_available":     psutil is not None,
    }

    if psutil is not None:
        try:
            # interval=0.1 gives a real (non-zero) reading on the first call
            telemetry["cpu_usage_percent"] = round(psutil.cpu_percent(interval=0.1), 1)
        except Exception as e:
            print(f"[telemetry] cpu_percent error: {e}")

        try:
            mem = psutil.virtual_memory()
            telemetry["memory_usage_percent"] = round(mem.percent, 1)
            telemetry["memory_used_mb"]       = round(mem.used / 1024 / 1024, 1)
            telemetry["memory_total_mb"]      = round(mem.total / 1024 / 1024, 1)
        except Exception as e:
            print(f"[telemetry] virtual_memory error: {e}")

        try:
            # Use "/" — works on Railway (Linux) and local Linux/macOS
            disk = psutil.disk_usage("/")
            telemetry["disk_usage_percent"] = round(disk.percent, 1)
            telemetry["disk_used_gb"]       = round(disk.used / 1024 / 1024 / 1024, 2)
            telemetry["disk_total_gb"]      = round(disk.total / 1024 / 1024 / 1024, 2)
        except Exception as e:
            print(f"[telemetry] disk_usage error: {e}")

    # Redis status check
    try:
        redis_manager.client.ping()
        telemetry["redis_status"] = "Connected"
    except Exception:
        telemetry["redis_status"] = "Unavailable"

    return telemetry


# =====================================================================
# PHASE 2.4: PAPER TRADING ENDPOINTS
# =====================================================================

class PaperExecuteRequest(BaseModel):
    trade_id: str


@app.post("/api/paper/execute")
def paper_execute(req: PaperExecuteRequest):
    """Execute a paper trade for an approved queue entry."""
    try:
        entries = execution_queue.get_all()
        entry = next((e for e in entries if e["trade_id"] == req.trade_id), None)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Trade {req.trade_id} not found in queue")

        if entry.get("status") not in ("approved", "pending"):
            raise HTTPException(
                status_code=400,
                detail=f"Trade {req.trade_id} has status '{entry.get('status')}' and cannot be executed"
            )

        d = entry.get("decision", entry)
        action    = d.get("decision", d.get("signal", "HOLD"))
        if action not in ("BUY", "SELL"):
            raise HTTPException(status_code=400, detail=f"Decision is {action}, not executable")

        ticker    = entry.get("ticker", "UNKNOWN")
        quantity  = int(d.get("position_size", {}).get("shares", 0) or 0)
        price     = float(d.get("entry_price", 0) or 0)
        stop_loss = float(d.get("stop_loss", 0) or 0)
        tp_dict   = d.get("take_profit", {}) or {}
        take_profit = float(tp_dict.get("tp1", price) or price)
        reason    = d.get("explanation", "")

        if quantity <= 0 or price <= 0:
            raise HTTPException(status_code=400, detail="Invalid quantity or price in decision payload")

        result = paper_broker.place_order(
            symbol=ticker,
            action=action,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trade_id=req.trade_id,
            reason=reason,
        )

        if result["success"]:
            execution_queue.update_status(req.trade_id, "executed")

        return clean_json_data(result)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/paper/portfolio")
def paper_portfolio():
    """Return current paper trading portfolio snapshot."""
    try:
        snapshot = paper_broker.get_portfolio_snapshot()
        return clean_json_data(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/paper/trades")
def paper_trades(limit: int = Query(50, ge=1, le=200)):
    """Return completed paper trade history."""
    try:
        trades = paper_broker.get_trade_history(limit=limit)
        return clean_json_data({"trades": trades, "count": len(trades)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/paper/reset")
def paper_reset():
    """Reset the paper trading portfolio to initial state."""
    try:
        paper_broker.reset()
        return {"success": True, "message": "Paper portfolio reset to initial state"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/paper/clear-emergency")
def paper_clear_emergency():
    """Clear emergency stop flag without resetting the portfolio."""
    try:
        auto_broker._emergency_stopped = False
        auto_broker._paused = False
        return {"status": "emergency stop cleared"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/paper/positions/check")
def paper_positions_check():
    """Check open positions against latest market prices; auto-close SL/TP hits."""
    try:
        positions = paper_broker.portfolio.get("positions", {})
        if not positions:
            return clean_json_data({"auto_closed": [], "portfolio": paper_broker.get_portfolio_snapshot()})

        current_prices: Dict[str, float] = {}
        for sym in positions:
            try:
                # Fetch latest close for this symbol from market data manager
                df, _ = get_price_data(sym, period="5d")
                if df is not None and not df.empty:
                    current_prices[sym] = float(df["Close"].iloc[-1])
            except Exception:
                pass

        auto_closed = paper_broker.check_positions(current_prices)
        snapshot    = paper_broker.get_portfolio_snapshot()
        return clean_json_data({"auto_closed": auto_closed, "portfolio": snapshot})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =====================================================================
# PHASE 3: SCHEDULER CONTROL ENDPOINTS
# =====================================================================

@app.post("/api/scheduler/start")
def start_scheduler():
    """Start the autonomous market scheduler in a background thread."""
    try:
        is_trading = market_scheduler.is_trading_day()
        if market_scheduler.running:
            return {"status": "already_running", "message": "Scheduler is already running", "is_trading_day": is_trading}
        t = _threading.Thread(target=market_scheduler.start, daemon=True, name="market-scheduler")
        t.start()
        return {"status": "started", "message": "Scheduler started in background thread", "is_trading_day": is_trading}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "is_trading_day": False}


@app.post("/api/scheduler/stop")
def stop_scheduler():
    """Stop the autonomous market scheduler."""
    try:
        market_scheduler.stop()
        return {"status": "stopped", "message": "Scheduler stopped and positions squared off"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/api/scheduler/pause")
def pause_scheduler():
    """Pause new trade execution (open positions continue to be monitored)."""
    try:
        auto_broker.pause()
        return {"status": "ok", "paused": True}
    except Exception as exc:
        return {"status": "error", "paused": False, "message": str(exc)}


@app.post("/api/scheduler/resume")
def resume_scheduler():
    """Resume new trade execution after a pause or emergency stop."""
    try:
        auto_broker.resume()
        # resume() only clears _paused; also clear emergency_stopped so trades
        # aren't permanently blocked after an emergency stop + resume cycle.
        auto_broker._emergency_stopped = False
        auto_broker._paused = False
        return {"status": "ok", "paused": False, "emergency_stopped": False}
    except Exception as exc:
        return {"status": "error", "paused": True, "message": str(exc)}


@app.post("/api/scheduler/emergency-stop")
def emergency_stop_scheduler():
    """Emergency stop: square off all positions immediately and halt all trading."""
    try:
        closed = auto_broker.emergency_stop(current_prices={})
        return {
            "status": "emergency_stopped",
            "positions_closed": len(closed),
            "message": f"Emergency stop triggered — {len(closed)} position(s) squared off",
        }
    except Exception as exc:
        return {"status": "error", "positions_closed": 0, "message": str(exc)}


@app.get("/api/scheduler/status")
def scheduler_status():
    """Return full scheduler and broker status."""
    try:
        import pytz as _pytz
        from datetime import datetime
        _IST = _pytz.timezone("Asia/Kolkata")
        now = datetime.now(_IST)
        now_mins = now.hour * 60 + now.minute
        market_open = (
            market_scheduler.is_trading_day(now.date())
            and (9 * 60 + 15) <= now_mins <= (15 * 60 + 30)
        )
        last_refresh = market_scheduler.last_intelligence_refresh
        return {
            "scheduler_running":        market_scheduler.running,
            "market_open":              market_open,
            "watchlist":                market_scheduler.watchlist,
            "intelligence_last_refresh": last_refresh.strftime("%Y-%m-%d %H:%M:%S IST") if last_refresh else None,
            "broker":                   auto_broker.get_portfolio_snapshot(),
            "daily_limits":             auto_broker.check_daily_limits(),
            "shadow_report":            shadow_manager.get_weekly_report(),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# =====================================================================
# PHASE 3: LIVE DATA ENDPOINTS
# =====================================================================

@app.get("/api/live/positions")
def live_positions():
    """Return current open positions and portfolio snapshot."""
    try:
        return auto_broker.get_portfolio_snapshot()
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/live/watchlist")
def live_watchlist():
    """Return active watchlist and cached intelligence."""
    try:
        return {
            "watchlist":    market_scheduler.watchlist,
            "count":        len(market_scheduler.watchlist),
            "intelligence": market_scheduler.intelligence_cache,
        }
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/live/trades/today")
def live_trades_today():
    """Return today's completed trades (newest first, up to 50)."""
    try:
        return auto_broker.get_trade_history(limit=50)
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/live/prices")
def live_prices():
    """Return latest tick prices for all tracked tickers."""
    try:
        return market_scheduler.current_prices
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/regime/matrix")
def regime_matrix():
    """Return latest detected regime for each ticker in the watchlist."""
    try:
        return market_scheduler.regime_cache
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/webhook/tv")
async def tradingview_webhook(request: Request):
    """Receive TradingView Pine Script alerts and store as ML features."""
    try:
        body     = await request.json()
        ticker   = str(body.get("ticker", "")).upper().strip()
        action   = str(body.get("action", "")).upper().strip()
        price    = float(body.get("price", 0) or 0)
        strategy = str(body.get("strategy", "unknown"))

        if not ticker:
            raise HTTPException(status_code=400, detail="ticker is required")

        score = 1.0 if action == "BUY" else (-1.0 if action == "SELL" else 0.0)

        import pytz as _pytz
        from datetime import datetime as _dt
        _IST = _pytz.timezone("Asia/Kolkata")
        _tv_signals[ticker] = {
            "score":     score,
            "action":    action,
            "price":     price,
            "strategy":  strategy,
            "timestamp": _dt.now(_IST).isoformat(),
        }
        logger.info("[webhook] TV signal: %s %s @ %.2f from %s", ticker, action, price, strategy)
        return {"status": "ok", "ticker": ticker, "processed": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/webhook/tv/signals")
def get_tv_signals():
    """Return all current TradingView signals (for debugging)."""
    return _tv_signals


@app.get("/api/data/source")
def data_source_status():
    """Return current data source status and cache stats."""
    try:
        from feeds.data_provider import data_provider
        from feeds.angel_feed import AngelOneFeed, _SMARTAPI_AVAILABLE, _PYOTP_AVAILABLE
        import os

        angel_creds_set = all(
            os.environ.get(k)
            for k in ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_SECRET")
        )
        angel_connected      = _SMARTAPI_AVAILABLE and _PYOTP_AVAILABLE and angel_creds_set
        angel_hist_available = angel_connected  # historical API available when SDK + creds present

        try:
            import yfinance as yf
            yf_available = True
        except ImportError:
            yf_available = False

        intraday_source = "angel_one" if angel_connected else "yfinance_fallback"

        # Last Angel auth time (check singleton's auth_token)
        last_angel_auth: str | None = None
        try:
            from feeds.angel_feed import AngelOneFeed as _AF
            # We don't track auth time globally; report None unless connected
            last_angel_auth = None
        except Exception:
            pass

        cache_stats = data_provider.get_cache_stats()

        return {
            "angel_one_connected":   angel_connected,
            "angel_one_historical":  angel_hist_available,
            "yfinance_available":    yf_available,
            "intraday_source":       intraday_source,
            "daily_source":          "yfinance",
            "macro_source":          "yfinance",
            "last_angel_auth":       last_angel_auth,
            "cache_stats":           cache_stats,
        }
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/shadow/report")
def shadow_report():
    """Return shadow agents weekly performance report."""
    try:
        return shadow_manager.get_weekly_report()
    except Exception as exc:
        return {"error": str(exc)}


from decay.decay_monitor import decay_monitor as _decay_monitor


@app.get("/api/decay/health")
def decay_health():
    """Return overall strategy decay system health summary."""
    try:
        return _decay_monitor.get_system_health_summary()
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/decay/setups")
def decay_setups():
    """Return full per-setup decay assessment (cached from last run)."""
    try:
        if not _decay_monitor._health_cache:
            return {"message": "No assessment run yet"}
        return _decay_monitor._health_cache
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/decay/run")
def decay_run():
    """Force an immediate decay assessment regardless of schedule."""
    try:
        trades = auto_broker.get_trade_history(limit=500)
        result = _decay_monitor.assess_all_setups(trades)
        return result
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/expiry/today")
def expiry_today():
    """Return F&O expiry context for today including risk multipliers."""
    try:
        from expiry.expiry_calendar import expiry_calendar
        return expiry_calendar.get_expiry_context()
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/health/full")
def full_health_check():
    """Return complete system health for deployment readiness checks."""
    import pytz as _pytz
    from datetime import datetime
    _IST = _pytz.timezone("Asia/Kolkata")
    ts = datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")

    checks: Dict[str, str] = {}

    checks["angel_credentials"] = (
        "set"
        if all(os.environ.get(k) for k in
               ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_SECRET"))
        else "missing"
    )
    checks["groq_api"]   = "set" if os.environ.get("GROQ_API_KEY") else "missing"
    checks["broker"]     = "emergency_stopped" if auto_broker._emergency_stopped else "active"
    checks["model"]      = "trained" if intraday_model.is_trained() else "untrained"
    checks["scheduler"]  = "running" if market_scheduler.running else "stopped"

    try:
        redis_manager.client.ping()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    degraded = (
        checks["angel_credentials"] == "missing"
        or checks["broker"] == "emergency_stopped"
        or checks["database"] == "error"
    )
    status = "degraded" if degraded else "healthy"

    try:
        broker_snapshot = auto_broker.get_portfolio_snapshot()
    except Exception:
        broker_snapshot = {}

    return {
        "status":          status,
        "timestamp":       ts,
        "checks":          checks,
        "broker_snapshot": broker_snapshot,
        "version":         "3.0.0-intraday",
    }


_training_lock = _threading.Lock()
_training_status: Dict[str, Any] = {"running": False, "last_result": None, "last_error": None}


@app.post("/api/model/train")
def model_train(tickers: Optional[List[str]] = None, days_back: int = Query(60, ge=7, le=180)):
    """
    Trigger XGBoost retraining in a background thread.
    Uses Angel One candle history for training data.
    POST body: optional JSON list of tickers (defaults to scheduler watchlist).
    Returns immediately; check GET /api/model/status for progress.
    """
    if not _training_lock.acquire(blocking=False):
        return {"status": "already_running", "message": "Training already in progress"}

    def _do_train():
        try:
            _training_status["running"] = True
            _training_status["last_error"] = None

            ticker_list = tickers or list(market_scheduler.watchlist) or [
                "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
                "SBIN", "BAJFINANCE", "WIPRO", "AXISBANK", "KOTAKBANK",
            ]
            logger.info("[api/model/train] Starting training on %d tickers, %d days back",
                        len(ticker_list), days_back)

            data = intraday_model.get_training_data(ticker_list, days_back=days_back)
            if len(data) < 30:
                _training_status["last_error"] = f"Insufficient training data: {len(data)} samples (need 30+)"
                logger.warning("[api/model/train] %s", _training_status["last_error"])
                return

            result = intraday_model.train(data)
            result["tickers_used"] = len(ticker_list)
            result["samples_total"] = len(data)
            _training_status["last_result"] = result
            logger.info("[api/model/train] Done — accuracy=%.3f baseline=%.3f n_train=%d",
                        result["accuracy"], result["baseline_accuracy"], result["n_train"])
        except Exception as exc:
            _training_status["last_error"] = str(exc)
            logger.warning("[api/model/train] Failed: %s", exc)
        finally:
            _training_status["running"] = False
            _training_lock.release()

    _threading.Thread(target=_do_train, daemon=True, name="model-retrain").start()
    return {"status": "started", "message": "Training started in background — check /api/model/status"}


@app.get("/api/model/status")
def model_status():
    """Return current model training status and last result."""
    return {
        "trained":        intraday_model.is_trained(),
        "training_now":   _training_status["running"],
        "last_result":    _training_status["last_result"],
        "last_error":     _training_status["last_error"],
        "model_path":     os.environ.get("MODEL_PATH", "backend/models/intraday_model.pkl (ephemeral)"),
        "durable_storage": bool(os.environ.get("MODEL_PATH")),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; manager handles broadcasts
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception:
        websocket_manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)