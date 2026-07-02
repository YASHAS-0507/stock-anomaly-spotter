export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function fetchAnalysis(ticker, period) {
  const res = await fetch(
    `${API_BASE}/api/analyze?ticker=${encodeURIComponent(ticker)}&period=${period}`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Analysis failed (${res.status})`);
  }
  return res.json();
}

export async function fetchPrediction(ticker, period, horizon) {
  const res = await fetch(
    `${API_BASE}/api/predict?ticker=${encodeURIComponent(ticker)}&period=${period}&horizon=${horizon}`
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Prediction failed (${res.status})`);
  }
  return res.json();
}
