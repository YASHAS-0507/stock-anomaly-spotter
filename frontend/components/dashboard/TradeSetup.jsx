import { formatPrice, formatPercent } from "@/utils/formatting";

function TradeMetricCard({ label, value, unit = "", trend, className = "" }) {
  return (
    <div className={`card p-md ${className}`}>
      <div className="text-label">{label}</div>
      <div className="flex items-baseline gap-xs mt-xs">
        <span className="text-metric-sm font-mono">{value}</span>
        {unit && <span className="text-caption text-2">{unit}</span>}
        {trend && (
          <span className={`badge-dot ${trend > 0 ? "status-connected" : trend < 0 ? "status-disconnected" : "status-warning"}`} style={{ marginLeft: "auto" }} />
        )}
      </div>
    </div>
  );
}

function DetailRow({ label, value, unit = "", highlight = false, trend }) {
  return (
    <div className="flex items-center justify-between py-sm border-b border-panel-border/50 last:border-0">
      <span className="text-caption">{label}</span>
      <div className="flex items-center gap-sm">
        <span className={`text-value font-mono ${highlight ? "signal-buy" : ""}`}>
          {value}{unit}
        </span>
        {trend !== undefined && (
          <span className={`badge-dot ${trend > 0 ? "status-connected" : trend < 0 ? "status-disconnected" : "status-warning"}`} />
        )}
      </div>
    </div>
  );
}

export default function TradeSetup({ risk, portfolio, signal }) {
  if (!risk || risk.decision !== "ENTER") {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Trade Setup</span>
          <span className="panel-badge bg-hold">NO ACTIVE SETUP</span>
        </div>
        <div className="panel-content flex items-center justify-center h-48">
          <div className="text-center text-2">
            <div className="text-display signal-hold mb-sm">◆</div>
            <div className="text-title">No Trade Signal</div>
            <div className="text-body text-2 mt-sm">
              {signal?.status || "Waiting for high-confidence setup..."}
            </div>
            <div className="mt-lg text-caption">
              {risk?.reason || "Risk engine requires >60% confidence"}
            </div>
          </div>
        </div>
      </div>
    );
  }

  const entry = risk.entry_price;
  const stopLoss = risk.stop_loss;
  const takeProfit = risk.take_profit;
  const quantity = risk.target_quantity || risk.quantity;
  const riskAmount = risk.actual_risk || risk.allocated_risk_cash;
  const riskReward = risk.risk_reward_ratio;
  const capitalRequired = entry * quantity;
  const expectedProfit = (takeProfit - entry) * quantity;
  const riskPct = portfolio?.free_cash ? (riskAmount / portfolio.free_cash * 100) : 0;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Trade Setup</span>
        <span className="badge bg-buy">ACTIVE SETUP</span>
      </div>

      <div className="panel-content">
        {/* Key Metrics Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-md mb-lg">
          <MetricCard label="Entry" value={formatPrice(entry)} />
          <MetricCard label="Stop Loss" value={formatPrice(stopLoss)} trend={-1} />
          <MetricCard label="Take Profit" value={formatPrice(takeProfit)} trend={1} />
          <MetricCard label="Risk/Reward" value={`${riskReward}:1`} highlight />
        </div>

        {/* Execution Details */}
        <div className="grid md:grid-cols-2 gap-lg mb-lg">
          <div className="card p-lg">
            <div className="card-title">Execution</div>
            <div className="space-sm mt-md">
              <DetailRow label="Quantity" value={quantity.toLocaleString()} unit=" shares" />
              <DetailRow label="Capital Required" value={formatPrice(entry * quantity)} highlight />
              <DetailRow label="Risk Amount" value={formatPrice(riskAmount)} unit={` (${riskPct.toFixed(1)}% of cash)`} trend={-1} />
              <DetailRow label="Expected Profit" value={formatPrice((takeProfit - entry) * quantity)} highlight trend={1} />
            </div>
          </div>

          <div className="card p-lg">
            <div className="card-title">Risk Parameters</div>
            <div className="space-sm mt-md">
              <DetailRow label="Risk per Trade" value={`${(risk.risk_per_trade * 100).toFixed(1)}%`} />
              <DetailRow label="Stop Distance" value={`${((entry - stopLoss) / entry * 100).toFixed(2)}%`} trend={-1} />
              <DetailRow label="Target Distance" value={`${((takeProfit - entry) / entry * 100).toFixed(2)}%`} trend={1} />
              <DetailRow label="Risk/Reward Ratio" value={`${riskReward}:1`} highlight />
            </div>
          </div>
        </div>

        {/* Visual Risk/Reward */}
        <div className="card p-lg">
          <div className="card-title">Risk / Reward Visualization</div>
          <div className="mt-md">
            <div className="flex items-center gap-sm mb-sm">
              <div className="flex-1 h-2 bg-red-dim rounded-full relative overflow-hidden">
                <div className="absolute top-0 bottom-0 bg-red" style={{ width: `${100 / (1 + riskReward)}%` }} />
              </div>
              <span className="text-caption font-mono w-16 text-right text-red">Risk</span>
            </div>
            <div className="flex items-center gap-sm">
              <div className="flex-1 h-2 bg-green-dim rounded-full relative overflow-hidden">
                <div className="absolute top-0 bottom-0 bg-green" style={{ width: `${riskReward / (1 + riskReward) * 100}%` }} />
              </div>
              <span className="text-caption font-mono w-16 text-right text-green">Reward</span>
            </div>
            <div className="mt-sm flex justify-between text-caption text-2">
              <span>Stop: {formatPrice(stopLoss)}</span>
              <span>Entry: {formatPrice(entry)}</span>
              <span>Target: {formatPrice(takeProfit)}</span>
            </div>
          </div>
        </div>

        {/* Portfolio Impact */}
        <div className="card p-lg mt-md">
          <div className="card-title">Portfolio Impact</div>
          <div className="grid grid-cols-3 gap-md mt-md">
            <DetailRow label="Available Cash" value={formatPrice(portfolio?.free_cash || 0)} />
            <DetailRow label="Capital Allocated" value={formatPrice(capitalRequired)} unit={` (${portfolio?.free_cash ? (capitalRequired / portfolio.free_cash * 100).toFixed(1) : 0}%)`} />
            <DetailRow label="Remaining Cash" value={formatPrice((portfolio?.free_cash || 0) - capitalRequired)} />
            <DetailRow label="Portfolio Value" value={formatPrice(portfolio?.portfolio_value || 0)} />
            <DetailRow label="Risk Used Today" value={formatPrice(riskAmount)} unit={` (${riskPct.toFixed(1)}% of cash)`} trend={-1} />
            <DetailRow label="Buying Power Left" value={formatPrice((portfolio?.free_cash || 0) - capitalRequired)} highlight />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit = "", trend, highlight = false }) {
  return (
    <div className="card p-md text-center">
      <div className="text-label">{label}</div>
      <div className="flex items-center justify-center gap-xs mt-sm">
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