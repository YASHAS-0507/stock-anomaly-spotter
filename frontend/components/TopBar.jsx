import { useEffect, useState } from "react";

export default function TopBar({ marketStatus, onLogout }) {
  const [currentTime, setCurrentTime] = useState("--:--:--");

  useEffect(() => {
    const tick = () => {
      // Use backend IST time if available, else compute locally
      if (marketStatus?.current_time_ist) {
        setCurrentTime(marketStatus.current_time_ist);
      } else {
        const now = new Date();
        const ist = new Date(now.getTime() + 5.5 * 60 * 60 * 1000);
        const h = String(ist.getUTCHours()).padStart(2, "0");
        const m = String(ist.getUTCMinutes()).padStart(2, "0");
        const s = String(ist.getUTCSeconds()).padStart(2, "0");
        setCurrentTime(`${h}:${m}:${s} IST`);
      }
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [marketStatus?.current_time_ist]);

  const marketPhase  = marketStatus?.market_status ?? "N/A";
  const feedStatus   = marketStatus?.feed_status   ?? "N/A";
  const latency      = marketStatus?.latency_ms    ?? "N/A";

  const phaseColor = {
    OPEN:     "var(--green)",
    PRE_OPEN: "var(--yellow)",
    CLOSED:   "var(--text-3)",
    WEEKEND:  "var(--text-3)",
  }[marketPhase] ?? "var(--text-3)";

  const feedColor = {
    LIVE:        "var(--green)",
    CONNECTED:   "var(--green)",
    DELAYED:     "var(--yellow)",
    RECONNECTING:"var(--yellow)",
    DISCONNECTED:"var(--red)",
    UNAVAILABLE: "var(--red)",
  }[feedStatus] ?? "var(--text-3)";

  return (
    <header className="topbar">
      {/* Brand */}
      <div className="topbar-brand">
        <div className="brand-dot" />
        <div>
          <div className="brand-name">STOCK ANOMALY SPOTTER</div>
          <div className="brand-tag">Institutional Trading Terminal</div>
        </div>
      </div>

      {/* Center — market info */}
      <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
        <div style={{ textAlign: "center" }}>
          <div className="stat-label">EXCHANGE</div>
          <div className="stat-sub" style={{ fontFamily: "var(--mono)", color: "var(--text)" }}>
            {marketStatus?.exchange ?? "NSE"}
          </div>
        </div>

        <div style={{ textAlign: "center" }}>
          <div className="stat-label">MARKET</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              width: 7, height: 7, borderRadius: "50%",
              background: phaseColor,
              boxShadow: `0 0 6px ${phaseColor}`,
              display: "inline-block",
            }} />
            <span className="stat-sub" style={{ fontFamily: "var(--mono)", color: phaseColor }}>
              {marketPhase}
            </span>
          </div>
        </div>

        <div style={{ textAlign: "center" }}>
          <div className="stat-label">FEED</div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              width: 7, height: 7, borderRadius: "50%",
              background: feedColor,
              boxShadow: `0 0 6px ${feedColor}`,
              display: "inline-block",
            }} />
            <span className="stat-sub" style={{ fontFamily: "var(--mono)", color: feedColor }}>
              {feedStatus}
            </span>
          </div>
        </div>

        <div style={{ textAlign: "center" }}>
          <div className="stat-label">LATENCY</div>
          <div className="stat-sub" style={{ fontFamily: "var(--mono)", color: "var(--cyan)" }}>
            {latency === "Unavailable" ? "N/A" : `${latency}ms`}
          </div>
        </div>
      </div>

      {/* Right — time + logout */}
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ textAlign: "right" }}>
          <div className="stat-label">IST TIME</div>
          <div className="stat-sub" style={{ fontFamily: "var(--mono)", color: "var(--text)" }}>
            {currentTime}
          </div>
        </div>
        <button className="btn-logout" onClick={onLogout}>
          LOGOUT
        </button>
      </div>
    </header>
  );
}
