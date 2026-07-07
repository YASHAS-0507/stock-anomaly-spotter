"""
llm_analyzer.py
---------------
Uses Groq (llama-3.1-8b-instant) to generate per-ticker sentiment and
trading intelligence from news headlines and market mood.

Falls back to keyword-based scoring when GROQ_API_KEY is missing or the
API call fails — never raises, always returns a valid dict.

Sentiment values: "POSITIVE" | "NEGATIVE" | "NEUTRAL"
Action values:    "BUY" | "SELL" | "HOLD"
"""

import json
import logging
import os
import re
import sys
import time as _time

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

try:
    from groq import Groq
    _GROQ_OK = True
except ImportError:
    _GROQ_OK = False
    Groq = None  # type: ignore

_GROQ_MODEL = "llama-3.1-8b-instant"

# Keywords for offline fallback scoring
_POSITIVE_KW = [
    "profit", "growth", "record", "beat", "upgrade", "buy", "strong",
    "surge", "rally", "gain", "bullish", "outperform", "positive",
    "revenue up", "earnings up", "dividend", "acquisition", "expansion",
]
_NEGATIVE_KW = [
    "loss", "decline", "miss", "downgrade", "sell", "weak", "fall",
    "crash", "drop", "bearish", "underperform", "negative", "fraud",
    "penalty", "probe", "investigation", "layoff", "recall", "cut",
]

_SYSTEM_PROMPT = """You are an expert Indian equity market analyst.
Given a stock ticker, its recent news headlines, and the current India VIX
market mood, output a JSON object with EXACTLY these keys:
  sentiment        : "POSITIVE" | "NEGATIVE" | "NEUTRAL"
  impact           : "HIGH" | "MEDIUM" | "LOW"
  action           : "BUY" | "SELL" | "HOLD"
  reason           : one concise sentence (max 20 words)
  confidence       : integer 0–100
  intelligence_score: float 0.0–1.0 (overall opportunity quality)

Rules:
- If headlines is empty, return NEUTRAL / LOW / HOLD with confidence=30
- Weigh market mood: EXTREME VIX → penalise BUY; LOW VIX → favour BUY
- Output ONLY the JSON object, no markdown, no explanation."""


class LLMAnalyzer:
    """Groq-powered intelligence analyzer with keyword fallback."""

    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if _GROQ_OK and api_key:
            self._client = Groq(api_key=api_key)
        else:
            self._client = None
            if not api_key:
                logger.info("[llm] GROQ_API_KEY not set — using keyword fallback")
            elif not _GROQ_OK:
                logger.info("[llm] groq package not installed — using keyword fallback")

        # Rate-limit protection
        self._last_groq_call: float = 0.0
        self._result_cache: dict = {}   # {ticker: (timestamp, result)}
        self._min_call_interval = 2.0   # seconds between successive Groq calls
        self._cache_ttl         = 600   # 10-minute cache TTL
        self._max_retries       = 3
        self._retry_wait_429    = 60    # seconds to wait after a 429

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def analyze(
        self,
        ticker: str,
        headlines: list[str],
        market_mood: dict,
    ) -> dict:
        """
        Analyze a single ticker.

        Returns
        -------
        dict with keys:
            ticker, sentiment, impact, action, reason,
            confidence, intelligence_score, source
        """
        if self._client is not None:
            result = self._analyze_groq(ticker, headlines, market_mood)
        else:
            result = self._analyze_keywords(ticker, headlines, market_mood)

        result["ticker"] = ticker
        return result

    def analyze_batch(
        self,
        watchlist: list[str],
        news_by_ticker: dict[str, list[str]],
        mood: dict,
    ) -> dict[str, dict]:
        """
        Analyze a list of tickers.

        Returns
        -------
        dict[str, dict]  — {ticker: analyze() result}
        """
        results: dict[str, dict] = {}
        for ticker in watchlist:
            headlines = news_by_ticker.get(ticker, [])
            try:
                results[ticker] = self.analyze(ticker, headlines, mood)
            except Exception as exc:
                logger.warning("[llm] analyze() failed for %s: %s", ticker, exc)
                results[ticker] = self._neutral(ticker)
        return results

    # ──────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────

    def _analyze_groq(
        self,
        ticker: str,
        headlines: list[str],
        market_mood: dict,
    ) -> dict:
        # Serve from cache if fresh (10-minute TTL)
        cached = self._result_cache.get(ticker)
        if cached:
            cached_ts, cached_result = cached
            if _time.time() - cached_ts < self._cache_ttl:
                logger.debug("[llm] Cache hit for %s", ticker)
                return dict(cached_result)

        vix_regime = market_mood.get("vix_regime", "NORMAL")
        vix_val    = market_mood.get("vix", "N/A")

        headlines_text = (
            "\n".join(f"- {h}" for h in headlines[:10])
            if headlines
            else "(no headlines available)"
        )

        user_msg = (
            f"Ticker: {ticker}\n"
            f"India VIX: {vix_val} (regime: {vix_regime})\n"
            f"Market bias: {market_mood.get('market_bias', 'NEUTRAL')}\n\n"
            f"Recent headlines:\n{headlines_text}"
        )

        for attempt in range(1, self._max_retries + 1):
            # Enforce minimum inter-call delay to avoid burst rate limiting
            elapsed = _time.time() - self._last_groq_call
            if elapsed < self._min_call_interval:
                _time.sleep(self._min_call_interval - elapsed)

            try:
                self._last_groq_call = _time.time()
                response = self._client.chat.completions.create(
                    model=_GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": user_msg},
                    ],
                    temperature=0.1,
                    max_tokens=256,
                )
                raw = response.choices[0].message.content.strip()
                parsed = self._parse_json(raw)
                if parsed:
                    parsed["source"] = "groq"
                    result = self._normalise(parsed)
                    # Cache the successful result
                    self._result_cache[ticker] = (_time.time(), dict(result))
                    return result
                break  # parse failure is not retriable
            except Exception as exc:
                exc_str = str(exc).lower()
                is_429  = (
                    "429" in exc_str
                    or "rate_limit" in exc_str
                    or "ratelimit" in exc_str
                    or "too many requests" in exc_str
                )
                if is_429 and attempt < self._max_retries:
                    logger.warning(
                        "[llm] Groq 429 rate limit for %s — waiting %ds (attempt %d/%d)",
                        ticker, self._retry_wait_429, attempt, self._max_retries,
                    )
                    _time.sleep(self._retry_wait_429)
                    continue
                logger.debug("[llm] Groq call failed for %s: %s", ticker, exc)
                break

        # All retries exhausted or non-retriable error → keyword fallback
        result = self._analyze_keywords(ticker, headlines, market_mood)
        result["source"] = "keyword_fallback_groq_error"
        return result

    def _analyze_keywords(
        self,
        ticker: str,
        headlines: list[str],
        market_mood: dict,
    ) -> dict:
        """Offline keyword-count sentiment scorer."""
        if not headlines:
            return self._neutral(ticker, source="keyword_no_headlines")

        text = " ".join(headlines).lower()
        pos = sum(1 for kw in _POSITIVE_KW if kw in text)
        neg = sum(1 for kw in _NEGATIVE_KW if kw in text)

        vix_regime = market_mood.get("vix_regime", "NORMAL")

        if pos > neg:
            sentiment = "POSITIVE"
            action    = "BUY" if vix_regime not in ("HIGH", "EXTREME") else "HOLD"
            confidence = min(90, 50 + pos * 5)
            score      = min(1.0, 0.5 + pos * 0.05)
            reason     = f"{ticker} shows positive news signals."
        elif neg > pos:
            sentiment = "NEGATIVE"
            action    = "SELL" if neg > 2 else "HOLD"
            confidence = min(90, 50 + neg * 5)
            score      = max(0.0, 0.5 - neg * 0.05)
            reason     = f"{ticker} shows negative news signals."
        else:
            return self._neutral(ticker, source="keyword_balanced")

        # Penalise if market is EXTREME
        if vix_regime == "EXTREME":
            action     = "HOLD"
            confidence = max(10, confidence - 20)
            score      = max(0.0, score - 0.2)

        impact = "HIGH" if confidence >= 70 else ("MEDIUM" if confidence >= 50 else "LOW")

        return {
            "sentiment":          sentiment,
            "impact":             impact,
            "action":             action,
            "reason":             reason,
            "confidence":         confidence,
            "intelligence_score": round(score, 3),
            "source":             "keyword",
        }

    # ──────────────────────────────────────────────────────
    # Utility helpers
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _neutral(ticker: str, source: str = "fallback") -> dict:
        return {
            "ticker":             ticker,
            "sentiment":          "NEUTRAL",
            "impact":             "LOW",
            "action":             "HOLD",
            "reason":             "Insufficient data for analysis.",
            "confidence":         30,
            "intelligence_score": 0.5,
            "source":             source,
        }

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Extract JSON from LLM response (handles markdown fences)."""
        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find first {...} block
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _normalise(d: dict) -> dict:
        """Ensure all expected keys exist and values are in valid ranges."""
        valid_sentiments = {"POSITIVE", "NEGATIVE", "NEUTRAL"}
        valid_impacts    = {"HIGH", "MEDIUM", "LOW"}
        valid_actions    = {"BUY", "SELL", "HOLD"}

        return {
            "sentiment":          d.get("sentiment", "NEUTRAL") if d.get("sentiment") in valid_sentiments else "NEUTRAL",
            "impact":             d.get("impact", "LOW")        if d.get("impact")    in valid_impacts    else "LOW",
            "action":             d.get("action", "HOLD")       if d.get("action")    in valid_actions    else "HOLD",
            "reason":             str(d.get("reason", "No reason provided."))[:200],
            "confidence":         max(0, min(100, int(d.get("confidence", 30)))),
            "intelligence_score": round(max(0.0, min(1.0, float(d.get("intelligence_score", 0.5)))), 3),
            "source":             d.get("source", "groq"),
        }
