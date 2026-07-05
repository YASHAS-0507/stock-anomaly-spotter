"""
sentiment_cache.py
------------------
Thread-safe in-memory cache for LLM sentiment results with per-entry TTL.

Default TTL is 7 minutes — long enough to avoid redundant Groq calls
during a morning scan, short enough to refresh when market conditions
change intraday.
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)

_DEFAULT_TTL_MINUTES = 7


class SentimentCache:
    """Thread-safe TTL cache for sentiment analysis results."""

    def __init__(self, default_ttl_minutes: int = _DEFAULT_TTL_MINUTES):
        self._store: dict[str, dict] = {}   # {ticker: {"result": dict, "expires_at": float}}
        self._lock  = threading.Lock()
        self._default_ttl = default_ttl_minutes * 60  # convert to seconds

    def get(self, ticker: str) -> dict | None:
        """
        Return the cached result for ticker if it is still fresh, else None.
        """
        with self._lock:
            entry = self._store.get(ticker)
            if entry is None:
                return None
            if time.time() > entry["expires_at"]:
                del self._store[ticker]
                return None
            return entry["result"]

    def set(self, ticker: str, result: dict, ttl_minutes: int | None = None) -> None:
        """
        Store result for ticker.

        Parameters
        ----------
        ticker      : stock ticker string
        result      : dict returned by LLMAnalyzer.analyze()
        ttl_minutes : override default TTL; pass None to use default
        """
        ttl_secs = (ttl_minutes * 60) if ttl_minutes is not None else self._default_ttl
        expires_at = time.time() + ttl_secs
        with self._lock:
            self._store[ticker] = {"result": result, "expires_at": expires_at}

    def is_fresh(self, ticker: str) -> bool:
        """Return True if ticker has a valid (non-expired) cache entry."""
        with self._lock:
            entry = self._store.get(ticker)
            if entry is None:
                return False
            if time.time() > entry["expires_at"]:
                del self._store[ticker]
                return False
            return True

    def clear(self) -> None:
        """Remove all cache entries."""
        with self._lock:
            self._store.clear()
        logger.debug("[cache] Sentiment cache cleared")

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# Module-level singleton
sentiment_cache = SentimentCache()
