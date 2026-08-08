import { useState } from "react";
import { authApi, ApiError } from "../api.js";

const PLACEHOLDER = `[
  {"patient_ref": "P-014", "age_years": 61, "height_cm": 168, "weight_kg": 82,
   "systolic_bp": 138, "diastolic_bp": 88, "heart_rate_bpm": 79,
   "medication_count": 2, "medication_mg_total": 120}
]`;

export default function UploadPanel({ token, onUploaded }) {
  const [text, setText] = useState(PLACEHOLDER);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setResult(null);

    let records;
    try {
      records = JSON.parse(text);
      if (!Array.isArray(records)) throw new Error("Must be a JSON array of records.");
    } catch (err) {
      setError(`Invalid JSON: ${err.message}`);
      return;
    }

    setBusy(true);
    try {
      const res = await authApi.uploadVitals(token, records);
      setResult(res);
      onUploaded?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="upload" onSubmit={handleSubmit}>
      <p className="upload__hint">
        Paste a JSON array of vitals records. Every record passes through
        Module 2's five-stage gate before storage — only <strong>passed</strong>{" "}
        and <strong>flagged</strong> records ever get stored against your
        hospital.
      </p>
      <textarea
        className="upload__textarea mono"
        rows={8}
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
      />
      <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
        {busy ? "Validating…" : "Validate & upload"}
      </button>

      {error && <p className="upload__error">{error}</p>}

      {result && (
        <dl className="upload__result">
          <div>
            <dt>Total</dt>
            <dd>{result.total}</dd>
          </div>
          <div>
            <dt>Passed</dt>
            <dd className="c-teal">{result.passed}</dd>
          </div>
          <div>
            <dt>Flagged</dt>
            <dd className="c-amber">{result.flagged}</dd>
          </div>
          <div>
            <dt>Rejected</dt>
            <dd className="c-coral">{result.rejected}</dd>
          </div>
          <div>
            <dt>Stored</dt>
            <dd>{result.stored}</dd>
          </div>
        </dl>
      )}
    </form>
  );
}
