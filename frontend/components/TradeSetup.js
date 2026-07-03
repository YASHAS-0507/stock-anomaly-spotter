import { useState, useCallback } from "react";
import { API_BASE } from "../services/api";
import { formatINR } from "../services/market";

export default function TradeSetup({ prediction, decision }) {
  const [execState, setExecState] = useState("idle"); // idle | loading | success | error
  const [execMessage, setExecMessage] = useState("");

  // Prefer decision engine output when available and actionable
  const useDecision = decision && (decision.decision === "BUY" || decision.decision === "SELL");

  const handleExecute = useCallback(async () => {
    const tradeId = decision?.queue?.trade_id;
    if (!tradeId) return;
    setExecState("loading");
    setExecMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/paper/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trade_id: tradeId }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const fill = data.order?.fill_price ?? decision.entry_price;
        setExecState("success");
        setExecMessage(`Filled @ ₹${fill} · Order ${data.order?.order_id ?? ""}`);
      } else {
        setExecState("error");
        setExecMessage(data.detail || data.rejection_reason || "Execution failed");
      }
    } catch (e) {
      setExecState("error");
      setExecMessage("Network error");
    }
  }, [decision]);

  if (useDecision) {
    const d = decision;
    const tp = d.take_profit || {};
    const ps = d.position_size || {};
    const canExecute = d.execution_permitted && d.queue?.trade_id && execState === "idle";

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

    const execBg    = execState === "success" ? "var(--green)" : execState === "error" ? "var(--red)" : d.decision === "BUY" ? "var(--green)" : "var(--red)";
    const execLabel = execState === "loading" ? "EXECUTING…" : execState === "success" ? "EXECUTED" : execState === "error" ? "FAILED" : `EXECUTE PAPER ${d.decision}`;

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

        {d.execution_permitted && (
          <div style={{ marginTop: 14 }}>
            <button
              onClick={handleExecute}
              disabled={execState !== "idle"}
              style={{
                width: "100%", padding: "9px 0",
                fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700,
                color: execState === "idle" ? "#0a0a0a" : "var(--text)",
                background: execState === "idle" ? execBg : "transparent",
                border: `1px solid ${execBg}`,
                borderRadius: 4, cursor: execState === "idle" ? "pointer" : "not-allowed",
                letterSpacing: "0.06em", transition: "opacity 0.15s",
                opacity: execState === "loading" ? 0.6 : 1,
              }}
            >
              {execLabel}
            </button>
            {execMessage && (
              <div style={{
                marginTop: 6, fontFamily: "var(--mono)", fontSize: 10, textAlign: "center",
                color: execState === "success" ? "var(--green)" : "var(--red)",
              }}>
                {execMessage}
              </div>
            )}
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
