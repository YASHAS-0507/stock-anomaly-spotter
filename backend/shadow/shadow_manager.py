"""
shadow_manager.py
-----------------
Orchestrates the three shadow agents. Called after every live signal;
never blocks the main trading loop.
"""

import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from shadow.shadow_logger  import ShadowLogger
from shadow.pattern_agent  import PatternAgent
from shadow.timing_agent   import TimingAgent
from shadow.regime_agent   import RegimeAgent

IST = timezone(timedelta(hours=5, minutes=30))


class ShadowManager:
    """Coordinates shadow agents and logs their predictions silently."""

    def __init__(self):
        self.logger        = ShadowLogger()
        self.pattern_agent = PatternAgent()
        self.timing_agent  = TimingAgent()
        self.regime_agent  = RegimeAgent()

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def observe(
        self,
        ticker: str,
        features: dict,
        regime: dict,
        live_signal: str,
        live_confidence: float,
        intelligence: dict,
        trade_id: str,
    ) -> None:
        """
        Ask all three agents to predict, then log everything.
        Runs in try/except so it can never block the main loop.
        """
        try:
            mood = {
                "vix":        features.get("vix", 15.0),
                "vix_regime": regime.get("vix_regime", "NORMAL"),
            }

            pattern_pred = self.pattern_agent.predict(features, regime, intelligence)
            timing_pred  = self.timing_agent.predict(features)
            regime_pred  = self.regime_agent.predict(features, regime, mood)

            entry = {
                "trade_id":        trade_id,
                "ticker":          ticker,
                "timestamp":       datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                "live_signal":     live_signal,
                "live_confidence": round(float(live_confidence), 4),
                "pattern_agent":   pattern_pred,
                "timing_agent":    timing_pred,
                "regime_agent":    regime_pred,
                "outcome":         None,
            }
            self.logger.log_prediction(entry)

        except Exception as exc:
            logger.warning("[shadow] observe() failed for %s: %s", ticker, exc)

    def on_trade_closed(self, trade_id: str, outcome: dict) -> None:
        """
        Update the log entry for trade_id with the actual outcome.
        outcome = {"outcome": "WIN"|"LOSS", "pnl_pct": float, "close_reason": str}
        """
        try:
            self.logger.update_outcome(trade_id, outcome)
        except Exception as exc:
            logger.warning("[shadow] on_trade_closed() failed: %s", exc)

    def get_weekly_report(self) -> dict:
        """
        Compare all agents against the live system.

        Returns
        -------
        dict with per-agent stats, total_observations, recommendation
        """
        try:
            stats = self.logger.get_agent_stats()
            live_wr = stats["live_system"]["win_rate"]

            agent_report: dict = {}
            for agent in ("pattern_agent", "timing_agent", "regime_agent"):
                wr = stats[agent]["win_rate"]
                agent_report[agent] = {
                    "win_rate":       wr,
                    "total":          stats[agent]["total"],
                    "vs_live_system": round(wr - live_wr, 4),
                }

            total_obs = len(self.logger.get_recent(10_000))

            # Simple recommendation
            best_agent = max(
                ("pattern_agent", "timing_agent", "regime_agent"),
                key=lambda a: agent_report[a]["win_rate"],
            )
            best_wr = agent_report[best_agent]["win_rate"]
            if best_wr > live_wr + 0.05:
                rec = (f"{best_agent} is outperforming live system by "
                       f"{(best_wr - live_wr)*100:.1f}% — consider integrating its signals.")
            elif live_wr > 0.6:
                rec = "Live system performing well. Continue monitoring shadow agents."
            else:
                rec = "Insufficient data for a recommendation. Keep accumulating observations."

            return {
                "pattern_agent":      agent_report["pattern_agent"],
                "timing_agent":       agent_report["timing_agent"],
                "regime_agent":       agent_report["regime_agent"],
                "live_system":        {"win_rate": live_wr, "total": stats["live_system"]["total"]},
                "total_observations": total_obs,
                "recommendation":     rec,
            }

        except Exception as exc:
            logger.warning("[shadow] get_weekly_report() failed: %s", exc)
            return {
                "pattern_agent":      {"win_rate": 0.0, "total": 0, "vs_live_system": 0.0},
                "timing_agent":       {"win_rate": 0.0, "total": 0, "vs_live_system": 0.0},
                "regime_agent":       {"win_rate": 0.0, "total": 0, "vs_live_system": 0.0},
                "live_system":        {"win_rate": 0.0, "total": 0},
                "total_observations": 0,
                "recommendation":     "Error generating report.",
            }


# Module-level singleton
shadow_manager = ShadowManager()
