"""
angel_feed.py
-------------
Angel One SmartAPI live market feed connector.

Authentication: pyotp TOTP + SmartConnect REST login
WebSocket:      SmartWebSocketV2 live tick stream
Reconnect:      exponential backoff (5s → 10s → 30s max)

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
from typing import Optional

logger = logging.getLogger(__name__)

# ── Optional dependency guard ──────────────────────────────────────────────────
# Imported lazily so the module is importable even if smartapi-python / pyotp
# are not yet installed (e.g., during syntax checks).
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

# ── Module-level session cache ─────────────────────────────────────────────────
# Angel One JWTs last until IST midnight. We cache for 6 hours conservatively.
# This prevents a fresh TOTP login on every per-ticker data_provider call.
_TOKEN_TTL = 21600  # 6 hours in seconds


class _AngelSession:
    """Shared session state — one real TOTP login per _TOKEN_TTL window."""
    _lock = threading.Lock()
    api        = None
    auth_token: str   = ""
    feed_token: str   = ""
    expiry:     float = 0.0

    @classmethod
    def is_valid(cls) -> bool:
        return bool(cls.auth_token) and time.time() < cls.expiry

    @classmethod
    def invalidate(cls) -> None:
        """Force re-auth on next authenticate() call (e.g. after an API 401)."""
        cls.expiry = 0.0


class AngelOneFeed:
    """
    Manages the full lifecycle of an Angel One SmartAPI live feed connection:
    authenticate → connect WebSocket → subscribe → receive ticks → reconnect.
    """

    def __init__(self, on_tick_callback=None, on_disconnect_callback=None):
        """
        Parameters
        ----------
        on_tick_callback : callable, optional
            Called for every tick with signature:
            callback(ticker: str, price: float, volume: int, timestamp: float)
            Defaults to the shared candle_builder singleton.
        on_disconnect_callback : callable, optional
            Called with no arguments when the WebSocket closes unexpectedly.
            Used by the scheduler to reset its _angel_connected flag.
        """
        self._api_key    = os.environ.get("ANGEL_API_KEY", "")
        self._client_id  = os.environ.get("ANGEL_CLIENT_ID", "")
        self._password   = os.environ.get("ANGEL_PASSWORD", "")
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

        self._on_disconnect_cb = on_disconnect_callback

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
        Authenticate with Angel One SmartAPI, reusing a cached JWT when valid.

        A module-level _AngelSession caches the JWT for _TOKEN_TTL seconds (6h).
        Only one real TOTP login happens per TTL window regardless of how many
        AngelOneFeed instances or concurrent threads call this method.

        Returns True on success, False on failure.
        """
        self._require_deps()
        self._require_credentials()

        # ── Fast path: reuse cached session ───────────────────────────────
        if _AngelSession.is_valid():
            self.auth_token = _AngelSession.auth_token
            self.feed_token = _AngelSession.feed_token
            self._api       = _AngelSession.api
            remaining = int(_AngelSession.expiry - time.time())
            logger.debug("[angel_feed] Reusing cached session (%ds remaining)", remaining)
            print(f"[angel] Reusing cached session ({remaining}s remaining)")
            return True

        # ── Slow path: acquire lock, re-check, then real TOTP login ───────
        with _AngelSession._lock:
            if _AngelSession.is_valid():  # another thread refreshed while we waited
                self.auth_token = _AngelSession.auth_token
                self.feed_token = _AngelSession.feed_token
                self._api       = _AngelSession.api
                print("[angel] Session refreshed by peer thread — reusing")
                return True

            from datetime import datetime as _dt
            print("[angel] Starting fresh authentication (no valid cached session)...")
            print(f"[angel] Client ID: {self._client_id[:4]}...")
            logger.info("[angel_feed] Authenticating client %s…", self._client_id)

            try:
                totp_code = pyotp.TOTP(self._totp_secret).now()
                print(f"[angel] TOTP code: {totp_code}")
                print(f"[angel] Current time: {_dt.now()}")
            except Exception as exc:
                print(f"[angel] TOTP generation failed: {exc}")
                logger.error("[angel_feed] TOTP generation failed: %s", exc)
                return False

            try:
                api  = SmartConnect(api_key=self._api_key)
                data = api.generateSession(
                    clientCode=self._client_id,
                    password=self._password,
                    totp=totp_code,
                )

                if not data or not data.get("status"):
                    print(f"[angel] generateSession failed: {data}")
                    logger.error("[angel_feed] generateSession failed: %s", data)
                    return False

                auth_token = data["data"]["jwtToken"]
                feed_token = api.getfeedToken()

                # Populate shared cache
                _AngelSession.api        = api
                _AngelSession.auth_token = auth_token
                _AngelSession.feed_token = feed_token
                _AngelSession.expiry     = time.time() + _TOKEN_TTL

                self._api        = api
                self.auth_token  = auth_token
                self.feed_token  = feed_token

                print(f"[angel] Auth result: {self.auth_token[:10]}...")
                print(f"[angel] Feed token: {self.feed_token[:10]}...")
                logger.info(
                    "[angel_feed] Fresh auth complete: client %s, session valid %dh",
                    self._client_id, _TOKEN_TTL // 3600,
                )
                self._reconnect_attempt = 0
                return True

            except Exception as exc:
                print(f"[angel] Authentication error: {exc}")
                logger.error("[angel_feed] Authentication error: %s", exc)
                return False

    def connect_websocket(self) -> None:
        """
        Create a SmartWebSocketV2 instance and start it in a background thread.
        Always re-authenticates to ensure a fresh TOTP token before connecting.
        """
        self._require_deps()

        # Always generate a fresh TOTP and authenticate before each connect
        print(f"[angel] WebSocket connecting to feed...")
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

        self._sws.on_open    = self._handle_open
        self._sws.on_data    = self._handle_data
        self._sws.on_error   = self._handle_error
        self._sws.on_close   = self._handle_close

        self._ws_thread = threading.Thread(
            target=self._run_ws,
            name="angel-ws",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("[angel_feed] WebSocket thread started.")

    def subscribe(self, tokens: list[str]) -> None:
        """
        Subscribe to a list of NSE instrument tokens (as strings, e.g. ["2885"]).
        Can be called before or after connect_websocket(); tokens are re-sent on
        every reconnect.
        """
        self._subscribed_tokens = list(tokens)
        if self._connected and self._sws:
            self._send_subscription()

    def reconnect(self) -> None:
        """
        Disconnect and reconnect with exponential backoff.
        Called internally on connection loss; may also be called externally.
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

        # connect_websocket() authenticates internally (cache hit if token still valid)
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
        print("[angel] WebSocket on_open called")
        logger.info("[angel_feed] WebSocket connected.")
        if self._subscribed_tokens:
            self._send_subscription()
        self._start_keepalive()

    def _handle_data(self, wsapp, message) -> None:
        """
        Parse incoming tick and forward to the tick callback.

        SmartWebSocketV2 delivers LTP ticks as dicts:
        {
            'token': '2885',
            'last_traded_price': 130350,   # paise → ÷100 = ₹1303.50
            'volume_trade_for_the_day': 45231,
            'exchange_timestamp': 1718000000000,  # milliseconds
            ...
        }
        """
        try:
            tick = message if isinstance(message, dict) else {}
            raw_token  = str(tick.get("token", ""))
            raw_ltp    = tick.get("last_traded_price", 0)
            raw_volume = tick.get("volume_trade_for_the_day", 0)
            raw_ts     = tick.get("exchange_timestamp", 0)

            # LTP from Angel One is in paise for NSE equity; convert to ₹
            price = round(float(raw_ltp) / 100.0, 2)
            volume = int(raw_volume)

            # Timestamp: exchange_timestamp is in milliseconds
            ts = float(raw_ts) / 1000.0 if raw_ts else time.time()

            # Resolve token → ticker symbol
            from feeds.ticker_registry import get_ticker_by_token
            ticker = get_ticker_by_token(raw_token) or raw_token

            print(
                f"{time.strftime('%H:%M:%S')}  {ticker}  LTP=₹{price:.2f}"
                f"  Vol={volume}"
            )

            if self._on_tick_cb and price > 0:
                self._on_tick_cb(ticker, price, volume, ts)

        except Exception as exc:
            logger.error("[angel_feed] Tick parsing error: %s  raw=%s", exc, message)

    def _handle_error(self, wsapp, error) -> None:
        logger.error("[angel_feed] WebSocket error: %s", error)
        print(f"[angel] WebSocket on_error: {error}")

    def _handle_close(self, wsapp, *args) -> None:
        self._connected = False
        # Extract close reason from optional args (close_status_code, close_msg)
        reason = str(args[1]) if len(args) >= 2 and args[1] else (str(args[0]) if args else "unknown")
        print(f"[angel] WebSocket on_close: {reason}")
        logger.warning("[angel_feed] WebSocket closed — reason: %s", reason)
        if self._on_disconnect_cb:
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
        """Send subscribe request for all registered tokens (LTP mode, NSE)."""
        if not self._sws or not self._subscribed_tokens:
            return
        token_list = [{"exchangeType": _NSE_EXCHANGE_TYPE, "tokens": self._subscribed_tokens}]
        print(f"[angel] Subscribing {len(self._subscribed_tokens)} tickers")
        logger.info("[angel_feed] Subscribing to %d tokens…", len(self._subscribed_tokens))
        try:
            self._sws.subscribe(
                correlation_id="angel_feed",
                mode=_MODE_LTP,
                token_list=token_list,
            )
            print("[angel] Subscribed successfully")
            logger.info("[angel_feed] Subscribed to tokens: %s", self._subscribed_tokens)
        except Exception as exc:
            logger.error("[angel_feed] Subscription error: %s", exc)

    def _start_keepalive(self) -> None:
        """Start a daemon thread that pings the WebSocket every 30 seconds."""
        def _keepalive_loop():
            while not self._stop_event.is_set():
                time.sleep(30)
                if self._connected and self._sws:
                    try:
                        # Attempt ping via underlying websocket socket
                        if hasattr(self._sws, "wsapp") and self._sws.wsapp:
                            sock = getattr(self._sws.wsapp, "sock", None)
                            if sock:
                                sock.ping()
                    except Exception:
                        pass  # Ping failure is non-fatal; reconnect handles dropout

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

        interval options: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                          THIRTY_MINUTE, ONE_HOUR, ONE_DAY
        from_date/to_date format: "YYYY-MM-DD HH:MM"

        Returns list of dicts with keys:
          timestamp, open, high, low, close, volume
        Returns empty list on any error.
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
                print(f"[angel_feed] getCandleData error: {response}")
                # If the error looks like an auth expiry, invalidate the session cache
                err_msg = str(response).lower() if response else ""
                if "unauthori" in err_msg or "token" in err_msg or "access" in err_msg:
                    _AngelSession.invalidate()
                    logger.warning("[angel_feed] Auth error detected — session cache invalidated")
                return []

            rows = response.get("data") or []
            candles = []
            for row in rows:
                try:
                    # Each row: [timestamp, open, high, low, close, volume]
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
        Gets last N days of 5min and 1min candles for model warmup.
        Returns {"1min": list, "5min": list}.
        Handles IST timezone correctly.
        """
        from datetime import datetime, timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        now   = datetime.now(IST)
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
        Looks up NIFTY_50_TOKENS first; falls back to Angel One instrument search.
        Returns empty string if not found.
        """
        try:
            from feeds.ticker_registry import NIFTY_50_TOKENS
            token = NIFTY_50_TOKENS.get(ticker, "")
            if token:
                return token

            # Strip .NS suffix and try instrument search via Angel One
            scrip = ticker.replace(".NS", "").replace(".BO", "")
            if self.auth_token or self.authenticate():
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
                ("ANGEL_API_KEY",    self._api_key),
                ("ANGEL_CLIENT_ID",  self._client_id),
                ("ANGEL_PASSWORD",   self._password),
                ("ANGEL_TOTP_SECRET", self._totp_secret),
            ]
            if not val
        ]
        if missing:
            raise EnvironmentError(
                f"Missing environment variables: {', '.join(missing)}"
            )
