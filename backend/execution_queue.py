"""
execution_queue.py
------------------
Tracks every trade decision through its full lifecycle in memory.
Max size is bounded to prevent unbounded growth in long-running deployments.
"""

from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))

# Status lifecycle (never auto-assign completed/cancelled — reserved for Phase 2.4)
_AUTO_STATUS_RULES = {
    "BUY":     "approved",    # execution_permitted must also be True
    "SELL":    "approved",
    "HOLD":    "pending",
    "BLOCKED": "rejected",
}


def _ist_now() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _trade_id(ticker: str) -> str:
    ts = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    safe = ticker.upper().replace(".", "_")
    return f"TRD-{safe}-{ts}"


class ExecutionQueue:
    def __init__(self, max_size: int = 100):
        self._queue: deque = deque(maxlen=max_size)

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def add(self, decision: dict, ticker: str) -> dict:
        """Create a queue entry from a decision payload and append it."""
        signal = decision.get("decision", "BLOCKED")
        execution_permitted = decision.get("execution_permitted", False)

        # Approved only when signal is BUY/SELL *and* execution was permitted
        if signal in ("BUY", "SELL") and execution_permitted:
            auto_status = "approved"
        else:
            auto_status = _AUTO_STATUS_RULES.get(signal, "rejected")

        entry = {
            "trade_id":         _trade_id(ticker),
            "ticker":           ticker.upper(),
            "timestamp":        _ist_now(),
            "status":           auto_status,
            "decision":         signal,
            "confidence":       decision.get("confidence"),
            "score":            decision.get("score"),
            "risk":             decision.get("risk"),
            "entry_price":      decision.get("entry_price"),
            "stop_loss":        decision.get("stop_loss"),
            "take_profit":      decision.get("take_profit"),
            "position_size":    decision.get("position_size"),
            "rejection_reason": decision.get("rejection_reason"),
            "explanation":      decision.get("explanation"),
            "execution_time_ms": decision.get("inference_time_ms"),
            "auto_status":      auto_status,
        }

        # Prepend so newest is first when iterating
        self._queue.appendleft(entry)
        return entry

    def update_status(self, trade_id: str, status: str, reason: Optional[str] = None) -> bool:
        """Update the status of an existing entry. Returns True if found."""
        for entry in self._queue:
            if entry["trade_id"] == trade_id:
                entry["status"] = status
                if reason is not None:
                    entry["rejection_reason"] = reason
                return True
        return False

    def get_all(self) -> list:
        """Return all entries, newest first."""
        return list(self._queue)

    def get_by_status(self, status: str) -> list:
        return [e for e in self._queue if e["status"] == status]

    def get_stats(self) -> dict:
        entries = list(self._queue)
        counts = {}
        for e in entries:
            counts[e["status"]] = counts.get(e["status"], 0) + 1

        approved = [e for e in entries if e["status"] == "approved"]
        completed = [e for e in entries if e["status"] == "completed"]
        win_rate = None
        if completed:
            # Placeholder: future Phase 2.4 will fill this from paper trading results
            win_rate = None

        return {
            "total":     len(entries),
            "approved":  counts.get("approved", 0),
            "pending":   counts.get("pending", 0),
            "rejected":  counts.get("rejected", 0),
            "completed": counts.get("completed", 0),
            "cancelled": counts.get("cancelled", 0),
            "win_rate":  win_rate,
        }

    def clear_completed(self) -> int:
        """Remove completed/cancelled entries older than 24 hours. Returns count removed."""
        now = datetime.now(IST)
        cutoff_statuses = {"completed", "cancelled"}
        to_remove = []

        for entry in list(self._queue):
            if entry["status"] not in cutoff_statuses:
                continue
            try:
                # Timestamp format: "YYYY-MM-DD HH:MM:SS IST"
                ts_str = entry["timestamp"].replace(" IST", "")
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
                age_h = (now - ts).total_seconds() / 3600
                if age_h > 24:
                    to_remove.append(entry["trade_id"])
            except Exception:
                pass

        before = len(self._queue)
        self._queue = deque(
            (e for e in self._queue if e["trade_id"] not in to_remove),
            maxlen=self._queue.maxlen,
        )
        return before - len(self._queue)


# Singleton
execution_queue = ExecutionQueue(max_size=100)
