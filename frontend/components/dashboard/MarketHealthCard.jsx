import { formatPercent } from "@/utils/formatting";
import { useEffect, useState } from "react";

export default function MarketHealthCard({ marketStatus, currentInterval }) {
  const [currentTime, setCurrentTime] = useState("--:--:--");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      // Convert to IST (UTC+5:30)
      const istOffset = 5.5 * 60 * 60 * 1000;
      const istTime = new Date(now.getTime() + istOffset);
      const hours = String(istTime.getUTCHours()).padStart(2, '0');
      const minutes = String(istTime.getUTCMinutes()).padStart(2, '0');
      const seconds = String(istTime.getUTCSeconds()).padStart(2, '0');
      setCurrentTime(`${hours}:${minutes}:${seconds}`);
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const statusColors = {
    OPEN: "var(--green)",
    PRE_OPEN: "var(--yellow)",
    CLOSED: "var(--text-3)",
    WEEKEND: "var(--text-3)",
  };

  const feedColors = {
    CONNECTED: "var(--green)",
    RECONNECTING: "var(--yellow)",
    DISCONNECTED: "var(--red)",
  };

  const feedStatus = marketStatus?.feed_status || "N/A";
  const marketPhase = marketStatus?.market_status || "N/A";
  const latency = marketStatus?.latency_ms ?? "N/A";
  const latestCandle = marketStatus?.latest_candle || "N/A";
  const dataQuality = marketStatus?.data_quality || "N/A";
  const serverTime = marketStatus?.current_time_ist || currentTime;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Market Health</span>
        <span className="panel-badge">NSE</span>
      </div>

      <div className="panel-content space-lg">
        {/* Market Status */}
        <div className="card p-lg">
          <div className="card-title">Market Status</div>
          <div className="mt-md flex items-center justify-between">
            <div className="flex items-center gap-sm">
              <span className="badge-dot" style={{ background: statusColors[marketPhase] || "var(--text-3)" }} />
              <span className="text-title" style={{ color: statusColors[marketPhase] || "var(--text-3)" }}>
                {marketPhase}
              </span>
            </div>
            <span className="text-caption font-mono text-2">IST</span>
          </div>
        </div>

        {/* Feed Status */}
        <div className="card p-lg">
          <div className="card-title">Feed Status</div>
          <div className="mt-md flex items-center justify-between">
            <div className="flex items-center gap-sm">
              <span className="badge-dot" style={{ background: feedColors[feedStatus] || "var(--red)" }} />
              <span className="text-title" style={{ color: feedColors[feedStatus] || "var(--red)" }}>
                {feedStatus}
              </span>
            </div>
            <span className="text-caption font-mono text-2">{latency}ms</span>
          </div>
        </div>

        {/* Grid Metrics */}
        <div className="grid grid-cols-2 gap-md">
          <div className="card p-md text-center">
            <div className="text-label">Latest Candle</div>
            <div className="text-metric-sm font-mono mt-sm">{latestCandle}</div>
          </div>
          <div className="card p-md text-center">
            <div className="text-label">Data Quality</div>
            <div className="text-metric-sm font-mono text-green mt-sm">{dataQuality}</div>
          </div>
          <div className="card p-md text-center">
            <div className="text-label">Current Interval</div>
            <div className="text-metric-sm font-mono mt-sm">{currentInterval}</div>
          </div>
          <div className="card p-md text-center">
            <div className="text-label">Exchange</div>
            <div className="text-metric-sm font-mono mt-sm">{marketStatus?.exchange || "NSE"}</div>
          </div>
        </div>

        {/* Time Sync */}
        <div className="card p-md">
          <div className="card-title">Time Sync</div>
          <div className="mt-md flex items-center justify-between">
            <span className="text-caption">Server Time (IST)</span>
            <span className="text-metric-sm font-mono" id="ist-time">{serverTime}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
