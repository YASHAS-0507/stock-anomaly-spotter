import { formatINR } from "../services/market";

export default function TradeSetup({ prediction }) {
  if (!prediction) return null;

  const risk   = prediction.stage_5_risk_matrix;
  const entry  = prediction.latest_day_forecast?.close_at_execution;
  const decision = risk?.decision;
  const hasSetup = decision === "ENTER" && entry != null;

  const rows = hasSetup ? [
    { label: "Entry",       value: formatINR(entry),                color: "var(--cyan)"   },
    { label: "Stop Loss",   value: formatINR(risk?.stop_loss_limit),  color: "var(--red)"    },
    { label: "Take Profit", value: formatINR(risk?.take_profit_limit), color: "var(--green)"  },
    { label: "Quantity",    value: risk?.target_quantity != null ? `${risk.target_quantity} sh` : "—", color: "var(--text)" },
    { label: "Risk Capital", value: formatINR(risk?.allocated_risk_cash), color: "var(--text-2)" },
  ] : [];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Trade Setup</span>
        <span className="panel-badge" style={{ color: hasSetup ? "var(--green)" : "var(--text-3)" }}>
          {decision || "—"}
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
