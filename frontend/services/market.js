import { API_BASE } from "./api";

export async function getMarketStatus() {
  const res = await fetch(`${API_BASE}/api/market/status`);
  if (!res.ok) throw new Error("Failed to fetch market status");
  return res.json();
}

export async function getValidationStats() {
  const res = await fetch(`${API_BASE}/api/market/validation/stats`);
  if (!res.ok) throw new Error("Failed to fetch validation stats");
  return res.json();
}

export async function getCacheInfo() {
  const res = await fetch(`${API_BASE}/api/market/cache/info`);
  if (!res.ok) throw new Error("Failed to fetch cache info");
  return res.json();
}

export async function getHistoricalCandles(symbol, interval, period, limit = 500, useCache = true) {
  const params = new URLSearchParams({
    interval,
    period,
    limit: String(limit),
    use_cache: String(useCache),
  });
  const res = await fetch(`${API_BASE}/api/market/candles/${encodeURIComponent(symbol)}?${params}`);
  if (!res.ok) throw new Error("Failed to fetch historical candles");
  return res.json();
}

export async function getLatestCandle(symbol, interval, useRedis = true) {
  const params = new URLSearchParams({ interval, use_redis: String(useRedis) });
  const res = await fetch(`${API_BASE}/api/market/candles/${encodeURIComponent(symbol)}/latest?${params}`);
  if (!res.ok) throw new Error("Failed to fetch latest candle");
  return res.json();
}

export async function addCandle(candleData) {
  const res = await fetch(`${API_BASE}/api/market/candles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(candleData),
  });
  if (!res.ok) throw new Error("Failed to add candle");
  return res.json();
}

export async function clearCache(symbol, interval) {
  const params = new URLSearchParams();
  if (symbol) params.append("symbol", symbol);
  if (interval) params.append("interval", interval);
  const res = await fetch(`${API_BASE}/api/market/cache/clear?${params}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear cache");
  return res.json();
}

export async function getSupportedIntervals() {
  const res = await fetch(`${API_BASE}/api/market/intervals`);
  if (!res.ok) throw new Error("Failed to fetch intervals");
  return res.json();
}