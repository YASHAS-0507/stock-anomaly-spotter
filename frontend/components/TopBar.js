import { useState, useEffect } from "react";
import { getISTTime, getMarketStatus } from "../services/market";

export default function TopBar({ analysis, latency }) {
  const [istTime, setIstTime] = useState("--:--:--");
  const [marketStatus, setMarketStatus] = useState("CLOSED");

  useEffect(() => {
    function tick() {
      setIstTime(getISTTime());
      setMarketStatus(getMarketStatus());
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const feedStatus = !analysis ? "—" : analysis.used_synthetic_data ? "SYNTHETIC" : "LIVE";
  const feedColor = !analysis ? "var(--text-3)" : analysis.used_synthetic_data ? "var(--text-3)" : "var(--green)";
  const latencyColor = !latency
    ? "var(--text-3)"
    : latency < 2000
    ? "var(--green)"
    : "var(--red)";

  return (
    <div className="topbar">
      <div className="topbar-brand">
        <div className="brand-dot" />
        <div>
          <div className="brand-name">Stock Anomaly Spotter</div>
          <div className="brand-tag">Institutional Trading Terminal · v1.0</div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 20, fontFamily: "var(--mono)", fontSize: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%",
            background: marketStatus === "OPEN" ? "var(--green)" : "var(--text-3)",
            boxShadow: marketStatus === "OPEN" ? "0 0 6px var(--green)" : "none",
          }} />
          <span style={{ color: marketStatus === "OPEN" ? "var(--green)" : "var(--text-3)" }}>
            NSE {marketStatus}
          </span>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <span style={{ color: "var(--text-3)" }}>FEED</span>
          <span style={{ color: feedColor }}>{feedStatus}</span>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <span style={{ color: "var(--text-3)" }}>API</span>
          <span style={{ color: latencyColor }}>{latency ? `${latency}ms` : "—"}</span>
        </div>

        <div style={{ color: "var(--cyan)", letterSpacing: "0.06em" }}>
          {istTime} IST
        </div>

        <button
          className="btn-logout"
          onClick={async () => {
            await fetch("/api/logout", { method: "POST" });
            window.location.href = "/login";
          }}
        >
          SIGN OUT
        </button>
      </div>
    </div>
  );
}
