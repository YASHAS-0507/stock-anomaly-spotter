import { useState, useEffect } from "react";
import { getMarketStatus, getValidationStats, getCacheInfo } from "@/services/market";

export default function MarketDataDashboard() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [interval, setInterval] = useState("1d");
  const [validationStats, setValidationStats] = useState(null);
  const [cacheInfo, setCacheInfo] = useState(null);

  const intervals = [
    { value: "1m", label: "1 Minute" },
    { value: "5m", label: "5 Minutes" },
    { value: "15m", label: "15 Minutes" },
    { value: "30m", label: "30 Minutes" },
    { value: "1h", label: "1 Hour" },
    { value: "1d", label: "1 Day" },
  ];

  const fetchStatus = async () => {
    try {
      const data = await getMarketStatus();
      setStatus(data);
    } catch (e) {
      setError(e.message);
    }
  };

  const fetchValidationStats = async () => {
    try {
      const data = await getValidationStats();
      setValidationStats(data);
    } catch (e) {
      console.warn("Validation stats fetch failed:", e);
    }
  };

  const fetchCacheInfo = async () => {
    try {
      const data = await getCacheInfo();
      setCacheInfo(data);
    } catch (e) {
      console.warn("Cache info fetch failed:", e);
    }
  };

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    await Promise.all([fetchStatus(), fetchValidationStats(), fetchCacheInfo()]);
    setLoading(false);
  };

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, 10000);
    return () => clearInterval(timer);
  }, []);

  const getStatusColor = (marketStatus) => {
    switch (marketStatus) {
      case "OPEN": return "var(--green)";
      case "PRE_OPEN": return "var(--yellow)";
      case "CLOSED": return "var(--text-3)";
      case "WEEKEND": return "var(--text-3)";
      default: return "var(--text-3)";
    }
  };

  const getFeedStatusColor = (feedStatus) => {
    switch (feedStatus) {
      case "CONNECTED": return "var(--green)";
      case "RECONNECTING": return "var(--yellow)";
      case "DISCONNECTED": return "var(--red)";
      default: return "var(--text-3)";
    }
  };

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Market Data Dashboard</span>
          <span className="panel-badge">Loading...</span>
        </div>
        <div className="loading-skeleton">
          <div className="skeleton-row">
            <div className="skeleton-item"></div>
            <div className="skeleton-item"></div>
            <div className="skeleton-item"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Market Data Dashboard</span>
        </div>
        <div className="error-bar">⚠ {error}</div>
      </div>
    );
  }

  const marketStatus = status?.market_status || "UNKNOWN";
  const feedStatus = status?.feed_status || "DISCONNECTED";

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">Market Data Dashboard</span>
        <span className="panel-badge">{status?.exchange || "NSE"}</span>
      </div>

      {/* STATUS GRID */}
      <div className="market-status-grid">
        <div className="status-card">
          <div className="status-label">Exchange</div>
          <div className="status-value">{status?.exchange || "NSE"}</div>
        </div>

        <div className="status-card">
          <div className="status-label">Market Status</div>
          <div className="status-value" style={{ color: getStatusColor(marketStatus) }}>
            {marketStatus}
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Feed Status</div>
          <div className="status-value" style={{ color: getFeedStatusColor(feedStatus) }}>
            {feedStatus}
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Latency</div>
          <div className="status-value">
            {status?.latency_ms || 0} ms
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Latest Candle</div>
          <div className="status-value font-mono">
            {status?.latest_candle || "N/A"}
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Current Interval</div>
          <div className="status-value">
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              className="interval-select"
            >
              {intervals.map((i) => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Data Quality</div>
          <div className="status-value" style={{ color: "var(--green)" }}>
            {status?.data_quality || "N/A"}
          </div>
        </div>

        <div className="status-card">
          <div className="status-label">Current Time (IST)</div>
          <div className="status-value font-mono" style={{ fontSize: "13px" }}>
            {status?.current_time_ist || "N/A"}
          </div>
        </div>
      </div>

      {/* VALIDATION STATS */}
      {(validationStats || status?.validation_stats) && (
        <div className="validation-section">
          <div className="section-title">Data Validation Statistics</div>
          <div className="validation-grid">
            <div className="validation-item">
              <span className="validation-label">Total Candles</span>
              <span className="validation-value">{validationStats?.total_candles || status?.validation_stats?.total_candles || 0}</span>
            </div>
            <div className="validation-item success">
              <span className="validation-label">Valid</span>
              <span className="validation-value">{validationStats?.valid_candles || status?.validation_stats?.valid_candles || 0}</span>
            </div>
            <div className="validation-item danger">
              <span className="validation-label">Invalid</span>
              <span className="validation-value">{validationStats?.invalid_candles || status?.validation_stats?.invalid_candles || 0}</span>
            </div>
            <div className="validation-item warning">
              <span className="validation-label">Missing Detected</span>
              <span className="validation-value">{validationStats?.missing_candles_detected || status?.validation_stats?.missing_candles_detected || 0}</span>
            </div>
            <div className="validation-item warning">
              <span className="validation-label">Duplicates Detected</span>
              <span className="validation-value">{validationStats?.duplicate_candles_detected || status?.validation_stats?.duplicate_candles_detected || 0}</span>
            </div>
            <div className="validation-item">
              <span className="validation-label">Validity Rate</span>
              <span className="validation-value">
                {(() => {
                  const total = validationStats?.total_candles || status?.validation_stats?.total_candles || 0;
                  const valid = validationStats?.valid_candles || status?.validation_stats?.valid_candles || 0;
                  return total > 0 ? ((valid / total) * 100).toFixed(1) + "%" : "N/A";
                })()}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* CACHE INFO */}
      {cacheInfo && (
        <div className="cache-section">
          <div className="section-title">Cache Status</div>
          <div className="cache-grid">
            <div className="cache-item">
              <span className="cache-label">Redis Connected</span>
              <span className={`cache-value ${cacheInfo.connected ? "connected" : "disconnected"}`}>
                {cacheInfo.connected ? "YES" : "NO (Local Fallback)"}
              </span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Cache Hit Rate</span>
              <span className="cache-value">{cacheInfo.cacheHitRate || "N/A"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Historical Cache</span>
              <span className="cache-value">{cacheInfo.historicalCacheSize || "0 MB"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Memory Usage</span>
              <span className="cache-value">{cacheInfo.memoryUsage || "N/A"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Total Keys</span>
              <span className="cache-value">{cacheInfo.totalKeys || 0}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">API Latency</span>
              <span className="cache-value">{cacheInfo.apiLatency || "N/A"}</span>
            </div>
          </div>
        </div>
      )}

      {/* INTERVAL SELECTOR */}
      <div className="interval-selector">
        <label className="interval-label">Default Interval for Historical Data:</label>
        <select
          value={interval}
          onChange={(e) => setInterval(e.target.value)}
          className="terminal-select"
        >
          {intervals.map((i) => (
            <option key={i.value} value={i.value}>{i.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}