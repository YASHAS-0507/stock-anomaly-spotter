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

export async function fetchSchedulerStatus() {
  const res = await fetch(`${API_BASE}/api/scheduler/status`);
  if (!res.ok) throw new Error('Status fetch failed');
  return res.json();
}

export async function fetchLivePositions() {
  const res = await fetch(`${API_BASE}/api/live/positions`);
  if (!res.ok) throw new Error('Positions fetch failed');
  return res.json();
}

export async function fetchTodayTrades() {
  const res = await fetch(`${API_BASE}/api/live/trades/today`);
  if (!res.ok) throw new Error('Trades fetch failed');
  return res.json();
}

export async function fetchWatchlist() {
  const res = await fetch(`${API_BASE}/api/live/watchlist`);
  if (!res.ok) throw new Error('Watchlist fetch failed');
  return res.json();
}

export async function postSchedulerControl(action) {
  const res = await fetch(
    `${API_BASE}/api/scheduler/${action}`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(`${action} failed`);
  return res.json();
}
