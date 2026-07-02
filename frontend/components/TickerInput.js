export default function TickerInput({
  ticker, setTicker,
  period, setPeriod,
  horizon, setHorizon,
  chartInterval, setChartInterval,
  onRun, loading,
}) {
  return (
    <div className="terminal-section">
      <div className="terminal-label">Enter ticker symbol</div>
      <div className="terminal-row">
        <div className="terminal-input-wrap">
          <span className="terminal-prompt">$</span>
          <input
            className="terminal-input"
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !loading && onRun()}
            placeholder="e.g. RELIANCE.NS or AAPL"
          />
        </div>

        <select className="terminal-select" value={period} onChange={e => setPeriod(e.target.value)}>
          <option value="3mo">3 months</option>
          <option value="6mo">6 months</option>
          <option value="1y">1 year</option>
          <option value="2y">2 years</option>
        </select>

        <select className="terminal-select" value={horizon} onChange={e => setHorizon(Number(e.target.value))}>
          <option value={1}>1-Day Horizon</option>
          <option value={5}>5-Day Horizon</option>
          <option value={10}>10-Day Horizon</option>
        </select>

        <select className="terminal-select" value={chartInterval} onChange={e => setChartInterval(e.target.value)}>
          <option value="1d">1D Candle</option>
          <option value="1wk">1W Candle</option>
        </select>

        <button className="btn-run" onClick={onRun} disabled={loading}>
          {loading ? "RUNNING..." : "RUN ANALYSIS"}
        </button>
      </div>
    </div>
  );
}
