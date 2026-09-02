export default function TopHUD({ me, overview, view, onSetView, onLogout, onRefresh, refreshing }) {
  return (
    <div className="hud">
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
        <button className={view === "map" ? "is-active" : ""} onClick={() => onSetView("map")}>
          Federation
        </button>
        <button className={view === "system" ? "is-active" : ""} onClick={() => onSetView("system")}>
          Architecture
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
    </div>
  );
}
