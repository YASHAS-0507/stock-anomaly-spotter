import { formatINR } from "../services/market";

export default function TradeSetup({ prediction, decision }) {
  // Prefer decision engine output when available and actionable
  const useDecision = decision && (decision.decision === "BUY" || decision.decision === "SELL");

  if (useDecision) {
    const d = decision;
    const tp = d.take_profit || {};
    const ps = d.position_size || {};

    const rows = [
      { label: "Entry",          value: formatINR(d.entry_price),           color: "var(--cyan)"   },
      { label: "Stop Loss",      value: formatINR(d.stop_loss),             color: "var(--red)"    },
      { label: "TP1 (1:1)",      value: formatINR(tp.tp1),                  color: "var(--green)"  },
      { label: "TP2 (1:2)",      value: formatINR(tp.tp2),                  color: "var(--green)"  },
      { label: "TP3 (1:3)",      value: formatINR(tp.tp3),                  color: "var(--green)"  },
      { label: "Shares",         value: ps.shares != null ? `${ps.shares} sh` : "—", color: "var(--text)" },
      { label: "Position Value", value: formatINR(ps.value),                color: "var(--text-2)" },
      { label: "Holding",        value: d.holding_period || "—",            color: "var(--text-3)" },
    ];

    return (
      <div className="panel" style={{ marginBottom: 0 }}>
        <div className="panel-head">
          <span className="panel-title">Trade Setup</span>
          <span className="panel-badge" style={{ color: d.decision === "BUY" ? "var(--green)" : "var(--red)" }}>
            {d.decision}
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          {rows.map(({ label, value, color }) => (
            <div key={label} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "8px 0", borderBottom: "1px solid var(--border)",
            }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase" }}>
                {label}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, color }}>
                {value}
              </span>
            </div>
          ))}
        </div>

        {d.explanation && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", lineHeight: 1.6, paddingTop: 10 }}>
            {d.explanation}
          </div>
        )}
      </div>
    );
  }

  // Fallback: original /api/predict stage_5_risk_matrix behaviour
  if (!prediction) return null;

  const risk          = prediction.stage_5_risk_matrix;
  const entry         = prediction.latest_day_forecast?.close_at_execution;
  const riskDecision  = risk?.decision;
  const hasSetup      = riskDecision === "ENTER" && entry != null;

  const rows = hasSetup ? [
    { label: "Entry",        value: formatINR(entry),                       color: "var(--cyan)"   },
    { label: "Stop Loss",    value: formatINR(risk?.stop_loss_limit),       color: "var(--red)"    },
    { label: "Take Profit",  value: formatINR(risk?.take_profit_limit),     color: "var(--green)"  },
    { label: "Quantity",     value: risk?.target_quantity != null ? `${risk.target_quantity} sh` : "—", color: "var(--text)" },
    { label: "Risk Capital", value: formatINR(risk?.allocated_risk_cash),   color: "var(--text-2)" },
  ] : [];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Trade Setup</span>
        <span className="panel-badge" style={{ color: hasSetup ? "var(--green)" : "var(--text-3)" }}>
          {riskDecision || "—"}
        </span>
      </div>

      {!hasSetup ? (
        <div style={{ padding: "20px 0", textAlign: "center" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)", marginBottom: 8 }}>
            NO ACTIVE SETUP
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", lineHeight: 1.6 }}>
            {risk?.risk_mitigation_reason || "Awaiting valid signal"}
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {rows.map(({ label, value, color }) => (
            <div key={label} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "9px 0", borderBottom: "1px solid var(--border)",
            }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase" }}>
                {label}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, color }}>
                {value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
