export default function StatStrip({ analysis }) {
  return (
    <div className="stat-strip">
      <div className="stat-card accent">
        <div className="stat-label">Ticker</div>
        <div className="stat-value cyan">{analysis.ticker}</div>
        <div className="stat-sub">{analysis.data_points} trading days</div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Anomalies detected</div>
        <div className="stat-value">{analysis?.anomaly_summary?.count ?? 0}</div>
        <div className="stat-sub">Volatility hotspots identified using rolling z-score anomaly detection</div>
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
  );
}