const STATUS_COLOR = {
  approved:  "#00C48C",
  pending:   "#FFB800",
  rejected:  "#FF4560",
  completed: "#00D4FF",
  cancelled: "#8A95A8",
};

const DECISION_COLOR = {
  BUY:     "#00C48C",
  SELL:    "#FF4560",
  HOLD:    "#FFB800",
  BLOCKED: "#8A95A8",
};

export default function ExecutionQueueCard({ decision, loading }) {
  const queue = decision?.queue ?? null;
  const queueSize = queue?.queue_size ?? 0;

  // Build the latest entry display from the decision payload itself
  // (the full entry list would require a separate /api/queue fetch;
  //  here we surface the current entry directly from the enriched decision)
  const hasEntry = decision && decision.decision;

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Execution Queue</span>
        <span className="panel-badge" style={{ color: "var(--cyan)" }}>
          {queueSize > 0 ? `${queueSize} entr${queueSize === 1 ? "y" : "ies"}` : "—"}
        </span>
      </div>

      {loading && (
        <div style={{ padding: "20px 0", textAlign: "center" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)" }}>
            PROCESSING…
          </div>
        </div>
      )}

      {!loading && !hasEntry && (
        <div style={{ padding: "20px 0", textAlign: "center" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)" }}>
            NO DECISIONS RECORDED THIS SESSION
          </div>
        </div>
      )}

      {!loading && hasEntry && queue && (
        <>
          {/* Latest queue entry */}
          <div style={{
            background: "#0D1117",
            borderRadius: 6,
            padding: "12px 14px",
            marginBottom: 12,
            borderLeft: `3px solid ${STATUS_COLOR[queue.status] ?? "var(--text-3)"}`,
          }}>
            {[
              { label: "TRADE ID",   value: queue.trade_id,
                color: "var(--text)", mono: true },
              { label: "STATUS",     value: (queue.status ?? "—").toUpperCase(),
                color: STATUS_COLOR[queue.status] ?? "var(--text-3)" },
              { label: "DECISION",   value: decision.decision,
                color: DECISION_COLOR[decision.decision] ?? "var(--text)" },
              { label: "CONFIDENCE", value: decision.confidence != null
                  ? `${(decision.confidence * 100).toFixed(1)}%` : "—",
                color: "var(--text)" },
              { label: "SCORE",      value: decision.score != null
                  ? `${decision.score}/100` : "—",
                color: "var(--cyan)" },
              { label: "RISK",       value: decision.risk ?? "—",
                color: DECISION_COLOR[decision.risk] ?? "var(--text)" },
            ].map(({ label, value, color, mono }) => (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "5px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{
                  fontFamily: "var(--mono)", fontSize: 10,
                  color: "var(--text-3)", textTransform: "uppercase",
                }}>
                  {label}
                </span>
                <span style={{
                  fontFamily: "var(--mono)", fontSize: 11, fontWeight: 700, color,
                  wordBreak: "break-all", textAlign: "right", maxWidth: "60%",
                }}>
                  {value ?? "—"}
                </span>
              </div>
            ))}
          </div>

          {/* Explanation */}
          {decision.explanation && (
            <div style={{
              fontFamily: "var(--mono)", fontSize: 10,
              color: "var(--text-3)", lineHeight: 1.6,
              marginBottom: 10,
            }}>
              {decision.explanation}
            </div>
          )}
        </>
      )}

      {/* Session note */}
      {!loading && (
        <div style={{
          fontFamily: "var(--mono)", fontSize: 9,
          color: "var(--text-3)", textAlign: "center",
          borderTop: hasEntry ? "1px solid var(--border)" : "none",
          paddingTop: hasEntry ? 8 : 0,
          opacity: 0.6,
        }}>
          QUEUE RESETS ON SERVER RESTART · PHASE 2.4 ADDS PAPER TRADING
        </div>
      )}
    </div>
  );
}
