import { useState, useEffect } from "react";
import { getMarketStatus } from "../services/market";

export default function MarketHealthCard({ analysis }) {
  const [status, setStatus] = useState("CLOSED");

  useEffect(() => {
    setStatus(getMarketStatus());
    const id = setInterval(() => setStatus(getMarketStatus()), 60000);
    return () => clearInterval(id);
  }, []);

  const lastDate  = analysis?.series?.date?.at(-1) ?? "—";
  const lastClose = analysis?.series?.close?.at(-1);
  const feedLive  = analysis && !analysis.used_synthetic_data;

  const rows = [
    { label: "Exchange",      value: "NSE / BSE",         color: "var(--text)"   },
    { label: "Market Status", value: status,               color: status === "OPEN" ? "var(--green)" : "var(--text-3)" },
    { label: "Feed",          value: feedLive ? "LIVE MARKET" : analysis ? "SYNTHETIC" : "—", color: feedLive ? "var(--green)" : "var(--text-3)" },
    { label: "Latest Candle", value: lastDate,             color: "var(--text-2)" },
    { label: "Last Close",    value: lastClose != null ? `₹${Number(lastClose).toFixed(2)}` : "—", color: "var(--cyan)" },
    { label: "Data Points",   value: analysis ? `${analysis.data_points} days` : "—", color: "var(--text-2)" },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Market Health</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%",
            background: status === "OPEN" ? "var(--green)" : "var(--text-3)",
            boxShadow: status === "OPEN" ? "0 0 6px var(--green)" : "none",
          }} />
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: status === "OPEN" ? "var(--green)" : "var(--text-3)" }}>
            {status}
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {rows.map(({ label, value, color }) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "9px 0", borderBottom: "1px solid var(--border)",
          }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase" }}>
              {label}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 500, color }}>
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
