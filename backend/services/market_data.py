"""
market_data.py
--------------
Market Data Manager Service.

Responsibilities:
- Download historical data from yfinance
- Manage live market feeds (WebSocket-ready architecture)
- Validate incoming candles
- Detect missing candles
- Handle retries with exponential backoff
- Normalize timestamps to UTC
- Support multiple intervals (1m, 5m, 15m, 30m, 1h, 1d)

Design: Thread-safe, async-compatible, production-ready.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from threading import Lock

import pandas as pd
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)


class Interval(Enum):
    """Supported market data intervals."""
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "1h"
    DAY_1 = "1d"

    @property
    def minutes(self) -> int:
        mapping = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "1d": 1440
        }
        return mapping[self.value]

    @property
    def yfinance_interval(self) -> str:
        """yfinance-compatible interval string."""
        mapping = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "60m", "1d": "1d"
        }
        return mapping[self.value]

    @property
    def max_period(self) -> str:
        """Maximum period yfinance allows for this interval."""
        mapping = {
            "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
            "1h": "730d", "1d": "max"
        }
        return mapping[self.value]


@dataclass
class Candle:
    """Normalized candle data structure."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    interval: Interval

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "interval": self.interval.value
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Candle":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            symbol=data["symbol"],
            interval=Interval(data["interval"])
        )


@dataclass
class ValidationResult:
    """Result of candle validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class MarketDataManager:
    """
    Central market data management service.
    
    Features:
    - Historical data download with retry logic
    - In-memory candle cache with Redis-ready interface
    - Incremental feature updates
    - Comprehensive data validation
    - Multi-interval support
    """
    
    def __init__(
        self,
        default_symbol: str = "RELIANCE.NS",
        cache_ttl_seconds: int = 300,
        max_retries: int = 3,
        retry_base_delay: float = 1.0
    ):
        self.default_symbol = default_symbol
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        
        # In-memory cache: {(symbol, interval): (DataFrame, last_updated)}
        self._cache: Dict[Tuple[str, Interval], Tuple[pd.DataFrame, float]] = {}
        self._cache_lock = Lock()
        
        # Live feed subscribers: {interval: [callback]}
        self._subscribers: Dict[Interval, List[callable]] = {i: [] for i in Interval}
        self._subscriber_lock = Lock()
        
        # Validation stats
        self._validation_stats = {
            "total_candles": 0,
            "valid_candles": 0,
            "invalid_candles": 0,
            "missing_candles_detected": 0,
            "duplicate_candles_detected": 0
        }
        
        # Feed status
        self._feed_status = "DISCONNECTED"
        self._last_latency_ms = 0
        self._last_candle_time: Optional[datetime] = None
    
    # ============================================================
    # HISTORICAL DATA
    # ============================================================
    
    def fetch_real_data(
        self,
        symbol: str,
        interval: Interval,
        period: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Download historical data with retry logic and validation.
        
        Args:
            symbol: Trading symbol (e.g., "RELIANCE.NS")
            interval: Data interval
            period: yfinance period string (e.g., "1y", "6mo") - used if start/end not provided
            start: Start datetime (alternative to period)
            end: End datetime (alternative to period)
            
        Returns:
            Validated DataFrame with OHLCV data
        """
        period = period or interval.max_period
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Downloading {symbol} {interval.value} data (attempt {attempt + 1})")
                ticker = yf.Ticker(symbol)
                
                if start and end:
                    df = ticker.history(
                        start=start.strftime("%Y-%m-%d"),
                        end=end.strftime("%Y-%m-%d"),
                        interval=interval.yfinance_interval,
                        auto_adjust=False
                    )
                else:
                    df = ticker.history(
                        period=period,
                        interval=interval.yfinance_interval,
                        auto_adjust=False
                    )
                
                if df.empty:
                    raise ValueError(f"No data returned for {symbol} {interval.value}")
                
                # Normalize and validate
                df = self._normalize_dataframe(df, symbol, interval)
                validation = self._validate_dataframe(df)
                
                if not validation.is_valid:
                    logger.warning(f"Validation warnings for {symbol}: {validation.warnings}")
                    if validation.errors:
                        raise ValueError(f"Validation failed: {validation.errors}")
                
                # Update cache
                with self._cache_lock:
                    self._cache[(symbol, interval)] = (df, time.time())
                
                logger.info(f"Successfully downloaded {len(df)} candles for {symbol} {interval.value}")
                return df
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < self.max_retries - 1:
                    delay = self.retry_base_delay * (2 ** attempt)
                    time.sleep(delay)
                else:
                    logger.error(f"All retries exhausted for {symbol}")
                    raise
        
        raise RuntimeError("Should not reach here")
    
    def get_cached_data(
        self,
        symbol: str,
        interval: Interval,
        max_age_seconds: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """Get cached data if fresh enough."""
        max_age = max_age_seconds or self.cache_ttl_seconds
        
        with self._cache_lock:
            cached = self._cache.get((symbol, interval))
            if cached:
                df, cached_time = cached
                if time.time() - cached_time < max_age:
                    return df.copy()
        return None
    
    def get_or_download(
        self,
        symbol: str,
        interval: Interval,
        period: Optional[str] = None,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """Get cached data or download fresh."""
        if not force_refresh:
            cached = self.get_cached_data(symbol, interval)
            if cached is not None:
                return cached
        return self.fetch_real_data(symbol, interval, period)
    
    # ============================================================
    # DATA NORMALIZATION & VALIDATION
    # ============================================================
    
    def _normalize_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: Interval
    ) -> pd.DataFrame:
        """
        Normalize yfinance DataFrame to standard format.
        
        - Ensures UTC timestamps
        - Standardizes column names
        - Adds symbol and interval metadata
        - Sorts by timestamp
        """
        df = df.copy()
        
        # Reset index to get datetime as column
        if df.index.name in ("Date", "Datetime", None):
            df = df.reset_index()
        
        # Find datetime column
        dt_col = None
        for col in ["Datetime", "Date", "datetime", "timestamp"]:
            if col in df.columns:
                dt_col = col
                break
        
        if dt_col is None:
            raise ValueError("No datetime column found in data")
        
        # Standardize columns
        df = df.rename(columns={
            dt_col: "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        
        # Ensure timestamp is timezone-aware UTC
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        
        # Add metadata
        df["symbol"] = symbol
        df["interval"] = interval.value
        
        # Select and order columns
        cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol", "interval"]
        df = df[cols]
        
        # Sort by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        # Remove duplicates (keep last)
        df = df.drop_duplicates(subset=["timestamp"], keep="last")
        
        return df
    
    def _validate_candle(self, candle: Candle) -> ValidationResult:
        """Validate a single candle."""
        errors = []
        warnings = []
        
        # Negative prices
        for price_field in ["open", "high", "low", "close"]:
            value = getattr(candle, price_field)
            if value <= 0:
                errors.append(f"{price_field} must be positive, got {value}")
        
        # Volume
        if candle.volume < 0:
            errors.append(f"volume must be non-negative, got {candle.volume}")
        
        # OHLC relationship
        if candle.high < candle.low:
            errors.append(f"high ({candle.high}) < low ({candle.low})")
        if candle.open > candle.high or candle.open < candle.low:
            errors.append(f"open ({candle.open}) outside high-low range")
        if candle.close > candle.high or candle.close < candle.low:
            errors.append(f"close ({candle.close}) outside high-low range")
        
        # NaN check
        for field in ["open", "high", "low", "close", "volume"]:
            if np.isnan(getattr(candle, field)):
                errors.append(f"{field} is NaN")
        
        # Future timestamp
        if candle.timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
            warnings.append("Candle timestamp is in the future")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _validate_dataframe(self, df: pd.DataFrame) -> ValidationResult:
        """Validate entire DataFrame."""
        errors = []
        warnings = []
        
        if df.empty:
            errors.append("DataFrame is empty")
            return ValidationResult(False, errors, warnings)
        
        # Check required columns
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            errors.append(f"Missing columns: {missing}")
        
        # NaN check
        nan_cols = df[required].columns[df[required].isna().any()].tolist()
        if nan_cols:
            errors.append(f"NaN values in columns: {nan_cols}")
        
        # Duplicate timestamps
        dup_count = df["timestamp"].duplicated().sum()
        if dup_count > 0:
            warnings.append(f"Found {dup_count} duplicate timestamps")
            self._validation_stats["duplicate_candles_detected"] += dup_count
        
        # Missing candles (gaps in time series)
        if len(df) > 1:
            # Infer interval from data
            dt_diff = df["timestamp"].diff().dropna()
            if len(dt_diff) > 0:
                median_diff = dt_diff.median()
                expected_diff = pd.Timedelta(minutes=Interval(df["interval"].iloc[0]).minutes)
                
                # Find gaps larger than 2x expected interval
                gaps = dt_diff[dt_diff > expected_diff * 2]
                if len(gaps) > 0:
                    warnings.append(f"Found {len(gaps)} potential missing candles (gaps > 2x interval)")
                    self._validation_stats["missing_candles_detected"] += len(gaps)
        
        # Out of order timestamps
        if not df["timestamp"].is_monotonic_increasing:
            errors.append("Timestamps are not in chronological order")
        
        # Update stats
        self._validation_stats["total_candles"] += len(df)
        if len(errors) == 0:
            self._validation_stats["valid_candles"] += len(df)
        else:
            self._validation_stats["invalid_candles"] += len(df)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def validate_candle(self, candle: Candle) -> ValidationResult:
        """Public method to validate a single candle."""
        return self._validate_candle(candle)
    
    # ============================================================
    # INCREMENTAL UPDATES
    # ============================================================
    
    def add_candle(self, symbol: str, interval: Interval, candle: Candle) -> bool:
        """
        Add a new candle to cache incrementally.
        
        Returns True if added, False if duplicate or invalid.
        """
        validation = self._validate_candle(candle)
        if not validation.is_valid:
            logger.warning(f"Rejected invalid candle for {symbol}: {validation.errors}")
            return False
        
        with self._cache_lock:
            key = (symbol, interval)
            df, _ = self._cache.get(key, (pd.DataFrame(), 0))
            
            # Check for duplicate timestamp
            if not df.empty and candle.timestamp in df["timestamp"].values:
                logger.debug(f"Duplicate candle for {symbol} at {candle.timestamp}")
                self._validation_stats["duplicate_candles_detected"] += 1
                return False
            
            # Append new candle
            new_row = pd.DataFrame([candle.to_dict()])
            new_row["timestamp"] = pd.to_datetime(new_row["timestamp"], utc=True)
            
            df = pd.concat([df, new_row], ignore_index=True)
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            self._cache[key] = (df, time.time())
            self._last_candle_time = candle.timestamp
            
            # Notify subscribers
            self._notify_subscribers(interval, candle)
            
            return True
    
    def add_candles_batch(
        self,
        symbol: str,
        interval: Interval,
        candles: List[Candle]
    ) -> int:
        """Add multiple candles efficiently."""
        added = 0
        for candle in candles:
            if self.add_candle(symbol, interval, candle):
                added += 1
        return added
    
    def get_latest_candle(
        self,
        symbol: str,
        interval: Interval
    ) -> Optional[Candle]:
        """Get the most recent candle."""
        with self._cache_lock:
            cached = self._cache.get((symbol, interval))
            if cached:
                df, _ = cached
                if not df.empty:
                    row = df.iloc[-1]
                    return Candle(
                        timestamp=row["timestamp"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        symbol=row["symbol"],
                        interval=Interval(row["interval"])
                    )
        return None
    
    # ============================================================
    # LIVE FEED SUBSCRIPTIONS
    # ============================================================
    
    def subscribe(self, interval: Interval, callback: callable) -> None:
        """Subscribe to live candle updates for an interval."""
        with self._subscriber_lock:
            self._subscribers[interval].append(callback)
    
    def unsubscribe(self, interval: Interval, callback: callable) -> None:
        """Unsubscribe from live updates."""
        with self._subscriber_lock:
            if callback in self._subscribers[interval]:
                self._subscribers[interval].remove(callback)
    
    def _notify_subscribers(self, interval: Interval, candle: Candle) -> None:
        """Notify all subscribers of new candle."""
        with self._subscriber_lock:
            for callback in self._subscribers[interval]:
                try:
                    callback(candle)
                except Exception as e:
                    logger.error(f"Subscriber callback failed: {e}")
    
    # ============================================================
    # MARKET STATUS
    # ============================================================
    
    def get_market_status(self) -> Dict[str, Any]:
        """Get current market and feed status."""
        now = datetime.now(timezone.utc)
        ist = now.astimezone(timezone(timedelta(hours=5, minutes=30)))
        
        # Determine NSE market status (9:15 AM - 3:30 PM IST, Mon-Fri)
        is_weekday = ist.weekday() < 5
        market_open = ist.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = ist.replace(hour=15, minute=30, second=0, microsecond=0)
        
        if is_weekday and market_open <= ist <= market_close:
            market_status = "OPEN"
        elif is_weekday and ist < market_open:
            market_status = "PRE_OPEN"
        elif is_weekday and ist > market_close:
            market_status = "CLOSED"
        else:
            market_status = "WEEKEND"
        
        # Data quality based on validation stats
        total = self._validation_stats["total_candles"]
        valid = self._validation_stats["valid_candles"]
        data_quality = f"{(valid / total * 100):.1f}%" if total > 0 else "N/A"
        
        return {
            "exchange": "NSE",
            "market_status": market_status,
            "feed_status": self._feed_status,
            "latency_ms": self._last_latency_ms,
            "latest_candle": self._last_candle_time.strftime("%H:%M:%S") if self._last_candle_time else "N/A",
            "data_quality": data_quality,
            "current_time_ist": ist.strftime("%Y-%m-%d %H:%M:%S"),
            "validation_stats": self._validation_stats.copy()
        }
    
    def update_feed_status(self, status: str, latency_ms: int = 0) -> None:
        """Update feed connection status."""
        self._feed_status = status
        self._last_latency_ms = latency_ms
    
    # ============================================================
    # UTILITY
    # ============================================================
    
    def get_cached_df(self, symbol: str, interval: Interval) -> Optional[pd.DataFrame]:
        """Get cached DataFrame (for feature pipeline)."""
        with self._cache_lock:
            cached = self._cache.get((symbol, interval))
            if cached:
                return cached[0].copy()
        return None
    
    def clear_cache(self, symbol: Optional[str] = None, interval: Optional[Interval] = None) -> None:
        """Clear cache for specific symbol/interval or all."""
        with self._cache_lock:
            if symbol and interval:
                self._cache.pop((symbol, interval), None)
            elif symbol:
                keys_to_remove = [k for k in self._cache if k[0] == symbol]
                for k in keys_to_remove:
                    self._cache.pop(k, None)
            else:
                self._cache.clear()


# Singleton instance
market_data_manager = MarketDataManager()


if __name__ == "__main__":
    # Test the service
    logging.basicConfig(level=logging.INFO)
    
    manager = MarketDataManager()
    
    # Test download
    df = manager.fetch_real_data("RELIANCE.NS", Interval.DAY_1, "1mo")
    print(f"Downloaded {len(df)} daily candles")
    print(df.head())
    
    # Test validation
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=2500.0,
        high=2550.0,
        low=2490000.0,
        close=2450.0,
        volume=1000000,
        symbol="RELIANCE.NS",
        interval=Interval.DAY_1
    )
    result = manager.validate_candle(candle)
    print(f"Validation: {result.is_valid}, errors: {result.errors}")
    
    # Test market status
    status = manager.get_market_status()
    print(f"Market Status: {status}")