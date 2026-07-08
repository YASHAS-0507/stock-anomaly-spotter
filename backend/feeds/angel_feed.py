"""
angel_feed.py
-------------
Angel One SmartAPI live market feed connector.

Authentication: pyotp TOTP + SmartConnect REST login
WebSocket:      SmartWebSocketV2 live tick stream
Reconnect:      exponential backoff (5s → 10s → 30s max)
Session cache:  module-level _AngelSession prevents burst re-logins.
                At most ONE real TOTP login per 6-hour window, shared
                across all AngelOneFeed instances in the process.

All credentials are read exclusively from environment variables:
    ANGEL_API_KEY      — Angel One API key
    ANGEL_CLIENT_ID    — Angel One client / user ID
    ANGEL_PASSWORD     — Angel One login password
    ANGEL_TOTP_SECRET  — Base32 TOTP secret from Angel One 2FA setup
"""

import os
import threading
import time
import logging
from datetime import datetime
from typing import Optional, Callable

import pytz

logger = logging.getLogger(__name__)

_IST = pytz.timezone("Asia/Kolkata")

# ── Optional dependency guard ──────────────────────────────────────────────────
try:
    import pyotp
    _PYOTP_AVAILABLE = True
except ImportError:
    _PYOTP_AVAILABLE = False
    pyotp = None  # type: ignore

try:
    from SmartApi import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    _SMARTAPI_AVAILABLE = True
except ImportError:
    try:
        from smartapi import SmartConnect
        from smartapi.smartWebSocketV2 import SmartWebSocketV2
        _SMARTAPI_AVAILABLE = True
    except ImportError:
        _SMARTAPI_AVAILABLE = False
        SmartConnect = None      # type: ignore
        SmartWebSocketV2 = None  # type: ignore
        print("[angel] SmartApi not installed")

# NSE Cash Market exchange type for SmartWebSocketV2
_NSE_EXCHANGE_TYPE = 1

# LTP subscription mode (least bandwidth)
_MODE_LTP = 1

# Backoff schedule in seconds
_BACKOFF = [5, 10, 30]

# Session cache TTL — Angel One JWTs last 24h; we refresh every 6h for safety
_TOKEN_TTL = 21600


# ── Process-wide session cache ─────────────────────────────────────────────────

class _AngelSession:
    """
    Shared JWT session state — at most ONE real TOTP login per _TOKEN_TTL window.
    All AngelOneFeed instances in this process share this cache via class variables.
    threading.Lock prevents concurrent threads from all triggering simultaneous re-auth.
    """
    _lock = threading.Lock()
    api         = None
    auth_token: str   = ""
    feed_token: str   = ""        # cleared on WS close; forces fresh token on reconnect
    expiry:     float = 0.0
    _last_login: float = 0.0      # epoch of last generateSession() call
    _MIN_LOGIN_INTERVAL = 65.0    # Angel One rate limit: max 1 login/minute

    @classmethod
    def is_valid(cls) -> bool:
        # Both auth_token AND feed_token must be present and within TTL.
        # feed_token is cleared on WebSocket close so reconnects always get a fresh one.
        return bool(cls.auth_token) and bool(cls.feed_token) and time.time() < cls.expiry

    @classmethod
    def invalidate(cls) -> None:
        """Force a fresh generateSession() on the next authenticate() call."""
        cls.expiry     = 0.0
        cls.feed_token = ""   # explicit clear — is_valid() checks this too

    @classmethod
    def seconds_since_last_login(cls) -> float:
        return time.time() - cls._last_login


class AngelOneFeed:
    """
    Manages the full lifecycle of an Angel One SmartAPI live feed connection:
    authenticate → connect WebSocket → subscribe → receive ticks → reconnect.
    """

    def __init__(
        self,
        on_tick_callback: Optional[Callable] = None,
        on_disconnect_callback: Optional[Callable] = None,
    ):
        """
        Parameters
        ----------
        on_tick_callback : callable, optional
            Called for every tick with signature:
            callback(ticker: str, price: float, volume: int, timestamp: float)
            Defaults to the shared candle_builder singleton.
        on_disconnect_callback : callable, optional
            Called with no args when the WebSocket closes unexpectedly.
        """
        self._api_key     = os.environ.get("ANGEL_API_KEY", "")
        self._client_id   = os.environ.get("ANGEL_CLIENT_ID", "")
        self._password    = os.environ.get("ANGEL_PASSWORD", "")
        self._totp_secret = os.environ.get("ANGEL_TOTP_SECRET", "")

        self.auth_token:  Optional[str] = None
        self.feed_token:  Optional[str] = None
        self._sws:        Optional[object] = None
        self._api:        Optional[object] = None

        self._subscribed_tokens: list[str] = []
        self._connected:  bool = False
        self._stop_event: threading.Event = threading.Event()
        self._ws_thread:  Optional[threading.Thread] = None
        self._reconnect_attempt: int = 0
        self._on_disconnect_cb: Optional[Callable] = on_disconnect_callback

        # Default tick callback → shared CandleBuilder singleton
        if on_tick_callback is not None:
            self._on_tick_cb = on_tick_callback
        else:
            try:
                from feeds.candle_builder import candle_builder
                self._on_tick_cb = candle_builder.on_tick
            except Exception:
                self._on_tick_cb = None

    # ─────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────

    def authenticate(self) -> bool:
        """
        Authenticate with Angel One SmartAPI.

        Fast path: reuses cached JWT if still within TTL window (≤6h old).
        Slow path: acquires lock, does a real TOTP login, populates cache.

        Returns True on success, False on failure.
        """
        # ── Fast path: cached session still valid ──
        if _AngelSession.is_valid():
            self._api       = _AngelSession.api
            self.auth_token = _AngelSession.auth_token
            self.feed_token = _AngelSession.feed_token
            remaining = int(_AngelSession.expiry - time.time())
            print(f"[angel] Reusing cached session — expires in {remaining}s")
            return True

        # ── Slow path: real TOTP login under lock ──
        with _AngelSession._lock:
            # Double-check after acquiring lock (another thread may have just authenticated)
            if _AngelSession.is_valid():
                self._api       = _AngelSession.api
                self.auth_token = _AngelSession.auth_token
                self.feed_token = _AngelSession.feed_token
                return True

            self._require_deps()
            self._require_credentials()

            now_ist = datetime.now(_IST).strftime("%H:%M:%S IST")
            print(f"[angel] Starting REAL authentication at {now_ist}…")
            print(f"[angel] Client ID: {self._client_id[:4]}…")
            logger.info("[angel_feed] Real TOTP login for client %s at %s", self._client_id, now_ist)

            # Angel One rate limit: 1 generateSession() per minute.
            # Enforce a minimum gap to prevent auth errors during rapid reconnects.
            elapsed = _AngelSession.seconds_since_last_login()
            if elapsed < _AngelSession._MIN_LOGIN_INTERVAL:
                wait = _AngelSession._MIN_LOGIN_INTERVAL - elapsed
                print(f"[angel] Rate limit: waiting {wait:.0f}s before generateSession()")
                logger.info("[angel_feed] Login rate limit — sleeping %.0fs", wait)
                time.sleep(wait)

            try:
                # TOTP must be generated fresh immediately before login
                totp_code = pyotp.TOTP(self._totp_secret).now()
                print(f"[angel] TOTP generated (time-sensitive — using immediately)")
                _AngelSession._last_login = time.time()
            except Exception as exc:
                print(f"[angel] TOTP generation failed: {exc}")
                logger.error("[angel_feed] TOTP generation failed: %s", exc)
                return False

            try:
                self._api = SmartConnect(api_key=self._api_key)
                data = self._api.generateSession(
                    clientCode=self._client_id,
                    password=self._password,
                    totp=totp_code,
                )

                if not data or not data.get("status"):
                    print(f"[angel] generateSession failed: {data}")
                    logger.error("[angel_feed] generateSession failed: %s", data)
                    return False

                self.auth_token = data["data"]["jwtToken"]
                self.feed_token = self._api.getfeedToken()

                print(f"[angel] Auth OK — token prefix: {self.auth_token[:10]}…")
                print(f"[angel] Feed token prefix: {self.feed_token[:10]}…")
                logger.info("[angel_feed] Authenticated: client %s", self._client_id)

                # Populate process-wide cache
                _AngelSession.api        = self._api
                _AngelSession.auth_token = self.auth_token
                _AngelSession.feed_token = self.feed_token
                _AngelSession.expiry     = time.time() + _TOKEN_TTL

                self._reconnect_attempt = 0
                return True

            except Exception as exc:
                print(f"[angel] Authentication error: {exc}")
                logger.error("[angel_feed] Authentication error: %s", exc)
                return False

    def connect_websocket(self) -> None:
        """
        Create a SmartWebSocketV2 instance and start it in a background thread.
        Calls authenticate() first — fast path if session cache is valid.
        """
        self._require_deps()

        print("[angel] WebSocket connecting…")
        ok = self.authenticate()
        if not ok:
            raise RuntimeError("Angel One authentication failed — cannot open WebSocket.")

        self._stop_event.clear()
        self._sws = SmartWebSocketV2(
            auth_token=self.auth_token,
            api_key=self._api_key,
            client_code=self._client_id,
            feed_token=self.feed_token,
        )

        self._sws.on_open  = self._handle_open
        self._sws.on_data  = self._handle_data
        self._sws.on_error = self._handle_error
        self._sws.on_close = self._handle_close

        # SmartWebSocketV2._on_close(self, wsapp) only accepts 2 args, but
        # modern websocket-client calls on_close(ws, close_code, close_reason).
        # Shadow the class method on this instance with a compat wrapper so the
        # signature matches and our disconnect/reconnect logic actually fires.
        _sws_ref = self._sws

        def _compat_on_close(wsapp, close_code=None, close_reason=None):
            logger.info(
                "[angel_feed] WS closed — code=%s reason=%s", close_code, close_reason
            )
            if _sws_ref.on_close:
                _sws_ref.on_close(wsapp)

        self._sws._on_close = _compat_on_close

        self._ws_thread = threading.Thread(
            target=self._run_ws,
            name="angel-ws",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("[angel_feed] WebSocket thread started.")

    def subscribe(self, tokens: list[str]) -> None:
        """
        Subscribe to a list of NSE instrument tokens (numeric strings, e.g. ["2885"]).
        Can be called before or after connect_websocket(); tokens are re-sent on
        every reconnect via _handle_open.
        """
        self._subscribed_tokens = list(tokens)
        print(f"[feed] Subscribed to {len(tokens)} tokens: {tokens}")
        logger.info("[feed] Subscribed to %d tokens: %s", len(tokens), tokens)
        if self._connected and self._sws:
            self._send_subscription()

    def reconnect(self) -> None:
        """
        Disconnect and reconnect with exponential backoff.
        Called internally on connection loss; may also be called externally.
        Respects Angel One rate limit: max 1 reconnect per 5 seconds.
        """
        if self._stop_event.is_set():
            return

        delay = _BACKOFF[min(self._reconnect_attempt, len(_BACKOFF) - 1)]
        self._reconnect_attempt += 1
        logger.warning(
            "[angel_feed] Reconnecting in %ds (attempt %d)…",
            delay, self._reconnect_attempt,
        )
        print(f"[angel_feed] Reconnecting in {delay}s (attempt {self._reconnect_attempt})…")
        time.sleep(delay)

        if self._stop_event.is_set():
            return

        # Feed token is invalidated when the WebSocket closes on the Angel One side.
        # Without clearing the cache, authenticate() fast-paths to the stale feed token,
        # and the new WebSocket immediately disconnects again — causing this loop.
        print("[angel] Clearing session cache — forcing fresh feed token for reconnect")
        logger.info("[angel_feed] Invalidating session cache before reconnect (fresh feed token required)")
        _AngelSession.invalidate()

        self.connect_websocket()

    def disconnect(self) -> None:
        """Clean shutdown — stops reconnect attempts and closes the WebSocket."""
        self._stop_event.set()
        self._connected = False
        if self._sws:
            try:
                self._sws.close_connection()
            except Exception:
                pass
            self._sws = None
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)
        logger.info("[angel_feed] Disconnected.")
        print("[angel_feed] Disconnected.")

    # ─────────────────────────────────────────────────────
    # WebSocket callbacks
    # ─────────────────────────────────────────────────────

    def _handle_open(self, wsapp) -> None:
        self._connected = True
        self._reconnect_attempt = 0
        self._session_tick_count = 0  # reset per-session tick counter
        print("[angel] WebSocket on_open — connection established — waiting for ticks…")
        logger.info("[angel_feed] WebSocket connected.")
        if self._subscribed_tokens:
            self._send_subscription()
        self._start_keepalive()

    def _handle_data(self, wsapp, message) -> None:
        """
        Parse incoming tick and forward to the tick callback.

        SmartWebSocketV2 LTP mode delivers ticks as dicts:
        {
            'token': '2885',
            'last_traded_price': 130350,   # paise → ÷100 = ₹1303.50
            'volume_trade_for_the_day': 45231,
            'exchange_timestamp': 1718000000000,  # milliseconds
        }
        """
        try:
            tick = message if isinstance(message, dict) else {}
            raw_token  = str(tick.get("token", ""))
            raw_ltp    = tick.get("last_traded_price", 0)
            raw_volume = tick.get("volume_trade_for_the_day", 0)
            raw_ts     = tick.get("exchange_timestamp", 0)

            # Angel One NSE equity LTP is in paise; convert to ₹
            price  = round(float(raw_ltp) / 100.0, 2)
            volume = int(raw_volume)

            # exchange_timestamp is milliseconds
            ts = float(raw_ts) / 1000.0 if raw_ts else time.time()

            # Resolve numeric token → ticker symbol (e.g. "2885" → "RELIANCE.NS")
            from feeds.ticker_registry import get_ticker_by_token
            ticker = get_ticker_by_token(raw_token) or raw_token

            ist_time = datetime.now(_IST).strftime("%H:%M:%S")
            self._session_tick_count = getattr(self, "_session_tick_count", 0) + 1
            n = self._session_tick_count
            if n <= 5 or n % 100 == 0:
                print(f"[tick #{n}] symbol={ticker} price={price} time={ist_time}")
            else:
                logger.debug("[tick #%d] %s price=%s", n, ticker, price)

            if self._on_tick_cb and price > 0:
                self._on_tick_cb(ticker, price, volume, ts)

        except Exception as exc:
            logger.error("[angel_feed] Tick parsing error: %s  raw=%s", exc, message)

    def _handle_error(self, wsapp, error) -> None:
        logger.error("[angel_feed] WebSocket error: %s", error)
        print(f"[angel] WebSocket on_error: {error}")

    def _handle_close(self, wsapp, *args) -> None:
        self._connected = False
        reason = (
            str(args[1]) if len(args) >= 2 and args[1]
            else (str(args[0]) if args else "unknown")
        )
        ticks = getattr(self, "_session_tick_count", 0)
        print(f"[angel] WebSocket on_close: {reason} | ticks this session: {ticks}")
        logger.warning("[angel_feed] WebSocket closed — reason: %s | session ticks: %d", reason, ticks)

        # Fire disconnect callback so callers can activate fallback
        if self._on_disconnect_cb is not None:
            try:
                self._on_disconnect_cb()
            except Exception:
                pass

        if not self._stop_event.is_set():
            time.sleep(5)
            self.reconnect()

    # ─────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────

    def _run_ws(self) -> None:
        """Target for the background WebSocket thread."""
        try:
            self._sws.connect()
        except Exception as exc:
            logger.error("[angel_feed] WebSocket run error: %s", exc)
            if not self._stop_event.is_set():
                self.reconnect()

    def _send_subscription(self) -> None:
        """Send subscribe request for all registered tokens (LTP mode, NSE cash segment)."""
        if not self._sws or not self._subscribed_tokens:
            return
        token_list = [{"exchangeType": _NSE_EXCHANGE_TYPE, "tokens": self._subscribed_tokens}]
        n = len(self._subscribed_tokens)
        print(f"[feed] Sending subscription for {n} tokens (exchangeType=1 NSE cash, mode=LTP)")
        logger.info("[feed] Sending subscription for %d tokens", n)
        try:
            self._sws.subscribe(
                correlation_id="angel_feed",
                mode=_MODE_LTP,
                token_list=token_list,
            )
            print(f"[feed] Subscription ACK — {n} tokens active")
            logger.info("[feed] Subscription ACK for %d tokens", n)
        except Exception as exc:
            logger.error("[angel_feed] Subscription error: %s", exc)
            print(f"[angel] Subscription error: {exc}")

    def _start_keepalive(self) -> None:
        """Daemon thread that pings the WebSocket every 30 seconds."""
        def _keepalive_loop():
            while not self._stop_event.is_set():
                time.sleep(30)
                if self._connected and self._sws:
                    try:
                        if hasattr(self._sws, "wsapp") and self._sws.wsapp:
                            sock = getattr(self._sws.wsapp, "sock", None)
                            if sock:
                                sock.ping()
                    except Exception:
                        pass

        t = threading.Thread(target=_keepalive_loop, name="angel-keepalive", daemon=True)
        t.start()

    @staticmethod
    def _require_deps() -> None:
        missing = []
        if not _SMARTAPI_AVAILABLE:
            missing.append("smartapi-python")
        if not _PYOTP_AVAILABLE:
            missing.append("pyotp")
        if missing:
            raise ImportError(
                f"Missing required packages: {', '.join(missing)}. "
                f"Run: pip install {' '.join(missing)}"
            )

    # ─────────────────────────────────────────────────────
    # Historical data API
    # ─────────────────────────────────────────────────────

    def get_historical_candles(
        self,
        symbol_token: str,
        interval: str,
        from_date: str,
        to_date: str,
        exchange: str = "NSE",
    ) -> list:
        """
        Fetches historical OHLCV candles from Angel One.

        Parameters
        ----------
        symbol_token : str  — Angel One numeric token (e.g. "2885")
        interval     : str  — one of ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                              THIRTY_MINUTE, ONE_HOUR, ONE_DAY
        from_date    : str  — "YYYY-MM-DD HH:MM" in IST
        to_date      : str  — "YYYY-MM-DD HH:MM" in IST
        exchange     : str  — "NSE" (default, NSE cash segment)

        Returns list of dicts: {timestamp, open, high, low, close, volume}
        Returns [] on any error.
        """
        try:
            if not self.auth_token:
                ok = self.authenticate()
                if not ok:
                    print("[angel_feed] get_historical_candles: auth failed")
                    return []

            params = {
                "exchange":    exchange,
                "symboltoken": symbol_token,
                "interval":    interval,
                "fromdate":    from_date,
                "todate":      to_date,
            }
            response = self._api.getCandleData(params)

            if not response or not response.get("status"):
                err_msg = str(response).lower() if response else ""
                if "unauthori" in err_msg or "token" in err_msg or "access" in err_msg:
                    print("[angel_feed] Auth error in getCandleData — invalidating session")
                    _AngelSession.invalidate()
                print(f"[angel_feed] getCandleData error: {response}")
                return []

            rows = response.get("data") or []
            candles = []
            for row in rows:
                try:
                    # Row format: [timestamp, open, high, low, close, volume]
                    candles.append({
                        "timestamp": str(row[0]),
                        "open":      round(float(row[1]), 4),
                        "high":      round(float(row[2]), 4),
                        "low":       round(float(row[3]), 4),
                        "close":     round(float(row[4]), 4),
                        "volume":    int(row[5]) if len(row) > 5 else 0,
                    })
                except Exception as row_exc:
                    print(f"[angel_feed] Row parse error: {row_exc}  row={row}")
            return candles

        except Exception as exc:
            print(f"[angel_feed] get_historical_candles error: {exc}")
            return []

    def get_warmup_candles(
        self,
        symbol_token: str,
        days_back: int = 30,
    ) -> dict:
        """
        Gets last N days of 5-min and 1-min candles for model warmup.
        Returns {"1min": list, "5min": list}.
        All timestamps constructed in IST to comply with Angel One API requirements.
        """
        now   = datetime.now(_IST)
        from datetime import timedelta
        start = now - timedelta(days=days_back)
        from_date = start.strftime("%Y-%m-%d %H:%M")
        to_date   = now.strftime("%Y-%m-%d %H:%M")

        candles_5min = self.get_historical_candles(
            symbol_token, "FIVE_MINUTE", from_date, to_date
        )
        candles_1min = self.get_historical_candles(
            symbol_token, "ONE_MINUTE", from_date, to_date
        )
        return {"1min": candles_1min, "5min": candles_5min}

    def get_symbol_token(self, ticker: str) -> str:
        """
        Returns Angel One symbol token for a ticker.
        Looks up NIFTY_50_TOKENS registry first; falls back to Angel One searchScrip.
        Returns empty string if not found.
        """
        try:
            from feeds.ticker_registry import NIFTY_50_TOKENS
            token = NIFTY_50_TOKENS.get(ticker, "")
            if token:
                return token

            # Strip .NS suffix and try instrument search via Angel One
            scrip = ticker.replace(".NS", "").replace(".BO", "")
            if self.authenticate():
                try:
                    result = self._api.searchScrip("NSE", scrip)
                    if result and result.get("data"):
                        for item in result["data"]:
                            if item.get("tradingsymbol", "").upper() == scrip.upper():
                                return str(item.get("symboltoken", ""))
                except Exception:
                    pass
        except Exception as exc:
            print(f"[angel_feed] get_symbol_token error for {ticker}: {exc}")
        return ""

    def _require_credentials(self) -> None:
        missing = [
            name for name, val in [
                ("ANGEL_API_KEY",     self._api_key),
                ("ANGEL_CLIENT_ID",   self._client_id),
                ("ANGEL_PASSWORD",    self._password),
                ("ANGEL_TOTP_SECRET", self._totp_secret),
            ]
            if not val
        ]
        if missing:
            raise EnvironmentError(
                f"Missing environment variables: {', '.join(missing)}"
            )
