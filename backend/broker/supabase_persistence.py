"""
supabase_persistence.py
-----------------------
Thin wrapper around the Supabase Python client for paper-broker state.

All public functions:
  - Never raise — log WARNING on failure and return None / empty.
  - Are designed to be called from background threads so DB latency
    never blocks order execution.

Required env vars: SUPABASE_URL, SUPABASE_KEY
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

_client      = None
_client_lock = threading.Lock()


# ── Client factory (lazy, singleton) ─────────────────────────────────────────

def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        if not url or not key:
            logger.warning("[supabase] SUPABASE_URL / SUPABASE_KEY not set — persistence disabled")
            return None
        try:
            from supabase import create_client
            _client = create_client(url, key)
            logger.info("[supabase] Client initialised (url=%s…)", url[:30])
        except Exception as exc:
            logger.warning("[supabase] Client init failed: %s", exc)
        return _client


def is_available() -> bool:
    return _get_client() is not None


# ── State load (synchronous — called once at startup) ────────────────────────

def load_broker_state() -> dict | None:
    """
    Read broker_state row (id=1).
    Returns the row as a dict, or None on failure / missing row.
    """
    try:
        sb = _get_client()
        if sb is None:
            return None
        resp = sb.table("broker_state").select("*").eq("id", 1).execute()
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("[supabase] load_broker_state failed: %s", exc)
        return None


def load_trades_today(today_str: str) -> list:
    """
    Return all paper_trades rows for today (trading_date = today_str 'YYYY-MM-DD').
    """
    try:
        sb = _get_client()
        if sb is None:
            return []
        resp = (
            sb.table("paper_trades")
            .select("*")
            .eq("trading_date", today_str)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("[supabase] load_trades_today failed: %s", exc)
        return []


# ── State writes (fire-and-forget background thread) ─────────────────────────

def _run_in_thread(fn):
    """Run fn() in a daemon thread — caller gets control back immediately."""
    t = threading.Thread(target=fn, daemon=True)
    t.start()


def upsert_broker_state(capital: float, daily_pnl: float, daily_loss: float, today_str: str) -> None:
    """Upsert broker_state row (id=1) — non-blocking."""
    def _do():
        try:
            sb = _get_client()
            if sb is None:
                return
            sb.table("broker_state").upsert({
                "id":           1,
                "capital":      round(capital,    2),
                "daily_pnl":    round(daily_pnl,  2),
                "daily_loss":   round(daily_loss, 2),
                "trading_date": today_str,
                "updated_at":   _now_iso(),
            }).execute()
        except Exception as exc:
            logger.warning("[supabase] upsert_broker_state failed: %s", exc)
    _run_in_thread(_do)


def insert_trade(position: dict, today_str: str, features: dict = None) -> None:
    """
    Insert a new (open) trade row into paper_trades on fill.
    Exit fields (exit_price, pnl, exit_reason, exit_time) are NULL until close.
    features_json stores the feature snapshot that triggered the signal.
    Non-blocking.
    """
    def _do():
        try:
            sb = _get_client()
            if sb is None:
                return
            row = {
                "id":           position["trade_id"],
                "ticker":       position["ticker"],
                "setup":        position.get("setup_type", ""),
                "entry_price":  round(float(position["fill_price"]), 4),
                "quantity":     int(position["shares"]),
                "entry_time":   _parse_ist_to_iso(position.get("opened_at", "")),
                "trading_date": today_str,
                "outcome":      None,
            }
            if features:
                row["features_json"] = {
                    k: (bool(v) if isinstance(v, bool)
                        else float(v) if isinstance(v, (int, float))
                        else v)
                    for k, v in features.items()
                }
            sb.table("paper_trades").insert(row).execute()
        except Exception as exc:
            logger.warning("[supabase] insert_trade failed: %s", exc)
    _run_in_thread(_do)


def update_trade_close(trade: dict) -> None:
    """
    Update paper_trades with exit fields + outcome after a position closes.
    outcome: 1 = win (pnl > 0), 0 = loss (pnl <= 0).
    Non-blocking.
    """
    def _do():
        try:
            sb = _get_client()
            if sb is None:
                return
            pnl = float(trade.get("pnl", 0.0))
            sb.table("paper_trades").update({
                "exit_price":  round(float(trade["exit_price"]), 4),
                "pnl":         round(pnl, 2),
                "exit_reason": trade.get("close_reason", ""),
                "exit_time":   _parse_ist_to_iso(trade.get("closed_at", "")),
                "outcome":     1 if pnl > 0 else 0,
            }).eq("id", trade["trade_id"]).execute()
        except Exception as exc:
            logger.warning("[supabase] update_trade_close failed: %s", exc)
    _run_in_thread(_do)


def fetch_all_trades(limit: int = 500) -> list:
    """
    Fetch up to `limit` trades from paper_trades, newest first.
    Returns [] on failure.
    """
    try:
        sb = _get_client()
        if sb is None:
            return []
        resp = (
            sb.table("paper_trades")
            .select("*")
            .order("entry_time", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("[supabase] fetch_all_trades failed: %s", exc)
        return []


def fetch_trades_by_date_range(days: int = 30) -> list:
    """
    Fetch trades for the past `days` calendar days.
    """
    try:
        sb = _get_client()
        if sb is None:
            return []
        from datetime import datetime, timedelta, timezone, date
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        resp = (
            sb.table("paper_trades")
            .select("*")
            .gte("trading_date", cutoff)
            .order("entry_time", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as exc:
        logger.warning("[supabase] fetch_trades_by_date_range failed: %s", exc)
        return []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime
    import pytz
    return datetime.now(pytz.utc).isoformat()


def _parse_ist_to_iso(ts_str: str) -> str | None:
    """Convert '2026-07-09 09:45:00 IST' → ISO-8601 with UTC offset, or None."""
    if not ts_str:
        return None
    try:
        import pytz
        from datetime import datetime
        IST = pytz.timezone("Asia/Kolkata")
        cleaned = ts_str.replace(" IST", "").strip()
        dt = IST.localize(datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S"))
        return dt.isoformat()
    except Exception:
        return ts_str  # pass raw string; Supabase will reject if unparseable
