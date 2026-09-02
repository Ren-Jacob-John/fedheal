import UploadPanel from "./UploadPanel.jsx";

function FlagsList({ flags }) {
  if (!flags) return <p className="drawer__muted">Loading flags…</p>;
  if (flags.length === 0) return <p className="drawer__muted">No flags reported.</p>;
  return (
    <ul className="flags">
      {flags.map((f) => (
        <li key={f.id} className={`flags__item flags__item--${f.status}`}>
          <span className="flags__dot" />
          <div>
            <p className="flags__reason">{f.reason}</p>
            <p className="flags__meta mono">
              {f.status} · ×{f.count} · {new Date(f.reported_at).toLocaleString()}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function DetailDrawer({
  selection,
  onClose,
  me,
  token,
  hospital,
  overview,
  rounds,
  flags,
  onTriggerRound,
  triggering,
  onUploaded,
  onSetHospitalActive,
}) {
  if (!selection) return null;

  const isCore = selection === "core";
  const isSuperAdmin = me.role === "super_admin";
  const isOwnHospital = !isCore && me.hospital_id === selection;

  return (
    <aside className="drawer glass" aria-label="Details">
      <button className="drawer__close" onClick={onClose} aria-label="Close">
        ×
      </button>

      {isCore ? (
        <>
          <p className="eyebrow">Shared model</p>
          <h2 className="drawer__title">Global federation</h2>
          <p className="drawer__body">
            Every round, each active hospital trains locally on only its own
            validated data, then sends <em>weights only</em> here to be
            averaged (FedAvg) — never a patient record.
          </p>

          {overview ? (
            <dl className="drawer__facts">
              <div>
                <dt>Active hospitals</dt>
                <dd>
                  {overview.active_hospitals} / {overview.total_hospitals}
                </dd>
              </div>
              <div>
                <dt>Rounds recorded</dt>
                <dd>{overview.total_rounds_recorded}</dd>
              </div>
              <div>
                <dt>Latest global accuracy</dt>
                <dd>
                  {overview.latest_global_accuracy != null
                    ? `${(overview.latest_global_accuracy * 100).toFixed(1)}%`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Flags, last 7 days</dt>
                <dd>{overview.flags_last_7_days}</dd>
              </div>
            </dl>
          ) : (
            <p className="drawer__muted">
              Overview stats are only visible to the platform operator (super
              admin).
            </p>
          )}

          {rounds && rounds.length > 0 && (
            <>
              <p className="eyebrow drawer__section-label">Recent rounds</p>
              <ul className="drawer__round-list">
                {rounds.slice(0, 6).map((r) => (
                  <li key={r.id}>
                    <span className="mono">#{r.round_number}</span>
                    <span>{r.n_hospitals} hospitals</span>
                    <span className="c-teal">
                      {r.global_accuracy != null ? `${(r.global_accuracy * 100).toFixed(1)}%` : "—"}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {isSuperAdmin && (
            <button className="btn btn--primary btn--block" onClick={onTriggerRound} disabled={triggering}>
              {triggering ? "Round in progress…" : "Trigger new federated round"}
            </button>
          )}
        </>
      ) : (
        <>
          <p className="eyebrow">{hospital?.is_active ? "Active hospital" : "Inactive hospital"}</p>
          <h2 className="drawer__title">
            {hospital?.name ?? "Unknown hospital"}
            {isOwnHospital && <span className="drawer__you"> · you</span>}
          </h2>

          {hospital?.status ? (
            <dl className="drawer__facts">
              <div>
                <dt>Status</dt>
                <dd>{hospital.status === "ready_for_training" ? "Ready for training" : "Collecting data"}</dd>
              </div>
              <div>
                <dt>Validated records</dt>
                <dd>{hospital.records}</dd>
              </div>
              <div>
                <dt>Last upload</dt>
                <dd>{hospital.last_upload ? new Date(hospital.last_upload).toLocaleString() : "never"}</dd>
              </div>
            </dl>
          ) : (
            <p className="drawer__muted">
              Only visible to this hospital's own users — every other
              hospital's upload activity stays private, on purpose.
            </p>
          )}

          {isSuperAdmin && (
            <button
              className="btn btn--ghost btn--block"
              onClick={() => onSetHospitalActive(hospital.id, !hospital.is_active)}
            >
              {hospital?.is_active ? "Deactivate hospital" : "Reactivate hospital"}
            </button>
          )}

          {isSuperAdmin && (
            <>
              <p className="eyebrow drawer__section-label">Validation flags</p>
              <FlagsList flags={flags} />
            </>
          )}

          {isOwnHospital && (
            <>
              <p className="eyebrow drawer__section-label">Upload vitals</p>
              <UploadPanel token={token} onUploaded={onUploaded} />
            </>
          )}
        </>
      )}
    </aside>
  );
}
