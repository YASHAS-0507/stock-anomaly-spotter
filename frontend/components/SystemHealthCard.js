import { useState, useEffect } from "react";
import { API_BASE } from "../services/api";

function metricColor(pct) {
  if (pct == null || pct === "Unavailable") return "var(--text-3)";
  const n = Number(pct);
  if (n < 60) return "var(--green)";
  if (n < 85) return "#FFB800";
  return "var(--red)";
}

export default function SystemHealthCard({ latency }) {
  const [telemetry, setTelemetry] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchTelemetry() {
      try {
        const res = await fetch(`${API_BASE}/api/system/telemetry`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setTelemetry(data);
      } catch (_) {}
    }

    fetchTelemetry();
    const id = setInterval(fetchTelemetry, 15000); // refresh every 15s
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const latencyDisp  = latency != null ? `${latency}ms` : "—";
  const latencyColor = !latency
    ? "var(--text-3)"
    : latency < 1000
    ? "var(--green)"
    : latency < 3000
    ? "#FFB800"
    : "var(--red)";

  const cpu    = telemetry?.cpu_usage_percent;
  const memPct = telemetry?.memory_usage_percent;
  const memUsed = telemetry?.memory_used_mb;
  const memTotal = telemetry?.memory_total_mb;
  const diskPct = telemetry?.disk_usage_percent;
  const diskUsed = telemetry?.disk_used_gb;
  const diskTotal = telemetry?.disk_total_gb;
  const redis = telemetry?.redis_status;

  const fmt = (v, unit) =>
    v == null || v === "Unavailable" ? "Unavailable" : `${v}${unit}`;

  const memLabel = memUsed != null && memTotal != null
    ? `${memPct}% (${Math.round(memUsed)}/${Math.round(memTotal)} MB)`
    : fmt(memPct, "%");

  const diskLabel = diskUsed != null && diskTotal != null
    ? `${diskPct}% (${diskUsed}/${diskTotal} GB)`
    : fmt(diskPct, "%");

  const rows = [
    { label: "Redis Cache",  value: redis ?? "—",            color: redis === "Connected" ? "var(--green)" : "var(--text-3)" },
    { label: "CPU Usage",    value: cpu != null && cpu !== "Unavailable" ? `${cpu}%` : "Unavailable", color: metricColor(cpu) },
    { label: "Memory Usage", value: memLabel,                color: metricColor(memPct) },
    { label: "Disk Usage",   value: diskLabel,               color: metricColor(diskPct) },
    { label: "API Latency",  value: latencyDisp,             color: latencyColor },
    { label: "Backend",      value: "Operational",           color: "var(--green)" },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">System Health</span>
        <span className="panel-badge" style={{ color: "var(--green)" }}>ONLINE</span>
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
