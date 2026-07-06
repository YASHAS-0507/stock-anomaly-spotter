"""
market_scanner.py
-----------------
Morning market scanner for Nifty 50 stocks.
Designed to run at 8:00 AM IST using previous-day close data.

Data source: data_pipeline.get_price_data() — shares the same yfinance
integration used by the rest of the backend, with automatic synthetic
fallback when network access is unavailable.

Scoring rubric (100 pts total):
  Liquidity     (20 pts) — avg volume > 10 lakh shares
  Volatility    (20 pts) — ATR% between 0.5% and 5%
  Momentum      (25 pts) — RSI between 40 and 70
  Trend         (20 pts) — latest close > EMA-21
  Volume Surge  (15 pts) — latest volume > 1.5× 20-day avg volume

Sector filter: maximum 1 stock per sector in final output.
Output: top 15 stocks ranked by composite score.
"""

import logging
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# Resolve backend root so data_pipeline is importable regardless of cwd
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from feeds.data_provider import data_provider
from feeds.ticker_registry import NIFTY_50_TOKENS, get_sector

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Scoring parameters
LIQUIDITY_THRESHOLD = 1_000_000  # 10 lakh shares
ATR_LOW,  ATR_HIGH  = 0.5, 5.0   # ATR% acceptable range
RSI_LOW,  RSI_HIGH  = 40.0, 70.0
EMA_SPAN            = 21
SURGE_THRESHOLD     = 1.5        # volume surge multiplier
TOP_N               = 15
FETCH_WORKERS       = 8          # parallel download threads
DATA_PERIOD         = "1mo"      # 30 days of daily OHLCV


class MarketScanner:
    """
    Scans every registered Nifty 50 stock, scores it on five criteria,
    applies a sector-diversity filter, and returns the top 15 candidates.
    """

    def scan(self) -> list[dict]:
        """
        Run the full morning scan.

        Returns a list of dicts (≤15, sorted by score descending):
        {
            ticker, sector, score,
            liquidity_score, volatility_score, momentum_score,
            trend_score, volume_surge_score,
            atr_pct, rsi, volume_surge_ratio,
            latest_close, avg_volume, ema21,
            scanned_at
        }
        """
        tickers = list(NIFTY_50_TOKENS.keys())
        logger.info("[scanner] Starting scan for %d tickers…", len(tickers))

        raw_data = self._fetch_all(tickers)
        scored: list[dict] = []

        for ticker, df in raw_data.items():
            if df is None or len(df) < 22:
                logger.debug("[scanner] Skipping %s — insufficient data", ticker)
                continue
            try:
                result = self._score(ticker, df)
                if result:
                    scored.append(result)
            except Exception as exc:
                logger.warning("[scanner] Score error for %s: %s", ticker, exc)

        # Sort by total score descending
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Sector filter: best-scoring stock per sector only
        sector_seen: set[str] = set()
        filtered: list[dict] = []
        for stock in scored:
            sec = stock["sector"]
            if sec not in sector_seen:
                sector_seen.add(sec)
                filtered.append(stock)
            if len(filtered) >= TOP_N:
                break

        logger.info("[scanner] Scan complete — %d candidates selected.", len(filtered))
        return filtered

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _fetch_all(self, tickers: list[str]) -> dict[str, Optional[pd.DataFrame]]:
        """Fetch OHLCV data for all tickers in parallel via data_pipeline."""
        results: dict[str, Optional[pd.DataFrame]] = {}

        def _fetch_one(ticker: str):
            try:
                df, _ = data_provider.get_daily_ohlcv(ticker, period=DATA_PERIOD)
                return ticker, df if df is not None and not df.empty else None
            except Exception as exc:
                logger.debug("[scanner] Fetch failed for %s: %s", ticker, exc)
                return ticker, None

        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, t): t for t in tickers}
            for future in as_completed(futures):
                ticker, df = future.result()
                results[ticker] = df

        return results

    def _score(self, ticker: str, df: pd.DataFrame) -> Optional[dict]:
        """Compute composite score for a single ticker."""
        # data_pipeline returns lowercase column names
        close  = df["close"].dropna()
        high   = df["high"].dropna()
        low    = df["low"].dropna()
        volume = df["volume"].dropna()

        if len(close) < 22 or len(volume) < 2:
            return None

        latest_close   = float(close.iloc[-1])
        latest_volume  = float(volume.iloc[-1])
        avg_volume     = float(volume.iloc[-20:].mean())

        # ── 1. Liquidity (20 pts) ────────────────────────────────────
        if avg_volume >= LIQUIDITY_THRESHOLD:
            liq_score = 20.0
        else:
            liq_score = round((avg_volume / LIQUIDITY_THRESHOLD) * 20.0, 2)

        # ── 2. Volatility / ATR% (20 pts) ───────────────────────────
        atr_series = (high - low).iloc[-14:]
        atr        = float(atr_series.mean())
        atr_pct    = (atr / latest_close * 100) if latest_close > 0 else 0.0

        if ATR_LOW <= atr_pct <= ATR_HIGH:
            vol_score = 20.0
        elif atr_pct < ATR_LOW:
            vol_score = round((atr_pct / ATR_LOW) * 20.0, 2)
        else:
            # Above 5% — still tradeable; taper score gently
            excess    = atr_pct - ATR_HIGH
            vol_score = max(0.0, round(20.0 - (excess / ATR_HIGH) * 10.0, 2))

        # ── 3. Momentum / RSI-14 (25 pts) ───────────────────────────
        rsi_val = self._rsi(close, period=14)
        if RSI_LOW <= rsi_val <= RSI_HIGH:
            mom_score = 25.0
        elif rsi_val < RSI_LOW:
            mom_score = round(max(0.0, (rsi_val / RSI_LOW) * 25.0), 2)
        else:
            distance_above = rsi_val - RSI_HIGH
            mom_score = round(max(0.0, 25.0 - (distance_above / RSI_HIGH) * 25.0), 2)

        # ── 4. Trend / EMA-21 (20 pts) ──────────────────────────────
        ema21        = float(close.ewm(span=EMA_SPAN, adjust=False).mean().iloc[-1])
        trend_score  = 20.0 if latest_close > ema21 else 0.0

        # ── 5. Volume Surge (15 pts) ─────────────────────────────────
        surge_ratio  = (latest_volume / avg_volume) if avg_volume > 0 else 0.0
        if surge_ratio >= SURGE_THRESHOLD:
            vsurge_score = 15.0
        else:
            vsurge_score = round((surge_ratio / SURGE_THRESHOLD) * 15.0, 2)

        total  = round(liq_score + vol_score + mom_score + trend_score + vsurge_score, 2)
        sector = get_sector(ticker) or "Unknown"

        return {
            "ticker":              ticker,
            "sector":              sector,
            "score":               total,
            "liquidity_score":     liq_score,
            "volatility_score":    vol_score,
            "momentum_score":      mom_score,
            "trend_score":         trend_score,
            "volume_surge_score":  vsurge_score,
            "atr_pct":             round(atr_pct, 3),
            "rsi":                 round(rsi_val, 2),
            "volume_surge_ratio":  round(surge_ratio, 3),
            "latest_close":        round(latest_close, 2),
            "avg_volume":          int(avg_volume),
            "ema21":               round(ema21, 2),
            "scanned_at":          datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
        }

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / (loss + 1e-9)
        rsi   = 100.0 - (100.0 / (1.0 + rs))
        val   = float(rsi.iloc[-1])
        return max(0.0, min(100.0, val if not np.isnan(val) else 50.0))
