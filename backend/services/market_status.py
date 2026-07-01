"""
market_status.py
----------------
Market Status Service.

Provides real-time market status information including:
- Exchange status (NSE)
- Market hours (OPEN, PRE_OPEN, CLOSED, WEEKEND)
- Feed connection status
- Latency metrics
- Latest candle timestamp
- Data quality metrics
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

from services.market_data import market_data_manager, Interval
from services.redis_manager import redis_manager

logger = logging.getLogger(__name__)


@dataclass
class MarketStatus:
    """Market status data structure."""
    exchange: str = "NSE"
    market_status: str = "UNKNOWN"      # OPEN, PRE_OPEN, CLOSED, WEEKEND
    feed_status: str = "DISCONNECTED"   # CONNECTED, DISCONNECTED, RECONNECTING
    latency_ms: int = 0
    latest_candle: str = "N/A"          # HH:MM:SS format
    data_quality: str = "N/A"           # Percentage
    current_time_ist: str = ""
    validation_stats: Dict[str, int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MarketStatusService:
    """
    Service for tracking and reporting market status.
    
    Integrates with:
    - MarketDataManager for validation stats and latest candles
    - RedisManager for feed status and latency
    """
    
    def __init__(
        self,
        exchange: str = "NSE",
        market_open_hour: int = 9,
        market_open_minute: int = 15,
        market_close_hour: int = 15,
        market_close_minute: int = 30,
        timezone_offset_hours: int = 5,
        timezone_offset_minutes: int = 30
    ):
        self.exchange = exchange
        self.market_open = (market_open_hour, market_open_minute)
        self.market_close = (market_close_hour, market_close_minute)
        self.tz_offset = timedelta(hours=timezone_offset_hours, minutes=timezone_offset_minutes)
        self.tz = timezone(self.tz_offset)
        
        # Feed status tracking
        self._feed_status = "DISCONNECTED"
        self._last_latency_ms = 0
        self._last_feed_update = 0
        self._feed_reconnect_attempts = 0
        
        # Subscribe to market data manager updates
        self._setup_subscriptions()
    
    def _setup_subscriptions(self) -> None:
        """Subscribe to market data updates."""
        try:
            # Subscribe to all intervals for latest candle tracking
            for interval in Interval:
                market_data_manager.subscribe(interval, self._on_new_candle)
        except Exception as e:
            logger.warning(f"Could not subscribe to market data updates: {e}")
    
    def _on_new_candle(self, candle) -> None:
        """Callback when new candle arrives."""
        # Update latest candle time
        pass  # market_data_manager handles this internally
    
    def update_feed_status(self, status: str, latency_ms: int = 0) -> None:
        """Update feed connection status."""
        self._feed_status = status
        self._last_latency_ms = latency_ms
        self._last_feed_update = time.time()
        
        if status == "CONNECTED":
            self._feed_reconnect_attempts = 0
        elif status == "RECONNECTING":
            self._feed_reconnect_attempts += 1
        
        # Also update in market data manager
        market_data_manager.update_feed_status(status, latency_ms)
        
        # Cache in Redis
        redis_manager.cache_market_status(self.get_status().to_dict())
    
    def get_market_phase(self) -> str:
        """
        Determine current market phase based on IST time.
        
        Returns:
            One of: OPEN, PRE_OPEN, CLOSED, WEEKEND
        """
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(self.tz)
        
        # Weekend check (Saturday=5, Sunday=6)
        if now_ist.weekday() >= 5:
            return "WEEKEND"
        
        # Market hours
        open_time = now_ist.replace(hour=self.market_open[0], minute=self.market_open[1], second=0, microsecond=0)
        close_time = now_ist.replace(hour=self.market_close[0], minute=self.market_close[1], second=0, microsecond=0)
        pre_open_time = open_time - timedelta(minutes=15)  # Pre-open starts 15 min before
        
        if pre_open_time <= now_ist < open_time:
            return "PRE_OPEN"
        elif open_time <= now_ist <= close_time:
            return "OPEN"
        elif now_ist < pre_open_time:
            return "CLOSED"  # Before pre-open
        else:
            return "CLOSED"  # After market close
    
    def get_status(self) -> MarketStatus:
        """Get comprehensive market status."""
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(self.tz)
        
        # Get market phase
        market_phase = self.get_market_phase()
        
        # Get data from market data manager
        md_status = market_data_manager.get_market_status()
        
        # Get latest candle from any interval (prefer 1m if available)
        latest_candle = "N/A"
        for interval in [Interval.MIN_1, Interval.MIN_5, Interval.MIN_15, Interval.HOUR_1, Interval.DAY_1]:
            candle = market_data_manager.get_latest_candle(market_data_manager.default_symbol, interval)
            if candle:
                latest_candle = candle.timestamp.strftime("%H:%M:%S")
                break
        
        # Build status
        status = MarketStatus(
            exchange=self.exchange,
            market_status=market_phase,
            feed_status=self._feed_status,
            latency_ms=self._last_latency_ms,
            latest_candle=latest_candle,
            data_quality=md_status.get("data_quality", "N/A"),
            current_time_ist=now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            validation_stats=md_status.get("validation_stats", {})
        )
        
        return status
    
    def get_status_dict(self) -> Dict[str, Any]:
        """Get status as dictionary."""
        return self.get_status().to_dict()
    
    def start_feed_monitoring(self, check_interval_seconds: int = 30) -> None:
        """Start background feed monitoring (placeholder for future WebSocket integration)."""
        # This would typically start a background thread that:
        # 1. Checks WebSocket connection health
        # 2. Measures latency
        # 3. Attempts reconnection on failure
        pass
    
    def simulate_feed_connected(self, latency_ms: int = 31) -> None:
        """Simulate feed connection (for testing)."""
        self.update_feed_status("CONNECTED", latency_ms)
    
    def simulate_feed_disconnected(self) -> None:
        """Simulate feed disconnection."""
        self.update_feed_status("DISCONNECTED", 0)


# Singleton instance
market_status_service = MarketStatusService()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    service = MarketStatusService()
    
    # Test market status
    status = service.get_status()
    print(f"Market Status: {status.to_dict()}")
    
    # Simulate feed
    service.simulate_feed_connected(31)
    status = service.get_status()
    print(f"With feed: {status.to_dict()}")