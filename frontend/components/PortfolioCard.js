import { formatINR } from "../services/market";

export default function PortfolioCard({ prediction }) {
  if (!prediction) return null;

  const portfolio = prediction.stage_6_portfolio_snapshot;
  const cash      = portfolio?.free_cash ?? 0;
  const total     = portfolio?.total_portfolio_value ?? 0;
  const positions = portfolio?.active_asset_exposure ?? [];

  const rows = [
    { label: "Total Value",   value: formatINR(total), color: "var(--cyan)"  },
    { label: "Free Cash",     value: formatINR(cash),  color: "var(--text)"  },
    { label: "Buying Power",  value: formatINR(cash),  color: "var(--text-2)" },
    { label: "Open Positions", value: String(positions.length), color: positions.length ? "var(--green)" : "var(--text-3)" },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Portfolio</span>
        <span className="panel-badge">{positions.length} positions</span>
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
            <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600, color }}>
              {value}
            </span>
          </div>
        ))}
      </div>

      {positions.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", marginBottom: 6 }}>
            Exposure
          </div>
          {positions.map((sym, i) => (
            <div key={i} style={{
              fontFamily: "var(--mono)", fontSize: 12, color: "var(--cyan)",
              padding: "4px 0", borderBottom: "1px solid var(--border)",
            }}>
              {sym}
            </div>
          ))}
        </div>
      )}

      {positions.length === 0 && (
        <div style={{ marginTop: 10, fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textAlign: "center" }}>
          No open positions
        </div>
      )}
    </div>
  );
}
