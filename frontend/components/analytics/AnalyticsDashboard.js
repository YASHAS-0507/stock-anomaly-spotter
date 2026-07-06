import { useMemo } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  ReferenceLine,
} from "recharts";

const GREEN  = "#00c48c";
const RED    = "#ff4560";
const CYAN   = "#00d0ff";
const YELLOW = "#f5a623";

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ fontSize: 20, color: color || "var(--text)" }}>
        {value ?? "—"}
      </div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

// ─── Skeletons ────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="stat-card">
      <div style={{ width: 64, height: 10, borderRadius: 4, background: "var(--border)", marginBottom: 10 }} />
      <div style={{ width: 80, height: 20, borderRadius: 4, background: "var(--border)" }} />
    </div>
  );
}

function SkeletonChart({ height = 180 }) {
  return (
    <div style={{
      height, background: "var(--elevated)", borderRadius: 8,
      display: "flex", alignItems: "center", justifyContent: "center",
      border: "1px solid var(--border)",
    }}>
      <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)" }}>
        Loading…
      </span>
    </div>
  );
}

// ─── Custom tooltips ──────────────────────────────────────────────────────────

function EquityTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div style={{
      background: "var(--elevated)", border: "1px solid var(--border)",
      borderRadius: 7, padding: "8px 12px", fontFamily: "var(--mono)", fontSize: 10,
    }}>
      <div style={{ color: "var(--text-3)", marginBottom: 4 }}>{d.timestamp?.slice(0, 10)}</div>
      <div style={{ color: GREEN }}>₹{Number(d.equity).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</div>
      {d.drawdown_pct > 0 && <div style={{ color: RED }}>DD {d.drawdown_pct.toFixed(1)}%</div>}
    </div>
  );
}

function SetupTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "var(--elevated)", border: "1px solid var(--border)",
      borderRadius: 7, padding: "8px 12px", fontFamily: "var(--mono)", fontSize: 10,
    }}>
      <div style={{ color: "var(--text-3)", marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.fill }}>
          {p.name}: {p.dataKey === "win_rate" ? `${(p.value * 100).toFixed(0)}%` : `₹${p.value.toFixed(0)}`}
        </div>
      ))}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function AnalyticsDashboard({ data, loading = false }) {
  const isLive = data?.data_source === "real";

  // Flatten equity curve — prefer from data.risk if available
  const equityPoints = useMemo(() => {
    const pts = data?.risk?.equity_curve || data?.equity_curve?.data_points || [];
    return pts.filter(p => p.equity > 0);
  }, [data]);

  // Setup breakdown for bar chart
  const setupChartData = useMemo(() => {
    const breakdown = data?.setup_breakdown || {};
    return Object.entries(breakdown).map(([name, d]) => ({
      name: name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
      win_rate: d.win_rate || 0,
      avg_pnl:  d.avg_pnl  || 0,
      trades:   (d.wins || 0) + (d.losses || 0),
    }));
  }, [data]);

  const fmt = (v, dec = 2) => (v == null ? "—" : Number(v).toFixed(dec));
  const fmtPct = (v) => (v == null ? "—" : `${(Number(v) * 100).toFixed(1)}%`);
  const fmtPnl = (v) => {
    if (v == null) return "—";
    const n = Number(v);
    return `${n >= 0 ? "+" : ""}₹${Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };

  const totalPnl = data?.total_pnl ?? 0;
  const maxDd    = data?.risk?.max_drawdown_pct ?? 0;

  if (loading) {
    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
        <SkeletonChart height={180} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="panel" style={{ marginBottom: 16 }}>
        <div style={{
          fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-3)",
          textAlign: "center", padding: "32px 0",
        }}>
          Analytics not yet loaded. Click "Analytics" tab to fetch.
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 16 }}>

      {/* Data source badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <div style={{
          fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700,
          padding: "3px 10px", borderRadius: 4, letterSpacing: "0.08em",
          background: isLive ? "rgba(0,196,140,0.15)" : "rgba(245,166,35,0.15)",
          border: `1px solid ${isLive ? "rgba(0,196,140,0.4)" : "rgba(245,166,35,0.4)"}`,
          color: isLive ? GREEN : YELLOW,
        }}>
          {isLive ? "● LIVE DATA" : "◎ MOCK DATA"}
        </div>
        {!isLive && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)" }}>
            Switches automatically when real trades begin
          </span>
        )}
      </div>

      {/* Section 1 — Performance summary cards */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16,
      }}>
        <StatCard
          label="Total Trades"
          value={data.total_trades ?? "—"}
          sub={`${data.winning_trades ?? 0}W / ${data.losing_trades ?? 0}L`}
          color="var(--cyan)"
        />
        <StatCard
          label="Win Rate"
          value={fmtPct(data.win_rate)}
          sub={`Avg winner ${fmtPct(data.avg_winner_pct ? data.avg_winner_pct / 100 : null)}`}
          color={(data.win_rate ?? 0) >= 0.5 ? GREEN : RED}
        />
        <StatCard
          label="Total P&L"
          value={fmtPnl(data.total_pnl)}
          sub={`Expectancy ₹${fmt(data.expectancy_per_trade, 0)} / trade`}
          color={totalPnl >= 0 ? GREEN : RED}
        />
        <StatCard
          label="Profit Factor"
          value={fmt(data.profit_factor)}
          sub="Gross profit / gross loss"
          color={(data.profit_factor ?? 0) >= 1.5 ? GREEN : (data.profit_factor ?? 0) >= 1 ? YELLOW : RED}
        />
        <StatCard
          label="Sharpe Ratio"
          value={fmt(data.risk?.sharpe_ratio)}
          sub={`Sortino ${fmt(data.risk?.sortino_ratio)}`}
          color={(data.risk?.sharpe_ratio ?? 0) >= 1 ? GREEN : YELLOW}
        />
        <StatCard
          label="Max Drawdown"
          value={`${fmt(maxDd, 1)}%`}
          sub={`Risk: ${data.risk?.risk_rating ?? "—"}`}
          color={maxDd > 15 ? RED : maxDd > 8 ? YELLOW : GREEN}
        />
      </div>

      {/* Section 2 — Equity curve */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="panel-title">Equity Curve</span>
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)" }}>
            {equityPoints.length} data points
          </span>
        </div>
        {equityPoints.length > 1 ? (
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={equityPoints} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={GREEN} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={GREEN} stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={RED} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={RED} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={v => typeof v === "string" ? v.slice(5, 10) : ""}
                tick={{ fontFamily: "var(--mono)", fontSize: 8, fill: "var(--text-3)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontFamily: "var(--mono)", fontSize: 8, fill: "var(--text-3)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`}
                width={48}
              />
              <Tooltip content={<EquityTooltip />} />
              <Area
                type="monotone"
                dataKey="equity"
                stroke={GREEN}
                strokeWidth={1.5}
                fill="url(#equityGrad)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{
            height: 120, display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
          }}>
            No equity curve data
          </div>
        )}
      </div>

      {/* Section 3 — Setup breakdown bar chart */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="panel-title">Setup Breakdown</span>
        </div>
        {setupChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={setupChartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fontFamily: "var(--mono)", fontSize: 9, fill: "var(--text-3)" }}
                tickLine={false}
                axisLine={{ stroke: "var(--border)" }}
              />
              <YAxis
                yAxisId="wr"
                orientation="left"
                domain={[0, 1]}
                tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                tick={{ fontFamily: "var(--mono)", fontSize: 8, fill: "var(--text-3)" }}
                tickLine={false}
                axisLine={false}
                width={38}
              />
              <Tooltip content={<SetupTooltip />} />
              <ReferenceLine yAxisId="wr" y={0.5} stroke="var(--border)" strokeDasharray="3 2" />
              <Bar yAxisId="wr" dataKey="win_rate" name="Win Rate" isAnimationActive={false} maxBarSize={40}>
                {setupChartData.map((entry, i) => (
                  <Cell key={i} fill={entry.win_rate >= 0.5 ? GREEN : RED} fillOpacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div style={{
            height: 80, display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
          }}>
            No setup data available
          </div>
        )}
      </div>

      {/* Section 4 — Pattern insights */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="panel-title">Pattern Insights</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(data.patterns?.insights || []).map((insight, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              padding: "10px 14px", borderRadius: 7,
              background: "var(--elevated)", border: "1px solid var(--border)",
            }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: CYAN, flexShrink: 0 }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-2)", lineHeight: 1.5 }}>
                {insight}
              </span>
            </div>
          ))}
          {!data.patterns?.insights?.length && (
            <div style={{
              fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)",
              textAlign: "center", padding: "16px 0",
            }}>
              No insights available yet
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
