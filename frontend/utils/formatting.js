export function formatPrice(v) {
  if (v >= 10000) return `₹${(v / 1000).toFixed(0)}k`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}k`;
  return `₹${Number(v).toFixed(0)}`;
}

export function formatPriceFull(v) {
  return `₹${Number(v).toFixed(2)}`;
}

export function formatPercent(v) {
  return `${(v * 100).toFixed(1)}%`;
}

export function formatTimestamp() {
  return new Date().toLocaleTimeString("en-IN", { 
    hour: "2-digit", 
    minute: "2-digit", 
    second: "2-digit", 
    timeZone: "Asia/Kolkata" 
  }) + " IST";
}