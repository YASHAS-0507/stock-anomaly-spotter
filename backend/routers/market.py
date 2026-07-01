"""
routers/market.py
-----------------
All /api/market/* endpoints. Mounted in app.py via include_router.

Endpoints:
  GET  /api/market/status
  GET  /api/market/candles/{symbol}
  GET  /api/market/candles/{symbol}/latest
  GET  /api/market/cache/info
  GET  /api/market/validation/stats
  GET  /api/market/intervals
  POST /api/market/candles
  POST /api/market/cache/clear
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from services.market_data import market_data_manager, Interval, Candle
from services.redis_manager import redis_manager
from services.market_status import market_status_service

router = APIRouter(prefix="/api/market", tags=["market"])


# ── Pydantic models ────────────────────────────────────────────────────

class CandleRequest(BaseModel):
    """Request body for POST /api/market/candles."""
    timestamp: str
    open:   float = Field(..., gt=0)
    high:   float = Field(..., gt=0)
    low:    float = Field(..., gt=0)
    close:  float = Field(..., gt=0)
    volume: float = Field(..., ge=0)
    symbol: str
    interval: str

    def to_candle(self) -> Candle:
        from datetime import datetime
        return Candle(
            timestamp=datetime.fromisoformat(self.timestamp),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            symbol=self.symbol,
            interval=Interval(self.interval),
        )


class CacheClearRequest(BaseModel):
    symbol:   Optional[str] = None
    interval: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────

def _parse_interval(interval: str) -> Interval:
    try:
        return Interval(interval)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval '{interval}'. Supported: {[i.value for i in Interval]}",
        )


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/status")
def get_market_status(force_refresh: bool = Query(False)):
    """
    Returns live NSE market status including open/closed state,
    feed latency, current IST time, and validation stats.
    """
    try:
        return market_status_service.get_status(force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles/{symbol}")
def get_historical_candles(
    symbol:        str  = Path(..., description="Trading symbol e.g. RELIANCE.NS"),
    interval:      str  = Query("1d",  description="Interval: 1m 5m 15m 30m 1h 1d"),
    period:        str  = Query("1mo", description="Period: 1d 5d 1mo 3mo 6mo 1y 2y max"),
    limit:         int  = Query(500,   description="Max candles to return", ge=1, le=5000),
    use_cache:     bool = Query(True,  description="Use cached data if available"),
    force_refresh: bool = Query(False, description="Force fresh download"),
):
    """
    Returns OHLCV candles for a symbol at the requested interval.
    Results are cached; use force_refresh=true to bypass.
    """
    try:
        interval_enum = _parse_interval(interval)

        df = market_data_manager.get_or_download(
            symbol=symbol,
            interval=interval_enum,
            period=period,
            force_refresh=force_refresh,
        )

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        df = df.tail(limit)

        candles = []
        for _, row in df.iterrows():
            candles.append({
                "timestamp": str(row["timestamp"]),
                "open":      float(row["open"]),
                "high":      float(row["high"]),
                "low":       float(row["low"]),
                "close":     float(row["close"]),
                "volume":    float(row["volume"]),
                "symbol":    str(row["symbol"]),
                "interval":  str(row["interval"]),
            })

        cached = market_data_manager.get_cached_data(symbol, interval_enum) is not None

        return {
            "symbol":   symbol.upper(),
            "interval": interval,
            "count":    len(candles),
            "candles":  candles,
            "cached":   cached,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get candles: {str(e)}")


@router.get("/candles/{symbol}/latest")
def get_latest_candle(
    symbol:   str  = Path(..., description="Trading symbol"),
    interval: str  = Query("1d", description="Interval"),
):
    """Returns only the most recent candle for a symbol."""
    try:
        interval_enum = _parse_interval(interval)

        # Try in-memory cache first
        candle = market_data_manager.get_latest_candle(symbol, interval_enum)

        # If nothing cached, do a fresh download
        if candle is None:
            market_data_manager.get_or_download(symbol, interval_enum)
            candle = market_data_manager.get_latest_candle(symbol, interval_enum)

        if candle is None:
            raise HTTPException(
                status_code=404,
                detail=f"No candle data found for {symbol} @ {interval}",
            )

        return {
            "symbol":   symbol.upper(),
            "interval": interval,
            "candle":   candle.to_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get latest candle: {str(e)}")


@router.get("/cache/info")
def get_cache_info():
    """
    Returns cache statistics: connected status, local entries,
    Redis memory usage, total keys, fetch count, error count.
    """
    try:
        return redis_manager.get_cache_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/stats")
def get_validation_stats():
    """Returns data quality/validation statistics."""
    try:
        md_status = market_data_manager.get_market_status()
        stats = md_status.get("validation_stats", {
            "total_candles": 0,
            "valid_candles": 0,
            "invalid_candles": 0,
            "missing_candles_detected": 0,
            "duplicate_candles_detected": 0,
        })
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intervals")
def get_supported_intervals():
    """Returns the list of supported candle intervals."""
    return {
        "intervals": [i.value for i in Interval]
    }


@router.post("/candles")
def add_candle(request: CandleRequest):
    """
    Add a new candle (for live feed integration).
    Validates before adding to cache.
    """
    try:
        candle = request.to_candle()
        validation = market_data_manager.validate_candle(candle)

        if not validation.is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid candle: {validation.errors}",
            )

        added = market_data_manager.add_candle(candle.symbol, candle.interval, candle)

        return {
            "success":  added,
            "message":  "Candle added successfully" if added else "Duplicate or invalid candle",
            "warnings": validation.warnings,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add candle: {str(e)}")


@router.post("/cache/clear")
def clear_cache(request: CacheClearRequest):
    """
    Clears cached candle data.
    Pass symbol to clear one ticker, omit to clear all.
    """
    try:
        interval_enum = _parse_interval(request.interval) if request.interval else None
        market_data_manager.clear_cache(symbol=request.symbol, interval=interval_enum)

        redis_keys_cleared = 0
        if request.symbol:
            redis_keys_cleared = redis_manager.clear_symbol_cache(request.symbol)

        return {
            "success":           True,
            "message":           "Cache cleared",
            "redis_keys_cleared": redis_keys_cleared,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
