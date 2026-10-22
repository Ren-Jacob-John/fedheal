export default function TopHUD({ me, overview, view, onSetView, onLogout, onRefresh, refreshing }) {
  return (
    <header className="hud">
      <div className="hud__brand glass">
        <span className="hud__brand-dot" aria-hidden="true" />
        <div>
          <h1 className="hud__brand-title">FedHeal</h1>
          <p className="eyebrow">
            {me.role.replace("_", " ")}
            {me.hospital_id ? ` · ${me.hospital_id.slice(0, 8)}` : ""}
          </p>
        </div>
      </div>

      <nav className="hud__tabs glass" aria-label="View">
        <button aria-current={view === "map" ? "page" : undefined} className={view === "map" ? "is-active" : ""} onClick={() => onSetView("map")}>
          <span className="hud__tab-icon" aria-hidden="true">◉</span>
          Federation
        </button>
        <button aria-current={view === "system" ? "page" : undefined} className={view === "system" ? "is-active" : ""} onClick={() => onSetView("system")}>
          <span className="hud__tab-icon" aria-hidden="true">⌘</span>
          Architecture
        </button>
        {me.role !== "super_admin" && (
          <button aria-current={view === "cases" ? "page" : undefined} className={view === "cases" ? "is-active" : ""} onClick={() => onSetView("cases")}>
            <span className="hud__tab-icon" aria-hidden="true">＋</span>
            {me.role === "hospital_admin" ? "Doctors" : "Cases"}
          </button>
        )}
        <button aria-current={view === "synthesis" ? "page" : undefined} className={view === "synthesis" ? "is-active" : ""} onClick={() => onSetView("synthesis")}>
          <span className="hud__tab-icon" aria-hidden="true">✦</span>
          Synthesis
        </button>
      </nav>

      {overview && (
        <div className="hud__stats glass">
          <div>
            <p className="eyebrow">Hospitals</p>
            <p className="hud__stat-value">
              <span className="c-teal">{overview.active_hospitals}</span>
              <span className="hud__stat-of"> / {overview.total_hospitals}</span>
            </p>
          </div>
          <div className="hud__divider" />
          <div>
            <p className="eyebrow">Latest round</p>
            <p className="hud__stat-value">
              {overview.latest_round_number != null ? `#${overview.latest_round_number}` : "—"}
            </p>
          </div>
          <div className="hud__divider" />
          <div>
            <p className="eyebrow">Global accuracy</p>
            <p className="hud__stat-value">
              {overview.latest_global_accuracy != null
                ? `${(overview.latest_global_accuracy * 100).toFixed(1)}%`
                : "—"}
            </p>
          </div>
          <div className="hud__divider" />
          <div>
            <p className="eyebrow">Flags (7d)</p>
            <p className="hud__stat-value">
              <span className={overview.flags_last_7_days > 0 ? "c-amber" : ""}>
                {overview.flags_last_7_days}
              </span>
            </p>
          </div>
        </div>
      )}

      <div className="hud__actions">
        <button className="hud__icon-btn glass" onClick={onRefresh} title="Refresh" aria-label="Refresh">
          <span className={refreshing ? "hud__spin" : ""}>⟳</span>
        </button>
        <button className="hud__icon-btn glass" onClick={onLogout} title="Log out" aria-label="Log out">
          ⏻
        </button>
      </div>
    </header>
  );
}
