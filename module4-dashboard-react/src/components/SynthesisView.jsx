import { useState } from "react";
import { synthesisApi, ApiError } from "../api.js";
import ShapChart from "./ShapChart.jsx";

// tabular_vitals.FEATURE_NAMES order — this is the vitals specialist's
// own feature space (module5-modelzoo/models/tabular_vitals.py), not
// Module 1's stored upload schema; the two aren't reconciled yet (see
// docs/DEVELOPMENT_PLAN.md's Sprint A risk register on the vitals
// schema), so a case is entered directly in the model's terms here, same
// as module8-synthesis/demo.py's synthetic cases.
const FIELDS = [
  { key: "age", label: "Age", placeholder: 55, step: 1 },
  { key: "resting_bp", label: "Resting BP (mmHg)", placeholder: 130, step: 1 },
  { key: "cholesterol", label: "Cholesterol (mg/dL)", placeholder: 220, step: 1 },
  { key: "max_heart_rate", label: "Max heart rate (bpm)", placeholder: 150, step: 1 },
  { key: "bmi", label: "BMI", placeholder: 27.5, step: 0.1 },
  { key: "glucose", label: "Glucose (mg/dL)", placeholder: 95, step: 1 },
  { key: "num_medications", label: "Medications, count", placeholder: 2, step: 1 },
  { key: "prior_admissions", label: "Prior admissions", placeholder: 1, step: 1 },
];

function StubBadge() {
  return <span className="synth-badge synth-badge--stub">STUB — placeholder model</span>;
}

function Finding({ finding }) {
  const shap = finding.explanation_details?.shap;
  const kg = finding.explanation_details?.knowledge_graph;
  return (
    <div className={`synth-finding${finding.is_stub ? " synth-finding--stub" : ""}`}>
      <div className="synth-finding__head">
        <div>
          <p className="eyebrow">{finding.specialist_id}</p>
          <p className="synth-finding__impression">
            <code>{finding.model_impression}</code>
            <span className="synth-finding__confidence mono">
              {(finding.confidence * 100).toFixed(1)}% confidence
            </span>
          </p>
          <p className="synth-finding__model mono">{finding.model_name}</p>
        </div>
        {finding.is_stub && <StubBadge />}
      </div>

      {kg && (
        <p className="synth-finding__note">
          <strong>{kg.icd10_code}</strong> — {kg.reason}
          {kg.suggested_next_step && (
            <>
              {" "}
              <em>{kg.suggested_next_step}</em>
            </>
          )}
        </p>
      )}

      {shap && <ShapChart contributions={shap} predictedLabel={finding.model_impression} />}

      {finding.unavailable_explainers.length > 0 && (
        <ul className="synth-finding__unavailable">
          {finding.unavailable_explainers.map((u) => (
            <li key={u}>explainer unavailable — {u}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SynthesisView({ token }) {
  const [values, setValues] = useState(
    Object.fromEntries(FIELDS.map((f) => [f.key, String(f.placeholder)]))
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);

  function setField(key, v) {
    setValues((prev) => ({ ...prev, [key]: v }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    const features = FIELDS.map((f) => Number(values[f.key]));
    if (features.some((v) => Number.isNaN(v))) {
      setError("Every field needs a number.");
      return;
    }

    setBusy(true);
    try {
      const res = await synthesisApi.synthesizeHeartDisease(token, features);
      setReport(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't build a synthesis report.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="synthesis-view">
      <div className="synthesis-view__scroll">
        <section className="synthesis-view__intro glass">
          <p className="eyebrow">Module 8 — Synthesis</p>
          <h2 className="drawer__title">Heart disease review packet</h2>
          <p className="drawer__body">
            Enter a case's vitals to route it through Module 6's condition
            router (the <code>vitals</code> specialist, SHAP + knowledge-graph
            explainers) and Module 8's synthesis layer. This is the one
            condition with a genuinely real, non-stub specialist end to end
            today — every other condition still routes to a labeled stub
            imaging/genomic model.
          </p>

          <form className="synth-form" onSubmit={handleSubmit}>
            <div className="synth-form__grid">
              {FIELDS.map((f) => (
                <label key={f.key} className="field">
                  {f.label}
                  <input
                    type="number"
                    step={f.step}
                    value={values[f.key]}
                    onChange={(e) => setField(f.key, e.target.value)}
                  />
                </label>
              ))}
            </div>
            <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
              {busy ? "Running synthesis…" : "Run synthesis"}
            </button>
            {error && <p className="upload__error">{error}</p>}
          </form>
        </section>

        {report && (
          <section className="synthesis-view__report glass">
            <p className="eyebrow">Review packet — {report.condition_queried}</p>
            <p className="synth-disclaimer">{report.disclaimer}</p>

            {report.urgent_review_flags.length > 0 && (
              <div className="synth-urgent">
                <p className="synth-urgent__title">Urgent review flags</p>
                <ul>
                  {report.urgent_review_flags.map((flag) => (
                    <li key={flag}>{flag}</li>
                  ))}
                </ul>
              </div>
            )}

            {report.overall_risk_score != null && (
              <dl className="drawer__facts">
                <div>
                  <dt>Combined risk score (Module 5 fusion)</dt>
                  <dd>
                    {report.overall_risk_score.toFixed(3)} ({report.overall_risk_level})
                  </dd>
                </div>
              </dl>
            )}

            <p className="eyebrow drawer__section-label">Specialist findings</p>
            <div className="synth-findings">
              {report.findings.map((f) => (
                <Finding key={f.specialist_id} finding={f} />
              ))}
            </div>

            {report.data_completeness.length > 0 && (
              <>
                <p className="eyebrow drawer__section-label">Missing inputs</p>
                <p className="drawer__muted">
                  No data was supplied for the following specialists this
                  condition normally uses — this report is based on partial
                  evidence:
                </p>
                <ul className="drawer__muted">
                  {report.data_completeness.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </>
            )}

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
