export default function SystemHealthCard({ latency }) {
  const latencyDisp  = latency != null ? `${latency}ms` : "—";
  const latencyColor = !latency
    ? "var(--text-3)"
    : latency < 1000
    ? "var(--green)"
    : latency < 3000
    ? "#FFB800"
    : "var(--red)";

  const rows = [
    { label: "Redis Cache",   value: "Unavailable", color: "var(--text-3)", tag: "Phase 2" },
    { label: "CPU Usage",     value: "Unavailable", color: "var(--text-3)", tag: "psutil"  },
    { label: "Memory Usage",  value: "Unavailable", color: "var(--text-3)", tag: "psutil"  },
    { label: "Disk Usage",    value: "Unavailable", color: "var(--text-3)", tag: "psutil"  },
    { label: "API Latency",   value: latencyDisp,   color: latencyColor,    tag: null       },
    { label: "Backend",       value: "Operational", color: "var(--green)",  tag: null       },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">System Health</span>
        <span className="panel-badge" style={{ color: "var(--green)" }}>ONLINE</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {rows.map(({ label, value, color, tag }) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "9px 0", borderBottom: "1px solid var(--border)",
          }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase" }}>
              {label}
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 500, color }}>
                {value}
              </span>
              {tag && (
                <span style={{
                  fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-3)",
                  background: "var(--elevated)", padding: "1px 5px", borderRadius: 3,
                  border: "1px solid var(--border)",
                }}>
                  {tag}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
