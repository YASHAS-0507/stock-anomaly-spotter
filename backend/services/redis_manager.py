"""
redis_manager.py
----------------
Redis Cache Layer — standalone, no imports from other services.
Provides a simple get/set/delete interface with local in-memory
fallback when Redis is not available.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class _LocalCache:
    """Thread-safe in-process dict cache with TTL support."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            exp = self._expiry.get(key)
            if exp and time.time() > exp:
                self._store.pop(key, None)
                self._expiry.pop(key, None)
                return None
            return self._store.get(key)

    def set(self, key: str, value: str, ex: int = 300) -> None:
        with self._lock:
            self._store[key] = value
            self._expiry[key] = time.time() + ex

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    def keys(self, pattern: str = "*") -> List[str]:
        with self._lock:
            now = time.time()
            expired = [k for k, exp in self._expiry.items() if now > exp]
            for k in expired:
                self._store.pop(k, None)
                self._expiry.pop(k, None)
            if pattern == "*":
                return list(self._store.keys())
            prefix = pattern.rstrip("*")
            return [k for k in self._store if k.startswith(prefix)]

    def flushdb(self) -> None:
        with self._lock:
            self._store.clear()
            self._expiry.clear()

    def dbsize(self) -> int:
        with self._lock:
            return len(self._store)

    def info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": "local_fallback",
                "keys": len(self._store),
            }


class RedisManager:
    """
    Unified cache interface. Transparently uses Redis when available,
    otherwise falls back to the in-process _LocalCache.
    """

    # Key constants
    STATUS_KEY  = "market:status"
    STATS_KEY   = "market:validation:stats"
    STATUS_TTL  = 60
    HISTORY_TTL = 3600
    LATEST_TTL  = 300

    def __init__(self):
        self._client = None
        self._local = _LocalCache()
        self._using_redis = False
        self._connect()

    def _connect(self) -> None:
        redis_url = os.environ.get("REDIS_URL", "")
        if not redis_url:
            logger.info("[redis_manager] REDIS_URL not set — using local in-memory fallback.")
            return
        try:
            import redis as redis_lib
            self._client = redis_lib.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            self._client.ping()
            self._using_redis = True
            logger.info(f"[redis_manager] Connected to Redis at {redis_url}")
        except Exception as e:
            logger.warning(f"[redis_manager] Redis connection failed ({e}) — using local fallback.")
            self._client = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._using_redis

    # ------------------------------------------------------------------
    # Core get / set / delete
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._client.get(key) if self._using_redis else self._local.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        try:
            serialized = json.dumps(value, default=str)
            if self._using_redis:
                self._client.set(key, serialized, ex=ttl)
            else:
                self._local.set(key, serialized, ex=ttl)
        except Exception as e:
            logger.debug(f"[redis_manager] set failed for {key}: {e}")

    def delete(self, key: str) -> None:
        try:
            if self._using_redis:
                self._client.delete(key)
            else:
                self._local.delete(key)
        except Exception:
            pass

    def keys(self, pattern: str = "*") -> List[str]:
        try:
            if self._using_redis:
                return self._client.keys(pattern)
            return self._local.keys(pattern)
        except Exception:
            return []

    def flush(self) -> None:
        try:
            if self._using_redis:
                self._client.flushdb()
            else:
                self._local.flushdb()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Convenience wrappers used by market_status and router
    # ------------------------------------------------------------------

    def cache_market_status(self, status: Dict[str, Any]) -> None:
        self.set(self.STATUS_KEY, status, ttl=self.STATUS_TTL)

    def get_market_status_cached(self) -> Optional[Dict[str, Any]]:
        return self.get(self.STATUS_KEY)

    def cache_validation_stats(self, stats: Dict[str, Any]) -> None:
        self.set(self.STATS_KEY, stats, ttl=self.STATUS_TTL)

    def get_validation_stats(self) -> Optional[Dict[str, Any]]:
        return self.get(self.STATS_KEY)

    # ------------------------------------------------------------------
    # Cache info (used by /api/market/cache/info endpoint)
    # ------------------------------------------------------------------

    def get_cache_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "connected": self._using_redis,
            "local_cache_entries": self._local.dbsize(),
            "redis_info": {},
        }
        if self._using_redis and self._client:
            try:
                mem = self._client.info("memory")
                info["redis_info"] = {
                    "used_memory_human": mem.get("used_memory_human", "N/A"),
                    "connected_clients": self._client.info().get("connected_clients", 0),
                    "total_keys": self._client.dbsize(),
                }
            except Exception:
                pass
        return info

    # ------------------------------------------------------------------
    # Symbol-level cache clear (used by router)
    # ------------------------------------------------------------------

    def clear_symbol_cache(self, symbol: str) -> int:
        pattern = f"market:*:{symbol}:*"
        keys = self.keys(pattern)
        for k in keys:
            self.delete(k)
        return len(keys)


# Singleton
redis_manager = RedisManager()
