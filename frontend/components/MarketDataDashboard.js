import { useState, useEffect } from "react";
import { getISTTime, getISTDate } from "../services/market";

export default function MarketDataDashboard({ analysis, prediction }) {
  const [istTime, setIstTime] = useState("--:--:--");
  const [istDate, setIstDate] = useState("—");

  useEffect(() => {
    function tick() {
      setIstTime(getISTTime());
      setIstDate(getISTDate());
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const execStatus = prediction
    ? prediction.realtime_signal?.action === "HOLD" && prediction.pipeline_routing_execution?.includes("Regime")
      ? "HALTED"
      : "COMPLETED"
    : "IDLE";

  const rows = [
    { label: "Exchange",         value: "NSE / BSE"                                                         },
    { label: "Timezone",         value: "Asia/Kolkata (UTC+5:30)"                                           },
    { label: "Market Date",      value: istDate                                                              },
    { label: "Market Time",      value: `${istTime} IST`                                                    },
    { label: "Ticker",           value: analysis?.ticker || "—"                                              },
    { label: "Data Points",      value: analysis ? `${analysis.data_points} trading days` : "—"             },
    { label: "Anomalies",        value: analysis ? `${analysis.anomaly_summary?.count ?? 0} flagged` : "—"  },
    { label: "Max |Z-Score|",    value: analysis ? String(analysis.anomaly_summary?.max_abs_zscore ?? "—") : "—" },
    { label: "Data Source",      value: !analysis ? "—" : analysis.used_synthetic_data ? "Synthetic (yfinance fallback)" : "Live (yfinance)" },
    { label: "Cache Layer",      value: "In-Memory (Redis: Phase 2)"                                        },
    { label: "Execution Status", value: execStatus                                                           },
  ];

  return (
    <div className="panel" style={{ marginBottom: 0 }}>
      <div className="panel-head">
        <span className="panel-title">Market Data Dashboard</span>
        <span className="panel-badge">NSE</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {rows.map(({ label, value }) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "7px 0", borderBottom: "1px solid var(--border)",
          }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-3)", textTransform: "uppercase" }}>
              {label}
            </span>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-2)" }}>
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
