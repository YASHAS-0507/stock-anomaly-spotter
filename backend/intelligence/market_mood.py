"""
market_mood.py
--------------
Fetches India VIX and derives a market mood (bias, regime, trading parameters).

Data source: yfinance ticker "^INDIAVIX" — with synthetic fallback when
network is unavailable (consistent with data_pipeline.py pattern).

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

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False
    yf = None  # type: ignore

IST = timezone(timedelta(hours=5, minutes=30))

# Fallback VIX used when the network is unavailable
_FALLBACK_VIX = 15.0

VIX_TICKER = "^INDIAVIX"


class MarketMood:
    """Derives market mood from India VIX."""

    def get_mood(self) -> dict:
        """
        Fetch India VIX and return a structured mood dict.

        Always returns a valid dict — uses a fallback VIX of 15.0 (NORMAL)
        when the network or yfinance is unavailable.

        Returns
        -------
        dict with keys:
            vix, vix_regime, market_bias, trading_recommended,
            size_multiplier, reason, fetched_at, data_source
        """
        vix, source = self._fetch_vix()
        return self._build_mood(vix, source)

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _fetch_vix(self) -> tuple[float, str]:
        """Return (vix_value, source_label). Falls back to default on any error."""
        if not _YF_OK:
            return _FALLBACK_VIX, "fallback_no_yfinance"

        try:
            df = yf.download(
                VIX_TICKER,
                period="2d",
                progress=False,
                auto_adjust=True,
            )
            if df is not None and not df.empty:
                # Flatten MultiIndex if present
                import pandas as pd
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                col = "Close" if "Close" in df.columns else df.columns[0]
                vix = float(df[col].dropna().iloc[-1])
                if vix > 0:
                    return round(vix, 2), "yfinance_live"
        except Exception as exc:
            logger.debug("[mood] VIX fetch failed: %s", exc)

        return _FALLBACK_VIX, "fallback_network_unavailable"

    @staticmethod
    def _build_mood(vix: float, source: str) -> dict:
        now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
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

        return {
            "vix":                 vix,
            "vix_regime":          regime,
            "market_bias":         bias,
            "trading_recommended": trading_recommended,
            "size_multiplier":     size_multiplier,
            "reason":              reason,
            "fetched_at":          now_ist,
            "data_source":         source,
        }
