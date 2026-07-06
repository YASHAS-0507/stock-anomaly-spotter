import { useState, useEffect } from "react";
import { postSchedulerControl } from "../../services/api";

const STATUS_STYLE = {
  RUNNING:  { color: "var(--green)",  dot: "var(--green)",  label: "RUNNING" },
  PAUSED:   { color: "var(--yellow)", dot: "var(--yellow)", label: "PAUSED"  },
  STOPPED:  { color: "var(--text-3)", dot: "var(--text-3)", label: "STOPPED" },
  WEEKEND:  { color: "var(--text-3)", dot: "var(--text-3)", label: "WEEKEND" },
  ERROR:    { color: "var(--red)",    dot: "var(--red)",    label: "ERROR"   },
};

function deriveStatus(status) {
  if (!status) return "STOPPED";
  if (status.scheduler_running && !status.broker?.paused) return "RUNNING";
  if (status.scheduler_running && status.broker?.paused) return "PAUSED";
  if (!status.market_open && status.market_open !== undefined) return "WEEKEND";
  return "STOPPED";
}

function getMarketCountdown() {
  // Returns "Market opens in Xh Ym" if before 9:15am IST today (weekday), else null
  const nowUTC  = Date.now();
  const istMs   = nowUTC + 5.5 * 60 * 60 * 1000;
  const istDate = new Date(istMs);
  const day     = istDate.getUTCDay(); // 0=Sun, 1=Mon … 6=Sat
  if (day === 0 || day === 6) return null; // weekend

  const openMs = new Date(istMs);
  openMs.setUTCHours(3, 45, 0, 0); // 9:15 IST = 03:45 UTC
  const diffMs = openMs - nowUTC;
  if (diffMs <= 0) return null;

  const totalMins = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMins / 60);
  const mins  = totalMins % 60;
  return hours > 0 ? `Market opens in ${hours}h ${mins}m` : `Market opens in ${mins}m`;
}

export default function SchedulerControls({ status, onAction, loading = false }) {
  const [busy, setBusy]             = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [lastMsg, setLastMsg]       = useState(null);
  const [countdown, setCountdown]   = useState(() => getMarketCountdown());

  useEffect(() => {
    const id = setInterval(() => setCountdown(getMarketCountdown()), 60000);
    return () => clearInterval(id);
  }, []);

  const derived = deriveStatus(status);
  const style   = STATUS_STYLE[derived] || STATUS_STYLE.STOPPED;

  const isRunning = derived === "RUNNING";
  const isPaused  = derived === "PAUSED";
  const isBusy    = loading || busy;

  async function handle(action) {
    setBusy(true);
    setLastMsg(null);
    try {
      const res = await postSchedulerControl(action);
      setLastMsg({ ok: true, text: res.message || `${action} successful` });
      if (onAction) onAction(action, res);
    } catch (err) {
      setLastMsg({ ok: false, text: err.message || `${action} failed` });
    } finally {
      setBusy(false);
    }
  }

  async function handleEmergencyStop() {
    setConfirmStop(false);
    await handle("emergency-stop");
  }

  const btnBase = {
    fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600,
    padding: "9px 18px", borderRadius: 7, cursor: "pointer",
    letterSpacing: "0.04em", border: "1px solid transparent",
    transition: "opacity 0.15s, box-shadow 0.15s",
    display: "inline-flex", alignItems: "center", gap: 6,
  };

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <span className="panel-title">Scheduler Controls</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: style.dot,
            boxShadow: derived === "RUNNING" ? `0 0 6px ${style.dot}` : "none",
          }} />
          <span style={{
            fontFamily: "var(--mono)", fontSize: 11, fontWeight: 600,
            color: style.color, letterSpacing: "0.08em",
          }}>
            {style.label}
          </span>
        </div>
      </div>

      {/* Market open countdown — only before 9:15am on weekdays when not running */}
      {countdown && !isRunning && (
        <div style={{
          fontFamily: "var(--mono)", fontSize: 11, color: "var(--cyan)",
          marginBottom: 12, padding: "7px 12px",
          background: "rgba(0,208,255,0.07)", border: "1px solid rgba(0,208,255,0.2)",
          borderRadius: 6,
        }}>
          ⏱ {countdown}
        </div>
      )}

      {/* Status snapshot */}
      {status && (
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 16,
        }}>
          {[
            { label: "Market Open",  val: status.market_open  ? "YES" : "NO",  color: status.market_open  ? "var(--green)" : "var(--text-3)" },
            { label: "Open Positions", val: status.broker?.open_count ?? 0, color: "var(--cyan)" },
            { label: "Daily P&L",    val: status.broker?.daily_pnl != null
                ? `${status.broker.daily_pnl >= 0 ? "+" : ""}₹${Number(status.broker.daily_pnl).toFixed(2)}`
                : "—",
              color: (status.broker?.daily_pnl ?? 0) >= 0 ? "var(--green)" : "var(--red)" },
          ].map(({ label, val, color }) => (
            <div key={label} style={{
              background: "var(--elevated)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "10px 14px",
            }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-3)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                {label}
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600, color }}>
                {val}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Buttons */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          disabled={isBusy || isRunning || isPaused}
          onClick={() => handle("start")}
          style={{
            ...btnBase,
            background: "var(--green)", color: "#000",
            opacity: (isBusy || isRunning || isPaused) ? 0.4 : 1,
            cursor: (isBusy || isRunning || isPaused) ? "not-allowed" : "pointer",
          }}
        >
          ▶ START
        </button>

        <button
          disabled={isBusy || !isRunning}
          onClick={() => handle("pause")}
          style={{
            ...btnBase,
            background: "var(--yellow)", color: "#000",
            opacity: (isBusy || !isRunning) ? 0.4 : 1,
            cursor: (isBusy || !isRunning) ? "not-allowed" : "pointer",
          }}
        >
          ⏸ PAUSE
        </button>

        <button
          disabled={isBusy || !isPaused}
          onClick={() => handle("resume")}
          style={{
            ...btnBase,
            background: "var(--cyan)", color: "#000",
            opacity: (isBusy || !isPaused) ? 0.4 : 1,
            cursor: (isBusy || !isPaused) ? "not-allowed" : "pointer",
          }}
        >
          ▶ RESUME
        </button>

        <button
          disabled={isBusy}
          onClick={() => setConfirmStop(true)}
          style={{
            ...btnBase,
            background: "rgba(255,69,96,0.15)",
            border: "1px solid rgba(255,69,96,0.4)",
            color: "var(--red)",
            marginLeft: "auto",
            opacity: isBusy ? 0.5 : 1,
            cursor: isBusy ? "not-allowed" : "pointer",
          }}
        >
          🛑 EMERGENCY STOP
        </button>
      </div>

      {/* Confirmation dialog */}
      {confirmStop && (
        <div style={{
          marginTop: 14, padding: "14px 16px",
          background: "rgba(255,69,96,0.08)", border: "1px solid rgba(255,69,96,0.3)",
          borderRadius: 8,
        }}>
          <div style={{
            fontFamily: "var(--mono)", fontSize: 12, color: "var(--red)",
            marginBottom: 12, fontWeight: 600,
          }}>
            Confirm emergency stop? All open positions will be squared off immediately.
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleEmergencyStop}
              style={{
                ...btnBase, background: "var(--red)", color: "#fff", fontSize: 11,
              }}
            >
              CONFIRM STOP
            </button>
            <button
              onClick={() => setConfirmStop(false)}
              style={{
                ...btnBase,
                background: "var(--elevated)", border: "1px solid var(--border)",
                color: "var(--text-2)", fontSize: 11,
              }}
            >
              CANCEL
            </button>
          </div>
        </div>
      )}

      {/* Status message */}
      {lastMsg && (
        <div style={{
          marginTop: 10, fontFamily: "var(--mono)", fontSize: 11,
          color: lastMsg.ok ? "var(--green)" : "var(--red)",
          padding: "8px 12px", borderRadius: 6,
          background: lastMsg.ok ? "rgba(0,196,140,0.08)" : "rgba(255,69,96,0.08)",
          border: `1px solid ${lastMsg.ok ? "rgba(0,196,140,0.25)" : "rgba(255,69,96,0.25)"}`,
        }}>
          {lastMsg.text}
        </div>
      )}
    </div>
  );
}
