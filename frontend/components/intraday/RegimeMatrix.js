const REGIME_COLOR = {
  TRENDING_UP:       { color: "var(--green)",  bg: "rgba(0,196,140,0.12)",  border: "rgba(0,196,140,0.3)" },
  BREAKOUT:          { color: "#00FF88",        bg: "rgba(0,255,136,0.12)",  border: "rgba(0,255,136,0.3)" },
  RANGING:           { color: "var(--yellow)", bg: "rgba(255,184,0,0.12)",  border: "rgba(255,184,0,0.3)" },
  CHOPPY:            { color: "#FF8C42",        bg: "rgba(255,140,66,0.12)", border: "rgba(255,140,66,0.3)" },
  TRENDING_DOWN:     { color: "var(--red)",    bg: "rgba(255,69,96,0.12)",  border: "rgba(255,69,96,0.3)" },
  HIGH_VOLATILITY:   { color: "var(--yellow)", bg: "rgba(255,184,0,0.08)",  border: "rgba(255,184,0,0.2)" },
  CLOSED:            { color: "var(--text-3)", bg: "var(--elevated)",        border: "var(--border)" },
  PRE_OPEN:          { color: "var(--text-3)", bg: "var(--elevated)",        border: "var(--border)" },
  DEAD_ZONE:         { color: "var(--text-3)", bg: "var(--elevated)",        border: "var(--border)" },
  VIX_EXTREME:       { color: "var(--red)",    bg: "rgba(255,69,96,0.08)",  border: "rgba(255,69,96,0.2)" },
  VIX_HIGH:          { color: "var(--yellow)", bg: "rgba(255,184,0,0.08)",  border: "rgba(255,184,0,0.2)" },
};

function RegimeBadge({ regime }) {
  const style = REGIME_COLOR[regime] || REGIME_COLOR.CLOSED;
  return (
    <span style={{
      fontFamily: "var(--mono)", fontSize: 9, fontWeight: 600,
      padding: "2px 6px", borderRadius: 4,
      color: style.color, background: style.bg,
      border: `1px solid ${style.border}`,
      letterSpacing: "0.04em", textTransform: "uppercase",
      whiteSpace: "nowrap",
    }}>
      {regime ? regime.replace(/_/g, " ") : "UNKNOWN"}
    </span>
  );
}

function SkeletonCell() {
  return (
    <div style={{
      background: "var(--elevated)", border: "1px solid var(--border)",
      borderRadius: 8, padding: "10px 12px",
    }}>
      <div style={{ width: 56, height: 11, borderRadius: 4, background: "var(--border)", marginBottom: 6 }} />
      <div style={{ width: 72, height: 10, borderRadius: 4, background: "var(--border)" }} />
    </div>
  );
}

export default function RegimeMatrix({ watchlist = [], regimes = {}, loading = false }) {
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <span className="panel-title">Regime Matrix</span>
        <span className="panel-badge" style={{ color: watchlist.length ? "var(--cyan)" : undefined }}>
          {loading ? "…" : watchlist.length ? `${watchlist.length} tickers` : "—"}
        </span>
      </div>

      {loading && (
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8,
        }}>
          {Array.from({ length: 10 }).map((_, i) => <SkeletonCell key={i} />)}
        </div>
      )}

      {!loading && !watchlist.length && (
        <div style={{
          padding: "28px 0", textAlign: "center",
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
        }}>
          Awaiting scanner data…
        </div>
      )}

      {!loading && watchlist.length > 0 && (
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8,
        }}>
          {watchlist.map((ticker) => {
            const regimeData = regimes[ticker];
            const regime = typeof regimeData === "string"
              ? regimeData
              : regimeData?.regime ?? null;
            const styleKey = regime ? regime.toUpperCase() : "CLOSED";
            const style = REGIME_COLOR[styleKey] || REGIME_COLOR.CLOSED;

            return (
              <div key={ticker} style={{
                background: "var(--elevated)", border: `1px solid ${style.border}`,
                borderRadius: 8, padding: "10px 12px",
                transition: "border-color 0.2s",
              }}>
                <div style={{
                  fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600,
                  color: "var(--text)", marginBottom: 5,
                  letterSpacing: "0.04em",
                }}>
                  {ticker.replace(".NSE", "").replace(".NS", "")}
                </div>
                <RegimeBadge regime={styleKey} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
