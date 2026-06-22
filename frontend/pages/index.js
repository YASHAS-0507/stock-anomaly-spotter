import { useState } from "react";
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const TREND_ICON = { "rising": "↗", "falling": "↘", "flat / choppy": "→" };
const TREND_COLOR = { "rising": "#00C48C", "falling": "#FF4560", "flat / choppy": "#8A95A8" };

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#0D1117", border: "1px solid #1C2332",
      borderRadius: 8, padding: "10px 14px",
      fontFamily: "JetBrains Mono, monospace", fontSize: 12,
    }}>
      <div style={{ color: "#8A95A8", marginBottom: 4 }}>{label}</div>
      <div style={{ color: "#00D4FF", fontWeight: 600 }}>
        ₹{Number(payload[0].value).toFixed(2)}
      </div>
    </div>
  );
}

export default function Home() {
  const [ticker, setTicker] = useState("RELIANCE.NS");
  const [period, setPeriod] = useState("1y");
  const [horizon, setHorizon] = useState("5");
  const [analysis, setAnalysis] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [chartTrend, setChartTrend] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [drag, setDrag] = useState(false);

  async function runAnalysis() {
  setLoading(true);
  setError(null);
  try {
    const [aRes, pRes] = await Promise.all([
      fetch(`${API_BASE}/api/analyze?ticker=${encodeURIComponent(ticker)}&period=${period}`),
      fetch(`${API_BASE}/api/predict?ticker=${encodeURIComponent(ticker)}&period=${period}&horizon=${horizon}`),
    ]);
      if (!aRes.ok) throw new Error((await aRes.json()).detail || "Analysis failed");
      if (!pRes.ok) throw new Error((await pRes.json()).detail || "Prediction failed");
      setAnalysis(await aRes.json());
      setPrediction(await pRes.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function uploadChart(file) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/chart-trend`, { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json()).detail || "Could not read chart");
      setChartTrend(await res.json());
    } catch (e) {
      setError(e.message);
    }
  }

  const chartData = analysis?.series.date.map((d, i) => ({
    date: d.slice(5),
    close: analysis.series.close[i],
    z: analysis.series.return_zscore[i],
  }));

  const anomalyDates = new Set(analysis?.anomalies.map(a => a.date.slice(5)));

  const probUp = prediction?.latest_day_prediction.prob_up ?? 0.5;
  const dir = prediction?.latest_day_prediction.predicted_direction;
  const accBeat = prediction && prediction.test_set_accuracy > prediction.baseline_majority_class_accuracy;
  const accTie = prediction && prediction.test_set_accuracy === prediction.baseline_majority_class_accuracy;
  const accDiff = prediction
    ? ((prediction.test_set_accuracy - prediction.baseline_majority_class_accuracy) * 100).toFixed(1)
    : 0;

  return (
    <div className="page">
      {/* TOPBAR */}
      <div className="topbar">
        <div className="topbar-brand">
          <div className="brand-dot" />
          <div>
            <div className="brand-name">Stock Anomaly Spotter</div>
            <div className="brand-tag">ML-powered technical analysis · Python + FastAPI</div>
          </div>
        </div>
        <button
          className="btn-logout"
          onClick={async () => {
            await fetch("/api/logout", { method: "POST" });
            window.location.href = "/login";
          }}
        >
          SIGN OUT
        </button>
      </div>

      {/* TERMINAL INPUT */}
      <div className="terminal-section">
        <div className="terminal-label">Enter ticker symbol</div>
        <div className="terminal-row">
          <div className="terminal-input-wrap">
            <span className="terminal-prompt">$</span>
            <input
              className="terminal-input"
              value={ticker}
              onChange={e => setTicker(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !loading && runAnalysis()}
              placeholder="e.g. RELIANCE.NS or AAPL"
            />
          </div>
          <select className="terminal-select" value={period} onChange={e => setPeriod(e.target.value)}>
            <option value="3mo">3 months</option>
            <option value="6mo">6 months</option>
            <option value="1y">1 year</option>
            <option value="2y">2 years</option>
          </select>
          <select className="terminal-select" value={horizon} onChange={e => setHorizon(e.target.value)}>
            <option value="1">1-Day Horizon</option>
            <option value="5">5-Day Horizon</option>
            <option value="10">10-Day Horizon</option>
          </select>
          <button className="btn-run" onClick={runAnalysis} disabled={loading}>
            {loading ? "RUNNING..." : "RUN ANALYSIS"}
          </button>
        </div>
      </div>

      {error && <div className="error-bar">⚠ {error}</div>}

      {analysis && (
        <div className="results">
          {/* STAT STRIP */}
          <div className="stat-strip">
            <div className="stat-card accent">
              <div className="stat-label">Ticker</div>
              <div className="stat-value cyan">{analysis.ticker}</div>
              <div className="stat-sub">{analysis.data_points} trading days</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Anomalies detected</div>
              <div className="stat-value">{analysis.anomaly_summary.count}</div>
              <div className="stat-sub">
                ↑{analysis.anomaly_summary.spike_up} spike up &nbsp;·&nbsp; ↓{analysis.anomaly_summary.spike_down} spike down
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Max |z-score|</div>
              <div className="stat-value">{analysis.anomaly_summary.max_abs_zscore}</div>
              <div className="stat-sub">rolling 20-day window</div>
            </div>
            <div className={`stat-card ${analysis.used_synthetic_data ? "" : "up"}`}>
              <div className="stat-label">Data source</div>
              <div className="stat-value" style={{ fontSize: 16, paddingTop: 6 }}>
                {analysis.used_synthetic_data ? "⚬ Synthetic" : "● Live market"}
              </div>
              <div className="stat-sub">via yfinance API</div>
            </div>
          </div>

          {/* TWO COL: CHART + ANOMALIES */}
          <div className="two-col">
            <div className="panel" style={{ marginBottom: 0 }}>
              <div className="panel-head">
                <span className="panel-title">Price series</span>
                <span className={`panel-badge ${analysis.used_synthetic_data ? "synthetic" : "live"}`}>
                  {analysis.used_synthetic_data ? "synthetic" : "live data"}
                </span>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#1C2332" />
                    <XAxis dataKey="date" stroke="#2A3448" tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis stroke="#2A3448" tick={{ fill: "#4A5568", fontSize: 10, fontFamily: "JetBrains Mono" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} width={56} tickFormatter={v => `₹${v >= 1000 ? (v/1000).toFixed(1)+"k" : v}`} />
                    <Tooltip content={<CustomTooltip />} />
                    {analysis.anomalies.map((a, i) => (
                      <ReferenceLine key={i} x={a.date.slice(5)} stroke={a.anomaly_direction === "spike_up" ? "#00C48C" : "#FF4560"} strokeDasharray="3 3" strokeWidth={1} />
                    ))}
                    <Line type="monotone" dataKey="close" stroke="#00D4FF" dot={false} strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel" style={{ marginBottom: 0 }}>
              <div className="panel-head">
                <span className="panel-title">Anomaly days</span>
                <span className="panel-badge">{analysis.anomaly_summary.count} flagged</span>
              </div>
              <div className="anomaly-list">
                {analysis.anomalies.length === 0 && (
                  <div style={{ color: "var(--text-3)", fontSize: 12, fontFamily: "var(--mono)" }}>
                    No anomalies at z ≥ 2.2σ
                  </div>
                )}
                {analysis.anomalies.slice(-7).reverse().map((a, i) => (
                  <div className="anomaly-item" key={i}>
                    <div className={`anomaly-bar ${a.anomaly_direction === "spike_up" ? "up" : "down"}`} />
                    <div>
                      <div className="anomaly-date">{a.date}</div>
                      <div className="anomaly-price">₹{Number(a.close).toFixed(2)}</div>
                    </div>
                    <div className={`anomaly-z ${a.anomaly_direction === "spike_up" ? "up" : "down"}`}>
                      z={Number(a.return_zscore).toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* SPACER */}
          <div style={{ height: 16 }} />

          {/* MODEL PANEL */}
          {prediction && (
            <div className="panel">
              <div className="panel-head">
                <span className="panel-title">Direction model</span>
                <span className="panel-badge">RandomForest · time-ordered split</span>
              </div>

              <div className="two-col" style={{ gap: 20, marginBottom: 0 }}>
                {/* LEFT: direction gauge */}
                <div>
                  <div className="direction-wrap">
                    <div className="direction-label">5-day direction probability</div>
                    <div className={`direction-arrow ${dir}`}>
                      {dir === "up" ? "↑ UP" : "↓ DOWN"}
                    </div>
                    <div className="direction-bar-bg">
                      <div className="direction-bar-fill" style={{ width: `${probUp * 100}%` }} />
                    </div>
                    <div className="direction-meta">
                      <span style={{ color: "var(--red)", fontSize: 11 }}>↓ {(prediction.latest_day_prediction.prob_down * 100).toFixed(1)}%</span>
                      <span style={{ color: "var(--green)", fontSize: 11 }}>↑ {(probUp * 100).toFixed(1)}%</span>
                    </div>
                  </div>

                  <div className="vs-row">
                    <span style={{ color: "var(--text-2)", marginRight: 4 }}>Model vs baseline:</span>
                    {accTie
                      ? <span className="tie">= tied at {(prediction.test_set_accuracy * 100).toFixed(1)}%</span>
                      : accBeat
                        ? <span className="beat">+{accDiff}pp over baseline</span>
                        : <span className="miss">{accDiff}pp vs baseline</span>
                    }
                  </div>
                </div>

                {/* RIGHT: accuracy metrics */}
                <div className="model-grid">
                  <div className="model-stat">
                    <div className="model-stat-label">Test accuracy</div>
                    <div className="model-stat-val">{(prediction.test_set_accuracy * 100).toFixed(1)}<span style={{ fontSize: 14 }}>%</span></div>
                  </div>
                  <div className="model-stat">
                    <div className="model-stat-label">Baseline</div>
                    <div className="model-stat-val" style={{ color: "var(--text-3)" }}>{(prediction.baseline_majority_class_accuracy * 100).toFixed(1)}<span style={{ fontSize: 14 }}>%</span></div>
                  </div>
                  <div className="model-stat">
                    <div className="model-stat-label">Precision</div>
                    <div className="model-stat-val">{(prediction.precision * 100).toFixed(0)}<span style={{ fontSize: 14 }}>%</span></div>
                  </div>
                  <div className="model-stat">
                    <div className="model-stat-label">F1 score</div>
                    <div className="model-stat-val">{prediction.f1_score}</div>
                  </div>
                </div>
              </div>

              <div className="disclaimer">{prediction.disclaimer}</div>
            </div>
          )}
        </div>
      )}

      {/* SCREENSHOT SECTION */}
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Chart screenshot reader</span>
          <span className="panel-badge">CV trend extraction</span>
        </div>

        <div
          className={`upload-zone ${drag ? "drag-over" : ""}`}
          onDragOver={e => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={e => { e.preventDefault(); setDrag(false); uploadChart(e.dataTransfer.files[0]); }}
        >
          <input className="upload-input" type="file" accept="image/*" onChange={e => uploadChart(e.target.files[0])} />
          <div className="upload-icon">📈</div>
          <div className="upload-text">Drop a chart screenshot here, or click to browse</div>
          <div className="upload-hint">PNG / JPG / WEBP — extracts visible trend shape only</div>
        </div>

        {chartTrend && (
          <div className="trend-result">
            <div className="trend-icon">{TREND_ICON[chartTrend.trend_label] ?? "→"}</div>
            <div>
              <div className="trend-label" style={{ color: TREND_COLOR[chartTrend.trend_label] ?? "var(--text)" }}>
                {chartTrend.trend_label}
              </div>
              <div className="trend-sub">{chartTrend.points_traced} px traced · slope {chartTrend.recent_slope_normalized > 0 ? "+" : ""}{chartTrend.recent_slope_normalized}</div>
            </div>
            <div style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", maxWidth: 240, textAlign: "right" }}>
              {chartTrend.note}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}