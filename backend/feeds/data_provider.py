"""
data_provider.py
----------------
Single source of truth for ALL market data.
- Angel One historical API for intraday data (accurate, real-time)
- yfinance for daily / macro data (acceptable latency)
- In-memory cache with per-category TTL
- Graceful fallbacks — never crashes callers

No other module should import yfinance directly.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pytz

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False
    yf = None  # type: ignore

_IST = pytz.timezone("Asia/Kolkata")

_MACRO_TICKERS = ["^INDIAVIX", "USDINR=X", "CL=F", "^GSPC", "^N225"]

# Module-level singleton — reuse one AngelOneFeed so _AngelSession cache is shared.
_angel_feed_singleton = None
_angel_feed_lock = threading.Lock()

# Process-wide rate limiter for Angel One historical API (max 3 req/sec).
# The scanner runs 8 parallel threads; without this they'd burst all at once.
_angel_api_lock = threading.Lock()
_angel_last_call: float = 0.0
_ANGEL_MIN_INTERVAL = 0.50  # seconds between historical API calls → 2 req/sec max


def _get_angel_feed():
    global _angel_feed_singleton
    if _angel_feed_singleton is None:
        with _angel_feed_lock:
            if _angel_feed_singleton is None:
                from feeds.angel_feed import AngelOneFeed
                _angel_feed_singleton = AngelOneFeed()
    return _angel_feed_singleton


def _angel_throttled(fn):
    """Serialize all Angel One historical API calls and enforce ≤3 req/sec."""
    global _angel_last_call
    with _angel_api_lock:
        elapsed = time.time() - _angel_last_call
        if elapsed < _ANGEL_MIN_INTERVAL:
            time.sleep(_ANGEL_MIN_INTERVAL - elapsed)
        result = fn()
        _angel_last_call = time.time()
        return result


def _period_to_days(period: str) -> int:
    """Convert yfinance-style period string to calendar days."""
    _map = {"1mo": 35, "3mo": 95, "6mo": 185, "1y": 375, "2y": 740}
    return _map.get(period, 35)


class DataProvider:
    def __init__(self):
        self._cache: dict = {}
        self._cache_timestamps: dict = {}
        self._cache_ttl = {
            "intraday": 60,
            "daily":   3600,
            "macro":    900,
        }

    def get_intraday_candles(self, ticker: str, interval: str = "FIVE_MINUTE", days_back: int = 5) -> tuple:
        cache_key = f"intraday:{ticker}:{interval}:{days_back}"
        cached = self._get_cached(cache_key, self._cache_ttl["intraday"])
        if cached is not None:
            return cached["candles"], cached["source"]
        candles, source = self._angel_intraday(ticker, interval, days_back)
        if not candles:
            candles, source = self._yf_intraday(ticker, interval, days_back)
        self._set_cache(cache_key, {"candles": candles, "source": source})
        return candles, source

    def get_daily_ohlcv(self, ticker: str, period: str = "1y") -> tuple:
        cache_key = f"daily:{ticker}:{period}"
        cached = self._get_cached(cache_key, self._cache_ttl["daily"])
        if cached is not None:
            return cached["df"], cached["source"]
        # Try Angel One first — not subject to Railway IP blocks
        days_back = _period_to_days(period)
        df, source = self._angel_daily_ohlcv(ticker, days_back=days_back)
        if df is not None and not df.empty:
            self._set_cache(cache_key, {"df": df, "source": source})
            return df, source
        # Fallback: yfinance (may be blocked on Railway for .NS tickers)
        try:
            from data_pipeline import get_price_data
            df, is_synthetic = get_price_data(ticker, period=period)
            source = "yfinance_synthetic" if is_synthetic else "yfinance"
            self._set_cache(cache_key, {"df": df, "source": source})
            return df, source
        except Exception as exc:
            logger.warning("[data_provider] get_daily_ohlcv failed for %s: %s", ticker, exc)
            return pd.DataFrame(), "error"

    def get_macro_data(self) -> dict:
        cache_key = "macro:global"
        cached = self._get_cached(cache_key, self._cache_ttl["macro"])
        if cached is not None:
            return cached
        result = self._fetch_macro()
        self._set_cache(cache_key, result)
        return result

    def get_previous_day_ohlcv(self, ticker: str) -> dict:
        cache_key = f"prevday:{ticker}"
        cached = self._get_cached(cache_key, self._cache_ttl["daily"])
        if cached is not None:
            return cached
        result = self._angel_prev_day(ticker)
        if not result or result.get("close", 0) <= 0:
            result = self._yf_prev_day(ticker)
        self._set_cache(cache_key, result)
        return result

    def get_cache_stats(self) -> dict:
        now = time.time()
        intraday = sum(1 for k in self._cache if k.startswith("intraday:") and (now - self._cache_timestamps.get(k, 0)) < self._cache_ttl["intraday"])
        daily = sum(1 for k in self._cache if (k.startswith("daily:") or k.startswith("prevday:")) and (now - self._cache_timestamps.get(k, 0)) < self._cache_ttl["daily"])
        macro = sum(1 for k in self._cache if k.startswith("macro:") and (now - self._cache_timestamps.get(k, 0)) < self._cache_ttl["macro"])
        return {"intraday_cached": intraday, "daily_cached": daily, "macro_cached": macro}

    def _angel_intraday(self, ticker: str, interval: str, days_back: int) -> tuple:
        try:
            feed      = _get_angel_feed()
            token     = feed.get_symbol_token(ticker)
            if not token:
                return [], "no_token"
            now       = datetime.now(_IST)
            from_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d") + " 09:15"
            to_date   = now.strftime("%Y-%m-%d") + " 15:30"
            candles   = _angel_throttled(
                lambda: feed.get_historical_candles(token, interval, from_date, to_date)
            )
            if candles:
                logger.debug("[data_provider] angel_intraday %s %s: %d candles", ticker, interval, len(candles))
                return candles, "angel_one"
        except Exception as exc:
            logger.warning("[data_provider] Angel One intraday failed: %s", exc)
        return [], "angel_unavailable"

    def _angel_prev_day(self, ticker: str) -> dict:
        try:
            feed  = _get_angel_feed()
            token = feed.get_symbol_token(ticker)
            if not token:
                return {}
            today     = datetime.now(_IST).date()
            from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d") + " 09:15"
            to_date   = today.strftime("%Y-%m-%d") + " 15:30"
            candles   = _angel_throttled(lambda: feed.get_historical_candles(token, "ONE_DAY", from_date, to_date))
            if candles:
                c = candles[-2] if len(candles) >= 2 else candles[-1]
                return {
                    "high":   float(c["high"]),
                    "low":    float(c["low"]),
                    "close":  float(c["close"]),
                    "open":   float(c["open"]),
                    "volume": int(c.get("volume", 0)),
                    "date":   str(c.get("timestamp", ""))[:10],
                    "source": "angel_one",
                }
        except Exception as exc:
            logger.warning("[data_provider] Angel One prev day failed: %s", exc)
        return {}

    def _angel_daily_ohlcv(self, ticker: str, days_back: int = 35) -> tuple:
        """
        Fetch daily OHLCV from Angel One and return as a DataFrame.
        Uses process-wide throttle to stay under 3 req/sec.
        Returns (DataFrame with lowercase columns, source_str).
        """
        try:
            feed  = _get_angel_feed()
            token = feed.get_symbol_token(ticker)
            if not token:
                return pd.DataFrame(), "no_token"
            now       = datetime.now(_IST)
            from_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d") + " 09:15"
            to_date   = now.strftime("%Y-%m-%d") + " 15:30"

            candles = _angel_throttled(
                lambda: feed.get_historical_candles(token, "ONE_DAY", from_date, to_date)
            )
            if not candles:
                return pd.DataFrame(), "angel_no_data"

            rows = []
            for c in candles:
                try:
                    rows.append({
                        "timestamp": pd.to_datetime(c.get("timestamp", "")),
                        "open":      float(c.get("open",   0) or 0),
                        "high":      float(c.get("high",   0) or 0),
                        "low":       float(c.get("low",    0) or 0),
                        "close":     float(c.get("close",  0) or 0),
                        "volume":    int(c.get("volume",   0) or 0),
                    })
                except Exception:
                    pass

            if not rows:
                return pd.DataFrame(), "angel_parse_error"

            df = pd.DataFrame(rows).set_index("timestamp").sort_index()
            logger.debug("[data_provider] angel_daily %s: %d rows", ticker, len(df))
            return df, "angel_one"

        except Exception as exc:
            logger.warning("[data_provider] Angel One daily failed for %s: %s", ticker, exc)
            return pd.DataFrame(), "angel_error"

    def _yf_intraday(self, ticker: str, interval: str, days_back: int) -> tuple:
        if not _YF_OK:
            return [], "yfinance_unavailable"
        try:
            yf_interval = "1m" if interval == "ONE_MINUTE" else "5m"
            period_str  = f"{min(days_back, 7)}d"
            ticker_obj  = yf.Ticker(ticker)
            df = ticker_obj.history(period=period_str, interval=yf_interval, auto_adjust=True)
            if df is None or df.empty:
                return [], "yfinance_no_data"
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            candles = []
            for ts, row in df.iterrows():
                try:
                    candles.append({
                        "timestamp": str(ts),
                        "open":      round(float(row.get("Open",   0) or 0), 4),
                        "high":      round(float(row.get("High",   0) or 0), 4),
                        "low":       round(float(row.get("Low",    0) or 0), 4),
                        "close":     round(float(row.get("Close",  0) or 0), 4),
                        "volume":    int(row.get("Volume", 0) or 0),
                    })
                except Exception:
                    pass
            logger.warning("[data_provider] Using yfinance_fallback intraday for %s", ticker)
            return candles, "yfinance_fallback"
        except Exception as exc:
            logger.warning("[data_provider] yfinance intraday failed for %s: %s", ticker, exc)
            return [], "yfinance_error"

    def _yf_prev_day(self, ticker: str) -> dict:
        _empty = {"high": 0.0, "low": 0.0, "close": 0.0, "open": 0.0, "volume": 0, "date": "", "source": "yfinance_error"}
        if not _YF_OK:
            return {**_empty, "source": "yfinance_unavailable"}
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="5d", auto_adjust=True)
            if df is None or df.empty:
                return _empty
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            idx = -2 if len(df) >= 2 else -1
            row = df.iloc[idx]
            return {
                "high":   round(float(row.get("High",  0) or 0), 2),
                "low":    round(float(row.get("Low",   0) or 0), 2),
                "close":  round(float(row.get("Close", 0) or 0), 2),
                "open":   round(float(row.get("Open",  0) or 0), 2),
                "volume": int(row.get("Volume", 0) or 0),
                "date":   str(df.index[idx])[:10],
                "source": "yfinance",
            }
        except Exception as exc:
            logger.warning("[data_provider] yfinance prev day failed for %s: %s", ticker, exc)
            return _empty

    def _fetch_macro(self) -> dict:
        result = {
            "india_vix": 15.0, "usdinr": 83.0, "usdinr_change_pct": 0.0,
            "crude_oil": 75.0, "crude_change_pct": 0.0, "sp500_change_pct": 0.0,
            "nikkei_change_pct": 0.0, "global_sentiment": "NEUTRAL",
            "macro_score": 50.0, "source": "fallback",
        }
        if not _YF_OK:
            return result

        def _fetch_single(sym):
            try:
                df = yf.Ticker(sym).history(period="3d", auto_adjust=True)
                if df is None or df.empty:
                    return pd.Series(dtype=float)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                col = "Close" if "Close" in df.columns else df.columns[0]
                return df[col].dropna()
            except Exception:
                return pd.Series(dtype=float)

        def _pct(curr, prev):
            return round((curr - prev) / prev * 100, 3) if curr and prev and prev != 0 else 0.0

        try:
            vix_s = _fetch_single("^INDIAVIX")
            usdinr_s = _fetch_single("USDINR=X")
            crude_s = _fetch_single("CL=F")
            sp500_s = _fetch_single("^GSPC")
            nikkei_s = _fetch_single("^N225")

            def _last(s): return float(s.iloc[-1]) if len(s) >= 1 else None
            def _prev(s): return float(s.iloc[-2]) if len(s) >= 2 else None

            if _last(vix_s) and _last(vix_s) > 0:
                result["india_vix"] = round(_last(vix_s), 2)
            if _last(usdinr_s) and _last(usdinr_s) > 0:
                result["usdinr"] = round(_last(usdinr_s), 2)
            if _last(crude_s) and _last(crude_s) > 0:
                result["crude_oil"] = round(_last(crude_s), 2)

            result["usdinr_change_pct"] = _pct(_last(usdinr_s), _prev(usdinr_s))
            result["crude_change_pct"]  = _pct(_last(crude_s),  _prev(crude_s))
            result["sp500_change_pct"]  = _pct(_last(sp500_s),  _prev(sp500_s))
            result["nikkei_change_pct"] = _pct(_last(nikkei_s), _prev(nikkei_s))
            result["source"] = "yfinance"
        except Exception as exc:
            logger.warning("[data_provider] Macro fetch failed: %s", exc)

        score = 50.0
        vix = result["india_vix"]
        if vix < 15:   score += 10
        elif vix > 25: score -= 25
        elif vix > 20: score -= 15

        c = result["crude_change_pct"]
        if c < -1.0:  score += 5
        elif c > 3.0: score -= 15
        elif c > 1.0: score -= 5

        u = result["usdinr_change_pct"]
        if u < -0.3:  score -= 8
        elif u > 0.3: score += 5

        s = result["sp500_change_pct"]
        if s > 0.5:    score += 8
        elif s < -1.5: score -= 20
        elif s < -0.5: score -= 8

        score = max(0.0, min(100.0, score))
        result["macro_score"] = round(score, 1)
        result["global_sentiment"] = "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL"
        return result

    def _is_cache_fresh(self, key: str, ttl_seconds: int) -> bool:
        ts = self._cache_timestamps.get(key)
        return ts is not None and (time.time() - ts) < ttl_seconds

    def _get_cached(self, key: str, ttl_seconds: int):
        return self._cache[key] if self._is_cache_fresh(key, ttl_seconds) else None

    def _set_cache(self, key: str, value) -> None:
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()


# Module-level singleton
data_provider = DataProvider()
