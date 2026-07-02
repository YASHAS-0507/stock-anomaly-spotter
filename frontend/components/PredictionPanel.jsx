import { formatPercent } from "@/utils/formatting";
import { getDominantClass, getAccuracyStatus } from "@/utils/prediction";
import MetricCard from "./MetricCard";

export default function PredictionPanel({ prediction }) {
  if (!prediction) return null;

  const { risk, portfolio, signal } = {
    risk: prediction.stage_5_risk_matrix ?? {},
    portfolio: prediction.stage_6_portfolio_snapshot ?? {},
    signal: prediction.realtime_signal ?? {}
  };

  const probSideways = prediction.latest_day_forecast?.probabilities?.sideways ?? 0;
  const probSpikeUp = prediction.latest_day_forecast?.probabilities?.spike_up ?? 0;
  const probSpikeDown = prediction.latest_day_forecast?.probabilities?.spike_down ?? 0;

  let dominantClass = "sideways";
  let maxProb = probSideways;
  if (probSpikeUp > maxProb) { dominantClass = "spike_up"; maxProb = probSpikeUp; }
  if (probSpikeDown > maxProb) { dominantClass = "spike_down"; maxProb = probSpikeDown; }

  const accBeat = prediction.metrics.test_set_accuracy > prediction.metrics.baseline_majority_accuracy;
  const accTie = prediction.metrics.test_set_accuracy === prediction.metrics.baseline_majority_accuracy;
  const accDiff = ((prediction.metrics.test_set_accuracy - prediction.metrics.baseline_majority_accuracy) * 100).toFixed(1);

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">Breakout Forecasting Model</span>
        <span className="panel-badge">{prediction.model_architecture}</span>
      </div>

      {/* REALTIME ACTION SIGNAL ALERT BANNER */}
      <div className="signal-banner" style={{ borderLeftColor: signal.color }}>
        <div>
          <div className="signal-label">Current Trade Recommendation</div>
          <div className="signal-status">{signal.status}</div>
          <div className="signal-details">
            Cash Available : ₹{portfolio.free_cash?.toFixed(2)}<br/>
            Suggested Quantity : {risk.target_quantity}<br/>
            Risk : ₹{risk.allocated_risk_cash?.toFixed(2)}
          </div>
        </div>
        <div className="signal-action" style={{ background: signal.color }}>
          {signal.action}
        </div>
      </div>

      <div className="two-col" style={{ gap: 40, marginBottom: 0 }}>
        {/* LEFT: MULTICLASS ODDS */}
        <div>
          <div className="direction-wrap">
            <div className="direction-label">
              Execution Target Forecast ({prediction.configuration.horizon_days}-day threshold: {prediction.configuration.spike_percentage_threshold})
            </div>

            <ProbabilityBar label="🟢 Spike Up" value={probSpikeUp} color="#00C48C" highlight={dominantClass === "spike_up"} />
            <ProbabilityBar label="🟡 Sideways / Neutral" value={probSideways} color="#FFB800" highlight={dominantClass === "sideways"} />
            <ProbabilityBar label="🔴 Spike Down" value={probSpikeDown} color="#FF4560" highlight={dominantClass === "spike_down"} />
          </div>

          <div className="vs-row" style={{ marginTop: "12px" }}>
            <span className="vs-label">Model vs baseline:</span>
            {accTie
              ? <span className="tie">= tied at {(prediction.metrics.test_set_accuracy * 100).toFixed(1)}%</span>
              : accBeat
                ? <span className="beat">+{accDiff}pp over baseline</span>
                : <span className="miss">{accDiff}pp vs baseline</span>
            }
          </div>
        </div>

        {/* RIGHT: METRIC GRID */}
        <div className="model-grid">
          <MetricCard label="Available Cash" value={`₹${portfolio.free_cash?.toFixed(2) ?? "0.00"}`} />
          <MetricCard label="Portfolio Value" value={`₹${portfolio.portfolio_value?.toFixed(2) ?? "0.00"}`} />
          <MetricCard label="Quantity" value={risk.target_quantity ?? 0} />
          <MetricCard label="Risk / Trade" value={`₹${risk.allocated_risk_cash?.toFixed(2) ?? "0"}`} />
          <MetricCard label="Entry" value={`₹${risk.entry_price?.toFixed(2) ?? "-"}`} />
          <MetricCard label="Stop Loss" value={`₹${risk.stop_loss?.toFixed(2) ?? "-"}`} />
          <MetricCard label="Take Profit" value={`₹${risk.take_profit?.toFixed(2) ?? "-"}`} />
          <MetricCard label="Risk Reward" value={risk.risk_reward_ratio ?? "-"} />
        </div>
      </div>
    </div>
  );
}

function ProbabilityBar({ label, value, color, highlight }) {
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
        <span style={{ color: highlight ? color : "var(--text-2)", fontWeight: highlight ? "600" : "400" }}>{label}</span>
        <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", color, fontWeight: "bold" }}>{formatPercent(value)}</span>
      </div>
      <div style={{ width: "100%", background: "var(--border)", height: "8px", borderRadius: "4px", overflow: "hidden" }}>
        <div style={{ width: `${value * 100}%`, background: color, height: "100%" }}></div>
      </div>
    </div>
  );
}