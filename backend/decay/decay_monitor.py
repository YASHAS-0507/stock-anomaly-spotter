"""
decay_monitor.py
----------------
Strategy health monitor: detects when a setup stops working BEFORE
it causes significant losses.

Three statistical tests per setup:
  1. Rolling metrics vs baseline (win rate, profit factor, Sharpe)
  2. CUSUM on trade returns (detects gradual mean drift)
  3. KS test on return distribution vs expected normal baseline

Three health states:
  HEALTHY              → trade normally, risk_multiplier = 1.0
  AT_RISK              → reduce size 50%, risk_multiplier = 0.5
  OFFLINE              → disable setup, risk_multiplier = 0.0
  INSUFFICIENT_DATA    → not enough history, risk_multiplier = 1.0

Runs weekly (Sunday evening via post_market) or on demand.
"""

import logging
import math

logger = logging.getLogger(__name__)

BASELINE_STATS = {
    "ORB_BREAKOUT": {
        "win_rate":      0.54,
        "profit_factor": 1.6,
        "sharpe":        1.2,
        "mean_return":   0.008,
    },
    "VWAP_BOUNCE": {
        "win_rate":      0.56,
        "profit_factor": 1.7,
        "sharpe":        1.3,
        "mean_return":   0.009,
    },
    "TREND_CONTINUATION": {
        "win_rate":      0.52,
        "profit_factor": 1.5,
        "sharpe":        1.1,
        "mean_return":   0.007,
    },
    "NEWS_CATALYST": {
        "win_rate":      0.58,
        "profit_factor": 1.8,
        "sharpe":        1.4,
        "mean_return":   0.010,
    },
}


class DecayMonitor:
    """
    Monitors strategy health using statistical tests.

    Runs weekly (Sunday evening) or on demand.
    """

    def __init__(self):
        self.baseline = BASELINE_STATS
        self.min_trades_for_assessment = 30
        self.cusum_drift      = 0.002
        self.cusum_threshold  = 0.05
        self._health_cache: dict = {}
        self._last_run = None

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def assess_all_setups(self, all_trades: list) -> dict:
        """
        Main entry point. Assesses health of all setups.

        Parameters
        ----------
        all_trades : completed trades from auto_broker

        Returns
        -------
        dict keyed by setup name + "overall" summary
        """
        result = {}

        for setup_name in self.baseline:
            trades = self._get_setup_trades(all_trades, setup_name)
            result[setup_name] = self._assess_single_setup(setup_name, trades)

        # Overall system health
        statuses = [v["status"] for v in result.values()]
        n_healthy  = statuses.count("HEALTHY") + statuses.count("INSUFFICIENT_DATA")
        n_at_risk  = statuses.count("AT_RISK")
        n_offline  = statuses.count("OFFLINE")
        total      = len(statuses)

        if n_offline > 0:
            system_health = "CRITICAL"
        elif n_at_risk >= total // 2:
            system_health = "DEGRADED"
        elif n_at_risk > 0:
            system_health = "DEGRADED"
        else:
            system_health = "HEALTHY"

        action_required = n_offline > 0 or n_at_risk > 0

        result["overall"] = {
            "system_health":   system_health,
            "setups_healthy":  n_healthy,
            "setups_at_risk":  n_at_risk,
            "setups_offline":  n_offline,
            "action_required": action_required,
            "summary": (
                f"System {system_health}: "
                f"{n_healthy} healthy, "
                f"{n_at_risk} at-risk, "
                f"{n_offline} offline."
            ),
        }

        self._health_cache = result
        return result

    def get_setup_risk_multipliers(self) -> dict:
        """
        Returns current risk multiplier per setup.
        Defaults to 1.0 for setups with no/insufficient data.
        """
        if not self._health_cache:
            return {s: 1.0 for s in self.baseline}
        result = {}
        for setup in self.baseline:
            health = self._health_cache.get(setup, {})
            result[setup] = health.get("risk_multiplier", 1.0)
        return result

    def get_system_health_summary(self) -> dict:
        """
        Returns overall system health for dashboard.
        Uses cached results from last assessment.
        """
        if not self._health_cache:
            return {
                "system_health": "UNKNOWN",
                "last_run":      None,
                "message":       "No assessment run yet",
            }
        return self._health_cache.get(
            "overall",
            {"system_health": "UNKNOWN"},
        )

    def run_if_due(self, all_trades: list) -> bool:
        """
        Runs assessment only if it hasn't been run today.

        Returns True if assessment was run.
        """
        import datetime
        today = datetime.date.today().isoformat()
        if self._last_run == today:
            return False
        if len(all_trades) >= self.min_trades_for_assessment:
            self._health_cache = self.assess_all_setups(all_trades)
            self._last_run = today
            return True
        return False

    # ──────────────────────────────────────────────────────
    # Setup filtering
    # ──────────────────────────────────────────────────────

    def _get_setup_trades(self, all_trades: list, setup_name: str) -> list:
        """Filter trades for a specific setup."""
        return [
            t for t in all_trades
            if t.get("setup_type", "") == setup_name
        ]

    # ──────────────────────────────────────────────────────
    # Rolling metrics
    # ──────────────────────────────────────────────────────

    def _compute_rolling_metrics(
        self, trades: list, window: int = 50
    ):
        """
        Compute metrics over last N trades.

        Returns dict with win_rate, profit_factor, sharpe,
        max_drawdown_pct, avg_winner_pct, avg_loser_pct, returns.
        Returns None if fewer than min_trades trades.
        """
        if len(trades) < self.min_trades_for_assessment:
            return None

        recent = trades[-window:] if len(trades) > window else trades

        # Compute pnl_pct per trade (broker may not store it)
        returns = []
        for t in recent:
            pnl_pct = t.get("pnl_pct")
            if pnl_pct is None:
                fill  = float(t.get("fill_price", 0) or 0)
                shrs  = int(t.get("shares", 0) or 0)
                pnl   = float(t.get("pnl", 0) or 0)
                cost  = fill * shrs
                pnl_pct = pnl / cost if cost > 0 else 0.0
            returns.append(float(pnl_pct))

        wins   = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        win_rate = len(wins) / len(returns) if returns else 0.0

        avg_winner = sum(wins) / len(wins) if wins else 0.0
        avg_loser  = sum(losses) / len(losses) if losses else 0.0

        sum_wins   = sum(wins)
        sum_losses = abs(sum(losses))
        profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (10.0 if sum_wins > 0 else 0.0)

        # Sharpe: annualised (intraday: multiply by sqrt(252))
        n = len(returns)
        mean_r = sum(returns) / n if n > 0 else 0.0
        variance = sum((r - mean_r) ** 2 for r in returns) / n if n > 1 else 0.0
        std_r = math.sqrt(variance) if variance > 0 else 1e-9
        sharpe = (mean_r / std_r) * math.sqrt(252)

        # Max drawdown from equity curve
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in returns:
            equity += r
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)

        return {
            "win_rate":          round(win_rate, 4),
            "avg_winner_pct":    round(avg_winner, 6),
            "avg_loser_pct":     round(avg_loser, 6),
            "profit_factor":     round(profit_factor, 3),
            "sharpe":            round(sharpe, 3),
            "max_drawdown_pct":  round(max_dd, 6),
            "returns":           returns,
        }

    # ──────────────────────────────────────────────────────
    # CUSUM test
    # ──────────────────────────────────────────────────────

    def _run_cusum(self, returns: list, baseline_mean: float) -> bool:
        """
        CUSUM test on trade returns.
        Detects persistent downward shift in mean return.

        S = max(0, S + baseline_mean - y_t - drift)
        Alert if S > cusum_threshold.

        Returns True if alert (decay detected).
        """
        if not returns:
            return False
        s = 0.0
        for r in returns:
            s = max(0.0, s + baseline_mean - r - self.cusum_drift)
            if s > self.cusum_threshold:
                return True
        return False

    # ──────────────────────────────────────────────────────
    # KS test
    # ──────────────────────────────────────────────────────

    def _run_ks_test(
        self,
        recent_returns: list,
        baseline_mean: float,
        baseline_std: float = 0.01,
    ) -> bool:
        """
        KS test: compares recent return distribution vs expected baseline.

        Alert if p_value < 0.05 AND recent mean is below baseline mean.
        Falls back gracefully if scipy unavailable.

        Returns True if alert (distribution shifted negatively).
        """
        if not recent_returns or len(recent_returns) < 10:
            return False

        n = len(recent_returns)
        recent_mean = sum(recent_returns) / n

        # Only alert if distribution shifted downward
        if recent_mean >= baseline_mean:
            return False

        try:
            from scipy import stats

            def cdf(x):
                return stats.norm.cdf(x, loc=baseline_mean, scale=baseline_std)

            _, p_value = stats.ks_1samp(recent_returns, cdf)
            return bool(p_value < 0.05)

        except ImportError:
            # Fallback: simple z-test on the mean
            std_err = baseline_std / math.sqrt(n)
            z = (recent_mean - baseline_mean) / std_err if std_err > 0 else 0.0
            # p ≈ 0.05 corresponds to z < -1.645 (one-tailed)
            return z < -1.645

    # ──────────────────────────────────────────────────────
    # Single-setup assessment
    # ──────────────────────────────────────────────────────

    def _assess_single_setup(self, setup_name: str, trades: list) -> dict:
        """Full assessment for one setup."""
        base = self.baseline[setup_name]

        if len(trades) < self.min_trades_for_assessment:
            return {
                "status":                      "INSUFFICIENT_DATA",
                "trade_count":                 len(trades),
                "win_rate":                    None,
                "profit_factor":               None,
                "sharpe":                      None,
                "cusum_alert":                 False,
                "ks_alert":                    False,
                "win_rate_vs_baseline":        None,
                "profit_factor_vs_baseline":   None,
                "risk_multiplier":             1.0,
                "reason":                      f"Only {len(trades)} trades — need {self.min_trades_for_assessment}",
                "recommendation":              "Collect more trades before assessment",
            }

        metrics = self._compute_rolling_metrics(trades)
        if metrics is None:
            return {
                "status":            "INSUFFICIENT_DATA",
                "trade_count":       len(trades),
                "win_rate":          None,
                "profit_factor":     None,
                "sharpe":            None,
                "cusum_alert":       False,
                "ks_alert":          False,
                "win_rate_vs_baseline":      None,
                "profit_factor_vs_baseline": None,
                "risk_multiplier":   1.0,
                "reason":            "Could not compute metrics",
                "recommendation":    "Collect more trades",
            }

        returns = metrics["returns"]
        cusum_alert = self._run_cusum(returns, base["mean_return"])
        ks_alert    = self._run_ks_test(returns, base["mean_return"])

        win_rate      = metrics["win_rate"]
        pf            = metrics["profit_factor"]
        sharpe        = metrics["sharpe"]

        wr_vs_base = round(win_rate - base["win_rate"], 4)
        pf_vs_base = round(pf - base["profit_factor"], 3)

        # Status determination
        if pf < 1.0 or win_rate < 0.42:
            status = "OFFLINE"
            risk_mult = 0.0
            reason = (
                f"Critical: profit_factor={pf:.2f}<1.0" if pf < 1.0
                else f"Critical: win_rate={win_rate:.2f}<0.42"
            )
            recommendation = (
                "Setup DISABLED — human review required. "
                "Check market regime shift or entry criteria."
            )
        elif (
            win_rate < base["win_rate"] - 0.12
            or pf < 1.2
            or sharpe < base["sharpe"] * 0.6
            or cusum_alert
            or ks_alert
        ):
            status = "AT_RISK"
            risk_mult = 0.5
            flags = []
            if win_rate < base["win_rate"] - 0.12:
                flags.append(f"win_rate={win_rate:.2f} (baseline {base['win_rate']:.2f})")
            if pf < 1.2:
                flags.append(f"profit_factor={pf:.2f}<1.2")
            if sharpe < base["sharpe"] * 0.6:
                flags.append(f"sharpe={sharpe:.2f} (baseline {base['sharpe']:.2f})")
            if cusum_alert:
                flags.append("CUSUM drift detected")
            if ks_alert:
                flags.append("KS distribution shift")
            reason = "AT_RISK: " + "; ".join(flags)
            recommendation = (
                "Reduce position size to 50%. "
                "Monitor for 2 more weeks before re-enabling full sizing."
            )
        else:
            status = "HEALTHY"
            risk_mult = 1.0
            reason = (
                f"Metrics within baseline — "
                f"win_rate={win_rate:.2f} pf={pf:.2f} sharpe={sharpe:.2f}"
            )
            recommendation = "Trade normally"

        return {
            "status":                    status,
            "trade_count":               len(trades),
            "win_rate":                  win_rate,
            "profit_factor":             round(pf, 3),
            "sharpe":                    round(sharpe, 3),
            "cusum_alert":               cusum_alert,
            "ks_alert":                  ks_alert,
            "win_rate_vs_baseline":      wr_vs_base,
            "profit_factor_vs_baseline": pf_vs_base,
            "risk_multiplier":           risk_mult,
            "reason":                    reason,
            "recommendation":            recommendation,
        }


# Module-level singleton
decay_monitor = DecayMonitor()
