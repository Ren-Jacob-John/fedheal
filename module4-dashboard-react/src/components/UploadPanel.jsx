import { useState } from "react";
import { authApi, ApiError } from "../api.js";

const PLACEHOLDER = `[
  {"patient_ref": "P-014", "age_years": 61, "height_cm": 168, "weight_kg": 82,
   "systolic_bp": 138, "diastolic_bp": 88, "heart_rate_bpm": 79,
   "medication_count": 2, "medication_mg_total": 120,
   "label": 0}
]`;

export default function UploadPanel({ token, onUploaded }) {
  // "json" — hand-typed/pasted records, mainly for testing.
  // "csv" — what most hospitals will actually use, exported straight from
  // their own EHR or spreadsheet system.
  const [mode, setMode] = useState("json");
  const [text, setText] = useState(PLACEHOLDER);
  const [csvFile, setCsvFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setResult(null);

    setBusy(true);
    try {
      let res;
      if (mode === "csv") {
        if (!csvFile) {
          setError("Choose a .csv file first.");
          setBusy(false);
          return;
        }
        res = await authApi.uploadVitalsCsv(token, csvFile);
      } else {
        let records;
        try {
          records = JSON.parse(text);
          if (!Array.isArray(records)) throw new Error("Must be a JSON array of records.");
        } catch (err) {
          setError(`Invalid JSON: ${err.message}`);
          setBusy(false);
          return;
        }
        res = await authApi.uploadVitals(token, records);
      }
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
      <div className="upload__tabs" role="tablist" aria-label="Upload format">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "json"}
          className={`upload__tab${mode === "json" ? " upload__tab--active" : ""}`}
          onClick={() => setMode("json")}
        >
          Paste JSON
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "csv"}
          className={`upload__tab${mode === "csv" ? " upload__tab--active" : ""}`}
          onClick={() => setMode("csv")}
        >
          Upload CSV
        </button>
      </div>

      <p className="upload__hint">
        Every record passes through Module 2's five-stage gate before
        storage — only <strong>passed</strong> and <strong>flagged</strong>{" "}
        records ever get stored against your hospital. Include a real{" "}
        <code>label</code> column (0 = no adverse outcome, 1 = adverse
        outcome) whenever your own records have one — federated accuracy
        is only as real as the labels behind it.
      </p>

      {mode === "csv" ? (
        <>
          <input
            type="file"
            accept=".csv,text/csv"
            className="upload__file"
            onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
          />
          <p className="upload__hint upload__hint--small">
            Expected columns: patient_ref, age_years, height_cm, weight_kg,
            systolic_bp, diastolic_bp, heart_rate_bpm, medication_count,
            medication_mg_total, label (optional). Missing optional columns
            are fine.
          </p>
        </>
      ) : (
        <textarea
          className="upload__textarea mono"
          rows={8}
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
        />
      )}

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
