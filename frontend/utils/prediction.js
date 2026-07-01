export function getDominantClass(prediction) {
  const probs = prediction?.latest_day_forecast?.probabilities ?? {};
  const probSideways = probs.sideways ?? 0;
  const probSpikeUp = probs.spike_up ?? 0;
  const probSpikeDown = probs.spike_down ?? 0;

  let dominant = "sideways";
  let max = probSideways;
  if (probSpikeUp > max) { dominant = "spike_up"; max = probSpikeUp; }
  if (probSpikeDown > max) { dominant = "spike_down"; max = probSpikeDown; }
  return { dominant, probSideways, probSpikeUp, probSpikeDown };
}

export function getAccuracyStatus(prediction) {
  if (!prediction) return { beat: false, tie: false, diff: "0" };
  const acc = prediction.metrics.test_set_accuracy;
  const base = prediction.metrics.baseline_majority_accuracy;
  const diff = ((acc - base) * 100).toFixed(1);
  return { beat: acc > base, tie: acc === base, diff };
}

export function extractRiskPortfolio(prediction) {
  const p = prediction || {};
  return {
    risk: p.stage_5_risk_matrix ?? {},
    portfolio: p.stage_6_portfolio_snapshot ?? {},
    explain: p.stage_4_explainability ?? {},
    signal: p.realtime_signal ?? {}
  };
}