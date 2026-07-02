import { useState, useEffect } from "react";
import {
  ResponsiveContainer, LineChart, Line, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
  Legend
} from "recharts";
import { formatPrice } from "@/utils/formatting";

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="tooltip-header">{label}</div>
      <div className="tooltip-row">
        <span className="tooltip-label">Price</span>
        <span className="tooltip-value">{formatPrice(payload[0].value)}</span>
      </div>
      {data.z !== undefined && (
        <div className="tooltip-row">
          <span className="tooltip-label">Z-Score</span>
          <span className="tooltip-value">{data.z.toFixed(2)}</span>
        </div>
      )}
      {data.volume !== undefined && (
        <div className="tooltip-row">
          <span className="tooltip-label">Volume</span>
          <span className="tooltip-value">{(data.volume / 1e6).toFixed(2)}M</span>
        </div>
      )}
    </div>
  );
}

const INTERVALS = [
  { value: "1m", label: "1m", minutes: 1 },
  { value: "5m", label: "5m", minutes: 5 },
  { value: "15m", label: "15m", minutes: 15 },
  { value: "30m", label: "30m", minutes: 30 },
  { value: "1h", label: "1h", minutes: 60 },
  { value: "1d", label: "1d", minutes: 1440 },
];

export default function LivePriceChart({ analysis, currentInterval, onIntervalChange }) {
  const [showVolume, setShowVolume] = useState(false);
  const [showMA, setShowMA] = useState(true);
  const [timeRange, setTimeRange] = useState("all");

  if (!analysis) {
    return (
      <div className="panel h-full flex flex-col">
        <div className="panel-header flex items-center justify-between">
          <span className="panel-title">Live Price Chart</span>
          <div className="flex items-center gap-sm">
            <select
              className="select"
              value={currentInterval}
              onChange={e => onIntervalChange(e.target.value)}
              style={{ width: "auto", minWidth: "80px" }}
            >
              {INTERVALS.map(i => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="panel-content flex-1 flex items-center justify-center">
          <div className="skeleton skeleton-card" />
        </div>
      </div>
    );
  }

  // Prepare chart data
  const chartData = analysis?.series?.date?.map((d, i) => ({
    timestamp: d,
    date: d.slice(5, 10),
    close: analysis.series.close[i],
    high: analysis.series.high?.[i] ?? analysis.series.close[i],
    low: analysis.series.low?.[i] ?? analysis.series.close[i],
    open: analysis.series.open?.[i] ?? analysis.series.close[i],
    volume: analysis.series.volume?.[i] ?? 0,
    z: analysis.series.return_zscore?.[i] ?? 0,
    ma20: analysis.series.ma20?.[i],
    ma50: analysis.series.ma50?.[i],
  })) || [];

  // Calculate simple MAs if not provided
  const calculateMA = (data, period) => {
    const result = [];
    for (let i = 0; i < data.length; i++) {
      if (i < period - 1) {
        result.push(null);
      } else {
        const sum = data.slice(i - period + 1, i + 1).reduce((a, b) => a + b.close, 0);
        result.push(sum / period);
      }
    }
    return result;
  };

  const ma20 = chartData.length ? calculateMA(chartData, 20) : [];
  const ma50 = chartData.length ? calculateMA(chartData, 50) : [];

  const enrichedData = chartData.map((d, i) => ({
    ...d,
    ma20: ma20[i],
    ma50: ma50[i],
  }));

  // Filter data based on time range
  let displayData = enrichedData;
  if (timeRange !== "all" && enrichedData.length > 0) {
    const now = new Date(enrichedData[enrichedData.length - 1].timestamp);
    const cutoff = new Date(now);
    const days = timeRange === "1m" ? 30 : timeRange === "3m" ? 90 : timeRange === "6m" ? 180 : timeRange === "1y" ? 365 : 0;
    if (days > 0) {
      cutoff.setDate(cutoff.getDate() - days);
      displayData = enrichedData.filter(d => new Date(d.timestamp) >= cutoff);
    }
  }

  const latestPrice = enrichedData[enrichedData.length - 1]?.close ?? 0;
  const priceChange = enrichedData.length > 1 
    ? latestPrice - enrichedData[enrichedData.length - 2].close 
    : 0;
  const priceChangePct = enrichedData.length > 1 
    ? (priceChange / enrichedData[enrichedData.length - 2].close) * 100 
    : 0;

  return (
    <div className="panel h-full flex flex-col">
      {/* Chart Header */}
      <div className="panel-header flex flex-wrap gap-md">
        <span className="panel-title">Live Price Chart</span>
        
        <div className="flex items-center gap-sm flex-1 justify-end flex-wrap">
          {/* Interval Selector */}
          <div className="flex items-center gap-xs">
            <span className="text-label hidden sm:inline">Interval</span>
            <select
              className="select"
              value={currentInterval}
              onChange={e => onIntervalChange(e.target.value)}
              style={{ width: "auto", minWidth: "80px" }}
            >
              {INTERVALS.map(i => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>

          {/* Time Range */}
          <div className="flex items-center gap-xs">
            <span className="text-label hidden sm:inline">Range</span>
            <select
              className="select"
              value={timeRange}
              onChange={e => setTimeRange(e.target.value)}
              style={{ width: "auto", minWidth: "100px" }}
            >
              <option value="all">All</option>
              <option value="1m">1 Month</option>
              <option value="3m">3 Months</option>
              <option value="6m">6 Months</option>
              <option value="1y">1 Year</option>
            </select>
          </div>

          {/* Overlays */}
          <div className="flex items-center gap-sm hidden sm:flex">
            <label className="flex items-center gap-xs cursor-pointer">
              <input
                type="checkbox"
                checked={showMA}
                onChange={e => setShowMA(e.target.checked)}
                className="accent-cyan"
              />
              <span className="text-caption">MA 20/50</span>
            </label>
            <label className="flex items-center gap-xs cursor-pointer ml-md">
              <input
                type="checkbox"
                checked={showVolume}
                onChange={e => setShowVolume(e.target.checked)}
                className="accent-cyan"
              />
              <span className="text-caption">Volume</span>
            </label>
          </div>

          {/* Live Price */}
          <div className="flex items-center gap-sm ml-auto">
            <div className="text-right hidden sm:block">
              <div className="text-metric font-mono">{formatPrice(latestPrice)}</div>
              <div className={`text-caption ${priceChange >= 0 ? "signal-buy" : "signal-sell"}`}>
                {priceChange >= 0 ? "+" : ""}{formatPrice(Math.abs(priceChange))} ({priceChangePct >= 0 ? "+" : ""}{priceChangePct.toFixed(2)}%)
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Chart Area */}
      <div className="panel-content flex-1 relative">
        <div className="chart-panel">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={displayData} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00D4FF" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00D4FF" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#FFB800" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#FFB800" stopOpacity={0} />
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="4 4" stroke="#1C2332" vertical={false} />
              
              <XAxis
                dataKey="date"
                stroke="#2A3448"
                tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
                tickCount={8}
              />
              
              <YAxis
                yAxisId="left"
                stroke="#2A3448"
                tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
                tickLine={false}
                axisLine={false}
                domain={["dataMin - 0.02", "dataMax + 0.02"]}
                width={70}
                tickFormatter={v => formatPrice(v)}
                orientation="right"
              />

              {showVolume && (
                <YAxis
                  yAxisId="right"
                  orientation="left"
                  stroke="#2A3448"
                  tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, "dataMax * 3"]}
                  width={60}
                  tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : v}
                  tickCount={3}
                  mirror={true}
                />
              )}

              <Tooltip content={<CustomTooltip />} />

              {/* Anomaly Reference Lines */}
              {analysis.anomalies?.map((a, i) => (
                <ReferenceLine
                  key={i}
                  x={a.date.slice(5)}
                  yAxisId="left"
                  stroke={a.anomaly_direction === "spike_up" ? "#00C48C" : "#FF4560"}
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  strokeOpacity={0.6}
                />
              ))}

              {/* Price Area */}
              <Area
                type="monotone"
                dataKey="close"
                stroke="#00D4FF"
                strokeWidth={1.5}
                fill="url(#priceGradient)"
                fillOpacity={1}
                yAxisId="left"
              />

              {/* Price Line */}
              <Line
                type="monotone"
                dataKey="close"
                stroke="#00D4FF"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, strokeWidth: 2, stroke: "#00D4FF", fill: "#0D1117" }}
                yAxisId="left"
              />

              {/* Moving Averages */}
              {showMA && (
                <>
                  <Line
                    type="monotone"
                    dataKey="ma20"
                    stroke="#FFB800"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                    dot={false}
                    opacity={0.7}
                    yAxisId="left"
                  />
                  <Line
                    type="monotone"
                    dataKey="ma50"
                    stroke="#FF4560"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                    dot={false}
                    opacity={0.7}
                    yAxisId="left"
                  />
                </>
              )}

              {/* Volume */}
              {showVolume && (
                <Area
                  yAxisId="right"
                  type="monotone"
                  dataKey="volume"
                  stroke="#FFB800"
                  strokeWidth={1}
                  fill="url(#volumeGradient)"
                  fillOpacity={1}
                  opacity={0.6}
                />
              )}

              <Legend
                wrapperStyle={{ paddingTop: 10 }}
                formatter={(value) => {
                  const labels = { close: "Price", ma20: "MA 20", ma50: "MA 50", volume: "Volume" };
                  return labels[value] || value;
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Anomaly Legend */}
        {analysis.anomalies?.length > 0 && (
          <div className="flex flex-wrap gap-sm mt-md pt-md border-t border-panel-border">
            <span className="text-label">Anomalies:</span>
            {analysis.anomalies.slice(-5).reverse().map((a, i) => (
              <span
                key={i}
                className={`badge px-sm py-xs ${a.anomaly_direction === "spike_up" ? "bg-buy" : "bg-sell"}`}
              >
                {a.date.slice(5)} z={a.return_zscore.toFixed(1)}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}