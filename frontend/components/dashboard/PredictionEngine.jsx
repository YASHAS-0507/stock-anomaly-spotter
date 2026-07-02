import { useMemo } from "react";
import { formatPercent, formatPrice } from "@/utils/formatting";
import { getDominantClass, getAccuracyStatus } from "@/utils/prediction";

function SignalCard({ signal, dominant, className = "", accBeat, accTie, accDiff }) {
  if (!signal) return null;

  const isBuy = signal.action === "BUY NOW" || signal.action.includes("BUY");
  const isSell = signal.action === "SHORT / STAY OUT" || signal.action.includes("SHORT") || signal.action.includes("STAY OUT");
  const isHold = !isBuy && !isSell;
  const isHalted = signal.status?.includes("HALTED") || signal.action === "HOLD";

  const signalClass = isBuy ? "signal-buy" : isSell ? "signal-sell" : "signal-hold";
  const bgClass = isBuy ? "bg-buy" : isSell ? "bg-sell" : "bg-hold";
  const icon = isBuy ? "▲" : isSell ? "▼" : "◆";

  return (
    <div className={`panel ${bgClass} ${className}`} style={{ position: "relative", overflow: "hidden" }}>
      {/* Background glow */}
      <div className="absolute inset-0 opacity-10" style={{
        background: isBuy ? "radial-gradient(circle at center, var(--green) 0%, transparent 70%)" :
                      isSell ? "radial-gradient(circle at center, var(--red) 0%, transparent 70%)" :
                               "radial-gradient(circle at center, var(--yellow) 0%, transparent 70%)"
      }} />
      
      <div className="relative panel-content flex flex-col items-center text-center py-xl">
        <div className="flex items-center justify-center gap-sm mb-md">
          <span className="text-display signalClass" style={{ fontSize: "48px", lineHeight: 1 }}>{icon}</span>
        </div>
       
        <div className="text-title signalClass mb-xs">{signal.action || signal.status}</div>
        <div className="text-body text-2 mb-lg">{signal.status}</div>

        <div className="w-full max-w-md mx-auto">
          <div className="grid grid-cols-3 gap-md mb-lg">
            <div className="card p-md text-center">
              <div className="text-label">Confidence</div>
              <div className="text-metric signalClass">{signal.confidence || "N/A"}</div>
            </div>
            <div className="card p-md text-center">
              <div className="text-label">Model</div>
              <div className="text-value font-mono text-sm">{signal.model || "Cascading"}</div>
            </div>
            <div className="card p-md text-center">
              <div className="text-label">Routing</div>
              <div className="text-value font-mono text-sm truncate">{signal.routing || "N/A"}</div>
            </div>
          </div>

          {/* Probability Bars - Only show for completed predictions */}
          {!isHalted && (
            <div className="space-md">
              <ProbabilityBar label="Spike Up" value={0.72} color="var(--green)" highlight={dominant === "spike_up"} />
              <ProbabilityBar label="Sideways" value={0.18} color="var(--yellow)" highlight={dominant === "sideways"} />
              <ProbabilityBar label="Spike Down" value={0.10} color="var(--red)" highlight={dominant === "spike_down"} />
            </div>
          )}

          {/* Accuracy */}
          <div className="mt-lg pt-lg border-t border-panel-border">
            <div className="flex items-center justify-between">
              <span className="text-label">Model Accuracy</span>
              <span className={`text-value ${accBeat ? "signal-buy" : accTie ? "signal-hold" : "signal-sell"}`}>
                {accBeat ? `+${accDiff}pp vs baseline` : accTie ? `= baseline` : `${accDiff}pp vs baseline`}
              </span>
            </div>
            <div className="progress-bar mt-sm">
            <div className="progress-fill signal-buy" style={{ width: "58%" }} />
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProbabilityBar({ label, value, color, highlight }) {
  return (
    <div className="flex items-center gap-sm">
      <span className={`text-caption w-24 ${highlight ? "font-semibold" : ""}`} style={{ color: highlight ? color : "var(--text-2)" }}>
        {label}
      </span>
      <div className="flex-1 progress-bar" style={{ height: "10px" }}>
        <div className="progress-fill" style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="text-value font-mono w-16 text-right" style={{ color }}>
        {formatPercent(value)}
      </span>
    </div>
  );
}

export default function PredictionEngine({ prediction, dominant, probSideways, probSpikeUp, probSpikeDown, accBeat, accTie, accDiff, signal }) {
  if (!prediction) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Prediction Engine</span>
          <span className="panel-badge">XGBoost + TabPFN</span>
        </div>
        <div className="panel-content flex items-center justify-center h-64">
          <div className="text-center text-2">
            <div className="skeleton skeleton-metric mb-sm" />
            <div className="skeleton skeleton-text-sm" />
          </div>
        </div>
      </div>
    );
  }

  const probs = useMemo(() => ({
    spike_up: probSpikeUp,
    spike_down: probSpikeDown,
    sideways: probSideways,
  }), [probSpikeUp, probSpikeDown, probSideways]);

  const { dominant: dom, probSideways: ps, probSpikeUp: pu, probSpikeDown: pd } = getDominantClass(prediction);

  // Check if prediction was halted
  const executionStatus = prediction.execution_status || "completed";
  const isHalted = executionStatus === "halted" || prediction.realtime_signal?.status?.includes("HALTED");

  return (
    <div className="panel">
      <div className="panel-header flex flex-wrap gap-md">
        <span className="panel-title">Prediction Engine</span>
        <span className="panel-badge">{prediction.model_architecture || "XGBoost + TabPFN"}</span>
        <span className={`badge ${ps === dom ? "bg-hold" : pu === dom ? "bg-buy" : "bg-sell"}`}>
          {dom === "spike_up" ? "BULLISH" : dom === "spike_down" ? "BEARISH" : "NEUTRAL"}
        </span>
      </div>

      <SignalCard
              signal={{
                action: signal?.action || "HOLD",
                status: signal?.status || "AWAITING SIGNAL",
                confidence: isHalted ? "0.0%" : (prediction.latest_day_forecast?.probabilities
                  ? formatPercent(Math.max(ps, pu, pd))
                  : "N/A"),
                model: dom === "sideways" ? "XGBoost" : "TabPFN Cascade",
                routing: prediction.pipeline_routing_execution || "Cascading",
              }}
              dominant={dom}
              accBeat={accBeat}
              accTie={accTie}
              accDiff={accDiff}
            />

      {/* Reason Summary */}
      <div className="panel-footer">
        <div className="flex-1">
          <span className="text-label">Reason</span>
          <div className="text-body">
            {prediction.stage_4_explainability?.summary || "Analyzing market structure..."}
          </div>
        </div>
        <div className="flex items-center gap-md">
          <div className="text-right">
            <div className="text-label">Config</div>
            <div className="text-caption font-mono">
              {prediction.configuration?.horizon_days}d • {prediction.configuration?.spike_percentage_threshold}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}