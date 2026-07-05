"""
opportunity_ranker.py
---------------------
Secondary scoring layer applied on top of MarketScanner results.

Adds two intraday setup probabilities:
  orb_prob  — Opening Range Breakout probability (0–100)
  vwap_prob — VWAP reversion/continuation setup probability (0–100)

Final combined score:
  combined = scanner_score * 0.60 + orb_prob * 0.20 + vwap_prob * 0.20

ORB probability drivers:
  High ATR% → larger opening range → more decisive breakout
  Volume surge → institutional participation → follow-through
  RSI in 45-65 → not overbought/oversold, room to move

VWAP probability drivers:
  Trend alignment (price > EMA21) → VWAP acts as support
  High liquidity → cleaner VWAP behaviour, tighter execution
  Momentum in 50-65 RSI range → controlled trending day
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Weight constants for combined score
W_SCANNER = 0.60
W_ORB     = 0.20
W_VWAP    = 0.20


class OpportunityRanker:
    """
    Receives a list of scanner result dicts (from MarketScanner.scan()),
    enriches each entry with orb_prob, vwap_prob, and combined_score,
    and returns the list re-sorted by combined_score descending.
    """

    def rank(self, scanner_results: list[dict]) -> list[dict]:
        """
        Parameters
        ----------
        scanner_results : list[dict]
            Output of MarketScanner.scan().

        Returns
        -------
        list[dict]
            Same entries with three new keys added and sorted by combined_score:
            - orb_prob      (float 0–100)
            - vwap_prob     (float 0–100)
            - combined_score (float)
        """
        enriched = []
        for stock in scanner_results:
            try:
                ranked = self._enrich(stock)
                enriched.append(ranked)
            except Exception as exc:
                logger.warning(
                    "[ranker] Failed to rank %s: %s",
                    stock.get("ticker", "?"), exc,
                )
                # Keep original entry without additional fields rather than drop it
                stock.setdefault("orb_prob",       0.0)
                stock.setdefault("vwap_prob",      0.0)
                stock.setdefault("combined_score", stock.get("score", 0.0))
                enriched.append(stock)

        enriched.sort(key=lambda x: x["combined_score"], reverse=True)
        logger.info("[ranker] Ranked %d opportunities.", len(enriched))
        return enriched

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _enrich(self, stock: dict) -> dict:
        stock = dict(stock)  # shallow copy — don't mutate original

        atr_pct      = stock.get("atr_pct",            0.0)
        surge_ratio  = stock.get("volume_surge_ratio",  1.0)
        rsi          = stock.get("rsi",                50.0)
        trend_score  = stock.get("trend_score",         0.0)
        liq_score    = stock.get("liquidity_score",     0.0)
        scanner_score = stock.get("score",              0.0)

        orb_prob  = self._orb_probability(atr_pct, surge_ratio, rsi)
        vwap_prob = self._vwap_probability(trend_score, liq_score, rsi)
        combined  = round(
            scanner_score * W_SCANNER +
            orb_prob      * W_ORB     +
            vwap_prob     * W_VWAP,
            2,
        )

        stock["orb_prob"]       = orb_prob
        stock["vwap_prob"]      = vwap_prob
        stock["combined_score"] = combined
        return stock

    @staticmethod
    def _orb_probability(atr_pct: float, surge_ratio: float, rsi: float) -> float:
        """
        ORB probability formula:
          atr_pct     : higher ATR → bigger opening range → cleaner breakout (max 40 pts)
          surge_ratio : volume above avg confirms participation (max 30 pts)
          rsi band    : RSI 45-65 → optimal momentum zone for ORB (max 30 pts)

        Returns a value clipped to [0, 100].
        """
        # ATR contribution — caps at 4% ATR for full 40 pts
        atr_score = min(40.0, (atr_pct / 4.0) * 40.0)

        # Volume surge contribution — caps at 3× for full 30 pts
        surge_score = min(30.0, ((surge_ratio - 1.0) / 2.0) * 30.0) if surge_ratio > 1 else 0.0

        # RSI band contribution — centred on 55, full 30 pts when RSI in [45, 65]
        if 45.0 <= rsi <= 65.0:
            rsi_score = 30.0
        elif rsi < 45.0:
            rsi_score = max(0.0, (rsi / 45.0) * 30.0)
        else:
            excess = rsi - 65.0
            rsi_score = max(0.0, 30.0 - (excess / 35.0) * 30.0)

        return round(min(100.0, atr_score + surge_score + rsi_score), 2)

    @staticmethod
    def _vwap_probability(trend_score: float, liq_score: float, rsi: float) -> float:
        """
        VWAP setup probability formula:
          trend_score  : price above EMA21 → VWAP likely to act as support (max 40 pts)
          liq_score    : high liquidity → cleaner VWAP interaction (max 30 pts)
          rsi band     : RSI 50-65 → controlled trend, VWAP bounces work well (max 30 pts)

        Returns a value clipped to [0, 100].
        """
        # Trend contribution — full 40 pts if trending (trend_score=20), scaled down if flat
        trend_contrib = min(40.0, (trend_score / 20.0) * 40.0) if trend_score > 0 else 0.0

        # Liquidity contribution — full 30 pts if liq_score=20
        liq_contrib = min(30.0, (liq_score / 20.0) * 30.0)

        # RSI contribution — centred on 57.5, full 30 pts when RSI in [50, 65]
        if 50.0 <= rsi <= 65.0:
            rsi_score = 30.0
        elif rsi < 50.0:
            rsi_score = max(0.0, (rsi / 50.0) * 30.0)
        else:
            excess = rsi - 65.0
            rsi_score = max(0.0, 30.0 - (excess / 35.0) * 30.0)

        return round(min(100.0, trend_contrib + liq_contrib + rsi_score), 2)
