const SIGNAL_COLOR = { BUY: "var(--green)", SHORT: "var(--red)", HOLD: "#FFB800" };

export default function ExplainabilityCard({ prediction }) {
  if (!prediction) return null;

  const explain    = prediction.stage_4_explainability;
  const signal     = explain?.primary_signal || "—";
  const confidence = explain?.confidence_rating || "—";
  const chain      = explain?.reasoning_chain || [];
  const color      = SIGNAL_COLOR[signal] || "var(--text-2)";

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Explainability</span>
        <span className="panel-badge" style={{ color }}>{signal}</span>
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <div style={{ background: "var(--elevated)", borderRadius: 8, padding: "12px 16px", flex: 1 }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", marginBottom: 4 }}>
            Signal
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 700, color }}>
            {signal}
          </div>
        </div>
        <div style={{ background: "var(--elevated)", borderRadius: 8, padding: "12px 16px", flex: 1 }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", marginBottom: 4 }}>
            Confidence
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 700, color: "var(--cyan)" }}>
            {confidence}
          </div>
        </div>
      </div>

      <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", marginBottom: 8 }}>
        Reasoning Chain
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {chain.length === 0 ? (
          <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)" }}>
            No signals detected.
          </div>
        ) : (
          chain.map((reason, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "8px 12px", background: "var(--elevated)", borderRadius: 6,
            }}>
              <div style={{ width: 4, height: 4, borderRadius: "50%", background: color, flexShrink: 0 }} />
              <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-2)" }}>
                {reason}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
