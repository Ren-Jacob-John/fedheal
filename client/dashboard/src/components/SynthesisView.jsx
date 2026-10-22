import { useEffect, useState } from "react";
import { authApi, synthesisApi, ApiError } from "../api.js";
import ShapChart from "./ShapChart.jsx";

// The application data flow, end to end:
//   logged-in hospital user -> pick a stored record (Module 1)
//   -> Module 8 reads that validated record with THIS session, maps it to
//      the model's inputs, routes it (Module 6 -> Module 5 specialist) and
//      returns prediction + status + explanation.
// Nothing here collects clinical values by hand, and no service credential
// exists in the browser — only the user's own session is ever sent.

const CONDITIONS = [{ value: "heart_disease", label: "Heart disease (vitals specialist)" }];

function Badge({ tone, children }) {
  return <span className={`synth-badge synth-badge--${tone}`}>{children}</span>;
}

function ModelStatus({ specialist, model }) {
  return (
    <div className="synth-status">
      <div className="synth-status__badges">
        {specialist.is_stub ? (
          <Badge tone="stub">STUB — placeholder, not a trained model</Badge>
        ) : (
          <Badge tone="ok">Real model class</Badge>
        )}
        {specialist.is_fallback && <Badge tone="stub">FALLBACK model</Badge>}
        <Badge tone="info">training: {specialist.training_status}</Badge>
        {model && !model.federated && <Badge tone="stub">not federated</Badge>}
      </div>
      <dl className="drawer__facts">
        <div><dt>Specialist</dt><dd>{specialist.specialist_id}</dd></div>
        <div><dt>Model</dt><dd className="mono">{specialist.model_name}</dd></div>
        <div><dt>Version</dt><dd className="mono">{specialist.model_version}</dd></div>
        {model && <div><dt>Source</dt><dd>{model.source}</dd></div>}
      </dl>
      {model?.description && <p className="drawer__muted">{model.description}</p>}
    </div>
  );
}

function Explanation({ explanation, positiveLabel }) {
  if (explanation.status !== "available") {
    return (
      <div className="synth-warning">
        <strong>Explanation unavailable.</strong> {explanation.reason}
        <br />
        No feature attribution is shown, because none was produced.
      </div>
    );
  }
  const contributions = Object.fromEntries(
    explanation.contributions.map((c) => [c.feature, c.contribution])
  );
  return <ShapChart contributions={contributions} positiveLabel={positiveLabel} />;
}

function Finding({ finding }) {
  const kg = finding.explanation_details?.knowledge_graph;
  return (
    <div className={`synth-finding${finding.is_stub ? " synth-finding--stub" : ""}`}>
      <p className="eyebrow">{finding.specialist_id}</p>
      <p className="synth-finding__impression">
        <code>{finding.model_impression}</code>
        <span className="synth-finding__confidence mono">
          {(finding.confidence * 100).toFixed(1)}% confidence
        </span>
      </p>
      {kg && (
        <p className="synth-finding__note">
          <strong>Reference note (static lookup on the label — not derived from this record):</strong>{" "}
          {kg.icd10_code} — {kg.reason}
        </p>
      )}
    </div>
  );
}

// Maps a structured server error to a clear on-screen message.
function ErrorPanel({ error }) {
  if (error.code === "incomplete_data") {
    return (
      <div className="synth-warning synth-warning--incomplete">
        <strong>Incomplete data — no result was produced.</strong>
        <p>
          This record is missing inputs the model needs. Nothing was estimated
          or filled in:
        </p>
        <ul>{error.detail.missing_features.map((f) => <li key={f}><code>{f}</code></li>)}</ul>
      </div>
    );
  }
  if (error.code === "record_not_validated") {
    return <div className="synth-warning">Only records that passed validation can be synthesized. Review flagged records first.</div>;
  }
  if (error.code === "specialist_unavailable") {
    return (
      <div className="synth-warning">
        <strong>Specialist unavailable.</strong> {error.message}
      </div>
    );
  }
  return <p className="upload__error">{error.message}</p>;
}

export default function SynthesisView({ token }) {
  const [records, setRecords] = useState(null);
  const [listError, setListError] = useState(null);
  const [recordId, setRecordId] = useState("");
  const [condition, setCondition] = useState(CONDITIONS[0].value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    authApi
      .listVitals(token)
      .then((rows) => !cancelled && setRecords(rows))
      .catch((err) => !cancelled && setListError(err instanceof ApiError ? err.message : "Couldn't load records."));
    return () => { cancelled = true; };
  }, [token]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!recordId) return;
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      setResult(await synthesisApi.synthesizeRecord(token, recordId, condition));
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("Couldn't build a synthesis report.", 0));
    } finally {
      setBusy(false);
    }
  }

  const report = result?.synthesis;

  return (
    <div className="synthesis-view">
      <div className="synthesis-view__scroll">
        <section className="synthesis-view__intro glass">
          <p className="eyebrow">Module 8 — Synthesis</p>
          <h2 className="drawer__title">Review packet for a stored record</h2>
          <p className="drawer__body">
            Choose one of your hospital's validated vitals records. The record is
            read from Module 1, mapped to the model's inputs, routed to the
            specialist for the condition, and explained. Only records that
            passed validation can be used.
          </p>

          {listError && <p className="upload__error">{listError}</p>}

          <form className="synth-form" onSubmit={handleSubmit}>
            <label className="field">
              Condition
              <select value={condition} onChange={(e) => setCondition(e.target.value)}>
                {CONDITIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </label>
            <label className="field">
              Record
              <select value={recordId} onChange={(e) => setRecordId(e.target.value)}>
                <option value="">{records ? "Select a record…" : "Loading records…"}</option>
                {(records || []).map((r) => (
                  <option key={r.id} value={r.id} disabled={r.validation_status !== "passed"}>
                    {r.patient_ref} — {r.validation_status}
                    {r.validation_status !== "passed" ? " (awaiting review)" : ""}
                  </option>
                ))}
              </select>
            </label>
            {records && records.length === 0 && (
              <p className="drawer__muted">No stored records yet — upload vitals first.</p>
            )}
            <button type="submit" className="btn btn--primary btn--block" disabled={busy || !recordId}>
              {busy ? "Running synthesis…" : "Run synthesis"}
            </button>
            {error && <ErrorPanel error={error} />}
          </form>
        </section>

        {result && (
          <section className="synthesis-view__report glass">
            <p className="eyebrow">Selected record</p>
            <dl className="drawer__facts">
              <div><dt>Patient ref</dt><dd className="mono">{result.record.patient_ref}</dd></div>
              <div><dt>Validation</dt><dd>{result.record.validation_status}</dd></div>
              <div><dt>Condition</dt><dd>{result.condition}</dd></div>
            </dl>

            {result.warnings.length > 0 && (
              <div className="synth-warning">
                {result.warnings.map((w) => <p key={w.code}>⚠️ {w.message}</p>)}
              </div>
            )}

            <p className="eyebrow drawer__section-label">Model</p>
            <ModelStatus specialist={result.specialist} model={result.model} />

            <p className="eyebrow drawer__section-label">Result</p>
            <p className="synth-finding__impression">
              <code>{result.prediction.label}</code>
              <span className="synth-finding__confidence mono">
                {(result.prediction.confidence * 100).toFixed(1)}% model confidence
              </span>
            </p>

            <p className="eyebrow drawer__section-label">
              Explanation — {result.explanation.status}
            </p>
            <Explanation explanation={result.explanation} positiveLabel="high_risk" />

            <p className="eyebrow drawer__section-label">Inputs used (from the stored record)</p>
            <table className="synth-inputs">
              <tbody>
                {result.inputs.map((i) => (
                  <tr key={i.feature}>
                    <td className="mono">{i.feature}</td>
                    <td>{i.value}</td>
                    <td className="drawer__muted">{i.unit}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p className="synth-disclaimer">{report.disclaimer}</p>
            {report.urgent_review_flags.length > 0 && (
              <div className="synth-urgent">
                <p className="synth-urgent__title">Urgent review flags</p>
                <ul>{report.urgent_review_flags.map((f) => <li key={f}>{f}</li>)}</ul>
              </div>
            )}
            <div className="synth-findings">
              {report.findings.map((f) => <Finding key={f.specialist_id} finding={f} />)}
            </div>
            <p className="synth-review-line">
              Requires clinician review before any action:{" "}
              <strong>{report.requires_clinician_review ? "yes" : "no"}</strong>
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
