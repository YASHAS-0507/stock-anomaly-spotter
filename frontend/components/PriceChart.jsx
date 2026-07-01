import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine } from "recharts";
import { formatPrice } from "@/utils/formatting";

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div className="tooltip-label">{label}</div>
      <div className="tooltip-value">{formatPrice(payload[0].value)}</div>
    </div>
  );
}

export default function PriceChart({ analysis }) {
  const chartData = analysis?.series.date.map((d, i) => ({
    date: d.slice(5),
    close: analysis.series.close[i],
    z: analysis.series.return_zscore[i],
  }));

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Price series</span>
        <span className={`panel-badge ${analysis.used_synthetic_data ? "synthetic" : "live"}`}>
          {analysis.used_synthetic_data ? "synthetic" : "live data"}
        </span>
      </div>
      <div className="chart-wrap chart-panel">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1C2332" />
            <XAxis
              dataKey="date"
              stroke="#2A3448"
              tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="left"
              stroke="#2A3448"
              tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
              tickLine={false}
              axisLine={false}
              domain={["auto", "auto"]}
              width={64}
              tickFormatter={formatPrice}
            />
            <Tooltip content={<CustomTooltip />} />
            {analysis.anomalies.map((a, i) => (
              <ReferenceLine
                key={i}
                x={a.date.slice(5)}
                yAxisId="left"
                stroke={a.anomaly_direction === "spike_up" ? "#00C48C" : "#FF4560"}
                strokeDasharray="3 3"
                strokeWidth={1}
              />
            ))}
            <Line type="monotone" dataKey="close" stroke="#00D4FF" dot={false} strokeWidth={1.5} yAxisId="left" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}