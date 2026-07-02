export default function TopBar({ onLogout }) {
  return (
    <header className="terminal-header panel">
      <div className="header-left flex items-center gap-lg">
        <div className="brand flex items-center gap-sm">
          <div className="w-3 h-3 rounded-full bg-cyan" style={{ boxShadow: "0 0 12px var(--cyan)" }} />
          <div>
            <div className="brand-name text-title font-mono">STOCK ANOMALY SPOTTER</div>
            <div className="brand-tag text-caption">Institutional Trading Terminal</div>
          </div>
        </div>
      </div>

      <div className="header-center hidden md:block">
        <div className="flex items-center gap-lg">
          <div className="text-center">
            <div className="text-label">EXCHANGE</div>
            <div className="text-value font-mono">NSE</div>
          </div>
          <div className="w-px h-8 bg-panel-border mx-md" />
          <div className="text-center">
            <div className="text-label">TIMEZONE</div>
            <div className="text-value font-mono">IST (UTC+5:30)</div>
          </div>
        </div>
      </div>

      <div className="header-right flex items-center gap-md">
        <div className="hidden lg:block text-right">
          <div className="text-label">SESSION</div>
          <div className="flex items-center justify-end gap-sm">
            <span className="badge-dot status-warning" />
            <span className="text-value font-mono signal-hold">PRE-MARKET</span>
          </div>
        </div>

        <div className="hidden lg:block text-right">
          <div className="text-label">FEED</div>
          <div className="flex items-center justify-end gap-sm">
            <span className="badge-dot status-disconnected" />
            <span className="text-value font-mono signal-sell">DISCONNECTED</span>
          </div>
        </div>

        <div className="text-right">
          <div className="text-label">TIME</div>
          <div className="flex items-center justify-end gap-sm">
            <span className="text-metric-sm font-mono" id="header-time">--:--:--</span>
          </div>
        </div>

        <button className="btn btn-ghost btn-sm ml-sm" onClick={onLogout}>
          LOGOUT
        </button>
      </div>
    </header>
  );
}