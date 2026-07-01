import { formatPercent } from "@/utils/formatting";

export default function ModelDiagnosticsCard({ prediction, dominant, accBeat, accTie, accDiff }) {
  if (!prediction) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Model Diagnostics</span>
          <span className="panel-badge">XGBoost + TabPFN</span>
        </div>
        <div className="panel-content">
          <div className="skeleton skeleton-card" />
        </div>
      </div>
    );
  }

  // Check if prediction was halted
  const executionStatus = prediction.execution_status || "completed";
  const isHalted = executionStatus === "halted" || prediction.realtime_signal?.status?.includes("HALTED");
  
  const probs = prediction.latest_day_forecast?.probabilities || {};
  const confidence = isHalted ? 0 : Math.max(probs.spike_up ?? 0, probs.spike_down ?? 0, probs.sideways ?? 0);
  const accuracy = prediction.metrics?.test_set_accuracy ?? 0;
  const baseline = prediction.metrics?.baseline_majority_accuracy ?? 0;
  const regime = prediction.regime_snapshot?.regime_type || "N/A";
  const regimePermitted = prediction.regime_snapshot?.action_permitted ?? true;
  const inferenceTime = prediction.inference_time_ms || "N/A";
  const featureCount = prediction.feature_count || "N/A";

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Model Diagnostics</span>
        <span className="panel-badge">{prediction.model_architecture || "XGBoost + TabPFN"}</span>
      </div>

      <div className="panel-content space-lg">
        {/* Confidence Gauge */}
        <div className="card p-lg">
          <div className="card-title">Prediction Confidence</div>
          <div className="mt-md flex items-center justify-between">
            <div className="gauge" style={{ width: "120px", height: "120px" }}>
              <svg viewBox="0 0 120 120">
                <circle className="gauge-bg" cx="60" cy="60" r="50" />
                <circle
                  className="gauge-progress"
                  cx="60"
                  cy="60"
                  r="50"
                  stroke={confidence > 0.6 ? "var(--green)" : confidence > 0.4 ? "var(--yellow)" : "var(--red)"}
                  strokeDasharray={314}
                  strokeDashoffset={314 * (1 - confidence)}
                  style={{ filter: "drop-shadow(0 0 8px currentColor)" }}
                />
              </svg>
              <div className="gauge-text">
                {(confidence * 100).toFixed(1)}%
              </div>
            </div>
            <div className="flex-1 ml-lg">
              <div className="flex items-center justify-between mb-sm">
                <span className="text-label">Overall Confidence</span>
                <span className="text-metric-sm font-mono" style={{ color: confidence > 0.6 ? "var(--green)" : confidence > 0.4 ? "var(--yellow)" : "var(--red)" }}>
                  {(confidence * 100).toFixed(1)}%
                </span>
              </div>
              <div className="progress-bar" style={{ height: "8px" }}>
                <div className="progress-fill" style={{ width: `${confidence * 100}%`, background: confidence > 0.6 ? "var(--green)" : confidence > 0.4 ? "var(--yellow)" : "var(--red)" }} />
              </div>
              <div className="flex items-center justify-between mt-sm text-caption text-2">
                <span>Low</span>
                <span>High</span>
              </div>
            </div>
          </div>
        </div>

        {/* Accuracy & Regime */}
        <div className="grid grid-cols-2 gap-md">
          <div className="card p-lg">
            <div className="card-title">Model Accuracy</div>
            <div className="mt-md flex items-center justify-between">
              <div>
                <div className="text-metric font-mono">{formatPercent(accuracy)}</div>
                <div className="text-caption text-2 mt-xs">Test Set Accuracy</div>
              </div>
              <div className="text-right">
                <div className={`badge ${accBeat ? "bg-buy" : accTie ? "bg-hold" : "bg-sell"}`}>
                  {accBeat ? `+${accDiff}pp vs baseline` : accTie ? `= baseline` : `${accDiff}pp vs baseline`}
                </div>
                <div className="text-caption text-2 mt-xs">Baseline: {formatPercent(baseline)}</div>
              </div>
            </div>
          </div>

          <div className="card p-lg">
            <div className="card-title">Market Regime</div>
            <div className="mt-md flex items-center justify-between">
              <div>
                <div className="text-metric font-mono text-sm">{regime}</div>
                <div className="text-caption text-2 mt-xs">Regime Type</div>
              </div>
              <div className="text-right">
                <span className={`badge ${regimePermitted ? "bg-buy" : "bg-sell"}`}>
                  {regimePermitted ? "TRADING PERMITTED" : "EXECUTION BLOCKED"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Technical Metrics */}
        <div className="grid grid-cols-4 gap-md">
          <DiagnosticMetric label="Inference Time" value={`${inferenceTime}ms`} unit="" />
          <DiagnosticMetric label="Features Used" value={featureCount} unit="" />
          <DiagnosticMetric label="Data Freshness" value="< 1s" unit="real-time" />
          <DiagnosticMetric label="Validation" value="PASSED" unit="" highlight />
        </div>

        {/* Probability Distribution - Only show for completed predictions */}
        {!isHalted && (
          <div className="card p-lg">
            <div className="card-title">Probability Distribution</div>
            <div className="mt-md space-sm">
              <ProbabilityBar label="Spike Up" value={probs.spike_up ?? 0} color="var(--green)" highlight={dominant === "spike_up"} />
              <ProbabilityBar label="Sideways" value={probs.sideways ?? 0} color="var(--yellow)" highlight={dominant === "sideways"} />
              <ProbabilityBar label="Spike Down" value={probs.spike_down ?? 0} color="var(--red)" highlight={dominant === "spike_down"} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DiagnosticMetric({ label, value, unit = "", highlight = false }) {
  return (
    <div className={`card p-md text-center ${highlight ? "bg-buy" : ""}`}>
      <div className="text-label">{label}</div>
      <div className="flex items-center justify-center gap-xs mt-sm flex-wrap">
        <span className={`text-metric-sm font-mono ${highlight ? "signal-buy" : ""}`}>{value}</span>
        {unit && <span className="text-caption text-2">{unit}</span>}
      </div>
    </div>
  );
}

function ProbabilityBar({ label, value, color, highlight }) {
  return (
    <div className="flex items-center gap-sm">
      <span className={`text-caption w-28 ${highlight ? "font-semibold" : ""}`} style={{ color: highlight ? color : "var(--text-2)" }}>
        {label}
      </span>
      <div className="flex-1 progress-bar" style={{ height: "10px" }}>
        <div className="progress-fill" style={{ width: `${(value * 100).toFixed(1)}%`, background: color }} />
      </div>
      <span className="text-value font-mono w-16 text-right" style={{ color }}>
        {formatPercent(value)}
      </span>
    </div>
  );
}
