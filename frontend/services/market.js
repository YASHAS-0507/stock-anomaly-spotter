export function getISTTime() {
  return new Date().toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function getISTDate() {
  return new Date().toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export function getMarketStatus() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay(); // 0=Sun, 6=Sat
  const total = ist.getHours() * 60 + ist.getMinutes();
  if (day === 0 || day === 6) return "CLOSED";
  // NSE: 9:15 AM – 3:30 PM IST
  if (total >= 555 && total <= 930) return "OPEN";
  return "CLOSED";
}

export function formatINR(value) {
  if (value == null || isNaN(value)) return "—";
  const v = Number(value);
  if (v >= 10000000) return `₹${(v / 10000000).toFixed(2)}Cr`;
  if (v >= 100000) return `₹${(v / 100000).toFixed(2)}L`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}k`;
  return `₹${v.toFixed(2)}`;
}

export function extractRegime(prediction) {
  if (!prediction) return "—";
  if (prediction.regime_snapshot?.regime_type) return prediction.regime_snapshot.regime_type;
  const exec = prediction.pipeline_routing_execution || "";
  const match = exec.match(/Regime Shield Block \[([^\]]+)\]/);
  if (match) return match[1];
  const action = prediction.realtime_signal?.action || "";
  if (action === "BUY NOW") return "BULL_TREND";
  if (action.includes("SHORT") || action.includes("STAY OUT")) return "BEAR_TREND";
  return "NORMAL";
}
