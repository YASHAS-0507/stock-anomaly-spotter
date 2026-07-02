"""
market.py
---------
Market Data API Router.

Endpoints:
- GET /api/market/status - Market and feed status
- GET /api/market/candles/{symbol} - Get historical candles
- GET /api/market/candles/{symbol}/latest - Get latest candle
- POST /api/market/candles - Add new candle (for live feed)
- GET /api/market/validation/stats - Data validation statistics
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from services.market_data import market_data_manager, Interval, Candle, ValidationResult
from services.redis_manager import redis_manager
from services.market_status import market_status_service

router = APIRouter(prefix="/api/market", tags=["market"])


# ============================================================
# PYDANTIC MODELS
# ============================================================

class CandleRequest(BaseModel):
    """Request model for adding a candle."""
    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)
    symbol: str
    interval: str
    
    def to_candle(self) -> Candle:
        return Candle(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            symbol=self.symbol,
            interval=Interval(self.interval)
        )


class CandleResponse(BaseModel):
    """Response model for candle data."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    interval: str


class MarketStatusResponse(BaseModel):
    """Market status response model."""
    exchange: str
    market_status: str
    feed_status: str
    latency_ms: int
    latest_candle: str
    data_quality: str
    current_time_ist: str
    validation_stats: Dict[str, int]


class ValidationStatsResponse(BaseModel):
    """Validation statistics response."""
    total_candles: int
    valid_candles: int
    invalid_candles: int
    missing_candles_detected: int
    duplicate_candles_detected: int


class HistoricalDataResponse(BaseModel):
    """Historical data response."""
    symbol: str
    interval: str
    count: int
    candles: List[CandleResponse]
    cached: bool


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/status", response_model=MarketStatusResponse)
async def get_market_status():
    """
    Get current market and feed status.
    
    Returns:
    {
        "exchange": "NSE",
        "market_status": "OPEN",
        "feed_status": "CONNECTED",
        "latency_ms": 31,
        "latest_candle": "09:42:00",
        "data_quality": "100%",
        "current_time_ist": "2025-06-28 09:42:15",
        "validation_stats": {...}
    }
    """
    try:
        status = market_status_service.get_status_dict()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get market status: {str(e)}")


@router.get("/candles/{symbol}", response_model=HistoricalDataResponse)
async def get_historical_candles(
    symbol: str = Path(..., description="Trading symbol (e.g., RELIANCE.NS)"),
    interval: str = Query("1d", description="Interval (1m, 5m, 15m, 30m, 1h, 1d)"),
    period: str = Query("1mo", description="Period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, max)"),
    limit: int = Query(500, description="Maximum candles to return", ge=1, le=5000),
    use_cache: bool = Query(True, description="Use cached data if available")
):
    """
    Get historical candles for a symbol.
    
    Supports all intervals: 1m, 5m, 15m, 30m, 1h, 1d
    """
    try:
        # Parse interval
        try:
            interval_enum = Interval(interval)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid interval. Supported: {[i.value for i in Interval]}"
            )
        
        # Get data (from cache or download)
        if use_cache:
            df = market_data_manager.get_or_download(symbol, interval_enum, period)
        else:
            df = market_data_manager.download_historical(symbol, interval_enum, period)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        
        # Limit results
        df = df.tail(limit)
        
        # Convert to response format
        candles = []
        for _, row in df.iterrows():
            candles.append(CandleResponse(
                timestamp=row["timestamp"].isoformat(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                symbol=row["symbol"],
                interval=row["interval"]
            ))
        
        # Check if from cache
        cached = market_data_manager.get_cached_data(symbol, interval_enum) is not None
        
        return HistoricalDataResponse(
            symbol=symbol,
            interval=interval,
            count=len(candles),
            candles=candles,
            cached=cached
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get candles: {str(e)}")


@router.get("/candles/{symbol}/latest", response_model=CandleResponse)
async def get_latest_candle(
    symbol: str = Path(..., description="Trading symbol"),
    interval: str = Query("1d", description="Interval"),
    use_redis: bool = Query(True, description="Try Redis cache first")
):
    """Get the latest candle for a symbol and interval."""
    try:
        try:
            interval_enum = Interval(interval)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid interval. Supported: {[i.value for i in Interval]}"
            )
        
        # Try Redis first
        candle = None
        if use_redis:
            candle = redis_manager.get_latest_candle(symbol, interval_enum)
        
        # Fallback to market data manager
        if not candle:
            candle = market_data_manager.get_latest_candle(symbol, interval_enum)
        
        if not candle:
            raise HTTPException(status_code=404, detail=f"No latest candle found for {symbol} {interval}")
        
        return CandleResponse(
            timestamp=candle.timestamp.isoformat(),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            symbol=candle.symbol,
            interval=candle.interval.value
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get latest candle: {str(e)}")


@router.post("/candles", response_model=Dict[str, Any])
async def add_candle(candle_request: CandleRequest):
    """
    Add a new candle (for live feed integration).
    
    Validates the candle before adding to cache.
    """
    try:
        candle = candle_request.to_candle()
        
        # Validate
        validation = market_data_manager.validate_candle(candle)
        if not validation.is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid candle: {validation.errors}")
        
        # Add to market data manager
        added = market_data_manager.add_candle(candle.symbol, candle.interval, candle)
        
        if not added:
            return {"success": False, "message": "Candle not added (duplicate or invalid)"}
        
        # Also cache in Redis
        redis_manager.cache_latest_candle(candle.symbol, candle.interval, candle)
        
        # Publish to Redis Pub/Sub for live subscribers
        redis_manager.publish_candle(candle.interval, candle)
        
        return {
            "success": True,
            "message": "Candle added successfully",
            "candle": candle.to_dict(),
            "warnings": validation.warnings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add candle: {str(e)}")


@router.get("/validation/stats", response_model=ValidationStatsResponse)
async def get_validation_stats():
    """Get data validation statistics."""
    try:
        stats = market_data_manager.get_market_status().get("validation_stats", {})
        
        return ValidationStatsResponse(
            total_candles=stats.get("total_candles", 0),
            valid_candles=stats.get("valid_candles", 0),
            invalid_candles=stats.get("invalid_candles", 0),
            missing_candles_detected=stats.get("missing_candles_detected", 0),
            duplicate_candles_detected=stats.get("duplicate_candles_detected", 0)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get validation stats: {str(e)}")


@router.get("/cache/info")
async def get_cache_info():
    """Get Redis cache information."""
    try:
        info = redis_manager.get_cache_info()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache info: {str(e)}")


@router.post("/cache/clear")
async def clear_cache(
    symbol: Optional[str] = Query(None, description="Symbol to clear (optional)"),
    interval: Optional[str] = Query(None, description="Interval to clear (optional)")
):
    """Clear cache for a symbol/interval or all."""
    try:
        interval_enum = None
        if interval:
            try:
                interval_enum = Interval(interval)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid interval")
        
        if symbol:
            market_data_manager.clear_cache(symbol, interval_enum)
            cleared = redis_manager.clear_symbol_cache(symbol)
        else:
            market_data_manager.clear_cache()
            cleared = 0
        
        return {
            "success": True,
            "message": "Cache cleared",
            "redis_keys_cleared": cleared
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/intervals")
async def get_supported_intervals():
    """Get list of supported intervals."""
    return {
        "intervals": [
            {"value": i.value, "label": f"{i.minutes} minute" if i.minutes < 60 else f"{i.minutes//60} hour" if i.minutes < 1440 else "1 day"}
            for i in Interval
        ]
    }


# Export for inclusion in main app
def get_market_router():
    return router