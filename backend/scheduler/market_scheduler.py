"""
market_scheduler.py
-------------------
Master autonomous scheduler: runs the full intraday pipeline from 8:00am
to 3:30pm IST without human intervention.

Pipeline:
  08:00 → pre_market_8am()   — VIX, model, mood
  08:00 → scanner_run_8am()  — Nifty 50 scan + ranking → watchlist
  08:15 → intelligence_scan() — news + Groq analysis
  09:15 → Angel One WebSocket open, on_tick() fires per tick
  09:15+→ on_new_candle()    — 5min candle close triggers full decision pipeline
  every 7min → intelligence_refresh()
  every 1s   → monitor_loop_tick() — SL/TP/time-stop checks
  15:15 → square_off_3_15pm()
  15:30 → post_market_3_30pm()
"""

import logging
import os
import sys
import time
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# ── All layer imports ──────────────────────────────────────────────────────────
from feeds.angel_feed       import AngelOneFeed
from feeds.candle_builder   import CandleBuilder
from feeds.ticker_registry  import NIFTY_50_TOKENS, SECTOR_MAP
from scanner.market_scanner import MarketScanner
from scanner.opportunity_ranker import OpportunityRanker
from intelligence.news_fetcher  import NewsFetcher
from intelligence.market_mood   import MarketMood
from intelligence.llm_analyzer  import LLMAnalyzer
from intelligence.sentiment_cache import SentimentCache
from indicators.intraday_features import IntradayFeatures
from regime.intraday_regime       import IntradayRegimeDetector
from models.intraday_model        import intraday_model
from decisions.intraday_decision  import intraday_decision_engine, DECISION_CONFIG
from risk.intraday_sizer          import IntradaySizer
from broker.auto_paper_broker     import auto_broker
from shadow.shadow_manager        import shadow_manager
from expiry.expiry_calendar       import expiry_calendar
from decay.decay_monitor          import decay_monitor

try:
    import schedule
    _SCHEDULE_OK = True
except ImportError:
    _SCHEDULE_OK = False
    schedule = None  # type: ignore

IST = timezone(timedelta(hours=5, minutes=30))

# NSE holidays 2026 (minimum required)
_NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti / Good Friday
    date(2026, 5,  1),   # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 12, 25),  # Christmas
}


class MarketScheduler:
    """
    Orchestrates the complete autonomous intraday trading pipeline.
    Instantiate once and call start() to begin.
    """

    def __init__(self):
        self.running   = False
        self.paused    = False
        self.skip_today = False
        self.day_min_score           = 65
        self.day_size_multiplier     = 1.0
        self.expiry_context          = None
        self.day_max_trades          = 999
        self.day_avoid_after         = "14:45"
        self.day_expiry_risk_mult    = 1.0

        self.watchlist:            list  = []
        self.intelligence_cache:   dict  = {}
        self.last_intelligence_refresh: Optional[datetime] = None
        self.current_prices:       dict  = {}
        self.market_mood_cache:    dict  = {}
        self._feed: Optional[AngelOneFeed] = None
        self._angel_connected: bool = False

        # Component instances
        self.candle_builder  = CandleBuilder()
        self.features_engine = IntradayFeatures()
        self.regime_detector = IntradayRegimeDetector()
        self.scanner         = MarketScanner()
        self.ranker          = OpportunityRanker()
        self.news_fetcher    = NewsFetcher()
        self.mood            = MarketMood()
        self.llm             = LLMAnalyzer()
        self.sizer           = IntradaySizer()

        # Wire candle_builder callback → on_new_candle
        self.candle_builder.on_candle_complete = self.on_new_candle

    # ──────────────────────────────────────────────────────
    # Trading day helpers
    # ──────────────────────────────────────────────────────

    def is_trading_day(self, date_obj: Optional[date] = None) -> bool:
        """Return True if the given date is a valid NSE trading day."""
        d = date_obj or datetime.now(IST).date()
        if d.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        if d in _NSE_HOLIDAYS_2026:
            return False
        return True

    # ──────────────────────────────────────────────────────
    # Pre-session checks
    # ──────────────────────────────────────────────────────

    def pre_session_checklist(self) -> dict:
        """Verify system readiness before market opens."""
        checks: dict = {}
        warnings: list = []

        checks["angel_credentials_set"] = all(
            os.environ.get(k) for k in
            ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_SECRET")
        )
        checks["groq_key_set"]                = bool(os.environ.get("GROQ_API_KEY"))
        checks["model_available"]             = intraday_model.is_trained()
        checks["broker_not_emergency_stopped"] = not auto_broker._emergency_stopped

        if not checks["angel_credentials_set"]:
            warnings.append("Angel One credentials missing — will use synthetic data fallback")
        if not checks["groq_key_set"]:
            warnings.append("GROQ_API_KEY missing — LLM analyzer will use keyword fallback")
        if not checks["model_available"]:
            warnings.append("ML model not trained — will use 0.5 probability fallback")
        if not checks["broker_not_emergency_stopped"]:
            warnings.append("CRITICAL: broker is emergency-stopped — call auto_broker.reset()")

        ready = checks["broker_not_emergency_stopped"]  # only hard requirement
        return {"ready": ready, "checks": checks, "warnings": warnings}

    # ──────────────────────────────────────────────────────
    # Scheduled jobs
    # ──────────────────────────────────────────────────────

    def apply_morning_bias(self, morning_bias: str) -> None:
        """Adjust day_min_score and day_size_multiplier based on macro morning bias."""
        if morning_bias == "STRONG_BEAR":
            self.day_min_score       = 75
            self.day_size_multiplier = 0.5
            logger.info("[scheduler] STRONG_BEAR day: min_score=75, size=0.5x")
        elif morning_bias == "BEAR":
            self.day_min_score       = 70
            self.day_size_multiplier = 0.7
            logger.info("[scheduler] BEAR day: min_score=70, size=0.7x")
        elif morning_bias == "NEUTRAL":
            self.day_min_score       = 65
            self.day_size_multiplier = 1.0
            logger.info("[scheduler] NEUTRAL day: normal settings")
        elif morning_bias == "BULL":
            self.day_min_score       = 62
            self.day_size_multiplier = 1.0
            logger.info("[scheduler] BULL day: min_score=62")
        elif morning_bias == "STRONG_BULL":
            self.day_min_score       = 60
            self.day_size_multiplier = 1.0
            logger.info("[scheduler] STRONG_BULL day: min_score=60")

    def pre_market_8am(self) -> None:
        """Run at 08:00 IST: VIX check, model load, initial mood."""
        logger.info("[scheduler] === pre_market_8am ===")
        checklist = self.pre_session_checklist()
        logger.info("[scheduler] Checklist: %s", checklist)

        # Angel One auth test
        try:
            _test_feed = AngelOneFeed()
            success = _test_feed.authenticate()
            print(f"[angel] Auth test: {success}")
        except Exception as exc:
            print(f"[angel] Auth test failed: {exc}")

        try:
            mood = self.mood.get_mood()
            self.market_mood_cache = mood
            vix = mood.get("vix", 15.0)
            morning_bias = mood.get("morning_bias", "NEUTRAL")
            self.apply_morning_bias(morning_bias)

            # Get expiry context for today
            self.expiry_context = expiry_calendar.get_expiry_context()
            self.day_expiry_risk_mult = self.expiry_context["risk_multiplier"]
            self.day_max_trades       = self.expiry_context["max_trades_today"]
            self.day_avoid_after      = self.expiry_context["avoid_after"]

            if self.expiry_context["is_expiry_day"]:
                loss_mult = self.expiry_context["daily_loss_multiplier"]
                auto_broker.max_daily_loss    *= loss_mult
                auto_broker.emergency_stop_loss *= loss_mult
                print(
                    f"[expiry] {self.expiry_context['expiry_type']} "
                    f"day: risk={self.day_expiry_risk_mult}x "
                    f"max_trades={self.day_max_trades}"
                )

            if vix > 25.0:
                self.skip_today = True
                logger.warning("[scheduler] VIX=%.1f > 25 — skipping trading today", vix)
            else:
                logger.info("[scheduler] VIX=%.1f regime=%s — trading enabled",
                            vix, mood.get("vix_regime", "NORMAL"))
        except Exception as exc:
            logger.warning("[scheduler] Mood fetch failed: %s", exc)

        # Try to load saved model
        if not intraday_model.is_trained():
            loaded = intraday_model.load()
            if loaded:
                logger.info("[scheduler] Loaded saved ML model")
            else:
                logger.info("[scheduler] No saved model — will use probability fallback")

        trading = "ENABLED" if not self.skip_today else "SKIPPED (VIX)"
        logger.info("[scheduler] Pre-market complete. VIX=%s Trading=%s",
                    self.market_mood_cache.get("vix", "?"), trading)

    def scanner_run_8am(self) -> None:
        """Run at 08:00 IST: Nifty 50 scan → ranked watchlist."""
        logger.info("[scheduler] === scanner_run_8am ===")
        try:
            scan_results = self.scanner.scan()
            ranked       = self.ranker.rank(scan_results)
            self.watchlist = [r["ticker"] for r in ranked[:15]]
            logger.info("[scheduler] Watchlist (%d): %s", len(self.watchlist), self.watchlist)
        except Exception as exc:
            logger.warning("[scheduler] Scanner failed: %s — using full Nifty 50", exc)
            self.watchlist = list(NIFTY_50_TOKENS.keys())[:15]

    def intelligence_scan(self) -> None:
        """Fetch news + LLM analysis for all watchlist tickers."""
        if not self.watchlist:
            return
        try:
            news      = self.news_fetcher.fetch(self.watchlist)
            mood      = self.market_mood_cache or self.mood.get_mood()
            analysis  = self.llm.analyze_batch(self.watchlist, news, mood)
            self.intelligence_cache = analysis
            self.last_intelligence_refresh = datetime.now(IST)
            logger.info("[scheduler] Intelligence refreshed for %d tickers", len(analysis))
        except Exception as exc:
            logger.warning("[scheduler] Intelligence scan failed: %s", exc)

    def intelligence_refresh(self) -> None:
        """Re-run intelligence_scan (called every 7 min by scheduler)."""
        self.intelligence_scan()

    # ──────────────────────────────────────────────────────
    # Tick + candle pipeline
    # ──────────────────────────────────────────────────────

    def on_tick(
        self,
        ticker: str,
        price: float,
        volume: int,
        timestamp: float,
    ) -> None:
        """Called by AngelOneFeed for every live tick."""
        try:
            if ticker in self.watchlist:
                self.current_prices[ticker] = price
            self.candle_builder.on_tick(ticker, price, volume, timestamp)
        except Exception as exc:
            logger.debug("[scheduler] on_tick error for %s: %s", ticker, exc)

    def on_new_candle(
        self,
        ticker: str,
        timeframe: str,
        candle: dict,
    ) -> None:
        """
        Called by CandleBuilder when a candle completes.
        Only acts on 5min candles for watchlist tickers.
        """
        if timeframe != "5min":
            return
        if ticker not in self.watchlist:
            return

        try:
            self._process_candle(ticker, candle)
        except Exception as exc:
            logger.warning("[scheduler] on_new_candle error for %s: %s", ticker, exc)

    def _process_candle(self, ticker: str, candle: dict) -> None:
        """Core decision pipeline for one completed 5-min candle."""
        now = datetime.now(IST)

        # Gate: only trade in active windows (9:30–14:45 IST)
        now_mins = now.hour * 60 + now.minute
        if not (9 * 60 + 30 <= now_mins <= 14 * 60 + 45):
            return

        # Gate: daily limits
        limits = auto_broker.check_daily_limits()
        if not limits["can_trade"]:
            logger.info("[scheduler] Daily limits exceeded: %s", limits["reason"])
            return

        # Gate: skip_today flag (extreme VIX)
        if self.skip_today:
            return

        # Gate: expiry day trade count limit
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        trades_today = len([
            t for t in auto_broker.trades
            if t.get("opened_at", "").startswith(today_str)
        ])
        if trades_today >= self.day_max_trades:
            return

        # Gate: expiry day time cutoff
        current_time_str = datetime.now(IST).strftime("%H:%M")
        if current_time_str >= self.day_avoid_after:
            return

        # Fetch candle history
        candles_5min = self.candle_builder.get_candles(ticker, "5min", 60)
        candles_1min = self.candle_builder.get_candles(ticker, "1min", 200)

        current_price = float(candle.get("close", 0) or 0)
        if current_price <= 0:
            current_price = self.current_prices.get(ticker, 0.0)
        if current_price <= 0:
            return

        # Compute features
        features = self.features_engine.compute(candles_5min, candles_1min, current_price)

        # Detect regime
        mood   = self.market_mood_cache or {"vix": 15.0, "vix_regime": "NORMAL"}
        regime = self.regime_detector.detect(features, mood, now)

        if not regime.get("trading_permitted", False):
            return

        # ML prediction
        ml_pred = intraday_model.predict(features)

        # Intelligence (cached)
        intel = self.intelligence_cache.get(ticker, {
            "action": "NORMAL", "intelligence_score": 50,
            "sentiment": "NEUTRAL", "source": "cache_miss",
        })

        # Generate signal
        open_count = len(auto_broker.positions)
        trade_id   = f"TRD-{ticker.split('.')[0]}-{datetime.now(IST).strftime('%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

        DECISION_CONFIG["min_combined_score"] = self.day_min_score
        signal = intraday_decision_engine.generate_signal(
            ticker=ticker,
            features=features,
            regime=regime,
            ml_prediction=ml_pred,
            intelligence=intel,
            open_positions=open_count,
        )

        # Shadow agents observe regardless of signal
        try:
            shadow_manager.observe(
                ticker=ticker,
                features=features,
                regime=regime,
                live_signal=signal["signal"],
                live_confidence=ml_pred.get("prob_up", 0.5),
                intelligence=intel,
                trade_id=trade_id,
            )
        except Exception as exc:
            logger.debug("[scheduler] shadow observe error: %s", exc)

        if signal["signal"] != "BUY":
            return

        # ATR-based stop loss: close - 1.5 × ATR
        atr = features.get("atr_14", 0.0) or 0.0
        stop_loss = current_price - (atr * 1.5) if atr > 0 else current_price * 0.98

        # Decay multiplier: AT_RISK setups trade at 50% size
        setup_multipliers = decay_monitor.get_setup_risk_multipliers()
        decay_mult = setup_multipliers.get(signal.get("setup_type", ""), 1.0)

        # Size the position
        sizing = self.sizer.calculate(
            entry_price=current_price,
            stop_loss=stop_loss,
            available_capital=auto_broker.capital,
            size_multiplier=regime.get("size_multiplier", 1.0) * self.day_size_multiplier * decay_mult,
            expiry_multiplier=self.day_expiry_risk_mult,
        )
        if not sizing.get("viable"):
            logger.info("[scheduler] %s sizing not viable: %s", ticker, sizing.get("reason"))
            return

        # Inject trade_id and ticker into signal for broker
        signal["ticker"]   = ticker
        signal["trade_id"] = trade_id

        # Execute
        order = auto_broker.execute_signal(signal, current_price, sizing)
        if order.get("status") == "filled":
            logger.info(
                "[scheduler] FILLED %s @ ₹%.2f x%d | SL=%.2f TP1=%.2f | id=%s",
                ticker, order["fill_price"], sizing["shares"],
                sizing["stop_loss"], sizing["take_profit_1"], trade_id,
            )
        else:
            logger.info("[scheduler] Order rejected for %s: %s", ticker, order.get("reason"))

    # ──────────────────────────────────────────────────────
    # Monitor loop (every second)
    # ──────────────────────────────────────────────────────

    def monitor_loop_tick(self) -> None:
        """Called every second — check SL/TP on all open positions."""
        try:
            if not self.current_prices:
                return
            closed = auto_broker.monitor_positions(self.current_prices)
            for trade in closed:
                trade_id = trade.get("trade_id", "")
                pnl      = trade.get("pnl", 0.0)
                reason   = trade.get("close_reason", "")
                logger.info("[scheduler] Position closed: %s %s pnl=₹%.2f", trade_id, reason, pnl)
                outcome = {
                    "outcome":     "WIN" if pnl > 0 else "LOSS",
                    "pnl_pct":     round(pnl / (trade.get("fill_price", 1) * trade.get("shares", 1)) * 100, 4),
                    "close_reason": reason,
                }
                try:
                    shadow_manager.on_trade_closed(trade_id, outcome)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("[scheduler] monitor_loop_tick error: %s", exc)

    # ──────────────────────────────────────────────────────
    # End-of-day jobs
    # ──────────────────────────────────────────────────────

    def square_off_3_15pm(self) -> None:
        """Hard square-off at 15:15 IST."""
        logger.info("[scheduler] === square_off_3_15pm ===")
        try:
            closed = auto_broker.square_off_all(self.current_prices)
            for t in closed:
                shadow_manager.on_trade_closed(t.get("trade_id", ""), {
                    "outcome":      "WIN" if t.get("pnl", 0) > 0 else "LOSS",
                    "pnl_pct":      0.0,
                    "close_reason": "square_off",
                })
            snap = auto_broker.get_portfolio_snapshot()
            logger.info(
                "[scheduler] Square-off complete. Closed=%d daily_pnl=₹%.2f win_rate=%.0f%%",
                len(closed), snap.get("daily_pnl", 0), snap.get("win_rate", 0),
            )
        except Exception as exc:
            logger.warning("[scheduler] square_off_3_15pm error: %s", exc)

    def post_market_3_30pm(self) -> None:
        """Post-market summary at 15:30 IST."""
        logger.info("[scheduler] === post_market_3_30pm ===")
        try:
            snap   = auto_broker.get_portfolio_snapshot()
            report = shadow_manager.get_weekly_report()
            logger.info(
                "[scheduler] Daily summary | Total trades=%d | Win rate=%.0f%% | "
                "Daily PnL=₹%.2f | Total value=₹%.2f",
                snap.get("total_trades", 0),
                snap.get("win_rate", 0),
                snap.get("daily_pnl", 0),
                snap.get("total_value", 0),
            )
            logger.info("[scheduler] Shadow report recommendation: %s",
                        report.get("recommendation", "N/A"))

            # Run decay monitor if due
            all_trades = auto_broker.get_trade_history(limit=500)
            ran = decay_monitor.run_if_due(all_trades)
            if ran:
                summary = decay_monitor.get_system_health_summary()
                print(f"[decay] System health: {summary.get('system_health')}")
                logger.info("[decay] Assessment complete: %s", summary.get("system_health"))

        except Exception as exc:
            logger.warning("[scheduler] post_market_3_30pm error: %s", exc)

        self.running = False

    # ──────────────────────────────────────────────────────
    # Historical candle fallback loop
    # ──────────────────────────────────────────────────────

    def _historical_fallback_loop(self) -> None:
        """
        Background thread: when Angel One WebSocket is offline, fetches the
        latest 5-min candle from the historical API every 5 minutes and feeds
        it into on_new_candle() so the decision engine keeps running.
        """
        while self.running:
            try:
                now = datetime.now(IST)
                time_str = f"{now.hour:02d}:{now.minute:02d}"

                in_window1 = "09:30" <= time_str <= "11:30"
                in_window2 = "14:00" <= time_str <= "14:45"

                if (in_window1 or in_window2) and not self._angel_connected:
                    print("[scheduler] Historical fallback: fetching candles for watchlist")

                    from feeds.data_provider import data_provider
                    for ticker in list(self.watchlist):
                        try:
                            candles, source = data_provider.get_intraday_candles(
                                ticker,
                                interval="FIVE_MINUTE",
                                days_back=1,
                            )
                            if candles and len(candles) >= 2:
                                latest = candles[-1]
                                self.on_new_candle(ticker, "5min", latest)
                        except Exception as exc:
                            print(f"[fallback] {ticker}: {exc}")

            except Exception as exc:
                print(f"[fallback] loop error: {exc}")

            time.sleep(300)  # 5 minutes

    # ──────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Main entry point. Checks trading day, runs pre-market jobs,
        connects Angel One feed, then loops until post_market completes.
        """
        if not self.is_trading_day():
            logger.info("[scheduler] Today is not a trading day — exiting")
            return

        logger.info("[scheduler] ========= MARKET SCHEDULER STARTING =========")
        self.running = True

        # Run initial jobs
        self.pre_market_8am()
        if self.skip_today:
            logger.info("[scheduler] VIX too high — skipping today")
            return

        self.scanner_run_8am()
        self.intelligence_scan()

        # Connect Angel One feed
        try:
            self._feed = AngelOneFeed(on_tick_callback=self.on_tick)
            authenticated = self._feed.authenticate()
            if authenticated:
                tokens = [
                    v for k, v in NIFTY_50_TOKENS.items()
                    if k in self.watchlist
                ]
                self._feed.connect_websocket()
                time.sleep(2)
                self._feed.subscribe(tokens)
                self._angel_connected = True
                logger.info("[scheduler] Angel One feed connected, %d tokens subscribed", len(tokens))
            else:
                self._angel_connected = False
                logger.warning("[scheduler] Angel One auth failed — running without live feed")
        except Exception as exc:
            self._angel_connected = False
            logger.warning("[scheduler] Feed connection failed: %s — continuing", exc)

        # Start historical fallback loop (fires every 5 min when Angel One is offline)
        import threading as _threading
        fallback_thread = _threading.Thread(
            target=self._historical_fallback_loop,
            name="historical-fallback",
            daemon=True,
        )
        fallback_thread.start()
        logger.info("[scheduler] Historical fallback thread started")

        # Set up schedule jobs
        if _SCHEDULE_OK:
            schedule.every(7).minutes.do(self.intelligence_refresh)
            schedule.every(1).seconds.do(self.monitor_loop_tick)
            schedule.every().day.at("15:15").do(self.square_off_3_15pm)
            schedule.every().day.at("15:30").do(self.post_market_3_30pm)
            logger.info("[scheduler] Schedule jobs registered")

        # Main loop
        logger.info("[scheduler] Entering main loop…")
        try:
            while self.running:
                if _SCHEDULE_OK:
                    schedule.run_pending()
                else:
                    self.monitor_loop_tick()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("[scheduler] KeyboardInterrupt — shutting down")
            self.stop()

    def stop(self) -> None:
        """Clean shutdown."""
        logger.info("[scheduler] === STOP ===")
        self.running = False

        # Square off any open positions
        try:
            if auto_broker.positions:
                logger.info("[scheduler] Squaring off %d open positions", len(auto_broker.positions))
                self.square_off_3_15pm()
        except Exception as exc:
            logger.warning("[scheduler] Stop square-off failed: %s", exc)

        # Disconnect feed
        try:
            if self._feed:
                self._feed.disconnect()
                logger.info("[scheduler] Angel One feed disconnected")
        except Exception as exc:
            logger.warning("[scheduler] Feed disconnect error: %s", exc)

        logger.info("[scheduler] ========= SHUTDOWN COMPLETE =========")


# Module-level singleton
market_scheduler = MarketScheduler()
