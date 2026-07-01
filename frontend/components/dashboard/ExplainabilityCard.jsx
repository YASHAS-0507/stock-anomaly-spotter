export default function ExplainabilityCard({ explain }) {
  if (!explain?.summary) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Explainability</span>
          <span className="panel-badge">Stage 4</span>
        </div>
        <div className="panel-content flex items-center justify-center h-48">
          <div className="text-center text-2">
            <div className="text-display signal-hold mb-sm">◆</div>
            <div className="text-title">Awaiting Prediction</div>
            <div className="text-body text-2 mt-sm">Run analysis to generate explanation</div>
          </div>
        </div>
      </div>
    );
  }

  const reasoningChain = explain.reasoning_chain || [];
  const primarySignal = explain.primary_signal || "HOLD";
  const confidence = explain.confidence_rating || "N/A";

  const signalColors = {
    BUY: "var(--green)",
    SELL: "var(--red)",
    HOLD: "var(--yellow)",
    SHORT: "var(--red)",
  };

  const signalIcons = {
    BUY: "▲",
    SELL: "▼",
    HOLD: "◆",
    SHORT: "▼",
  };

  const steps = [
    { id: "trend", label: "Trend Strength", icon: "📈", check: reasoningChain.some(r => r.includes("Oversold") || r.includes("Overbought") || r.includes("Momentum")) },
    { id: "momentum", label: "Momentum", icon: "⚡", check: reasoningChain.some(r => r.includes("Momentum") || r.includes("Volume")) },
    { id: "volatility", label: "Volatility", icon: "📊", check: reasoningChain.some(r => r.includes("Volatility") || r.includes("z-score")) },
    { id: "risk", label: "Risk Gate", icon: "🛡️", check: reasoningChain.some(r => r.includes("Risk") || r.includes("confidence")) },
    { id: "decision", label: "Final Decision", icon: "⚖️", check: true },
  ];

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Explainability</span>
        <span className="panel-badge">Stage 4</span>
      </div>

      <div className="panel-content space-lg">
        {/* Signal Header */}
        <div className="card p-lg" style={{ borderLeft: `4px solid ${signalColors[primarySignal] || "var(--text-3)"}` }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-md">
              <div className="w-16 h-16 rounded-xl flex items-center justify-center text-3xl" style={{ background: `${signalColors[primarySignal] || "var(--text-3)"}20` }}>
                <span style={{ color: signalColors[primarySignal] || "var(--text-3)" }}>{signalIcons[primarySignal] || "◆"}</span>
              </div>
              <div>
                <div className="text-title" style={{ color: signalColors[primarySignal] || "var(--text)" }}>{primarySignal}</div>
                <div className="flex items-center gap-sm mt-xs">
                  <span className="text-caption">Confidence</span>
                  <span className="text-value font-mono">{confidence}</span>
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-label">Summary</div>
              <div className="text-caption text-2 truncate max-w-xs">{explain.summary}</div>
            </div>
          </div>
        </div>

        {/* Reasoning Timeline */}
        <div className="card p-lg">
          <div className="card-title">Reasoning Chain</div>
          <div className="mt-md relative">
            {/* Vertical line */}
            <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-panel-border" />
            
            <div className="space-lg relative">
              {steps.map((step, index) => (
                <div key={step.id} className="flex items-start gap-md animate-slide-up stagger-{index + 1}" style={{ animationDelay: `${index * 0.1}s` }}>
                  {/* Timeline dot */}
                  <div className="flex-shrink-0 w-12 h-12 flex items-center justify-center relative z-10">
                    <div className={`w-3 h-3 rounded-full border-2 ${step.check ? "bg-green border-green" : "bg-panel-border border-panel-border-hover"}`} style={{ 
                      boxShadow: step.check ? "0 0 8px var(--green)" : "none" 
                    }} />
                    {/* Connecting line handled by parent relative line */}
                  </div>
                  
                  {/* Step content */}
                  <div className="flex-1 min-w-0 pt-sm">
                    <div className="flex items-center gap-sm">
                      <span className="text-xl">{step.icon}</span>
                      <span className="text-title">{step.label}</span>
                      {step.check && (
                        <span className="badge bg-buy text-xs">VERIFIED</span>
                      )}
                    </div>
                    {reasoningChain[index] && (
                      <div className="text-body text-2 mt-xs ml-12">
                        {reasoningChain[index]}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Raw Summary */}
        <div className="card p-lg">
          <div className="card-title">Full Explanation</div>
          <div className="mt-md text-body whitespace-pre-wrap text-2">{explain.summary}</div>
        </div>

        {/* Confidence Breakdown */}
        {explain.confidence_breakdown && (
          <div className="card p-lg">
            <div className="card-title">Confidence Breakdown</div>
            <div className="mt-md grid grid-cols-3 gap-md">
              {Object.entries(explain.confidence_breakdown).map(([key, value]) => (
                <div key={key} className="card p-md text-center">
                  <div className="text-label">{key}</div>
                  <div className="text-metric-sm font-mono mt-sm">{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}