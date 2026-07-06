import { useState, useMemo } from "react";
import {
  ComposedChart, Bar, Line, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";

const GREEN  = "#00c48c";
const RED    = "#ff4560";
const CYAN   = "#00d0ff";
const YELLOW = "#f5a623";

const INTERVALS = ["1min", "5min", "15min"];

function calcEma(values, period) {
  const k = 2 / (period + 1);
  let e = null;
  return values.map(v => {
    if (v == null) return null;
    e = e == null ? v : v * k + e * (1 - k);
    return parseFloat(e.toFixed(2));
  });
}

function calcVwap(candles) {
  let cumTP = 0, cumVol = 0;
  return candles.map(c => {
    const tp = (c.high + c.low + c.close) / 3;
    cumTP  += tp * (c.volume || 1);
    cumVol += (c.volume || 1);
    return cumVol > 0 ? parseFloat((cumTP / cumVol).toFixed(2)) : null;
  });
}

function fmtTime(ts) {
  try {
    const d = new Date(ts);
    if (isNaN(d)) return String(ts).slice(11, 16);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return String(ts).slice(11, 16);
  }
}

function CandleShape(props) {
  const { x, y, width, height, payload } = props;
  if (!payload || height <= 0 || width <= 0) return null;
  const { open, high, low, close } = payload;
  if (open == null || high == null || low == null || close == null) return null;

  const isGreen = close >= open;
  const color   = isGreen ? GREEN : RED;
  const midX    = x + width / 2;

  // y = top pixel (≡ high price), y+height = bottom pixel (≡ low price)
  const priceRange = high - low;
  const pxPerPrice = priceRange > 0 ? height / priceRange : 1;

  const bodyTop    = y + (high - Math.max(open, close)) * pxPerPrice;
  const bodyBottom = y + (high - Math.min(open, close)) * pxPerPrice;
  const bodyH      = Math.max(1, bodyBottom - bodyTop);
  const bw         = Math.max(4, width * 0.65);
  const bx         = midX - bw / 2;

  return (
    <g>
      {/* Upper wick */}
      <line x1={midX} y1={y} x2={midX} y2={bodyTop} stroke={color} strokeWidth={1} />
      {/* Lower wick */}
      <line x1={midX} y1={bodyBottom} x2={midX} y2={y + height} stroke={color} strokeWidth={1} />
      {/* Body */}
      <rect x={bx} y={bodyTop} width={bw} height={bodyH} fill={color} />
    </g>
  );
}

function OhlcvTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const isGreen = d.close >= d.open;
  return (
    <div style={{
      background: "var(--elevated)", border: "1px solid var(--border)",
      borderRadius: 8, padding: "10px 14px", fontFamily: "var(--mono)", fontSize: 11,
      minWidth: 140,
    }}>
      <div style={{ color: "var(--text-3)", marginBottom: 6 }}>{d.time}</div>
      {[["O", d.open], ["H", d.high], ["L", d.low], ["C", d.close]].map(([k, v]) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <span style={{ color: "var(--text-3)" }}>{k}</span>
          <span style={{ color: k === "C" ? (isGreen ? GREEN : RED) : "var(--text)" }}>
            ₹{Number(v).toFixed(2)}
          </span>
        </div>
      ))}
      <div style={{
        display: "flex", justifyContent: "space-between", gap: 12,
        marginTop: 4, borderTop: "1px solid var(--border)", paddingTop: 4,
      }}>
        <span style={{ color: "var(--text-3)" }}>Vol</span>
        <span style={{ color: "var(--text-2)" }}>{Number(d.volume || 0).toLocaleString("en-IN")}</span>
      </div>
      {d.vwap != null && (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <span style={{ color: CYAN }}>VWAP</span>
          <span style={{ color: CYAN }}>₹{Number(d.vwap).toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, padding: "20px 16px", marginBottom: 16,
      height: 360, display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)" }}>
        Loading candles…
      </span>
    </div>
  );
}

export default function CandlestickChart({
  candles = [],
  ticker = "",
  interval = "5min",
  anomalies = [],
  loading = false,
  onIntervalChange,
}) {
  const [activeInterval, setActiveInterval] = useState(interval);

  function handleInterval(iv) {
    setActiveInterval(iv);
    if (onIntervalChange) onIntervalChange(iv);
  }

  // Build chart data: compute overlays if not provided by backend
  const { chartData, priceDomain, barDomain, maxVol } = useMemo(() => {
    if (!candles.length) return { chartData: [], priceDomain: ["auto", "auto"], barDomain: [0, 1], maxVol: 1 };

    const closes   = candles.map(c => c.close);
    const e9       = calcEma(closes, 9);
    const e21      = calcEma(closes, 21);
    const vwapVals = calcVwap(candles);

    const minLow  = Math.min(...candles.map(c => c.low));
    const maxHigh = Math.max(...candles.map(c => c.high));
    const pad     = Math.max((maxHigh - minLow) * 0.04, 1);
    const base    = minLow - pad;
    const top     = maxHigh + pad;
    const span    = top - base;

    const mVol = Math.max(...candles.map(c => c.volume || 0), 1);

    const data = candles.map((c, i) => ({
      ...c,
      time:   fmtTime(c.timestamp),
      vwap:   c.vwap  != null ? c.vwap  : vwapVals[i],
      ema9:   c.ema9  != null ? c.ema9  : e9[i],
      ema21:  c.ema21 != null ? c.ema21 : e21[i],
      // Stacked bar: barAxis domain [0, span]
      spacer: parseFloat((c.low  - base).toFixed(4)),
      range:  parseFloat((c.high - c.low).toFixed(4)),
    }));

    return {
      chartData:   data,
      priceDomain: [base, top],
      barDomain:   [0, span],
      maxVol:      mVol,
    };
  }, [candles]);

  const anomalyTimes = useMemo(
    () => (anomalies || []).map(a => fmtTime(a.timestamp || a.time)),
    [anomalies]
  );

  if (loading) return <Skeleton />;

  const displayTicker = ticker
    ? ticker.replace(".NSE", "").replace(".NS", "")
    : "Chart";

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      {/* Header */}
      <div className="panel-head">
        <span className="panel-title">{displayTicker} — {activeInterval}</span>
        <div style={{ display: "flex", gap: 6 }}>
          {INTERVALS.map(iv => (
            <button
              key={iv}
              onClick={() => handleInterval(iv)}
              style={{
                fontFamily: "var(--mono)", fontSize: 10,
                padding: "4px 10px", borderRadius: 5, cursor: "pointer",
                border: "1px solid",
                borderColor: activeInterval === iv ? "var(--cyan)" : "var(--border)",
                background: activeInterval === iv ? "rgba(0,208,255,0.12)" : "var(--elevated)",
                color: activeInterval === iv ? "var(--cyan)" : "var(--text-3)",
                letterSpacing: "0.04em",
              }}
            >
              {iv}
            </button>
          ))}
        </div>
      </div>

      {!chartData.length ? (
        <div style={{
          height: 280, display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
        }}>
          No candle data available
        </div>
      ) : (
        <>
          {/* OHLC price chart */}
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 60, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="time"
                tick={{ fontFamily: "var(--mono)", fontSize: 9, fill: "var(--text-3)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
                interval="preserveStartEnd"
              />
              {/* Price axis (for VWAP/EMA lines) — hidden, right side */}
              <YAxis
                yAxisId="price"
                orientation="right"
                domain={priceDomain}
                tick={{ fontFamily: "var(--mono)", fontSize: 9, fill: "var(--text-3)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `₹${Math.round(v)}`}
                width={56}
              />
              {/* Bar axis (for stacked candle bars) — hidden, left side */}
              <YAxis
                yAxisId="bar"
                orientation="left"
                domain={barDomain}
                hide
              />

              <Tooltip
                content={<OhlcvTooltip />}
                cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
              />

              {/* Anomaly markers */}
              {anomalyTimes.map((t, i) => (
                <ReferenceLine
                  key={i}
                  yAxisId="price"
                  x={t}
                  stroke="var(--yellow)"
                  strokeDasharray="4 2"
                  strokeWidth={1.5}
                />
              ))}

              {/* Invisible spacer bar (offsets candle body upward) */}
              <Bar
                yAxisId="bar"
                dataKey="spacer"
                stackId="candle"
                fill="transparent"
                isAnimationActive={false}
                legendType="none"
              />

              {/* Candlestick body + wicks (custom shape) */}
              <Bar
                yAxisId="bar"
                dataKey="range"
                stackId="candle"
                shape={<CandleShape />}
                isAnimationActive={false}
                legendType="none"
              >
                {chartData.map((_, i) => <Cell key={i} />)}
              </Bar>

              {/* VWAP overlay — cyan */}
              <Line
                yAxisId="price"
                dataKey="vwap"
                stroke={CYAN}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                legendType="none"
                connectNulls
              />

              {/* EMA9 — yellow dashed */}
              <Line
                yAxisId="price"
                dataKey="ema9"
                stroke={YELLOW}
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                legendType="none"
                connectNulls
              />

              {/* EMA21 — red dashed */}
              <Line
                yAxisId="price"
                dataKey="ema21"
                stroke={RED}
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                legendType="none"
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>

          {/* Volume bars */}
          <ResponsiveContainer width="100%" height={52}>
            <ComposedChart data={chartData} margin={{ top: 0, right: 60, bottom: 2, left: 4 }}>
              <XAxis dataKey="time" hide />
              <YAxis hide domain={[0, maxVol * 4]} />
              <Bar dataKey="volume" isAnimationActive={false} legendType="none" maxBarSize={16}>
                {chartData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.close >= entry.open
                      ? "rgba(0,196,140,0.45)"
                      : "rgba(255,69,96,0.45)"}
                  />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{
            display: "flex", gap: 14, padding: "6px 8px 2px",
            fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)",
          }}>
            <span style={{ color: CYAN }}>── VWAP</span>
            <span style={{ color: YELLOW }}>╌ EMA9</span>
            <span style={{ color: RED }}>╌ EMA21</span>
            {anomalyTimes.length > 0 && (
              <span style={{ color: "var(--yellow)" }}>│ Anomaly×{anomalyTimes.length}</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
