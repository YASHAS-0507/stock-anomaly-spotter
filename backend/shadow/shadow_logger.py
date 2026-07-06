"""
shadow_logger.py
----------------
Append-only JSONL log for shadow agent predictions and their outcomes.
Never raises — all I/O errors are printed as warnings.
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


class ShadowLogger:
    def __init__(self, log_file: str = "shadow/shadow_predictions.jsonl"):
        self.log_file = os.path.join(_BACKEND_ROOT, log_file)
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        except Exception as exc:
            logger.warning("[shadow_logger] Could not create log dir: %s", exc)

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def log_prediction(self, entry: dict) -> None:
        """Append a prediction entry to the JSONL log."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("[shadow_logger] log_prediction failed: %s", exc)

    def update_outcome(self, trade_id: str, outcome: dict) -> None:
        """
        Find the entry matching trade_id and overwrite it with the outcome appended.
        Rewrites the whole file — log is kept small (last 10k entries max).
        """
        try:
            lines = self._read_lines()
            updated = False
            new_lines = []
            for line in lines:
                try:
                    entry = json.loads(line)
                    if entry.get("trade_id") == trade_id:
                        entry["outcome"] = outcome
                        updated = True
                    new_lines.append(json.dumps(entry))
                except json.JSONDecodeError:
                    new_lines.append(line.rstrip())

            if updated:
                with open(self.log_file, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(new_lines) + "\n" if new_lines else "")
        except Exception as exc:
            logger.warning("[shadow_logger] update_outcome failed: %s", exc)

    def get_recent(self, n: int = 50) -> list:
        """Return the last N log entries. Returns [] on any error."""
        try:
            lines = self._read_lines()
            entries = []
            for line in lines:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return entries[-n:]
        except Exception:
            return []

    def get_agent_stats(self) -> dict:
        """
        Compute win rate per agent from completed (outcome != null) entries.

        An agent is "correct" when its signal matches the trade outcome:
          signal=BUY + outcome=WIN  → correct
          signal=BUY + outcome=LOSS → incorrect
          signal=SKIP/HOLD          → not scored (excluded)
        """
        agents = ["pattern_agent", "timing_agent", "regime_agent", "live_system"]
        stats  = {a: {"correct": 0, "total": 0, "win_rate": 0.0} for a in agents}

        try:
            for entry in self.get_recent(10_000):
                if not entry.get("outcome"):
                    continue
                outcome_val = entry["outcome"].get("outcome", "")
                if outcome_val not in ("WIN", "LOSS"):
                    continue

                # Live system
                live_sig = entry.get("live_signal", "")
                if live_sig == "BUY":
                    stats["live_system"]["total"] += 1
                    if outcome_val == "WIN":
                        stats["live_system"]["correct"] += 1

                # Shadow agents
                for agent in ("pattern_agent", "timing_agent", "regime_agent"):
                    ag_data = entry.get(agent, {})
                    if ag_data.get("signal") == "BUY":
                        stats[agent]["total"] += 1
                        if outcome_val == "WIN":
                            stats[agent]["correct"] += 1

            for a in agents:
                t = stats[a]["total"]
                stats[a]["win_rate"] = round(stats[a]["correct"] / t, 4) if t else 0.0

        except Exception as exc:
            logger.warning("[shadow_logger] get_agent_stats failed: %s", exc)

        return stats

    # ──────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────

    def _read_lines(self) -> list:
        if not os.path.exists(self.log_file):
            return []
        with open(self.log_file, "r", encoding="utf-8") as fh:
            return [l for l in fh.readlines() if l.strip()]
