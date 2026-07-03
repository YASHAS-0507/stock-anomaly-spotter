import { useState, useEffect, useCallback } from "react";
import { API_BASE } from "../services/api";
import { formatINR } from "../services/market";

export default function PortfolioCard() {
  const [portfolio, setPortfolio] = useState(null);
  const [resetting, setResetting] = useState(false);

  const fetchPortfolio = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/paper/portfolio`);
      if (!res.ok) return;
      const data = await res.json();
      setPortfolio(data);
    } catch (_) {}
  }, []);

  useEffect(() => {
    fetchPortfolio();
    const id = setInterval(fetchPortfolio, 10000);
    return () => clearInterval(id);
  }, [fetchPortfolio]);

  async function handleReset() {
    if (!confirm("Reset paper trading portfolio to ₹1,00,000?")) return;
    setResetting(true);
    try {
      await fetch(`${API_BASE}/api/paper/reset`, { method: "POST" });
      await fetchPortfolio();
    } catch (_) {}
    setResetting(false);
  }

  const p = portfolio;
  const pnlColor = !p
    ? "var(--text-3)"
    : p.total_pnl > 0
    ? "var(--green)"
    : p.total_pnl < 0
    ? "var(--red)"
    : "var(--text)";

  const rows = [
    { label: "Total Value",   value: p ? formatINR(p.total_value)  : "—", color: "var(--cyan)" },
    { label: "Cash",          value: p ? formatINR(p.cash)         : "—", color: "var(--text)" },
    { label: "Invested",      value: p ? formatINR(p.invested)     : "—", color: "var(--text-2)" },
    { label: "Total P&L",     value: p ? `${p.total_pnl >= 0 ? "+" : ""}${formatINR(p.total_pnl)} (${p.total_pnl_pct >= 0 ? "+" : ""}${p.total_pnl_pct}%)` : "—", color: pnlColor },
    { label: "Win Rate",      value: p ? `${p.win_rate}%` : "—",  color: p?.win_rate >= 50 ? "var(--green)" : "var(--text-2)" },
    { label: "Trades",        value: p ? `${p.total_trades} (${p.win_count}W / ${p.loss_count}L)` : "—", color: "var(--text)" },
    { label: "Open Positions", value: p ? String(p.open_count) : "—", color: p?.open_count ? "var(--green)" : "var(--text-3)" },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Paper Portfolio</span>
        <span className="panel-badge" style={{ color: "var(--cyan)" }}>VIRTUAL</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {rows.map(({ label, value, color }) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "9px 0", borderBottom: "1px solid var(--border)",
          }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase" }}>
              {label}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color }}>
              {value}
            </span>
          </div>
        ))}
      </div>

      {p?.positions?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", marginBottom: 6 }}>
            Open Positions
          </div>
          {p.positions.map((pos) => {
            const posColor = pos.unrealized_pnl >= 0 ? "var(--green)" : "var(--red)";
            return (
              <div key={pos.symbol} style={{
                display: "flex", justifyContent: "space-between",
                fontFamily: "var(--mono)", fontSize: 11,
                padding: "5px 0", borderBottom: "1px solid var(--border)",
              }}>
                <span style={{ color: "var(--cyan)" }}>{pos.symbol}</span>
                <span style={{ color: "var(--text-2)" }}>{pos.quantity} @ ₹{pos.fill_price}</span>
                <span style={{ color: posColor }}>
                  {pos.unrealized_pnl >= 0 ? "+" : ""}{formatINR(pos.unrealized_pnl)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {p?.positions?.length === 0 && (
        <div style={{ marginTop: 10, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textAlign: "center" }}>
          No open positions
        </div>
      )}

      <button
        onClick={handleReset}
        disabled={resetting}
        style={{
          marginTop: 14, width: "100%", padding: "7px 0",
          fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600,
          color: "var(--text-3)", background: "transparent",
          border: "1px solid var(--border)", borderRadius: 4,
          cursor: resetting ? "not-allowed" : "pointer", letterSpacing: "0.05em",
        }}
      >
        {resetting ? "RESETTING…" : "RESET PORTFOLIO"}
      </button>
    </div>
  );
}
