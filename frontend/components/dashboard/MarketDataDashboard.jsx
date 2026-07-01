import { useState, useEffect } from "react";

export default function MarketDataDashboard({ status, validationStats, cacheInfo, loading = false, error = null, currentInterval = "1d", onIntervalChange }) {
  const [localInterval, setLocalInterval] = useState(currentInterval);

  const intervals = [
    { value: "1m", label: "1 Minute" },
    { value: "5m", label: "5 Minutes" },
    { value: "15m", label: "15 Minutes" },
    { value: "30m", label: "30 Minutes" },
    { value: "1h", label: "1 Hour" },
    { value: "1d", label: "1 Day" },
  ];

  useEffect(() => {
    setLocalInterval(currentInterval);
  }, [currentInterval]);

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

  const marketStatus = status?.market_status || "N/A";
  const feedStatus = status?.feed_status || "N/A";

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
              value={localInterval}
              onChange={(e) => {
                setLocalInterval(e.target.value);
                onIntervalChange?.(e.target.value);
              }}
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
              <span className="validation-value">{validationStats?.total_candles ?? status?.validation_stats?.total_candles ?? "N/A"}</span>
            </div>
            <div className="validation-item success">
              <span className="validation-label">Valid</span>
              <span className="validation-value">{validationStats?.valid_candles ?? status?.validation_stats?.valid_candles ?? "N/A"}</span>
            </div>
            <div className="validation-item danger">
              <span className="validation-label">Invalid</span>
              <span className="validation-value">{validationStats?.invalid_candles ?? status?.validation_stats?.invalid_candles ?? "N/A"}</span>
            </div>
            <div className="validation-item warning">
              <span className="validation-label">Missing Detected</span>
              <span className="validation-value">{validationStats?.missing_candles_detected ?? status?.validation_stats?.missing_candles_detected ?? "N/A"}</span>
            </div>
            <div className="validation-item warning">
              <span className="validation-label">Duplicates Detected</span>
              <span className="validation-value">{validationStats?.duplicate_candles_detected ?? status?.validation_stats?.duplicate_candles_detected ?? "N/A"}</span>
            </div>
            <div className="validation-item">
              <span className="validation-label">Validity Rate</span>
              <span className="validation-value">
                {(() => {
                  const total = validationStats?.total_candles ?? status?.validation_stats?.total_candles;
                  const valid = validationStats?.valid_candles ?? status?.validation_stats?.valid_candles;
                  return total != null && total > 0 ? ((valid / total) * 100).toFixed(1) + "%" : "N/A";
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
              <span className="cache-label">Cache Size</span>
              <span className="cache-value">{cacheInfo.local_cache_entries ?? "N/A"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Historical Cache</span>
              <span className="cache-value">{cacheInfo.redis_info?.total_keys ?? "N/A"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Memory Usage</span>
              <span className="cache-value">{cacheInfo.redis_info?.used_memory_human ?? "N/A"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">Total Keys</span>
              <span className="cache-value">{cacheInfo.redis_info?.total_keys ?? "N/A"}</span>
            </div>
            <div className="cache-item">
              <span className="cache-label">API Latency</span>
              <span className="cache-value">{cacheInfo.apiLatency ?? "N/A"}</span>
            </div>
          </div>
        </div>
      )}

      {/* INTERVAL SELECTOR */}
    </div>
  );
}
