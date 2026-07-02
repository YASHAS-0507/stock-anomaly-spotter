"""
redis_manager.py
----------------
Redis Cache Layer for Market Data.

Features:
- Historical data cached in memory (with Redis persistence)
- Latest candles updated incrementally
- Pub/Sub for live feed distribution
- TTL-based expiration
- Connection pooling and retry logic
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from threading import Lock

import redis
import pandas as pd

from services.market_data import Interval, Candle, market_data_manager

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Redis connection configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 10
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    decode_responses: bool = True
    
    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class RedisManager:
    """
    Redis cache manager for market data.
    
    Caches:
    - Historical DataFrames (key: market:{symbol}:{interval}:history)
    - Latest candles (key: market:{symbol}:{interval}:latest)
    - Validation stats (key: market:validation:stats)
    - Market status (key: market:status)
    
    Pub/Sub channels:
    - market:candles:{interval} - New candle notifications
    - market:status - Status updates
    """
    
    # Key prefixes
    HISTORY_PREFIX = "market:history"
    LATEST_PREFIX = "market:latest"
    STATS_KEY = "market:validation:stats"
    STATUS_KEY = "market:status"
    
    # Default TTLs (seconds)
    HISTORY_TTL = 3600      # 1 hour for historical data
    LATEST_TTL = 300        # 5 minutes for latest candle
    STATUS_TTL = 60         # 1 minute for status
    
    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or RedisConfig()
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._connected = False
        self._lock = Lock()
        
        # Local fallback cache (when Redis unavailable)
        self._local_cache: Dict[str, Tuple[Any, float]] = {}
    
    # ============================================================
    # CONNECTION MANAGEMENT
    # ============================================================
    
    def connect(self) -> bool:
        """Establish Redis connection with retry logic."""
        with self._lock:
            if self._connected and self._client:
                try:
                    self._client.ping()
                    return True
                except Exception:
                    self._connected = False
            
            try:
                self._pool = redis.ConnectionPool.from_url(
                    self.config.url,
                    max_connections=self.config.max_connections,
                    socket_timeout=self.config.socket_timeout,
                    socket_connect_timeout=self.config.socket_connect_timeout,
                    decode_responses=self.config.decode_responses
                )
                self._client = redis.Redis(connection_pool=self._pool)
                
                # Test connection
                self._client.ping()
                self._connected = True
                logger.info("Redis connection established")
                return True
                
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using local cache fallback.")
                self._connected = False
                self._client = None
                self._pool = None
                return False
    
    def disconnect(self) -> None:
        """Close Redis connection."""
        with self._lock:
            if self._pubsub:
                self._pubsub.close()
                self._pubsub = None
            if self._client:
                self._client.close()
                self._client = None
            if self._pool:
                self._pool.disconnect()
                self._pool = None
            self._connected = False
            logger.info("Redis connection closed")
    
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        if not self._connected or not self._client:
            return False
        try:
            self._client.ping()
            return True
        except Exception:
            self._connected = False
            return False
    
    # ============================================================
    # KEY HELPERS
    # ============================================================
    
    def _history_key(self, symbol: str, interval: Interval) -> str:
        return f"{self.HISTORY_PREFIX}:{symbol}:{interval.value}"
    
    def _latest_key(self, symbol: str, interval: Interval) -> str:
        return f"{self.LATEST_PREFIX}:{symbol}:{interval.value}"
    
    # ============================================================
    # HISTORICAL DATA CACHING
    # ============================================================
    
    def cache_history(
        self,
        symbol: str,
        interval: Interval,
        df: pd.DataFrame,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache historical DataFrame."""
        if df.empty:
            return False
        
        key = self._history_key(symbol, interval)
        ttl = ttl or self.HISTORY_TTL
        
        try:
            # Convert DataFrame to JSON-serializable format
            data = df.copy()
            data["timestamp"] = data["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            payload = {
                "data": data.to_dict(orient="records"),
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "rows": len(df)
            }
            
            if self.is_connected():
                self._client.setex(key, ttl, json.dumps(payload))
            else:
                self._local_cache[key] = (payload, time.time() + ttl)
            
            logger.debug(f"Cached {len(df)} rows for {key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache history for {key}: {e}")
            return False
    
    def get_cached_history(
        self,
        symbol: str,
        interval: Interval
    ) -> Optional[pd.DataFrame]:
        """Retrieve cached historical DataFrame."""
        key = self._history_key(symbol, interval)
        
        try:
            if self.is_connected():
                raw = self._client.get(key)
            else:
                cached = self._local_cache.get(key)
                if cached and cached[1] > time.time():
                    raw = json.dumps(cached[0])
                else:
                    raw = None
            
            if not raw:
                return None
            
            payload = json.loads(raw)
            df = pd.DataFrame(payload["data"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            return df
            
        except Exception as e:
            logger.error(f"Failed to get cached history for {key}: {e}")
            return None
    
    # ============================================================
    # LATEST CANDLE CACHING (Incremental)
    # ============================================================
    
    def cache_latest_candle(
        self,
        symbol: str,
        interval: Interval,
        candle: Candle,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache latest candle (overwrites previous)."""
        key = self._latest_key(symbol, interval)
        ttl = ttl or self.LATEST_TTL
        
        try:
            payload = {
                "candle": candle.to_dict(),
                "cached_at": datetime.now(timezone.utc).isoformat()
            }
            
            if self.is_connected():
                self._client.setex(key, ttl, json.dumps(payload))
            else:
                self._local_cache[key] = (payload, time.time() + ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache latest candle for {key}: {e}")
            return False
    
    def get_latest_candle(
        self,
        symbol: str,
        interval: Interval
    ) -> Optional[Candle]:
        """Get latest cached candle."""
        key = self._latest_key(symbol, interval)
        
        try:
            if self.is_connected():
                raw = self._client.get(key)
            else:
                cached = self._local_cache.get(key)
                if cached and cached[1] > time.time():
                    raw = json.dumps(cached[0])
                else:
                    raw = None
            
            if not raw:
                return None
            
            payload = json.loads(raw)
            return Candle.from_dict(payload["candle"])
            
        except Exception as e:
            logger.error(f"Failed to get latest candle for {key}: {e}")
            return None
    
    # ============================================================
    # VALIDATION STATS
    # ============================================================
    
    def cache_validation_stats(self, stats: Dict[str, int]) -> bool:
        """Cache validation statistics."""
        try:
            payload = {
                "stats": stats,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if self.is_connected():
                self._client.setex(self.STATS_KEY, self.STATUS_TTL, json.dumps(payload))
            else:
                self._local_cache[self.STATS_KEY] = (payload, time.time() + self.STATUS_TTL)
            
            return True
        except Exception as e:
            logger.error(f"Failed to cache validation stats: {e}")
            return False
    
    def get_validation_stats(self) -> Optional[Dict[str, int]]:
        """Get cached validation statistics."""
        try:
            if self.is_connected():
                raw = self._client.get(self.STATS_KEY)
            else:
                cached = self._local_cache.get(self.STATS_KEY)
                if cached and cached[1] > time.time():
                    raw = json.dumps(cached[0])
                else:
                    raw = None
            
            if not raw:
                return None
            
            payload = json.loads(raw)
            return payload["stats"]
        except Exception as e:
            logger.error(f"Failed to get validation stats: {e}")
            return None
    
    # ============================================================
    # MARKET STATUS
    # ============================================================
    
    def cache_market_status(self, status: Dict[str, Any]) -> bool:
        """Cache market status."""
        try:
            payload = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if self.is_connected():
                self._client.setex(self.STATUS_KEY, self.STATUS_TTL, json.dumps(payload))
            else:
                self._local_cache[self.STATUS_KEY] = (payload, time.time() + self.STATUS_TTL)
            
            return True
        except Exception as e:
            logger.error(f"Failed to cache market status: {e}")
            return False
    
    def get_market_status(self) -> Optional[Dict[str, Any]]:
        """Get cached market status."""
        try:
            if self.is_connected():
                raw = self._client.get(self.STATUS_KEY)
            else:
                cached = self._local_cache.get(self.STATUS_KEY)
                if cached and cached[1] > time.time():
                    raw = json.dumps(cached[0])
                else:
                    raw = None
            
            if not raw:
                return None
            
            payload = json.loads(raw)
            return payload["status"]
        except Exception as e:
            logger.error(f"Failed to get market status: {e}")
            return None
    
    # ============================================================
    # PUB/SUB FOR LIVE FEEDS
    # ============================================================
    
    def _channel(self, interval: Interval) -> str:
        return f"market:candles:{interval.value}"
    
    def publish_candle(self, interval: Interval, candle: Candle) -> bool:
        """Publish new candle to subscribers."""
        if not self.is_connected():
            return False
        
        try:
            channel = self._channel(interval)
            payload = json.dumps(candle.to_dict())
            self._client.publish(channel, payload)
            return True
        except Exception as e:
            logger.error(f"Failed to publish candle: {e}")
            return False
    
    def subscribe_candles(self, interval: Interval, callback: callable) -> bool:
        """Subscribe to candle updates for an interval."""
        if not self.is_connected():
            return False
        
        try:
            self._pubsub = self._client.pubsub()
            self._pubsub.subscribe(self._channel(interval))
            
            # Run listener in background
            def listener():
                for message in self._pubsub.listen():
                    if message["type"] == "message":
                        try:
                            candle_data = json.loads(message["data"])
                            candle = Candle.from_dict(candle_data)
                            callback(candle)
                        except Exception as e:
                            logger.error(f"PubSub callback error: {e}")
            
            import threading
            thread = threading.Thread(target=listener, daemon=True)
            thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False
    
    # ============================================================
    # UTILITY
    # ============================================================
    
    def clear_symbol_cache(self, symbol: str) -> int:
        """Clear all cached data for a symbol."""
        if not self.is_connected():
            # Clear local cache
            keys_to_remove = [k for k in self._local_cache if symbol in k]
            for k in keys_to_remove:
                del self._local_cache[k]
            return len(keys_to_remove)
        
        try:
            pattern = f"market:*:{symbol}:*"
            keys = self._client.keys(pattern)
            if keys:
                return self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Failed to clear cache for {symbol}: {e}")
            return 0
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics."""
        info = {
            "connected": self.is_connected(),
            "local_cache_entries": len(self._local_cache),
            "redis_info": {}
        }
        
        if self.is_connected():
            try:
                redis_info = self._client.info("memory")
                info["redis_info"] = {
                    "used_memory_human": redis_info.get("used_memory_human"),
                    "connected_clients": redis_info.get("connected_clients"),
                    "total_keys": self._client.dbsize()
                }
            except Exception:
                pass
        
        return info


# Singleton instance
redis_manager = RedisManager()


if __name__ == "__main__":
    # Test the service
    logging.basicConfig(level=logging.INFO)
    
    manager = RedisManager()
    
    if manager.connect():
        print("Redis connected")
        
        # Test caching
        candle = Candle(
            timestamp=datetime.now(timezone.utc),
            open=2500.0,
            high=2550.0,
            low=2490.0,
            close=2530.0,
            volume=1000000,
            symbol="RELIANCE.NS",
            interval=Interval.DAY_1
        )
        
        manager.cache_latest_candle("RELIANCE.NS", Interval.DAY_1, candle)
        retrieved = manager.get_latest_candle("RELIANCE.NS", Interval.DAY_1)
        print(f"Retrieved: {retrieved}")
        
        print(f"Cache info: {manager.get_cache_info()}")
    else:
        print("Redis not available, using local cache")
        
        # Test local cache fallback
        candle = Candle(
            timestamp=datetime.now(timezone.utc),
            open=2500.0,
            high=2550.0,
            low=2490.0,
            close=2530.0,
            volume=1000000,
            symbol="RELIANCE.NS",
            interval=Interval.DAY_1
        )
        
        manager.cache_latest_candle("RELIANCE.NS", Interval.DAY_1, candle)
        retrieved = manager.get_latest_candle("RELIANCE.NS", Interval.DAY_1)
        print(f"Retrieved from local cache: {retrieved}")