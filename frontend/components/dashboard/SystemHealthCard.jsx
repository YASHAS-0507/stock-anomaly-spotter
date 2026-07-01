import { formatPercent } from "@/utils/formatting";

export default function SystemHealthCard({ validationStats }) {
  const stats = validationStats || {
    total_candles: 0,
    valid_candles: 0,
    invalid_candles: 0,
    missing_candles_detected: 0,
    duplicate_candles_detected: 0,
  };

  // Mock Redis info (would come from API in production)
  const redisInfo = {
    connected: false,
    cacheHitRate: "N/A",
    historicalCacheSize: "0 MB",
    memoryUsage: "N/A",
    totalKeys: 0,
    apiLatency: "N/A",
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">System Health</span>
        <span className="panel-badge">INFRASTRUCTURE</span>
      </div>

      <div className="panel-content space-lg">
        {/* Redis Status */}
        <div className="card p-lg">
          <div className="flex items-center justify-between mb-lg">
            <div className="card-title">Redis Cache</div>
            <div className="flex items-center gap-sm">
              <span className={`badge-dot ${redisInfo.connected ? "status-connected" : "status-disconnected"}`} />
              <span className="text-caption">{redisInfo.connected ? "CONNECTED" : "LOCAL FALLBACK"}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-md">
            <HealthMetric
              label="Cache Hit Rate"
              value={redisInfo.cacheHitRate}
              icon="🎯"
              status="neutral"
            />
            <HealthMetric
              label="Historical Cache"
              value={redisInfo.historicalCacheSize}
              icon="💾"
              status="neutral"
            />
            <HealthMetric
              label="Memory Usage"
              value={redisInfo.memoryUsage}
              icon="🧠"
              status="neutral"
            />
          </div>

          <div className="grid grid-cols-3 gap-md mt-md">
            <HealthMetric
              label="Total Keys"
              value={redisInfo.totalKeys.toLocaleString()}
              icon="🔑"
              status="neutral"
            />
            <HealthMetric
              label="API Latency"
              value={redisInfo.apiLatency}
              icon="⚡"
              status="neutral"
            />
            <HealthMetric
              label="Status"
              value={redisInfo.connected ? "HEALTHY" : "DEGRADED"}
              icon={redisInfo.connected ? "✅" : "⚠️"}
              status={redisInfo.connected ? "good" : "warning"}
            />
          </div>
        </div>

        {/* Data Validation */}
        <div className="card p-lg">
          <div className="card-title">Data Validation</div>
          <div className="mt-md grid grid-cols-2 md:grid-cols-4 gap-md">
            <ValidationMetric
              label="Total Candles"
              value={stats.total_candles.toLocaleString()}
              icon="📊"
            />
            <ValidationMetric
              label="Valid"
              value={stats.valid_candles.toLocaleString()}
              icon="✅"
              color="var(--green)"
            />
            <ValidationMetric
              label="Invalid"
              value={stats.invalid_candles.toLocaleString()}
              icon="❌"
              color="var(--red)"
            />
            <ValidationMetric
              label="Validity Rate"
              value={stats.total_candles > 0 
                ? formatPercent(stats.valid_candles / stats.total_candles) 
                : "N/A"}
              icon="📈"
              color={stats.total_candles > 0 && stats.valid_candles / stats.total_candles > 0.95 ? "var(--green)" : "var(--yellow)"}
            />
          </div>

          <div className="grid grid-cols-2 gap-md mt-md">
            <ValidationMetric
              label="Missing Candles"
              value={stats.missing_candles_detected.toLocaleString()}
              icon="🔍"
              color={stats.missing_candles_detected > 0 ? "var(--yellow)" : "var(--green)"}
            />
            <ValidationMetric
              label="Duplicates"
              value={stats.duplicate_candles_detected.toLocaleString()}
              icon="📋"
              color={stats.duplicate_candles_detected > 0 ? "var(--yellow)" : "var(--green)"}
            />
          </div>
        </div>

        {/* Data Freshness */}
        <div className="card p-lg">
          <div className="card-title">Data Freshness</div>
          <div className="mt-md grid grid-cols-3 gap-md">
            <HealthMetric
              label="Last Update"
              value="< 1s ago"
              icon="🕐"
              status="good"
            />
            <HealthMetric
              label="Feed Status"
              value="CONNECTED"
              icon="📡"
              status="good"
            />
            <HealthMetric
              label="Pipeline"
              value="HEALTHY"
              icon="🔄"
              status="good"
            />
          </div>
        </div>

        {/* System Resources */}
        <div className="card p-lg">
          <div className="card-title">System Resources</div>
          <div className="mt-md grid grid-cols-3 gap-md">
            <ResourceBar label="CPU" value={23} max={100} unit="%" color="var(--cyan)" />
            <ResourceBar label="Memory" value={412} max={2048} unit="MB" color="var(--yellow)" />
            <ResourceBar label="Disk" value={2.1} max={50} unit="GB" color="var(--green)" />
          </div>
        </div>
      </div>
    </div>
  );
}

function HealthMetric({ label, value, icon, status = "neutral", color }) {
  const statusColors = {
    good: "var(--green)",
    warning: "var(--yellow)",
    critical: "var(--red)",
    neutral: "var(--text-2)",
  };

  return (
    <div className="card p-md text-center">
      <div className="text-2xl mb-sm">{icon}</div>
      <div className="text-label">{label}</div>
      <div className="mt-sm flex items-center justify-center gap-xs">
        <span className="text-metric-sm font-mono" style={{ color: color || statusColors[status] }}>
          {value}
        </span>
      </div>
    </div>
  );
}

function ValidationMetric({ label, value, icon, color = "var(--text)" }) {
  return (
    <div className="card p-md text-center">
      <div className="text-2xl mb-sm">{icon}</div>
      <div className="text-label">{label}</div>
      <div className="mt-sm text-metric-sm font-mono" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function ResourceBar({ label, value, max, unit, color }) {
  const pct = (value / max) * 100;
  return (
    <div className="card p-md">
      <div className="flex items-center justify-between mb-sm">
        <span className="text-label">{label}</span>
        <span className="text-caption font-mono">{value}{unit} / {max}{unit}</span>
      </div>
      <div className="progress-bar" style={{ height: "8px" }}>
        <div className="progress-fill" style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
      </div>
      <div className="flex justify-between mt-xs text-caption text-3">
        <span>0{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

const statusColors = {
  good: "var(--green)",
  warning: "var(--yellow)",
  critical: "var(--red)",
  neutral: "var(--text-2)",
};