"""
tv_signals_store.py
-------------------
Shared in-memory store for TradingView webhook signals.
Imported by both app.py (writes) and market_scheduler.py (reads).
Using a shared module avoids circular imports between app and scheduler.
"""

tv_signals: dict = {}  # ticker → {score, action, price, strategy, timestamp}
