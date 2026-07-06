const REGIME_DOT = {
  TRENDING_UP:       "var(--green)",
  BREAKOUT:          "var(--green)",
  TRENDING_DOWN:     "var(--red)",
  CHOPPY:            "var(--red)",
  RANGING:           "var(--yellow)",
  HIGH_VOLATILITY:   "var(--yellow)",
};

function dotColor(regime) {
  return REGIME_DOT[regime] || "var(--text-3)";
}

function SkeletonTicker() {
  return (
    <div style={{
      display: "inline-flex", flexDirection: "column", gap: 4,
      background: "var(--elevated)", borderRadius: 8,
      padding: "10px 16px", minWidth: 100,
    }}>
      <div style={{ width: 48, height: 10, borderRadius: 4, background: "var(--border)" }} />
      <div style={{ width: 64, height: 12, borderRadius: 4, background: "var(--border)" }} />
    </div>
  );
}

export default function LiveTickerStrip({ prices = {}, watchlist = [], loading = false }) {
  if (loading) {
    return (
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, padding: "12px 16px", marginBottom: 16, overflowX: "auto",
      }}>
        <div style={{ display: "flex", gap: 10, width: "max-content" }}>
          {Array.from({ length: 8 }).map((_, i) => <SkeletonTicker key={i} />)}
        </div>
      </div>
    );
  }

  if (!watchlist.length) {
    return (
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, padding: "14px 20px", marginBottom: 16,
        fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
      }}>
        Scanner running…
      </div>
    );
  }

  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 12, padding: "12px 16px", marginBottom: 16,
      overflowX: "auto",
    }}>
      <div style={{ display: "flex", gap: 10, width: "max-content" }}>
        {watchlist.map((ticker) => {
          const data = prices[ticker];
          const price   = data?.price  ?? data ?? null;
          const prevClose = data?.prev_close ?? null;
          const regime  = data?.regime  ?? null;
          const changePct = (price != null && prevClose && prevClose > 0)
            ? ((price - prevClose) / prevClose) * 100
            : null;
          const changeColor = changePct == null ? "var(--text-3)"
            : changePct > 0 ? "var(--green)" : changePct < 0 ? "var(--red)" : "var(--text-2)";

          return (
            <div key={ticker} style={{
              display: "inline-flex", flexDirection: "column", gap: 3,
              background: "var(--elevated)", borderRadius: 8,
              padding: "10px 16px", minWidth: 96, flexShrink: 0,
              border: "1px solid var(--border)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: dotColor(regime),
                  boxShadow: regime ? `0 0 4px ${dotColor(regime)}` : "none",
                  flexShrink: 0,
                }} />
                <span style={{
                  fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600,
                  color: "var(--text-2)", letterSpacing: "0.06em",
                }}>
                  {ticker.replace(".NSE", "").replace(".NS", "")}
                </span>
              </div>
              <div style={{
                fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600,
                color: "var(--text)",
              }}>
                {price != null ? `₹${Number(price).toFixed(2)}` : "—"}
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: changeColor }}>
                {changePct != null
                  ? `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%`
                  : "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
