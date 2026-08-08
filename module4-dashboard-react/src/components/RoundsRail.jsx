import { useState } from "react";

// Rounds arrive newest-first from the API; render oldest -> newest so the
// rail reads left-to-right as a timeline.
export default function RoundsRail({ rounds, onTrigger, triggering, canTrigger }) {
  const [hovered, setHovered] = useState(null);
  const ordered = [...rounds].reverse();
  const maxAcc = Math.max(0.01, ...ordered.map((r) => r.global_accuracy ?? 0));

  return (
    <div className="rail glass">
      <div className="rail__label">
        <p className="eyebrow">Federated rounds</p>
        <p className="rail__count mono">{rounds.length ? `${rounds.length} recorded` : "no rounds yet"}</p>
      </div>

      <div className="rail__track scrollable">
        {ordered.length === 0 && (
          <p className="rail__empty">Trigger the first round to see it appear here.</p>
        )}
        {ordered.map((r) => {
          const h = r.global_accuracy != null ? Math.max(6, (r.global_accuracy / maxAcc) * 46) : 6;
          return (
            <button
              key={r.id}
              className="rail__round"
              onMouseEnter={() => setHovered(r.id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(r.id)}
              onBlur={() => setHovered(null)}
            >
              <span className="rail__bar" style={{ height: `${h}px` }} />
              <span className="rail__round-num mono">#{r.round_number}</span>

              {hovered === r.id && (
                <div className="rail__tooltip glass">
                  <p className="rail__tooltip-title">Round {r.round_number}</p>
                  <dl>
                    <div>
                      <dt>Hospitals</dt>
                      <dd>{r.n_hospitals}</dd>
                    </div>
                    <div>
                      <dt>Global acc.</dt>
                      <dd>{r.global_accuracy != null ? `${(r.global_accuracy * 100).toFixed(1)}%` : "—"}</dd>
                    </div>
                    <div>
                      <dt>Local-only baseline</dt>
                      <dd>{r.baseline_accuracy != null ? `${(r.baseline_accuracy * 100).toFixed(1)}%` : "—"}</dd>
                    </div>
                  </dl>
                  {r.notes && <p className="rail__tooltip-notes">{r.notes}</p>}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {canTrigger && (
        <button className="btn btn--primary rail__trigger" onClick={onTrigger} disabled={triggering}>
          {triggering ? "Round in progress…" : "Trigger new round"}
        </button>
      )}
    </div>
  );
}
