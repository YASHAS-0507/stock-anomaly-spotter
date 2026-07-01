import { useEffect, useState } from "react";
import { API_BASE } from "@/services/api";

export default function SystemHealthCard({ validationStats, cacheInfo }) {
  const [telemetry, setTelemetry] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const fetchTelemetry = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/system/telemetry`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setTelemetry(data);
      } catch {
        // silently fail — Unavailable shown in UI
      }
    };

    fetchTelemetry();
    const timer = setInterval(fetchTelemetry, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const stats = validationStats || {
    total_candles: 0,
    valid_candles: 0,
    invalid_candles: 0,
    missing_candles_detected: 0,
    duplicate_candles_detected: 0,
  };

  // cacheInfo comes from /api/market/cache/info
  // fields: connected, local_cache_entries, redis_info.used_memory_human,
  //         redis_info.total_keys, redis_info.connected_clients
  const redisInfo = cacheInfo || {};
  const isRedisConnected = redisInfo.connected ?? false;

  const cpu    = telemetry?.cpu_usage_percent    ?? "Unavailable";
  const memory = telemetry?.memory_usage_mb      ?? "Unavailable";
  const disk   = telemetry?.disk_usage_gb        ?? "Unavailable";

  const cpuNum    = typeof cpu    === "number" ? cpu    : null;
  const memNum    = typeof memory === "number" ? memory : null;
  const diskNum   = typeof disk   === "number" ? disk   : null;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">System Health</span>
        <span className="panel-badge">INFRASTRUCTURE</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>

        {/* Redis / Cache Status */}
        <div style={{ background: "var(--elevated)", borderRadius: 10, padding: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span className="panel-title" style={{ fontSize: 11 }}>Cache Status</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className={`badge-dot ${isRedisConnected ? "status-open" : "status-closed"}`} />
              <span className="text-body" style={{ fontSize: 11 }}>
                {isRedisConnected ? "REDIS CONNECTED" : "LOCAL FALLBACK"}
              </span>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            <MetricTile
              label="Local Entries"
              value={redisInfo.local_cache_entries ?? "N/A"}
            />
            <MetricTile
              label="Redis Keys"
              value={redisInfo.redis_info?.total_keys ?? "N/A"}
            />
            <MetricTile
              label="Memory"
              value={redisInfo.redis_info?.used_memory_human ?? "N/A"}
            />
          </div>
        </div>

        {/* System Resources — real telemetry from /api/system/telemetry */}
        <div style={{ background: "var(--elevated)", borderRadius: 10, padding: "16px" }}>
          <span className="panel-title" style={{ fontSize: 11, display: "block", marginBottom: 12 }}>
            System Resources
          </span>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <ResourceRow
              label="CPU"
              value={cpu}
              numValue={cpuNum}
              max={100}
              unit="%"
              color="var(--cyan)"
            />
            <ResourceRow
              label="Memory"
              value={memory}
              numValue={memNum}
              max={16384}
              unit=" MB"
              color="var(--yellow)"
            />
            <ResourceRow
              label="Disk"
              value={disk}
              numValue={diskNum}
              max={500}
              unit=" GB"
              color="var(--green)"
            />
          </div>
        </div>

        {/* Data Validation */}
        <div style={{ background: "var(--elevated)", borderRadius: 10, padding: "16px" }}>
          <span className="panel-title" style={{ fontSize: 11, display: "block", marginBottom: 12 }}>
            Data Validation
          </span>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
            <MetricTile label="Total Candles"  value={stats.total_candles} />
            <MetricTile label="Valid"          value={stats.valid_candles}   color="var(--green)" />
            <MetricTile label="Invalid"        value={stats.invalid_candles} color={stats.invalid_candles > 0 ? "var(--red)" : "var(--green)"} />
            <MetricTile
              label="Validity Rate"
              value={
                stats.total_candles > 0
                  ? `${((stats.valid_candles / stats.total_candles) * 100).toFixed(1)}%`
                  : "N/A"
              }
              color={
                stats.total_candles > 0 && stats.valid_candles / stats.total_candles > 0.95
                  ? "var(--green)"
                  : "var(--yellow)"
              }
            />
            <MetricTile
              label="Missing"
              value={stats.missing_candles_detected}
              color={stats.missing_candles_detected > 0 ? "var(--yellow)" : "var(--green)"}
            />
            <MetricTile
              label="Duplicates"
              value={stats.duplicate_candles_detected}
              color={stats.duplicate_candles_detected > 0 ? "var(--yellow)" : "var(--green)"}
            />
          </div>
        </div>

      </div>
    </div>
  );
}

function MetricTile({ label, value, color = "var(--text)" }) {
  return (
    <div style={{
      background: "var(--surface)",
      borderRadius: 8,
      padding: "10px 12px",
      textAlign: "center",
    }}>
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ fontSize: 16, color }}>
        {value ?? "N/A"}
      </div>
    </div>
  );
}

function ResourceRow({ label, value, numValue, max, unit, color }) {
  const pct = numValue !== null ? Math.min((numValue / max) * 100, 100) : 0;
  const displayValue = numValue !== null ? `${value}${unit}` : "Unavailable";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span className="stat-label">{label}</span>
        <span className="stat-sub" style={{ fontFamily: "var(--mono)", color: numValue !== null ? color : "var(--text-3)" }}>
          {displayValue}
        </span>
      </div>
      <div style={{ height: 6, background: "var(--border)", borderRadius: 999, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: numValue !== null ? `${pct}%` : "0%",
          background: color,
          borderRadius: 999,
          transition: "width 0.6s ease",
        }} />
      </div>
    </div>
  );
}
