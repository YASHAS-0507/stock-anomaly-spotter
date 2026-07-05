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
    from SmartApi.SmartWebSocketV2 import SmartWebSocketV2
    _SMARTAPI_AVAILABLE = True
except ImportError:
    _SMARTAPI_AVAILABLE = False
    SmartConnect = None      # type: ignore
    SmartWebSocketV2 = None  # type: ignore

# NSE Cash Market exchange type for SmartWebSocketV2
_NSE_EXCHANGE_TYPE = 1

# LTP subscription mode (least bandwidth)
_MODE_LTP = 1

# Backoff schedule in seconds
_BACKOFF = [5, 10, 30]


class AngelOneFeed:
    """
    Manages the full lifecycle of an Angel One SmartAPI live feed connection:
    authenticate → connect WebSocket → subscribe → receive ticks → reconnect.
    """

    def __init__(self, on_tick_callback=None):
        """
        Parameters
        ----------
        on_tick_callback : callable, optional
            Called for every tick with signature:
            callback(ticker: str, price: float, volume: int, timestamp: float)
            Defaults to the shared candle_builder singleton.
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
        Generate a TOTP code and authenticate with Angel One SmartAPI.
        Stores auth_token and feed_token for WebSocket use.

        Returns True on success, False on failure.
        """
        self._require_deps()
        self._require_credentials()

        try:
            totp_code = pyotp.TOTP(self._totp_secret).now()
        except Exception as exc:
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
                logger.error("[angel_feed] generateSession failed: %s", data)
                return False

            self.auth_token = data["data"]["jwtToken"]
            self.feed_token = self._api.getfeedToken()

            logger.info("[angel_feed] Authenticated: Client ID %s", self._client_id)
            print(f"Authenticated: Client ID {self._client_id}")
            self._reconnect_attempt = 0
            return True

        except Exception as exc:
            logger.error("[angel_feed] Authentication error: %s", exc)
            return False

    def connect_websocket(self) -> None:
        """
        Create a SmartWebSocketV2 instance and start it in a background thread.
        Authenticate first if auth_token is not yet available.
        """
        self._require_deps()

        if not self.auth_token:
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

        # Re-authenticate to get a fresh token, then re-connect
        ok = self.authenticate()
        if ok:
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
        logger.info("[angel_feed] WebSocket connected.")
        print("WebSocket connected")
        if self._subscribed_tokens:
            self._send_subscription()

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
        print(f"[angel_feed] WebSocket error: {error}")

    def _handle_close(self, wsapp) -> None:
        self._connected = False
        logger.warning("[angel_feed] WebSocket closed.")
        print("[angel_feed] WebSocket closed.")
        if not self._stop_event.is_set():
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
        try:
            self._sws.subscribe(
                correlation_id="angel_feed",
                mode=_MODE_LTP,
                token_list=token_list,
            )
            logger.info("[angel_feed] Subscribed to tokens: %s", self._subscribed_tokens)
            print(f"Subscribed to tokens: {self._subscribed_tokens}")
        except Exception as exc:
            logger.error("[angel_feed] Subscription error: %s", exc)

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
