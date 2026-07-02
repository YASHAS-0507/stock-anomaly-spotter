import { useState } from "react";

const PERIODS = [
  { value: "1mo", label: "1 Month" },
  { value: "3mo", label: "3 Months" },
  { value: "6mo", label: "6 Months" },
  { value: "1y", label: "1 Year" },
  { value: "2y", label: "2 Years" },
];

const HORIZONS = [
  { value: "1", label: "1 Day" },
  { value: "5", label: "5 Days" },
  { value: "10", label: "10 Days" },
  { value: "20", label: "20 Days" },
];

export default function TickerInput({ 
  ticker, 
  period, 
  horizon, 
  currentInterval,
  onTickerChange, 
  onPeriodChange, 
  onHorizonChange,
  onIntervalChange,
  onRun, 
  loading 
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <div className="panel">
      <div className="panel-header flex flex-wrap gap-md">
        <span className="panel-title">Signal Generator</span>
        <span className="panel-badge">XGBoost + TabPFN</span>
        <button 
          className="btn btn-ghost btn-sm"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          {showAdvanced ? "Hide Advanced" : "Show Advanced"}
        </button>
      </div>

      <div className="panel-content">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-md items-end">
          {/* Ticker Input */}
          <div className="md:col-span-2">
            <label className="input-label">Symbol</label>
            <div className="flex items-center gap-sm">
              <span className="text-value font-mono text-lg px-sm py-sm bg-panel-border rounded-md">
                $
              </span>
              <input
                className="input flex-1 font-mono text-lg text-uppercase"
                value={ticker}
                onChange={e => onTickerChange(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === "Enter" && !loading && onRun()}
                placeholder="RELIANCE.NS"
                disabled={loading}
              />
            </div>
          </div>

          {/* Period */}
          <div>
            <label className="input-label">Period</label>
            <select
              className="select"
              value={period}
              onChange={onPeriodChange}
              disabled={loading}
            >
              {PERIODS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {/* Horizon */}
          <div>
            <label className="input-label">Horizon</label>
            <select
              className="select"
              value={horizon}
              onChange={onHorizonChange}
              disabled={loading}
            >
              {HORIZONS.map(h => (
                <option key={h.value} value={h.value}>{h.label}</option>
              ))}
            </select>
          </div>

          {/* Interval */}
          <div>
            <label className="input-label">Chart Interval</label>
            <select
              className="select"
              value={currentInterval}
              onChange={onIntervalChange}
              disabled={loading}
            >
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="30m">30m</option>
              <option value="1h">1h</option>
              <option value="1d">1d</option>
            </select>
          </div>

          {/* Run Button */}
          <div>
            <button 
              className="btn btn-primary btn-lg w-full"
              onClick={onRun}
              disabled={loading}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-sm">
                  <span className="skeleton skeleton-text-sm" />
                  <span>Analyzing...</span>
                </span>
              ) : (
                <>
                  <span className="badge-dot status-connected" />
                  RUN ANALYSIS
                </>
              )}
            </button>
          </div>
        </div>

        {/* Advanced Options */}
        {showAdvanced && (
          <div className="mt-lg pt-lg border-t border-panel-border grid grid-cols-2 md:grid-cols-4 gap-md">
            <div className="card p-md">
              <div className="text-label">Risk per Trade</div>
              <select className="select mt-sm">
                <option value="0.01">1%</option>
                <option value="0.02" defaultValue>2%</option>
                <option value="0.03">3%</option>
                <option value="0.05">5%</option>
              </select>
            </div>
            <div className="card p-md">
              <div className="text-label">Confidence Threshold</div>
              <select className="select mt-sm">
                <option value="0.55">55%</option>
                <option value="0.60" defaultValue>60%</option>
                <option value="0.65">65%</option>
                <option value="0.70">70%</option>
              </select>
            </div>
            <div className="card p-md">
              <div className="text-label">Max Positions</div>
              <select className="select mt-sm">
                <option value="1" defaultValue>1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="5">5</option>
              </select>
            </div>
            <div className="card p-md">
              <div className="text-label">Regime Filter</div>
              <label className="flex items-center gap-sm mt-sm cursor-pointer">
                <input type="checkbox" defaultChecked className="accent-cyan" />
                <span className="text-caption">Block in adverse regimes</span>
              </label>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}