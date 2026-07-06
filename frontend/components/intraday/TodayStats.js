function fmt(val, decimals = 2) {
  if (val == null) return "—";
  return Number(val).toFixed(decimals);
}

function StatBox({ label, value, valueColor, sub, accentClass }) {
  return (
    <div className={`stat-card${accentClass ? " " + accentClass : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ fontSize: 22, color: valueColor || "var(--text)" }}>
        {value ?? "—"}
      </div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function SkeletonBox() {
  return (
    <div className="stat-card">
      <div style={{ width: 64, height: 10, borderRadius: 4, background: "var(--border)", marginBottom: 10 }} />
      <div style={{ width: 80, height: 22, borderRadius: 4, background: "var(--border)" }} />
    </div>
  );
}

export default function TodayStats({ portfolio, loading = false }) {
  if (loading) {
    return (
      <div style={{ marginBottom: 16 }}>
        <div className="stat-strip" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          {Array.from({ length: 8 }).map((_, i) => <SkeletonBox key={i} />)}
        </div>
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="panel" style={{ marginBottom: 16 }}>
        <div style={{
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
          textAlign: "center", padding: "16px 0",
        }}>
          Awaiting session data…
        </div>
      </div>
    );
  }

  const dailyPnl   = portfolio.daily_pnl ?? 0;
  const pnlColor   = dailyPnl > 0 ? "var(--green)" : dailyPnl < 0 ? "var(--red)" : "var(--text-2)";
  const pnlClass   = dailyPnl > 0 ? "up" : dailyPnl < 0 ? "down" : "";
  const winRate    = portfolio.win_rate ?? 0;
  const totalTrades = portfolio.total_trades ?? 0;

  const trades = Array.isArray(portfolio.open_positions) ? [] : [];
  const completedTrades = portfolio._trades ?? [];
  const sorted  = [...completedTrades].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0));
  const bestPnl  = sorted[0]?.pnl;
  const worstPnl = sorted[sorted.length - 1]?.pnl;

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 12,
      }}>
        <StatBox
          label="Trades Today"
          value={totalTrades}
          valueColor="var(--cyan)"
          accentClass="accent"
        />
        <StatBox
          label="Win / Loss"
          value={`${portfolio.win_count ?? 0} / ${portfolio.loss_count ?? 0}`}
          valueColor="var(--text)"
        />
        <StatBox
          label="Win Rate"
          value={`${fmt(winRate, 1)}%`}
          valueColor={winRate >= 50 ? "var(--green)" : "var(--red)"}
          accentClass={winRate >= 50 ? "up" : "down"}
        />
        <StatBox
          label="Today P&L"
          value={`${dailyPnl >= 0 ? "+" : ""}₹${fmt(dailyPnl)}`}
          valueColor={pnlColor}
          accentClass={pnlClass}
        />
        <StatBox
          label="Cash Available"
          value={`₹${Number(portfolio.cash ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          valueColor="var(--text)"
        />
        <StatBox
          label="Portfolio Value"
          value={`₹${Number(portfolio.total_value ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
          valueColor="var(--text)"
          accentClass="accent"
        />
        <StatBox
          label="Best Trade"
          value={bestPnl != null ? `${bestPnl >= 0 ? "+" : ""}₹${fmt(bestPnl)}` : "—"}
          valueColor="var(--green)"
          accentClass="up"
        />
        <StatBox
          label="Worst Trade"
          value={worstPnl != null ? `${worstPnl >= 0 ? "+" : ""}₹${fmt(worstPnl)}` : "—"}
          valueColor="var(--red)"
          accentClass="down"
        />
      </div>
    </div>
  );
}
