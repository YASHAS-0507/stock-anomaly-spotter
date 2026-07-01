export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

if (!process.env.NEXT_PUBLIC_API_BASE) {
  console.warn("[api.js] NEXT_PUBLIC_API_BASE not set, defaulting to http://localhost:8000");
}

export async function analyze(ticker, period) {
  const res = await fetch(`${API_BASE}/api/analyze?ticker=${encodeURIComponent(ticker)}&period=${period}`);
  if (!res.ok) throw new Error((await res.json()).detail || "Analysis failed");
  return res.json();
}

export async function predict(ticker, period, horizon) {
  const res = await fetch(`${API_BASE}/api/predict?ticker=${encodeURIComponent(ticker)}&period=${period}&horizon=${horizon}`);
  if (!res.ok) throw new Error((await res.json()).detail || "Prediction failed");
  return res.json();
}

export async function uploadChartImage(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/chart-trend`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "Could not read chart");
  return res.json();
}

export async function logout() {
  await fetch(`${API_BASE}/api/logout`, { method: "POST" });
  window.location.href = "/login";
}