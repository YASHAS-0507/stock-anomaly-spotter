import { useState, useEffect } from "react";
import { getISTTime } from "../services/market";
import { useWebSocket } from "../hooks/useWebSocket";

export default function TopBar({ analysis, latency: propLatency }) {
  const [istTime, setIstTime] = useState("--:--:--");
  const ws = useWebSocket();

  useEffect(() => {
    function tick() { setIstTime(getISTTime()); }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const marketStatus = ws.marketStatus;
  const displayLatency = ws.latency ?? propLatency;

  const feedStatus = ws.connected ? "LIVE" : "DISCONNECTED";
  const feedColor  = ws.connected ? "var(--green)" : "var(--red)";
  const schedulerRunning = ws.wsSchedulerStatus?.running === true;

  const latencyColor = !displayLatency
    ? "var(--text-3)"
    : displayLatency < 2000
    ? "var(--green)"
    : "var(--red)";

  return (
    <div className="topbar">
      <style>{`
        @keyframes scheduler-pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 6px #00c48c; }
          50%       { opacity: 0.4; box-shadow: 0 0 2px #00c48c; }
        }
      `}</style>
      <div className="topbar-brand">
        <div className="brand-dot" />
        <div>
          <div className="brand-name">Stock Anomaly Spotter</div>
          <div className="brand-tag">Institutional Trading Terminal · v1.0</div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 20, fontFamily: "var(--mono)", fontSize: 12 }}>
        {schedulerRunning && (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{
              width: 6, height: 6, borderRadius: "50%",
              background: "#00c48c",
              animation: "scheduler-pulse 1.2s ease-in-out infinite",
            }} />
            <span style={{ color: "#00c48c" }}>AUTO</span>
          </div>
        )}
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
          <span style={{ color: latencyColor }}>{displayLatency ? `${displayLatency}ms` : "—"}</span>
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
