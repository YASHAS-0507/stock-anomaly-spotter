import { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export default function Home() {
  const [ticker, setTicker] = useState("RELIANCE.NS");
  const [period, setPeriod] = useState("1y");
  const [analysis, setAnalysis] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [chartTrend, setChartTrend] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function runAnalysis() {
    setLoading(true);
    setError(null);
    try {
      const [aRes, pRes] = await Promise.all([
        fetch(`${API_BASE}/api/analyze?ticker=${encodeURIComponent(ticker)}&period=${period}`),
        fetch(`${API_BASE}/api/predict?ticker=${encodeURIComponent(ticker)}&period=${period}`),
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

  async function uploadChart(e) {
    const file = e.target.files[0];
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

  const chartData =
    analysis &&
    analysis.series.date.map((d, i) => ({
      date: d.slice(5),
      close: analysis.series.close[i],
      z: analysis.series.return_zscore[i],
    }));

  return (
    <div className="page">
      <div className="header">
        <div>
          <div className="title">Stock anomaly spotter</div>
          <div className="subtitle">Technical-indicator analysis &amp; direction modeling — Python backend, real backtested accuracy</div>
        </div>
        <button
          className="secondary"
          onClick={async () => {
            await fetch("/api/logout", { method: "POST" });
            window.location.href = "/login";
          }}
        >
          Log out
        </button>
      </div>

      <div className="controls">
        <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="e.g. RELIANCE.NS, AAPL" />
        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="3mo">3 months</option>
          <option value="6mo">6 months</option>
          <option value="1y">1 year</option>
          <option value="2y">2 years</option>
        </select>
        <button onClick={runAnalysis} disabled={loading}>
          {loading ? "Analyzing..." : "Run analysis"}
        </button>
      </div>

      {error && <div className="panel" style={{ color: "#f87171" }}>{error}</div>}

      {analysis && (
        <>
          <div className="grid">
            <div className="card">
              <div className="card-label">Data points</div>
              <div className="card-value">{analysis.data_points}</div>
            </div>
            <div className="card">
              <div className="card-label">Anomalies found</div>
              <div className="card-value">{analysis.anomaly_summary.count}</div>
            </div>
            <div className="card">
              <div className="card-label">Max |z-score|</div>
              <div className="card-value">{analysis.anomaly_summary.max_abs_zscore}</div>
            </div>
            <div className="card">
              <div className="card-label">Data source</div>
              <div className="card-value" style={{ fontSize: 16 }}>
                {analysis.used_synthetic_data ? "Synthetic (offline)" : "Live market data"}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">Price series</div>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f232c" />
                <XAxis dataKey="date" stroke="#6b7280" fontSize={11} />
                <YAxis stroke="#6b7280" fontSize={11} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ background: "#14171f", border: "1px solid #262a35" }} />
                <Line type="monotone" dataKey="close" stroke="#3b82f6" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="panel">
            <div className="panel-title">Flagged anomaly days</div>
            {analysis.anomalies.length === 0 && <div className="subtitle">No anomalies at this threshold.</div>}
            {analysis.anomalies.slice(-8).reverse().map((a, i) => (
              <div className="anomaly-row" key={i}>
                <span>{a.date} — ₹{a.close}</span>
                <span className={a.anomaly_direction === "spike_up" ? "spike-up" : "spike-down"}>
                  z = {a.return_zscore}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {prediction && (
        <div className="panel">
          <div className="panel-title">Direction model — honest accuracy report</div>
          <div className="grid">
            <div className="card">
              <div className="card-label">Test accuracy</div>
              <div className="card-value">{(prediction.test_set_accuracy * 100).toFixed(1)}%</div>
            </div>
            <div className="card">
              <div className="card-label">Baseline (majority class)</div>
              <div className="card-value">{(prediction.baseline_majority_class_accuracy * 100).toFixed(1)}%</div>
            </div>
            <div className="card">
              <div className="card-label">F1 score</div>
              <div className="card-value">{prediction.f1_score}</div>
            </div>
            <div className="card">
              <div className="card-label">Next-day probability</div>
              <div className="card-value">
                {prediction.latest_day_prediction.predicted_direction === "up" ? "↑ " : "↓ "}
                {(Math.max(prediction.latest_day_prediction.prob_up, prediction.latest_day_prediction.prob_down) * 100).toFixed(0)}%
              </div>
            </div>
          </div>
          <div className="disclaimer">{prediction.disclaimer}</div>
        </div>
      )}

      <div className="panel">
        <div className="panel-title">Chart screenshot trend reader</div>
        <div className="upload-box">
          <input type="file" accept="image/*" onChange={uploadChart} />
          <div style={{ marginTop: 8 }}>Upload a chart screenshot to extract its visible trend shape</div>
        </div>
        {chartTrend && (
          <div style={{ marginTop: 16 }}>
            <div className="anomaly-row">
              <span>Trend</span>
              <span style={{ fontWeight: 600 }}>{chartTrend.trend_label}</span>
            </div>
            <div className="anomaly-row">
              <span>Points traced</span>
              <span>{chartTrend.points_traced}</span>
            </div>
            <div className="disclaimer">{chartTrend.note}</div>
          </div>
        )}
      </div>
    </div>
  );
}
