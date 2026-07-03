"""
decision_logger.py
------------------
Appends every decision to disk in JSONL and CSV formats for audit trail
and offline analysis. Never raises — all I/O is wrapped in try/except.
"""

import csv
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))

_CSV_FIELDS = [
    "timestamp", "ticker", "decision", "confidence", "score", "risk",
    "execution_permitted", "rejection_reason", "entry_price", "stop_loss",
    "rr_ratio", "inference_time_ms", "queue_status", "trade_id",
]


class DecisionLogger:
    def __init__(self, log_dir: str = "decision_logs"):
        self._dir = Path(log_dir)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[decision_logger] WARNING: could not create log dir: {e}")

        self._jsonl_path = self._dir / "decisions.jsonl"
        self._csv_path   = self._dir / "decisions.csv"

        # Write CSV header if file is new/empty
        try:
            if not self._csv_path.exists() or self._csv_path.stat().st_size == 0:
                with open(self._csv_path, "w", newline="") as f:
                    csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()
        except Exception as e:
            print(f"[decision_logger] WARNING: could not initialise CSV: {e}")

    # ──────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────

    def log(
        self,
        ticker: str,
        decision_payload: dict,
        queue_entry: dict,
        inference_time_ms: float = 0.0,
    ) -> None:
        record = {
            "timestamp":          datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "ticker":             ticker.upper(),
            "decision":           decision_payload.get("decision", ""),
            "confidence":         decision_payload.get("confidence"),
            "score":              decision_payload.get("score"),
            "risk":               decision_payload.get("risk", ""),
            "execution_permitted": decision_payload.get("execution_permitted", False),
            "rejection_reason":   decision_payload.get("rejection_reason"),
            "entry_price":        decision_payload.get("entry_price"),
            "stop_loss":          decision_payload.get("stop_loss"),
            "rr_ratio":           decision_payload.get("rr_ratio"),
            "inference_time_ms":  inference_time_ms,
            "queue_status":       queue_entry.get("status", ""),
            "trade_id":           queue_entry.get("trade_id", ""),
        }

        try:
            with open(self._jsonl_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[decision_logger] WARNING: JSONL write failed: {e}")

        try:
            with open(self._csv_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
                writer.writerow(record)
        except Exception as e:
            print(f"[decision_logger] WARNING: CSV write failed: {e}")

    def get_recent(self, n: int = 20) -> list:
        """Return the last n decisions from the JSONL log."""
        try:
            if not self._jsonl_path.exists():
                return []
            lines = self._jsonl_path.read_text().strip().splitlines()
            recent = lines[-n:] if len(lines) > n else lines
            result = []
            for line in reversed(recent):   # newest first
                try:
                    result.append(json.loads(line))
                except Exception:
                    pass
            return result
        except Exception as e:
            print(f"[decision_logger] WARNING: get_recent failed: {e}")
            return []

    def get_stats(self) -> dict:
        """Aggregate stats from the CSV log."""
        try:
            if not self._csv_path.exists():
                return {}

            rows = []
            with open(self._csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)

            if not rows:
                return {}

            counts: dict = {}
            confidences = []
            scores = []
            ticker_counts: dict = {}

            for row in rows:
                d = row.get("decision", "")
                counts[d] = counts.get(d, 0) + 1

                try:
                    confidences.append(float(row["confidence"]))
                except (TypeError, ValueError, KeyError):
                    pass

                try:
                    scores.append(float(row["score"]))
                except (TypeError, ValueError, KeyError):
                    pass

                t = row.get("ticker", "")
                if t:
                    ticker_counts[t] = ticker_counts.get(t, 0) + 1

            most_traded = max(ticker_counts, key=ticker_counts.get) if ticker_counts else None

            return {
                "total_decisions":    len(rows),
                "buy_count":          counts.get("BUY", 0),
                "sell_count":         counts.get("SELL", 0),
                "hold_count":         counts.get("HOLD", 0),
                "blocked_count":      counts.get("BLOCKED", 0),
                "avg_confidence":     round(sum(confidences) / len(confidences), 4) if confidences else None,
                "avg_score":          round(sum(scores) / len(scores), 1) if scores else None,
                "most_traded_ticker": most_traded,
            }
        except Exception as e:
            print(f"[decision_logger] WARNING: get_stats failed: {e}")
            return {}


# Singleton
decision_logger = DecisionLogger(log_dir="decision_logs")
