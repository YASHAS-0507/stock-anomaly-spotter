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

export async function fetchDecision(ticker, period, horizon) {
  const res = await fetch(
    `${API_BASE}/api/decision?ticker=${encodeURIComponent(ticker)}&period=${period}&horizon=${horizon}`
  );
  if (!res.ok) throw new Error("Decision fetch failed");
  return res.json();
}

export async function fetchQueue() {
  const res = await fetch(`${API_BASE}/api/queue`);
  if (!res.ok) throw new Error("Queue fetch failed");
  return res.json();
}

export async function fetchLogStats() {
  const res = await fetch(`${API_BASE}/api/logs/stats`);
  if (!res.ok) throw new Error("Log stats fetch failed");
  return res.json();
}
