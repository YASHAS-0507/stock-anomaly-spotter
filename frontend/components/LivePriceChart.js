import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";

function computeMA(closes, window) {
  return closes.map((_, i) => {
    if (i < window - 1) return null;
    const sum = closes.slice(i - window + 1, i + 1).reduce((a, b) => a + b, 0);
    return +(sum / window).toFixed(2);
  });
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#0D1117", border: "1px solid #1C2332",
      borderRadius: 8, padding: "10px 14px",
      fontFamily: "JetBrains Mono, monospace", fontSize: 12,
    }}>
      <div style={{ color: "#8A95A8", marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) =>
        p.value != null ? (
          <div key={i} style={{ color: p.color, fontWeight: 600 }}>
            {p.name}: ₹{Number(p.value).toFixed(2)}
          </div>
        ) : null
      )}
    </div>
  );
}

export default function LivePriceChart({ analysis }) {
  if (!analysis) return null;

  const closes = analysis.series.close;
  const ma20 = computeMA(closes, 20);
  const ma50 = computeMA(closes, 50);

  const chartData = analysis.series.date.map((d, i) => ({
    date: d.slice(5),
    close: closes[i],
    ma20: ma20[i],
    ma50: ma50[i],
  }));

  const tickFormatter = (v) => {
    if (v >= 10000) return `₹${(v / 1000).toFixed(0)}k`;
    if (v >= 1000) return `₹${(v / 1000).toFixed(1)}k`;
    return `₹${Number(v).toFixed(0)}`;
  };

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Live Price Chart · {analysis.ticker}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "#00D4FF" }}>— Price</span>
          <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "#FFB800" }}>— MA20</span>
          <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "#8A95A8" }}>— MA50</span>
          <span className={`panel-badge ${analysis.used_synthetic_data ? "synthetic" : "live"}`}>
            {analysis.used_synthetic_data ? "synthetic" : "live data"}
          </span>
        </div>
      </div>

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1C2332" />
            <XAxis
              dataKey="date"
              stroke="#2A3448"
              tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
              tickLine={false} axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              stroke="#2A3448"
              tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
              tickLine={false} axisLine={false}
              domain={["auto", "auto"]} width={64}
              tickFormatter={tickFormatter}
            />
            <Tooltip content={<ChartTooltip />} />
            {analysis.anomalies.map((a, i) => (
              <ReferenceLine
                key={i}
                x={a.date.slice(5)}
                stroke={a.anomaly_direction === "spike_up" ? "#00C48C" : "#FF4560"}
                strokeDasharray="3 3" strokeWidth={1}
              />
            ))}
            <Line type="monotone" dataKey="close" name="Close" stroke="#00D4FF" dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="ma20" name="MA20" stroke="#FFB800" dot={false} strokeWidth={1} strokeDasharray="4 2" connectNulls={false} />
            <Line type="monotone" dataKey="ma50" name="MA50" stroke="#8A95A8" dot={false} strokeWidth={1} strokeDasharray="4 2" connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {analysis.anomalies.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {analysis.anomalies.slice(-6).reverse().map((a, i) => (
            <div key={i} style={{
              fontFamily: "var(--mono)", fontSize: 10,
              padding: "3px 8px", borderRadius: 4,
              background: a.anomaly_direction === "spike_up" ? "rgba(0,196,140,0.1)" : "rgba(255,69,96,0.1)",
              border: `1px solid ${a.anomaly_direction === "spike_up" ? "rgba(0,196,140,0.3)" : "rgba(255,69,96,0.3)"}`,
              color: a.anomaly_direction === "spike_up" ? "#00C48C" : "#FF4560",
            }}>
              {a.date} z={Number(a.return_zscore).toFixed(2)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
