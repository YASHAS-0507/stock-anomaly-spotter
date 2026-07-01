"""
market_status.py
----------------
Market Status Service.

Provides real-time NSE market status:
- Market phase (OPEN, PRE_OPEN, CLOSED, WEEKEND)
- Feed connection status and latency
- Latest candle timestamp
- Data quality metrics
- Current IST time (authoritative server time for frontend)

Import order is safe: market_data -> redis_manager -> market_status
No circular dependencies.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from services.market_data import market_data_manager, Interval
from services.redis_manager import redis_manager

logger = logging.getLogger(__name__)

# IST offset
_IST_OFFSET = timedelta(hours=5, minutes=30)

# NSE trading hours (IST)
_MARKET_OPEN_H  = 9
_MARKET_OPEN_M  = 15
_MARKET_CLOSE_H = 15
_MARKET_CLOSE_M = 30

# Cache TTL for status (seconds)
_STATUS_TTL = 30


def _ist_now() -> datetime:
    """Return current time in IST (naive datetime for display)."""
    return datetime.now(timezone.utc) + _IST_OFFSET


def _get_market_phase(now_ist: datetime) -> str:
    """Determine NSE market phase from IST datetime."""
    if now_ist.weekday() >= 5:
        return "WEEKEND"

    open_time     = now_ist.replace(hour=_MARKET_OPEN_H,  minute=_MARKET_OPEN_M,  second=0, microsecond=0)
    close_time    = now_ist.replace(hour=_MARKET_CLOSE_H, minute=_MARKET_CLOSE_M, second=0, microsecond=0)
    pre_open_time = open_time - timedelta(minutes=15)

    if pre_open_time <= now_ist < open_time:
        return "PRE_OPEN"
    elif open_time <= now_ist <= close_time:
        return "OPEN"
    else:
        return "CLOSED"


def _probe_latency(symbol: str = "^NSEI") -> Optional[float]:
    """Measure yfinance round-trip latency in ms."""
    try:
        import yfinance as yf
        start = time.perf_counter()
        yf.Ticker(symbol).history(period="1d", interval="1d")
        return round((time.perf_counter() - start) * 1000, 1)
    except Exception:
        return None


def _latest_candle_date(symbol: str = "^NSEI") -> Optional[str]:
    """Return the date string of the most recent daily candle."""
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True)
        if df is not None and not df.empty:
            return str(df.index[-1].date())
    except Exception:
        pass
    return None


class MarketStatusService:
    """
    Provides comprehensive market status with caching.
    Uses redis_manager for caching and market_data_manager
    for validation stats and feed status.
    """

    def __init__(self):
        self._feed_status = "DISCONNECTED"
        self._last_latency_ms: int = 0
        self._feed_reconnect_attempts = 0
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        """Subscribe to market data updates for all intervals."""
        try:
            for interval in Interval:
                market_data_manager.subscribe(interval, self._on_new_candle)
        except Exception as e:
            logger.warning(f"[market_status] Could not subscribe to market data: {e}")

    def _on_new_candle(self, candle) -> None:
        """Called when a new candle arrives — update feed status."""
        self._feed_status = "CONNECTED"

    def update_feed_status(self, status: str, latency_ms: int = 0) -> None:
        """Manually update feed connection status."""
        self._feed_status = status
        self._last_latency_ms = latency_ms
        if status == "CONNECTED":
            self._feed_reconnect_attempts = 0
        elif status == "RECONNECTING":
            self._feed_reconnect_attempts += 1
        market_data_manager.update_feed_status(status, latency_ms)

    def get_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Return full market status dict.
        Cached for _STATUS_TTL seconds unless force_refresh=True.
        """
        if not force_refresh:
            cached = redis_manager.get_market_status_cached()
            if cached is not None:
                return cached

        now_ist = _ist_now()
        market_phase = _get_market_phase(now_ist)

        # Probe live latency and latest candle from yfinance
        latency = _probe_latency()
        latest_candle = _latest_candle_date()

        # Derive feed status from latency probe
        feed_status = "LIVE" if latency is not None else "DELAYED"

        # Pull validation stats from market_data_manager
        md_status = market_data_manager.get_market_status()
        validation_stats = md_status.get("validation_stats", {
            "total_candles": 0,
            "valid_candles": 0,
            "invalid_candles": 0,
            "missing_candles_detected": 0,
            "duplicate_candles_detected": 0,
        })

        status = {
            "exchange":         "NSE",
            "market_status":    market_phase,
            "feed_status":      feed_status,
            "latency_ms":       latency if latency is not None else "Unavailable",
            "current_time_ist": now_ist.strftime("%H:%M:%S IST"),
            "current_date_ist": now_ist.strftime("%Y-%m-%d"),
            "latest_candle":    latest_candle if latest_candle else "Unavailable",
            "data_quality":     "LIVE" if latency is not None else "UNAVAILABLE",
            "validation_stats": validation_stats,
        }

        redis_manager.cache_market_status(status)
        return status

    # Alias for router compatibility
    def get_status_dict(self) -> Dict[str, Any]:
        return self.get_status()


# Singleton
market_status_service = MarketStatusService()
