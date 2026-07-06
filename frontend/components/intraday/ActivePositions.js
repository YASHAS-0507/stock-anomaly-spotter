function timeSince(openedAt) {
  if (!openedAt) return "—";
  try {
    const ts = openedAt.replace(" IST", "");
    const opened = new Date(ts.replace(" ", "T") + "+05:30");
    const diffMs = Date.now() - opened.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  } catch {
    return "—";
  }
}

function SkeletonRow() {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr 1fr 1fr",
      gap: 8, padding: "10px 0", borderBottom: "1px solid var(--border)",
    }}>
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} style={{ height: 12, borderRadius: 4, background: "var(--border)" }} />
      ))}
    </div>
  );
}

const COL_STYLE = {
  fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
  letterSpacing: "0.06em", textTransform: "uppercase", paddingBottom: 8,
};

export default function ActivePositions({ positions = [], currentPrices = {}, loading = false }) {
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <span className="panel-title">Active Positions</span>
        <span className="panel-badge" style={{ color: positions.length ? "var(--cyan)" : undefined }}>
          {loading ? "…" : positions.length ? `${positions.length} open` : "—"}
        </span>
      </div>

      {loading && (
        <div>
          {Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      )}

      {!loading && !positions.length && (
        <div style={{
          padding: "28px 0", textAlign: "center",
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
        }}>
          No open positions
        </div>
      )}

      {!loading && positions.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1.2fr 1fr 1fr 1fr 1.1fr 1fr 1fr",
            gap: 8, minWidth: 640,
          }}>
            {["Ticker", "Setup", "Entry", "Current", "Unreal P&L", "SL / TP1", "Held"].map((h) => (
              <div key={h} style={COL_STYLE}>{h}</div>
            ))}

            {positions.map((pos) => {
              const livePrice = currentPrices[pos.ticker] ?? pos.fill_price;
              const upnl = pos.unrealized_pnl ?? ((livePrice - pos.fill_price) * pos.shares);
              const pnlColor = upnl > 0 ? "var(--green)" : upnl < 0 ? "var(--red)" : "var(--text-2)";

              return [
                <div key={`${pos.ticker}-tk`} style={{
                  fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600,
                  color: "var(--text)", padding: "8px 0",
                  borderBottom: "1px solid var(--border)",
                }}>
                  {pos.ticker?.replace(".NSE", "").replace(".NS", "")}
                </div>,

                <div key={`${pos.ticker}-st`} style={{
                  fontFamily: "var(--mono)", fontSize: 10, color: "var(--cyan)",
                  padding: "8px 0", borderBottom: "1px solid var(--border)",
                  letterSpacing: "0.04em",
                }}>
                  {pos.setup_type || "—"}
                </div>,

                <div key={`${pos.ticker}-en`} style={{
                  fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-2)",
                  padding: "8px 0", borderBottom: "1px solid var(--border)",
                }}>
                  ₹{Number(pos.fill_price).toFixed(2)}
                </div>,

                <div key={`${pos.ticker}-cu`} style={{
                  fontFamily: "var(--mono)", fontSize: 12, color: "var(--text)",
                  padding: "8px 0", borderBottom: "1px solid var(--border)",
                }}>
                  ₹{Number(livePrice).toFixed(2)}
                </div>,

                <div key={`${pos.ticker}-pnl`} style={{
                  fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600,
                  color: pnlColor, padding: "8px 0", borderBottom: "1px solid var(--border)",
                }}>
                  {upnl >= 0 ? "+" : ""}₹{upnl.toFixed(2)}
                </div>,

                <div key={`${pos.ticker}-sl`} style={{
                  fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
                  padding: "8px 0", borderBottom: "1px solid var(--border)",
                }}>
                  <span style={{ color: "var(--red)" }}>₹{Number(pos.stop_loss).toFixed(1)}</span>
                  <span style={{ color: "var(--text-3)", margin: "0 4px" }}>/</span>
                  <span style={{ color: "var(--green)" }}>₹{Number(pos.take_profit_1).toFixed(1)}</span>
                </div>,

                <div key={`${pos.ticker}-hl`} style={{
                  fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
                  padding: "8px 0", borderBottom: "1px solid var(--border)",
                }}>
                  {timeSince(pos.opened_at)}
                </div>,
              ];
            })}
          </div>
        </div>
      )}
    </div>
  );
}
