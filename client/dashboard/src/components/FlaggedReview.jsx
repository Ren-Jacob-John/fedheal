import { useEffect, useState } from "react";
import { authApi, ApiError } from "../api.js";

// Human-in-the-loop review for records Module 2's isolation-forest pass
// flagged as statistical outliers within their upload batch — stored, but
// not yet trusted. A hospital_admin (or super_admin, for their own
// hospital) decides per record: approve (-> "passed", eligible for the
// next federated round) or reject (-> deleted, same as if Module 2 had
// rejected it outright). Closes the gap both Module 1's and Module 2's
// READMEs called out: flagged records used to just accumulate with no
// way for anyone to actually look at them.
export default function FlaggedReview({ token, onReviewed }) {
  const [records, setRecords] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  async function load() {
    try {
      const res = await authApi.flaggedVitals(token);
      setRecords(res);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load flagged records.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function decide(id, decision) {
    setBusyId(id);
    try {
      await authApi.reviewFlaggedVitals(token, id, decision);
      setRecords((prev) => (prev ? prev.filter((r) => r.id !== id) : prev));
      onReviewed?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Review failed.");
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <p className="upload__error">{error}</p>;
  if (!records) return <p className="drawer__muted">Loading flagged records…</p>;
  if (records.length === 0) return <p className="drawer__muted">Nothing waiting on review.</p>;

  return (
    <ul className="flagged-review">
      {records.map((r) => (
        <li key={r.id} className="flagged-review__item">
          <div className="flagged-review__vitals mono">
            <span>{r.patient_ref}</span>
            <span>age {r.age_years}</span>
            <span>BP {r.systolic_bp ?? "—"}/{r.diastolic_bp ?? "—"}</span>
            <span>HR {r.heart_rate_bpm ?? "—"}</span>
            <span>meds ×{r.medication_count} ({r.medication_mg_total}mg)</span>
            {r.label != null && <span>label {r.label}</span>}
          </div>
          <div className="flagged-review__actions">
            <button
              type="button"
              className="btn btn--ghost"
              disabled={busyId === r.id}
              onClick={() => decide(r.id, "reject")}
            >
              Reject
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busyId === r.id}
              onClick={() => decide(r.id, "approve")}
            >
              Approve
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
