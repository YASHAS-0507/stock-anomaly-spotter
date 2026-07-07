"""
candle_builder.py
-----------------
Aggregates live ticks into 1-minute and 5-minute OHLCV candles in memory.
Stores the last 200 completed candles per (ticker, timeframe) combination.

Thread-safe. Uses relative bucketing from each ticker's first tick so that
unit tests with synthetic timestamps are deterministic regardless of wall-clock time.
"""

import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Callable, Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")
MAX_CANDLES = 200

TIMEFRAME_SECONDS = {
    "1min": 60,
    "5min": 300,
}


class CandleBuilder:
    def __init__(self):
        self._lock = threading.Lock()

        # (ticker, timeframe) → deque of completed candle dicts (newest at right)
        self._history: dict = defaultdict(lambda: deque(maxlen=MAX_CANDLES))

        # (ticker, timeframe) → in-progress candle dict
        self._current: dict = {}

        # ticker → Unix timestamp of the first tick (for relative bucketing)
        self._session_start: dict = {}

        # Optional user callback: on_candle_complete(ticker, timeframe, candle)
        self.on_candle_complete: Optional[Callable] = None

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def on_tick(self, ticker: str, price: float, volume: int, timestamp: float) -> None:
        """
        Feed a single tick.

        Parameters
        ----------
        ticker    : e.g. "RELIANCE.NS"
        price     : last traded price (₹)
        volume    : trade volume for this tick
        timestamp : Unix epoch float (seconds) — e.g. time.time()
        """
        with self._lock:
            # Anchor relative bucketing to this ticker's very first tick
            if ticker not in self._session_start:
                self._session_start[ticker] = timestamp

            for tf, tf_secs in TIMEFRAME_SECONDS.items():
                self._process_tick(ticker, tf, tf_secs, price, volume, timestamp)

    def get_candles(self, ticker: str, timeframe: str, n: int) -> list:
        """
        Return the last `n` completed candles for `ticker` / `timeframe`.
        Oldest candle is at index 0; newest at index -1.
        """
        key = (ticker, timeframe)
        with self._lock:
            history = self._history.get(key)
            if not history:
                return []
            candles = list(history)
            return candles[-n:]

    def get_latest_candle(self, ticker: str, timeframe: str) -> Optional[dict]:
        """Return the most-recently completed candle, or None."""
        key = (ticker, timeframe)
        with self._lock:
            history = self._history.get(key)
            if not history:
                return None
            return history[-1]

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _bucket(self, ticker: str, timestamp: float, tf_secs: int) -> int:
        """Bucket index relative to this ticker's session start."""
        elapsed = timestamp - self._session_start[ticker]
        return int(elapsed / tf_secs)

    def _process_tick(
        self,
        ticker: str,
        timeframe: str,
        tf_secs: int,
        price: float,
        volume: int,
        timestamp: float,
    ) -> None:
        """Core per-timeframe tick processing (called under self._lock)."""
        key = (ticker, timeframe)
        bucket = self._bucket(ticker, timestamp, tf_secs)
        cur = self._current.get(key)

        if cur is None:
            self._current[key] = _new_candle(ticker, timeframe, bucket, price, volume, timestamp)
            return

        if bucket == cur["_bucket"]:
            # Same candle — update OHLCV
            cur["high"]   = max(cur["high"], price)
            cur["low"]    = min(cur["low"],  price)
            cur["close"]  = price
            cur["volume"] += volume
        else:
            # Minute boundary crossed — finalise and store
            completed = _finalise(cur)
            self._history[key].append(completed)
            _print_candle(completed)
            if self.on_candle_complete is not None:
                try:
                    self.on_candle_complete(ticker, timeframe, completed)
                except Exception:
                    pass
            # Start new candle
            self._current[key] = _new_candle(ticker, timeframe, bucket, price, volume, timestamp)


# ──────────────────────────────────────────────────────────────
# Module-level helpers (stateless, no self reference needed)
# ──────────────────────────────────────────────────────────────

def _new_candle(
    ticker: str,
    timeframe: str,
    bucket: int,
    price: float,
    volume: int,
    timestamp: float,
) -> dict:
    ist_dt = datetime.fromtimestamp(timestamp, tz=IST).replace(second=0, microsecond=0)
    return {
        "_bucket":   bucket,
        "ticker":    ticker,
        "timeframe": timeframe,
        "timestamp": ist_dt.isoformat(),
        "open":      price,
        "high":      price,
        "low":       price,
        "close":     price,
        "volume":    volume,
    }


def _finalise(candle: dict) -> dict:
    c = {k: v for k, v in candle.items() if not k.startswith("_")}
    c["open"]  = round(c["open"],  2)
    c["high"]  = round(c["high"],  2)
    c["low"]   = round(c["low"],   2)
    c["close"] = round(c["close"], 2)
    return c


def _print_candle(candle: dict) -> None:
    print(
        f"{candle['ticker']} {candle['timeframe']}: "
        f"O={candle['open']:.2f} "
        f"H={candle['high']:.2f} "
        f"L={candle['low']:.2f} "
        f"C={candle['close']:.2f} "
        f"V={candle['volume']}"
    )


# Shared singleton — imported by angel_feed
candle_builder = CandleBuilder()
