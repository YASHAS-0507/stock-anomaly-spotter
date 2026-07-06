"""
market_mood.py
--------------
Fetches India VIX + macro data and derives a market mood dict.

Primary source: feeds.data_provider.get_macro_data() (15-min cached)
Fallback: direct yfinance VIX fetch (legacy path)

VIX regimes and trading multipliers:
  < 13   → LOW      — compressed volatility, size_multiplier = 1.2
  13–20  → NORMAL   — typical conditions, size_multiplier = 1.0
  20–25  → HIGH     — elevated fear, size_multiplier = 0.5
  > 25   → EXTREME  — tail risk, trading_recommended = False
"""

import logging
import sys
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

IST = timezone(timedelta(hours=5, minutes=30))

_FALLBACK_VIX = 15.0


class MarketMood:
    """Derives market mood from India VIX + macro data via DataProvider."""

    def get_mood(self) -> dict:
        """
        Fetch macro data and return a structured mood dict.

        Always returns a valid dict — falls back to VIX=15 (NORMAL) when
        data sources are unavailable.

        Returns
        -------
        dict with keys:
            vix, vix_regime, market_bias, trading_recommended,
            size_multiplier, reason, fetched_at, data_source,
            macro_score, global_sentiment, usdinr, usdinr_change_pct,
            crude_oil, crude_change_pct, sp500_change_pct, nikkei_change_pct,
            gift_nifty_gap_pts
        """
        macro = self._fetch_macro()
        vix    = macro.get("india_vix", _FALLBACK_VIX)
        source = macro.get("source", "fallback")
        return self._build_mood(vix, source, macro)

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _fetch_macro(self) -> dict:
        """Use DataProvider; fall back to direct VIX fetch on error."""
        try:
            from feeds.data_provider import data_provider
            return data_provider.get_macro_data()
        except Exception as exc:
            logger.warning("[mood] DataProvider unavailable: %s — using legacy VIX fetch", exc)
            vix, source = self._legacy_fetch_vix()
            return {
                "india_vix":          vix,
                "usdinr":             83.0,
                "usdinr_change_pct":   0.0,
                "crude_oil":          75.0,
                "crude_change_pct":    0.0,
                "sp500_change_pct":    0.0,
                "nikkei_change_pct":   0.0,
                "global_sentiment":   "NEUTRAL",
                "macro_score":         50.0,
                "source":              source,
            }

    @staticmethod
    def _legacy_fetch_vix() -> tuple:
        """Legacy VIX fetch — delegates to data_provider to avoid direct yfinance."""
        try:
            from feeds.data_provider import data_provider
            macro = data_provider.get_macro_data()
            vix = macro.get("india_vix", _FALLBACK_VIX)
            src = macro.get("source", "fallback")
            return vix, src
        except Exception as exc:
            logger.debug("[mood] Legacy VIX fallback failed: %s", exc)
        return _FALLBACK_VIX, "fallback_network_unavailable"

    @staticmethod
    def _build_mood(vix: float, source: str, macro: dict) -> dict:
        now_ist     = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        is_fallback = source.startswith("fallback")

        if vix < 13.0:
            regime              = "LOW"
            bias                = "BULLISH"
            trading_recommended = True
            size_multiplier     = 1.2
            reason = (
                f"India VIX={vix:.1f} (< 13) — compressed volatility, "
                "markets are calm; full position sizing allowed."
            )
        elif vix <= 20.0:
            regime              = "NORMAL"
            bias                = "NEUTRAL" if vix > 17 else "BULLISH"
            trading_recommended = True
            size_multiplier     = 1.0
            reason = (
                f"India VIX={vix:.1f} (13–20) — normal market conditions; "
                "standard position sizing."
            )
        elif vix <= 25.0:
            regime              = "HIGH"
            bias                = "BEARISH"
            trading_recommended = True
            size_multiplier     = 0.5
            reason = (
                f"India VIX={vix:.1f} (20–25) — elevated fear; "
                "reduce position size to 50% of normal."
            )
        else:
            regime              = "EXTREME"
            bias                = "BEARISH"
            trading_recommended = False
            size_multiplier     = 0.0
            reason = (
                f"India VIX={vix:.1f} (> 25) — extreme fear / tail risk; "
                "trading not recommended today."
            )

        if is_fallback:
            reason += " [VIX data unavailable — using default NORMAL baseline]"

        # Gift Nifty gap — not reliably available via free API; set to None
        gift_nifty_gap_pts = None

        macro_score = macro.get("macro_score", 50.0)

        return {
            "vix":                 vix,
            "vix_regime":          regime,
            "market_bias":         bias,
            "trading_recommended": trading_recommended,
            "size_multiplier":     size_multiplier,
            "reason":              reason,
            "fetched_at":          now_ist,
            "data_source":         source,
            # New macro fields
            "macro_score":         macro_score,
            "global_sentiment":    macro.get("global_sentiment",    "NEUTRAL"),
            "usdinr":              macro.get("usdinr",              83.0),
            "usdinr_change_pct":   macro.get("usdinr_change_pct",   0.0),
            "crude_oil":           macro.get("crude_oil",           75.0),
            "crude_change_pct":    macro.get("crude_change_pct",    0.0),
            "sp500_change_pct":    macro.get("sp500_change_pct",    0.0),
            "nikkei_change_pct":   macro.get("nikkei_change_pct",   0.0),
            "gift_nifty_gap_pts":  gift_nifty_gap_pts,
            "morning_bias": (
                "STRONG_BULL" if macro_score > 70 else
                "BULL"        if macro_score > 60 else
                "NEUTRAL"     if macro_score >= 40 else
                "BEAR"        if macro_score >= 25 else
                "STRONG_BEAR"
            ),
        }
