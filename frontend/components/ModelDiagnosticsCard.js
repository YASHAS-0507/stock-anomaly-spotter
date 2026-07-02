import { extractRegime } from "../services/market";

const REGIME_COLOR = {
  BULL_TREND:       "var(--green)",
  BEAR_TREND:       "var(--red)",
  HIGH_VOLATILITY:  "var(--red)",
  SIDEWAYS_SQUEEZE: "#FFB800",
  NORMAL:           "var(--text-2)",
};

export default function ModelDiagnosticsCard({ prediction }) {
  if (!prediction) return null;

  const regime        = extractRegime(prediction);
  const inferenceMs   = prediction.inference_time_ms;
  const inferenceDisp = inferenceMs == null ? "N/A" : `${inferenceMs}ms`;
  const featureCount  = prediction.feature_count ?? "N/A";
  const testAcc       = prediction.metrics?.test_set_accuracy;
  const routing       = prediction.pipeline_routing_execution || "—";

  const rows = [
    { label: "Market Regime",  value: regime,                                        color: REGIME_COLOR[regime] || "var(--text-2)" },
    { label: "Inference Time", value: inferenceDisp,                                  color: "var(--text-2)" },
    { label: "Features Used",  value: String(featureCount),                           color: "var(--text-2)" },
    { label: "Test Accuracy",  value: testAcc != null ? `${(testAcc * 100).toFixed(1)}%` : "N/A", color: "var(--cyan)" },
    { label: "Engine Routing", value: routing,                                         color: "var(--text-3)" },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Model Diagnostics</span>
        <span className="panel-badge">{prediction.model_architecture}</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {rows.map(({ label, value, color }) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between", alignItems: "flex-start",
            gap: 12, padding: "9px 0", borderBottom: "1px solid var(--border)",
          }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", flexShrink: 0 }}>
              {label}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 500, color, textAlign: "right", wordBreak: "break-word" }}>
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
