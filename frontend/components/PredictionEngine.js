export default function PredictionEngine({ prediction, decision }) {
  if (!prediction) return null;

  const { realtime_signal, probabilities, latest_day_forecast, metrics, configuration, disclaimer } = prediction;
  const probs = latest_day_forecast?.probabilities || probabilities || {};
  const pUp   = probs.spike_up   ?? 0;
  const pDown = probs.spike_down ?? 0;
  const pSide = probs.sideways   ?? 0;

  let dominant = "sideways";
  if (pUp >= pDown && pUp >= pSide) dominant = "spike_up";
  else if (pDown > pUp && pDown >= pSide) dominant = "spike_down";

  const testAcc = metrics?.test_set_accuracy ?? 0;
  const baseAcc = metrics?.baseline_majority_accuracy ?? 0;
  const diff = ((testAcc - baseAcc) * 100).toFixed(1);
  const beat = testAcc > baseAcc;
  const tie  = testAcc === baseAcc;

  const bars = [
    { key: "spike_up",   label: "Spike Up",   prob: pUp,   color: "#00C48C" },
    { key: "sideways",   label: "Sideways",   prob: pSide, color: "#FFB800" },
    { key: "spike_down", label: "Spike Down", prob: pDown, color: "#FF4560" },
  ];

  // Decision engine section
  const hasDecision = decision && decision.decision !== "BLOCKED";
  const decisionColor = {
    BUY:     "#00C48C",
    SELL:    "#FF4560",
    HOLD:    "#FFB800",
    BLOCKED: "var(--text-3)",
  }[decision?.decision] || "var(--text-3)";
  const riskColor = {
    LOW:     "#00C48C",
    MEDIUM:  "#FFB800",
    HIGH:    "#FF4560",
    EXTREME: "#FF4560",
  }[decision?.risk] || "var(--text-3)";

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Prediction Engine</span>
        <span className="panel-badge">{prediction.model_architecture}</span>
      </div>

      {/* Signal Banner */}
      <div style={{
        background: "#0D1117",
        borderLeft: `4px solid ${realtime_signal.color}`,
        padding: "14px 16px", borderRadius: 6, marginBottom: 16,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--mono)", textTransform: "uppercase", marginBottom: 2 }}>
            Signal · {configuration?.horizon_days ?? 5}‑Day · {configuration?.spike_percentage_threshold ?? "5.0%"}
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>
            {realtime_signal.status}
          </div>
        </div>
        <div style={{
          background: realtime_signal.color, color: "#0D1117",
          fontFamily: "var(--mono)", fontWeight: 900,
          padding: "7px 14px", borderRadius: 4, fontSize: 13, letterSpacing: "0.5px",
        }}>
          {realtime_signal.action}
        </div>
      </div>

      {/* Probability Bars */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
        {bars.map(({ key, label, prob, color }) => (
          <div key={key}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3, fontFamily: "var(--mono)" }}>
              <span style={{ color: dominant === key ? color : "var(--text-3)", fontWeight: dominant === key ? 600 : 400 }}>
                {label}
              </span>
              <span style={{ color, fontWeight: 700 }}>{(prob * 100).toFixed(1)}%</span>
            </div>
            <div style={{ width: "100%", background: "#1C2332", height: 6, borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                width: `${prob * 100}%`, background: color,
                height: "100%", borderRadius: 3,
                transition: "width 0.6s cubic-bezier(.4,0,.2,1)",
              }} />
            </div>
          </div>
        ))}
      </div>

      {/* Accuracy Row */}
      <div className="vs-row" style={{ marginBottom: decision ? 14 : 0 }}>
        <span style={{ color: "var(--text-3)" }}>Model vs baseline:</span>
        {tie
          ? <span className="tie">= tied at {(testAcc * 100).toFixed(1)}%</span>
          : beat
          ? <span className="beat">+{diff}pp over {(baseAcc * 100).toFixed(1)}%</span>
          : <span className="miss">{diff}pp vs {(baseAcc * 100).toFixed(1)}%</span>
        }
      </div>

      {/* ── AI Decision Engine Section ── */}
      {decision && (
        <div style={{
          borderTop: "1px solid var(--border)",
          paddingTop: 12,
          marginTop: 2,
        }}>
          <div style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
            AI Decision Engine
          </div>

          {/* Score bar */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontFamily: "var(--mono)", marginBottom: 4 }}>
              <span style={{ color: "var(--text-3)" }}>INSTITUTIONAL SCORE</span>
              <span style={{ color: "var(--cyan)", fontWeight: 700 }}>{decision.score}/100</span>
            </div>
            <div style={{ width: "100%", background: "#1C2332", height: 5, borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                width: `${decision.score}%`, background: "var(--cyan)",
                height: "100%", borderRadius: 3,
                transition: "width 0.6s cubic-bezier(.4,0,.2,1)",
              }} />
            </div>
          </div>

          {/* Decision metrics grid */}
          {[
            { label: "DECISION",          value: decision.decision,                                        color: decisionColor },
            { label: "CONFIDENCE",        value: `${(decision.confidence * 100).toFixed(1)}%`,             color: "var(--text)" },
            { label: "RISK",              value: decision.risk,                                            color: riskColor },
            { label: "EXPECTED RETURN",   value: decision.expected_return != null ? `${decision.expected_return > 0 ? "+" : ""}${decision.expected_return.toFixed(2)}%` : "—", color: decision.expected_return >= 0 ? "#00C48C" : "#FF4560" },
            { label: "EXPECTED DRAWDOWN", value: decision.expected_drawdown != null ? `${decision.expected_drawdown.toFixed(2)}%` : "—", color: "#FF4560" },
            { label: "R/R RATIO",         value: decision.rr_ratio != null ? `${decision.rr_ratio.toFixed(1)}:1` : "—", color: "var(--text)" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "6px 0", borderBottom: "1px solid var(--border)",
            }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", textTransform: "uppercase" }}>
                {label}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700, color }}>
                {value}
              </span>
            </div>
          ))}

          {/* Rejection reason */}
          {decision.rejection_reason && (
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", lineHeight: 1.5, marginTop: 8 }}>
              {decision.rejection_reason}
            </div>
          )}
        </div>
      )}

      {disclaimer && <div className="disclaimer">{disclaimer}</div>}
    </div>
  );
}
