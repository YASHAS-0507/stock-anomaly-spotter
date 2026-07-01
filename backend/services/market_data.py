"""
market_data.py
--------------
Market Data Manager Service.

Responsibilities:
- Download historical OHLCV data from yfinance
- In-memory cache with TTL
- Candle validation
- Incremental candle updates
- Multi-interval support (1m, 5m, 15m, 30m, 1h, 1d)

Design: Thread-safe, no circular imports.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from threading import Lock

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class Interval(str, Enum):
    """Supported market data intervals."""
    MIN_1  = "1m"
    MIN_5  = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "1h"
    DAY_1  = "1d"

    @property
    def minutes(self) -> int:
        return {
            "1m": 1, "5m": 5, "15m": 15,
            "30m": 30, "1h": 60, "1d": 1440,
        }[self.value]

    @property
    def yfinance_interval(self) -> str:
        return {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "30m": "30m", "1h": "60m", "1d": "1d",
        }[self.value]

    @property
    def max_period(self) -> str:
        return {
            "1m": "7d", "5m": "60d", "15m": "60d",
            "30m": "60d", "1h": "730d", "1d": "max",
        }[self.value]


@dataclass
class Candle:
    """Normalized OHLCV candle."""
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
            "open":   self.open,
            "high":   self.high,
            "low":    self.low,
            "close":  self.close,
            "volume": self.volume,
            "symbol": self.symbol,
            "interval": self.interval.value,
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
            interval=Interval(data["interval"]),
        )


@dataclass
class ValidationResult:
    """Result of candle validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class MarketDataManager:
    """
    Central market data service.
    Thread-safe, no imports from redis_manager or market_status
    to avoid circular dependencies.
    """

    def __init__(
        self,
        default_symbol: str = "RELIANCE.NS",
        cache_ttl_seconds: int = 300,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ):
        self.default_symbol = default_symbol
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

        # {(symbol, interval): (DataFrame, last_updated_ts)}
        self._cache: Dict[Tuple[str, Interval], Tuple[pd.DataFrame, float]] = {}
        self._cache_lock = Lock()

        # Live feed subscribers
        self._subscribers: Dict[Interval, List] = {i: [] for i in Interval}
        self._subscriber_lock = Lock()

        # Validation stats
        self._validation_stats = {
            "total_candles": 0,
            "valid_candles": 0,
            "invalid_candles": 0,
            "missing_candles_detected": 0,
            "duplicate_candles_detected": 0,
        }

        # Feed status
        self._feed_status = "DISCONNECTED"
        self._last_latency_ms: int = 0
        self._last_candle_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    def fetch_real_data(
        self,
        symbol: str,
        interval: Interval,
        period: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Download historical data with retry logic."""
        import yfinance as yf

        period = period or interval.max_period

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Downloading {symbol} {interval.value} (attempt {attempt + 1})")
                ticker = yf.Ticker(symbol)

                if start and end:
                    df = ticker.history(
                        start=start.strftime("%Y-%m-%d"),
                        end=end.strftime("%Y-%m-%d"),
                        interval=interval.yfinance_interval,
                        auto_adjust=False,
                    )
                else:
                    df = ticker.history(
                        period=period,
                        interval=interval.yfinance_interval,
                        auto_adjust=False,
                    )

                if df.empty:
                    raise ValueError(f"No data returned for {symbol} {interval.value}")

                df = self._normalize_dataframe(df, symbol, interval)
                validation = self._validate_dataframe(df)

                if validation.errors:
                    raise ValueError(f"Validation failed: {validation.errors}")

                with self._cache_lock:
                    self._cache[(symbol, interval)] = (df, time.time())

                logger.info(f"Downloaded {len(df)} candles for {symbol} {interval.value}")
                return df

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_base_delay * (2 ** attempt))
                else:
                    logger.error(f"All retries exhausted for {symbol}")
                    raise

        raise RuntimeError("Should not reach here")

    # Alias so old call sites using download_historical still work
    def download_historical(
        self,
        symbol: str,
        interval: Interval,
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        return self.fetch_real_data(symbol, interval, period)

    def get_cached_data(
        self,
        symbol: str,
        interval: Interval,
        max_age_seconds: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """Return cached DataFrame if still fresh."""
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
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Return cached data or download fresh."""
        if not force_refresh:
            cached = self.get_cached_data(symbol, interval)
            if cached is not None:
                return cached
        return self.fetch_real_data(symbol, interval, period)

    # ------------------------------------------------------------------
    # Normalization & validation
    # ------------------------------------------------------------------

    def _normalize_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: Interval,
    ) -> pd.DataFrame:
        df = df.copy()

        if df.index.name in ("Date", "Datetime", None):
            df = df.reset_index()

        dt_col = next(
            (c for c in ("Datetime", "Date", "datetime", "timestamp") if c in df.columns),
            None,
        )
        if dt_col is None:
            raise ValueError("No datetime column found in data")

        df = df.rename(columns={
            dt_col:   "timestamp",
            "Open":   "open",
            "High":   "high",
            "Low":    "low",
            "Close":  "close",
            "Volume": "volume",
        })

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["symbol"]    = symbol
        df["interval"]  = interval.value

        cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol", "interval"]
        existing = [c for c in cols if c in df.columns]
        df = df[existing].sort_values("timestamp").reset_index(drop=True)
        df = df.drop_duplicates(subset=["timestamp"], keep="last")
        return df

    def _validate_dataframe(self, df: pd.DataFrame) -> ValidationResult:
        errors, warnings = [], []

        if df.empty:
            errors.append("DataFrame is empty")
            return ValidationResult(False, errors, warnings)

        required = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            errors.append(f"Missing columns: {missing}")
            return ValidationResult(False, errors, warnings)

        nan_cols = [c for c in required if df[c].isna().any()]
        if nan_cols:
            warnings.append(f"NaN values in: {nan_cols}")

        dup_count = int(df["timestamp"].duplicated().sum())
        if dup_count:
            warnings.append(f"{dup_count} duplicate timestamps")
            self._validation_stats["duplicate_candles_detected"] += dup_count

        if not df["timestamp"].is_monotonic_increasing:
            errors.append("Timestamps not in chronological order")

        self._validation_stats["total_candles"] += len(df)
        if not errors:
            self._validation_stats["valid_candles"] += len(df)
        else:
            self._validation_stats["invalid_candles"] += len(df)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_candle(self, candle: Candle) -> ValidationResult:
        errors, warnings = [], []

        for f in ("open", "high", "low", "close"):
            v = getattr(candle, f)
            if v <= 0:
                errors.append(f"{f} must be positive, got {v}")
            if np.isnan(v):
                errors.append(f"{f} is NaN")

        if candle.volume < 0:
            errors.append(f"volume must be non-negative, got {candle.volume}")

        if candle.high < candle.low:
            errors.append(f"high ({candle.high}) < low ({candle.low})")

        if candle.timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
            warnings.append("Candle timestamp is in the future")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_candle(self, candle: Candle) -> ValidationResult:
        return self._validate_candle(candle)

    # ------------------------------------------------------------------
    # Incremental updates
    # ------------------------------------------------------------------

    def add_candle(self, symbol: str, interval: Interval, candle: Candle) -> bool:
        validation = self._validate_candle(candle)
        if not validation.is_valid:
            logger.warning(f"Rejected invalid candle: {validation.errors}")
            return False

        with self._cache_lock:
            key = (symbol, interval)
            df, _ = self._cache.get(key, (pd.DataFrame(), 0))

            if not df.empty and candle.timestamp in df["timestamp"].values:
                self._validation_stats["duplicate_candles_detected"] += 1
                return False

            new_row = pd.DataFrame([candle.to_dict()])
            new_row["timestamp"] = pd.to_datetime(new_row["timestamp"], utc=True)
            df = pd.concat([df, new_row], ignore_index=True)
            df = df.sort_values("timestamp").reset_index(drop=True)
            self._cache[key] = (df, time.time())
            self._last_candle_time = candle.timestamp

        self._notify_subscribers(interval, candle)
        return True

    # ------------------------------------------------------------------
    # Latest candle
    # ------------------------------------------------------------------

    def get_latest_candle(self, symbol: str, interval: Interval) -> Optional[Candle]:
        with self._cache_lock:
            cached = self._cache.get((symbol, interval))
            if cached:
                df, _ = cached
                if not df.empty:
                    row = df.iloc[-1]
                    return Candle(
                        timestamp=row["timestamp"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        symbol=str(row["symbol"]),
                        interval=Interval(str(row["interval"])),
                    )
        return None

    # ------------------------------------------------------------------
    # Subscriptions (for future WebSocket / live feed)
    # ------------------------------------------------------------------

    def subscribe(self, interval: Interval, callback) -> None:
        with self._subscriber_lock:
            self._subscribers[interval].append(callback)

    def unsubscribe(self, interval: Interval, callback) -> None:
        with self._subscriber_lock:
            if callback in self._subscribers[interval]:
                self._subscribers[interval].remove(callback)

    def _notify_subscribers(self, interval: Interval, candle: Candle) -> None:
        with self._subscriber_lock:
            for cb in self._subscribers[interval]:
                try:
                    cb(candle)
                except Exception as e:
                    logger.error(f"Subscriber callback failed: {e}")

    # ------------------------------------------------------------------
    # Market status (used by market_status service)
    # ------------------------------------------------------------------

    def get_market_status(self) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        ist_offset = timedelta(hours=5, minutes=30)
        ist = now_utc + ist_offset

        is_weekday = ist.weekday() < 5
        market_open  = ist.replace(hour=9,  minute=15, second=0, microsecond=0)
        market_close = ist.replace(hour=15, minute=30, second=0, microsecond=0)

        if is_weekday and market_open <= ist <= market_close:
            market_status = "OPEN"
        elif is_weekday and ist < market_open:
            market_status = "PRE_OPEN"
        elif is_weekday:
            market_status = "CLOSED"
        else:
            market_status = "WEEKEND"

        total = self._validation_stats["total_candles"]
        valid = self._validation_stats["valid_candles"]
        data_quality = f"{(valid / total * 100):.1f}%" if total > 0 else "N/A"

        return {
            "exchange": "NSE",
            "market_status": market_status,
            "feed_status": self._feed_status,
            "latency_ms": self._last_latency_ms,
            "latest_candle": (
                self._last_candle_time.strftime("%H:%M:%S")
                if self._last_candle_time else "N/A"
            ),
            "data_quality": data_quality,
            "current_time_ist": ist.strftime("%Y-%m-%d %H:%M:%S"),
            "validation_stats": self._validation_stats.copy(),
        }

    def update_feed_status(self, status: str, latency_ms: int = 0) -> None:
        self._feed_status = status
        self._last_latency_ms = latency_ms

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def get_cached_df(self, symbol: str, interval: Interval) -> Optional[pd.DataFrame]:
        with self._cache_lock:
            cached = self._cache.get((symbol, interval))
            return cached[0].copy() if cached else None

    def clear_cache(
        self,
        symbol: Optional[str] = None,
        interval: Optional[Interval] = None,
    ) -> None:
        with self._cache_lock:
            if symbol and interval:
                self._cache.pop((symbol, interval), None)
            elif symbol:
                keys = [k for k in self._cache if k[0] == symbol]
                for k in keys:
                    self._cache.pop(k, None)
            else:
                self._cache.clear()


# Singleton
market_data_manager = MarketDataManager()
