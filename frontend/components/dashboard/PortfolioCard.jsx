import { formatPrice, formatPercent } from "@/utils/formatting";

export default function PortfolioCard({ portfolio, risk }) {
  const freeCash = portfolio?.free_cash ?? 0;
  const portfolioValue = portfolio?.portfolio_value ?? 0;
  const buyingPower = freeCash; // Simplified
  const riskUsed = risk?.allocated_risk_cash ?? 0;
  const riskPct = freeCash > 0 ? (riskUsed / freeCash * 100) : 0;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Portfolio</span>
        <span className="panel-badge">LIVE</span>
      </div>

      <div className="panel-content space-lg">
        {/* Main Metrics */}
        <div className="grid grid-cols-2 gap-md">
          <MetricCard
            label="Available Cash"
            value={formatPrice(freeCash)}
            highlight
          />
          <MetricCard
            label="Portfolio Value"
            value={formatPrice(portfolioValue)}
          />
          <MetricCard
            label="Buying Power"
            value={formatPrice(buyingPower)}
          />
          <MetricCard
            label="Risk Used Today"
            value={formatPrice(riskUsed)}
            unit={`(${riskPct.toFixed(1)}%)`}
            trend={-1}
          />
        </div>

        {/* Progress Bars */}
        <div className="space-md pt-md border-t border-panel-border">
          <div className="flex items-center justify-between mb-xs">
            <span className="text-label">Cash Utilization</span>
            <span className="text-caption font-mono">
              {freeCash > 0 ? formatPercent((portfolioValue - freeCash) / portfolioValue) : "0%"}
            </span>
          </div>
          <div className="progress-bar" style={{ height: "10px" }}>
            <div className="progress-fill signal-buy" style={{ width: `${portfolioValue > 0 ? (1 - freeCash / portfolioValue) * 100 : 0}%` }} />
          </div>

          <div className="flex items-center justify-between mb-xs mt-md">
            <span className="text-label">Risk Exposure</span>
            <span className="text-caption font-mono">{riskPct.toFixed(1)}%</span>
          </div>
          <div className="progress-bar" style={{ height: "10px" }}>
            <div className="progress-fill signal-sell" style={{ width: `${Math.min(riskPct, 100)}%` }} />
          </div>
        </div>

        {/* Open Positions */}
        <div className="pt-md border-t border-panel-border">
          <div className="flex items-center justify-between mb-md">
            <span className="panel-title text-sm">Open Positions</span>
          </div>
          {portfolio?.open_positions?.length > 0 ? (
            <div className="space-sm">
              {portfolio.open_positions.map((pos, i) => (
                <div key={i} className="card p-sm flex items-center justify-between">
                  <div className="flex items-center gap-sm">
                    <span className="badge bg-buy">{pos.side || "LONG"}</span>
                    <span className="text-value font-mono">{pos.symbol}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-value font-mono">{pos.qty} @ {formatPrice(pos.entry)}</div>
                    <div className="text-caption signal-buy">+{pos.unrealized_pnl_pct?.toFixed(2)}%</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="card p-lg text-center text-2">
              No open positions
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit = "", highlight = false, trend }) {
  return (
    <div className={`card p-md ${highlight ? "bg-buy" : ""}`}>
      <div className="text-label">{label}</div>
      <div className="flex items-baseline gap-xs mt-sm">
        <span className={`text-metric ${highlight ? "signal-buy" : ""}`}>{value}</span>
        {unit && <span className="text-caption text-2">{unit}</span>}
      </div>
      {trend !== undefined && (
        <div className="mt-xs flex justify-center">
          <span className={`badge-dot ${trend > 0 ? "status-connected" : trend < 0 ? "status-disconnected" : "status-warning"}`} />
        </div>
      )}
    </div>
  );
}