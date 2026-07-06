const REASON_LABEL = {
  stop_loss:   "SL",
  take_profit: "TP",
  time_stop:   "TIME",
  square_off:  "EOD",
};

const REASON_COLOR = {
  stop_loss:   "var(--red)",
  take_profit: "var(--green)",
  time_stop:   "var(--yellow)",
  square_off:  "var(--text-3)",
};

function formatTime(ts) {
  if (!ts) return "—";
  try {
    const clean = ts.replace(" IST", "");
    const d = new Date(clean.replace(" ", "T") + "+05:30");
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return ts.slice(11, 16) || "—";
  }
}

function SkeletonRow() {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "60px 80px 1fr 1fr 80px 60px",
      gap: 8, padding: "10px 0", borderBottom: "1px solid var(--border)",
    }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} style={{ height: 12, borderRadius: 4, background: "var(--border)" }} />
      ))}
    </div>
  );
}

export default function AutoTradeLog({ trades = [], loading = false }) {
  const displayed = trades.slice(0, 20);

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <span className="panel-title">Trade Log — Today</span>
        <span className="panel-badge" style={{ color: trades.length ? "var(--cyan)" : undefined }}>
          {loading ? "…" : trades.length ? `${trades.length} trade${trades.length !== 1 ? "s" : ""}` : "—"}
        </span>
      </div>

      {loading && (
        <div>
          {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      )}

      {!loading && !trades.length && (
        <div style={{
          padding: "28px 0", textAlign: "center",
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
        }}>
          No trades yet today
        </div>
      )}

      {!loading && displayed.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          {/* Header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "60px 80px 1fr 1fr 100px 60px",
            gap: 8, minWidth: 560, paddingBottom: 8,
            borderBottom: "1px solid var(--border)",
          }}>
            {["Time", "Ticker", "Entry → Exit", "Setup", "P&L", "Exit"].map((h) => (
              <div key={h} style={{
                fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
                letterSpacing: "0.06em", textTransform: "uppercase",
              }}>
                {h}
              </div>
            ))}
          </div>

          {displayed.map((trade, idx) => {
            const won = (trade.pnl ?? 0) > 0;
            const pnlColor = won ? "var(--green)" : (trade.pnl ?? 0) < 0 ? "var(--red)" : "var(--text-2)";
            const rowBg = idx % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)";
            const reason = trade.close_reason ?? "";

            return (
              <div key={trade.trade_id || idx} style={{
                display: "grid",
                gridTemplateColumns: "60px 80px 1fr 1fr 100px 60px",
                gap: 8, minWidth: 560,
                padding: "9px 0",
                borderBottom: "1px solid var(--border)",
                background: rowBg,
                borderLeft: `3px solid ${pnlColor}`,
                paddingLeft: 8,
              }}>
                <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)" }}>
                  {formatTime(trade.closed_at)}
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--text)" }}>
                  {(trade.ticker || "").replace(".NSE", "").replace(".NS", "")}
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-2)" }}>
                  ₹{Number(trade.fill_price ?? 0).toFixed(2)}
                  <span style={{ color: "var(--text-3)", margin: "0 4px" }}>→</span>
                  ₹{Number(trade.exit_price ?? 0).toFixed(2)}
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--cyan)", letterSpacing: "0.04em" }}>
                  {trade.setup_type || "—"}
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: pnlColor }}>
                  {(trade.pnl ?? 0) >= 0 ? "+" : ""}₹{Number(trade.pnl ?? 0).toFixed(2)}
                </div>
                <div style={{
                  fontFamily: "var(--mono)", fontSize: 10, fontWeight: 600,
                  color: REASON_COLOR[reason] || "var(--text-3)",
                  textTransform: "uppercase",
                }}>
                  {REASON_LABEL[reason] || reason || "—"}
                </div>
              </div>
            );
          })}

          {trades.length > 20 && (
            <div style={{
              padding: "10px 0", fontFamily: "var(--mono)", fontSize: 11,
              color: "var(--text-3)", textAlign: "center",
            }}>
              +{trades.length - 20} more trades not shown
            </div>
          )}
        </div>
      )}
    </div>
  );
}
