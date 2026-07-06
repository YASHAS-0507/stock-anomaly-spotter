const ACTION_STYLE = {
  BOOST:  { color: "var(--green)",  bg: "rgba(0,196,140,0.12)",  border: "rgba(0,196,140,0.3)"  },
  BLOCK:  { color: "var(--red)",    bg: "rgba(255,69,96,0.12)",  border: "rgba(255,69,96,0.3)"  },
  WATCH:  { color: "var(--yellow)", bg: "rgba(255,184,0,0.12)",  border: "rgba(255,184,0,0.3)"  },
  NORMAL: { color: "var(--text-3)", bg: "var(--elevated)",       border: "var(--border)"        },
};

function ActionBadge({ action }) {
  const style = ACTION_STYLE[action] || ACTION_STYLE.NORMAL;
  return (
    <span style={{
      fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600,
      padding: "2px 7px", borderRadius: 4,
      color: style.color, background: style.bg,
      border: `1px solid ${style.border}`,
      letterSpacing: "0.04em",
    }}>
      {action || "NORMAL"}
    </span>
  );
}

function SkeletonRow() {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 0", borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ width: 24, height: 12, borderRadius: 4, background: "var(--border)" }} />
      <div style={{ width: 72, height: 12, borderRadius: 4, background: "var(--border)" }} />
      <div style={{ width: 48, height: 12, borderRadius: 4, background: "var(--border)", marginLeft: "auto" }} />
    </div>
  );
}

export default function ScannerCard({ watchlist = [], intelligence = {}, loading = false }) {
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <span className="panel-title">Scanner Results</span>
        <span className="panel-badge" style={{ color: watchlist.length ? "var(--cyan)" : undefined }}>
          {loading ? "…" : watchlist.length ? `${watchlist.length} stocks` : "—"}
        </span>
      </div>

      {loading && (
        <div>
          <div style={{
            padding: "12px 0", fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
            borderBottom: "1px solid var(--border)", marginBottom: 8,
          }}>
            Scanner runs at 8:00am
          </div>
          {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      )}

      {!loading && !watchlist.length && (
        <div style={{
          padding: "28px 0", textAlign: "center",
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
        }}>
          Scanner runs at 8:00am
        </div>
      )}

      {!loading && watchlist.length > 0 && (
        <div>
          {watchlist.map((ticker, idx) => {
            const intel   = intelligence[ticker] || {};
            const action  = (intel.action || "NORMAL").toUpperCase();
            const score   = intel.intelligence_score ?? intel.score ?? null;
            const sentiment = intel.sentiment || null;
            const sector  = intel.sector || null;

            return (
              <div key={ticker} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "10px 0", borderBottom: "1px solid var(--border)",
              }}>
                <div style={{
                  fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
                  minWidth: 20, textAlign: "right",
                }}>
                  {idx + 1}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--text)",
                  }}>
                    {ticker.replace(".NSE", "").replace(".NS", "")}
                  </div>
                  {(sector || sentiment) && (
                    <div style={{
                      fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", marginTop: 1,
                    }}>
                      {[sector, sentiment].filter(Boolean).join(" · ")}
                    </div>
                  )}
                </div>

                {score != null && (
                  <div style={{
                    fontFamily: "var(--mono)", fontSize: 11, color: "var(--cyan)",
                    minWidth: 32, textAlign: "right",
                  }}>
                    {score}
                  </div>
                )}

                <ActionBadge action={action} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
