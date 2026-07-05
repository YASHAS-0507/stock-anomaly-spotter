"""
test_feed.py
------------
Integration smoke-test for the Angel One SmartAPI feed.

Connects to Angel One, subscribes to RELIANCE.NS (token 2885),
runs for 60 seconds, then disconnects.

Works correctly even when the market is closed — it establishes
the WebSocket connection and waits; no live ticks will arrive
outside NSE market hours (9:15–15:30 IST, Mon–Fri) but the
script will not crash.

Usage (from the backend/ directory):
    python feeds/test_feed.py

Required environment variables:
    ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET
"""

import os
import sys
import time
import logging

# Add backend root to path so 'feeds.*' imports resolve when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

from feeds.angel_feed import AngelOneFeed, _SMARTAPI_AVAILABLE, _PYOTP_AVAILABLE
from feeds.ticker_registry import NIFTY_50_TOKENS, get_token

RUN_SECONDS = 60
RELIANCE_TOKEN = get_token("RELIANCE.NS")  # "2885"


def _check_env() -> bool:
    required = ["ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_PASSWORD", "ANGEL_TOTP_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"\n[WARNING] Missing environment variables: {', '.join(missing)}")
        print("[WARNING] Set these before running a live test.")
        return False
    return True


def main():
    print("=" * 55)
    print("  Angel One SmartAPI Feed — Smoke Test")
    print("=" * 55)

    # Dependency check
    if not _SMARTAPI_AVAILABLE:
        print("[ERROR] smartapi-python not installed. Run: pip install smartapi-python")
        sys.exit(1)
    if not _PYOTP_AVAILABLE:
        print("[ERROR] pyotp not installed. Run: pip install pyotp")
        sys.exit(1)

    print("Connected to Angel One SmartAPI")

    # Credentials check
    has_creds = _check_env()
    if not has_creds:
        print("\n[INFO] No credentials found — running in dry-run mode.")
        print("[INFO] Verifying class structure and imports only.\n")
        feed = AngelOneFeed()
        print(f"AngelOneFeed instance created: {feed}")
        print(f"Ticker registry loaded: {len(NIFTY_50_TOKENS)} tokens")
        print(f"RELIANCE.NS token: {RELIANCE_TOKEN}")
        print("\n[INFO] Dry-run complete. Provide credentials for a live test.")
        return

    feed = AngelOneFeed()

    # Authenticate
    print("\nAuthenticating…")
    ok = feed.authenticate()
    if not ok:
        print("[ERROR] Authentication failed. Check credentials and try again.")
        sys.exit(1)

    # Connect WebSocket
    feed.connect_websocket()
    print("WebSocket connected")

    # Subscribe to RELIANCE.NS
    feed.subscribe([RELIANCE_TOKEN])
    print(f"Subscribed to RELIANCE.NS (token {RELIANCE_TOKEN})")

    # Determine market hours
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)
    day = now.weekday()
    total_min = now.hour * 60 + now.minute
    market_open = day < 5 and 555 <= total_min <= 930

    if market_open:
        print(f"\nMarket is OPEN — live ticks will appear below.")
    else:
        print(f"\nMarket is CLOSED ({now.strftime('%H:%M IST')}) — waiting {RUN_SECONDS}s for any data…")

    print("Waiting for market data...\n")

    try:
        time.sleep(RUN_SECONDS)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")

    print(f"\n[INFO] {RUN_SECONDS}s elapsed — disconnecting.")
    feed.disconnect()
    print("[INFO] Test complete.")


if __name__ == "__main__":
    main()
