"""
news_fetcher.py
---------------
Fetches financial news headlines from free RSS feeds and the NSE
corporate-announcements API.

Returns {ticker: [headline, ...]} filtered to headlines that mention
the company name. Never raises — returns {} on any network or parse error.

Timeout: 5 seconds per feed.
"""

import logging
import re
import sys
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Backend root on sys.path so peer packages resolve
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

try:
    import feedparser
    _FEEDPARSER_OK = True
except ImportError:
    _FEEDPARSER_OK = False
    feedparser = None  # type: ignore

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False
    requests = None  # type: ignore

RSS_FEEDS = [
    "https://www.moneycontrol.com/rss/latestnews.xml",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
]

NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.nseindia.com",
    "Accept":     "application/json",
}

FETCH_TIMEOUT = 5  # seconds
MAX_HEADLINES_PER_TICKER = 10


class NewsFetcher:
    """Fetches and filters financial news headlines for given tickers."""

    def fetch(self, tickers: list[str]) -> dict[str, list[str]]:
        """
        Fetch news headlines for the given tickers.

        Parameters
        ----------
        tickers : list[str]
            e.g. ["RELIANCE.NS", "TCS.NS"]

        Returns
        -------
        dict[str, list[str]]
            {ticker: [headline, ...]}  — may be empty for any ticker
        """
        result: dict[str, list[str]] = {t: [] for t in tickers}

        # Build company-name lookup: "RELIANCE.NS" → "RELIANCE"
        name_map = {t: t.split(".")[0].upper() for t in tickers}

        rss_headlines  = self._fetch_rss()
        nse_headlines  = self._fetch_nse(tickers)

        all_headlines = rss_headlines + nse_headlines

        for ticker, company in name_map.items():
            matched = [
                h for h in all_headlines
                if self._mentions(h, company)
            ][:MAX_HEADLINES_PER_TICKER]
            result[ticker] = matched

        return result

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _fetch_rss(self) -> list[str]:
        """Fetch all RSS feeds and return a flat list of headline strings."""
        if not _FEEDPARSER_OK:
            logger.warning("[news] feedparser not installed — skipping RSS feeds")
            return []

        headlines: list[str] = []
        for url in RSS_FEEDS:
            try:
                feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in feed.get("entries", []):
                    title = entry.get("title", "").strip()
                    if title:
                        headlines.append(title)
            except Exception as exc:
                logger.debug("[news] RSS fetch failed for %s: %s", url, exc)

        return headlines

    def _fetch_nse(self, tickers: list[str]) -> list[str]:
        """Fetch NSE corporate announcements. Returns empty list on any error."""
        if not _REQUESTS_OK:
            return []

        try:
            resp = requests.get(
                NSE_ANNOUNCEMENTS_URL,
                headers=NSE_HEADERS,
                timeout=FETCH_TIMEOUT,
            )
            if not resp.ok:
                return []

            data = resp.json()
            headlines: list[str] = []
            for item in data if isinstance(data, list) else []:
                subject = item.get("subject") or item.get("desc") or ""
                symbol  = item.get("symbol", "")
                if subject:
                    headlines.append(f"{symbol}: {subject}" if symbol else subject)
            return headlines

        except Exception as exc:
            logger.debug("[news] NSE announcements fetch failed: %s", exc)
            return []

    @staticmethod
    def _mentions(headline: str, company: str) -> bool:
        """True if the headline mentions the company name (case-insensitive, word boundary)."""
        pattern = r'\b' + re.escape(company) + r'\b'
        return bool(re.search(pattern, headline, re.IGNORECASE))
