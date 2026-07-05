"""
earnings_calendar.py
--------------------
Checks if any watchlist stock has earnings announced today or tomorrow.

Data source: yfinance .calendar attribute (with graceful fallback when
network is unavailable, consistent with data_pipeline.py approach).

Flags:
  "AVOID" — earnings today (results cause unpredictable gaps/halts)
  "WATCH" — earnings tomorrow (manage position size carefully)
"""

import logging
import sys
import os
from datetime import datetime, date, timedelta, timezone

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
FETCH_TIMEOUT = 8  # seconds


class EarningsCalendar:
    """Checks upcoming earnings for a list of tickers."""

    def get_earnings_this_week(self, tickers: list[str]) -> dict[str, dict]:
        """
        Check for earnings events for each ticker this week.

        Returns
        -------
        dict[str, dict]
            {ticker: {"earnings_date": date_str, "flag": "AVOID"|"WATCH"|"CLEAR"}}
            Tickers with no earnings data → "CLEAR".
        """
        result: dict[str, dict] = {}
        today = date.today()
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=7)

        for ticker in tickers:
            try:
                entry = self._check_ticker(ticker, today, tomorrow, week_end)
                result[ticker] = entry
            except Exception as exc:
                logger.debug("[earnings] Error checking %s: %s", ticker, exc)
                result[ticker] = {"earnings_date": None, "flag": "CLEAR", "source": "error"}

        return result

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _check_ticker(
        self,
        ticker: str,
        today: date,
        tomorrow: date,
        week_end: date,
    ) -> dict:
        if not _YF_OK:
            return {"earnings_date": None, "flag": "CLEAR", "source": "unavailable"}

        try:
            info = yf.Ticker(ticker)
            calendar = info.calendar  # dict or DataFrame depending on yf version
        except Exception:
            return {"earnings_date": None, "flag": "CLEAR", "source": "fetch_error"}

        earnings_date = self._extract_earnings_date(calendar)
        if earnings_date is None:
            return {"earnings_date": None, "flag": "CLEAR", "source": "no_data"}

        # Normalise to date object
        if hasattr(earnings_date, "date"):
            earnings_date = earnings_date.date()

        date_str = str(earnings_date)

        if earnings_date == today:
            return {"earnings_date": date_str, "flag": "AVOID",
                    "reason": "Earnings today — unpredictable gap risk"}
        elif earnings_date == tomorrow:
            return {"earnings_date": date_str, "flag": "WATCH",
                    "reason": "Earnings tomorrow — reduce position size"}
        elif today < earnings_date <= week_end:
            return {"earnings_date": date_str, "flag": "WATCH",
                    "reason": f"Earnings this week ({date_str}) — monitor closely"}
        else:
            return {"earnings_date": date_str, "flag": "CLEAR", "source": "upcoming"}

    @staticmethod
    def _extract_earnings_date(calendar) -> "date | None":
        """Extract an earnings date from yfinance calendar output (handles multiple formats)."""
        if calendar is None:
            return None

        # yfinance < 0.2: calendar is a DataFrame with 'Earnings Date' column
        try:
            import pandas as pd
            if isinstance(calendar, pd.DataFrame) and "Earnings Date" in calendar.columns:
                val = calendar["Earnings Date"].iloc[0]
                if pd.notna(val):
                    return pd.Timestamp(val).date()
        except Exception:
            pass

        # yfinance >= 0.2: calendar is a dict
        if isinstance(calendar, dict):
            for key in ("Earnings Date", "earningsDate", "earnings_date"):
                val = calendar.get(key)
                if val is not None:
                    try:
                        import pandas as pd
                        if isinstance(val, (list, tuple)) and val:
                            return pd.Timestamp(val[0]).date()
                        return pd.Timestamp(val).date()
                    except Exception:
                        pass

        return None
