import { useCallback, useEffect, useState } from "react";
import { authApi, synthesisApi, ApiError } from "../api.js";
import ShapChart from "./ShapChart.jsx";

// Doctor workflow: Cases -> create -> vitals -> history -> AI analysis -> report -> clinician review.
// Hospital admins see the Doctors panel instead (they manage people, not patients).
// Hospital scoping is enforced by the services from the session; nothing here sends a hospital id.

const MODEL_TONE = { VALIDATED: "ok", DEPLOYED: "ok", FALLBACK: "stub", STUB: "stub", UNAVAILABLE: "stub", EXPERIMENTAL: "info" };
const VITAL_FIELDS = [
  ["age_years", "Age (years)"], ["height_cm", "Height (cm)"], ["weight_kg", "Weight (kg)"],
  ["systolic_bp", "Systolic BP"], ["diastolic_bp", "Diastolic BP"], ["heart_rate_bpm", "Heart rate (bpm)"],
  ["medication_count", "Medication count"], ["medication_mg_total", "Medication total (mg)"],
];
const HISTORY_LISTS = [
  ["conditions", "Chronic conditions"], ["previous_diagnoses", "Previous diagnoses"], ["surgeries", "Surgeries / procedures"],
  ["allergies", "Allergies"], ["medications", "Current medications"], ["family_history", "Relevant family history"],
  ["previous_admissions", "Previous admissions"],
];

const splitList = (t) => t.split("\n").map((x) => x.trim()).filter(Boolean);

function explainError(e) {
  if (e instanceof ApiError) {
    if (e.status === 401) return "Your session has expired. Please log in again.";
    if (e.status === 403) return "You are not permitted to access this resource.";
    if (e.code === "INSUFFICIENT_DATA") return `Insufficient data: ${e.message}`;
    if (e.code === "MODEL_UNAVAILABLE") return `Model unavailable: ${e.message}`;
    return e.message;
  }
  return "Something went wrong.";
}

function Msg({ error, ok }) {
  return (
    <>
      {error && <p className="cases__error" role="alert">{error}</p>}
      {ok && <p className="cases__ok" role="status">{ok}</p>}
    </>
  );
}

function DoctorsPanel({ token }) {
  const [doctors, setDoctors] = useState(null);
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);
  const load = useCallback(() => authApi.listDoctors(token).then(setDoctors).catch((e) => setError(explainError(e))), [token]);
  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault();
    setError(null); setOk(null);
    try {
      await authApi.createDoctor(token, form);
      setForm({ full_name: "", email: "", password: "" });
      setOk("Doctor created. They belong to your hospital only.");
      load();
    } catch (err) { setError(explainError(err)); }
  }
  async function toggle(d) {
    setError(null);
    try { await authApi.setDoctorActive(token, d.id, !d.is_active); load(); } catch (err) { setError(explainError(err)); }
  }
  return (
    <section className="cases glass" aria-labelledby="doctors-h">
      <h2 id="doctors-h">Doctors at your hospital</h2>
      <form className="cases__form" onSubmit={create}>
        <div className="cases__grid">
          <label>Full name<input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
          <label>Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Initial password (min 10)<input required type="password" minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        </div>
        <button type="submit">Create doctor</button>
      </form>
      <Msg error={error} ok={ok} />
      {doctors === null ? <p>Loading…</p> : doctors.length === 0 ? <p className="cases__empty">No doctors yet.</p> : (
        <ul className="cases__list">
          {doctors.map((d) => (
            <li key={d.id}>
              {d.full_name || d.email} — {d.email} — {d.is_active ? "active" : "disabled"}{" "}
              <button onClick={() => toggle(d)}>{d.is_active ? "Disable" : "Enable"}</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function VitalsForm({ token, caseId, onSaved }) {
  const [v, setV] = useState({});
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);
  async function submit(e) {
    e.preventDefault();
    setError(null); setOk(null);
    const record = {};
    for (const [k] of VITAL_FIELDS) if (v[k] !== undefined && v[k] !== "") record[k] = Number(v[k]);
    try {
      const r = await authApi.addCaseVitals(token, caseId, record);
      setOk(r.validation_status === "flagged" ? "Saved, but flagged for review (not used for analysis until approved)." : "Vitals validated and saved.");
      onSaved();
    } catch (err) {
      const reasons = err.detail?.reasons;
      setError(reasons?.length ? `Rejected: ${reasons.join("; ")}` : explainError(err));
    }
  }
  return (
    <form className="cases__form" onSubmit={submit} aria-label="Vitals">
      <h3>Vitals</h3>
      <div className="cases__grid">
        {VITAL_FIELDS.map(([k, label]) => (
          <label key={k}>{label}<input type="number" step="any" value={v[k] ?? ""} onChange={(e) => setV({ ...v, [k]: e.target.value })} /></label>
        ))}
      </div>
      <p className="cases__empty">Leave a field blank if it was not measured; nothing is filled in for you.</p>
      <button type="submit">Validate &amp; save vitals</button>
      <Msg error={error} ok={ok} />
    </form>
  );
}

function HistoryForm({ token, caseId, onSaved }) {
  const [h, setH] = useState({});
  const [notes, setNotes] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);
  useEffect(() => {
    authApi.getHistory(token, caseId).then((x) => {
      setH(Object.fromEntries(HISTORY_LISTS.map(([k]) => [k, (x[k] || []).join("\n")])));
      setNotes(x.notes || "");
    }).catch(() => {}).finally(() => setLoaded(true));
  }, [token, caseId]);
  async function submit(e) {
    e.preventDefault();
    setError(null); setOk(null);
    const body = { notes: notes || null, symptoms: [] };
    for (const [k] of HISTORY_LISTS) body[k] = splitList(h[k] || "");
    try { await authApi.putHistory(token, caseId, body); setOk("Medical history saved."); onSaved(); }
    catch (err) { setError(explainError(err)); }
  }
  if (!loaded) return <p>Loading history…</p>;
  return (
    <form className="cases__form" onSubmit={submit} aria-label="Medical history">
      <h3>Medical history</h3>
      <p className="cases__empty">One item per line. Only record what the clinical question needs.</p>
      <div className="cases__grid">
        {HISTORY_LISTS.map(([k, label]) => (
          <label key={k}>{label}<textarea rows={3} value={h[k] ?? ""} onChange={(e) => setH({ ...h, [k]: e.target.value })} /></label>
        ))}
      </div>
      <label>Notes (max 2000 characters)<textarea rows={3} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      <button type="submit">Save medical history</button>
      <Msg error={error} ok={ok} />
    </form>
  );
}

function Report({ report }) {
  const contributions = report.explanation?.status === "available"
    ? Object.fromEntries(report.explanation.contributions.map((c) => [c.feature, c.contribution])) : null;
  return (
    <article aria-label="AI report" className="cases__form">
      <p className="cases__banner" role="note">{report.safety.banner} · {report.safety.footer}</p>
      <h3>Available data</h3>
      <ul>
        {report.available_modalities.map((m) => <li key={m}>✓ {m.replace("_", " ")}</li>)}
        {report.missing_modalities.map((m) => <li key={m}>✗ {m.replace("_", " ")} — {report.unsupported_modalities?.[m] || "not available"}</li>)}
      </ul>
      <p>{report.basis_statement}</p>
      <h3>Model</h3>
      <p>
        <span className={`synth-badge synth-badge--${MODEL_TONE[report.model.status] || "info"}`}>{report.model.status}</span>{" "}
        {report.model.name} · {report.model.version}
        {report.stub_or_fallback && <strong> — fallback/demo model: not a validated clinical result.</strong>}
      </p>
      <h3>Model output</h3>
      {report.findings.map((f, i) => <p key={i}>{f.label} <em>({f.note})</em></p>)}
      <p>Model score: {report.confidence != null ? report.confidence.toFixed(2) : "—"} — {report.uncertainty.note}</p>
      <h3>Explanation</h3>
      {contributions ? <ShapChart contributions={contributions} positiveLabel="toward model's positive class" />
        : <p className="synth-warning">Explanation unavailable: {report.explanation?.reason}</p>}
      <p className="cases__empty">{report.explanation.reliability}</p>
      {report.data_quality_warnings.length > 0 && (
        <ul className="synth-warning">{report.data_quality_warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul>
      )}
      {report.warnings.length > 0 && (
        <ul className="synth-warning">{report.warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul>
      )}
    </article>
  );
}

function CaseDetail({ token, caseItem, onChanged }) {
  const [report, setReport] = useState(null);
  const [state, setState] = useState({ busy: false, error: null });
  const [decision, setDecision] = useState("ACCEPTED");
  const [note, setNote] = useState("");
  const [reviewMsg, setReviewMsg] = useState({ error: null, ok: null });
  useEffect(() => { setReport(null); setState({ busy: false, error: null }); setReviewMsg({ error: null, ok: null }); }, [caseItem.id]);

  async function analyze() {
    setState({ busy: true, error: null }); setReport(null);
    try { setReport(await synthesisApi.analyzeCase(token, caseItem.id)); setState({ busy: false, error: null }); }
    catch (e) { setState({ busy: false, error: explainError(e) }); }
  }
  async function review(e) {
    e.preventDefault();
    setReviewMsg({ error: null, ok: null });
    try { await authApi.reviewCase(token, caseItem.id, decision, note); setReviewMsg({ error: null, ok: "Review recorded." }); onChanged(); }
    catch (err) { setReviewMsg({ error: explainError(err), ok: null }); }
  }
  return (
    <div className="cases__panel glass">
      <h2>{caseItem.patient_ref} <small>({caseItem.status})</small></h2>
      <p>Admission: {caseItem.admission_reason} · Condition: {caseItem.current_condition || "not set"}</p>
      <VitalsForm token={token} caseId={caseItem.id} onSaved={() => setReport(null)} />
      <HistoryForm token={token} caseId={caseItem.id} onSaved={() => setReport(null)} />
      <h3>AI analysis</h3>
      <button onClick={analyze} disabled={state.busy}>{state.busy ? "Analysing…" : "Run AI analysis"}</button>
      <Msg error={state.error} />
      {report && <Report report={report} />}
      <form className="cases__form" onSubmit={review} aria-label="Clinician review">
        <h3>Clinician review</h3>
        <label>Decision
          <select value={decision} onChange={(e) => setDecision(e.target.value)}>
            <option value="ACCEPTED">Accepted</option><option value="OVERRIDDEN">Overridden</option>
            <option value="NEEDS_MORE_DATA">Needs more data</option>
          </select>
        </label>
        <label>Note<textarea rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <button type="submit">Submit review</button>
        <Msg error={reviewMsg.error} ok={reviewMsg.ok} />
      </form>
    </div>
  );
}

export default function CasesView({ token, me }) {
  const [cases, setCases] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [form, setForm] = useState({ patient_ref: "", admission_reason: "", current_condition: "heart_disease", symptoms: "" });
  const [error, setError] = useState(null);

  const load = useCallback(() => authApi.listCases(token).then(setCases).catch((e) => { setCases([]); setError(explainError(e)); }), [token]);
  useEffect(() => { if (me.role === "clinician") load(); }, [load, me.role]);

  if (me.role === "hospital_admin") return <DoctorsPanel token={token} />;
  if (me.role !== "clinician") return <section className="cases glass"><p>Patient cases are available to clinicians of the owning hospital only.</p></section>;

  async function create(e) {
    e.preventDefault();
    setError(null);
    try {
      const c = await authApi.createCase(token, {
        patient_ref: form.patient_ref, admission_reason: form.admission_reason,
        current_condition: form.current_condition || null, presenting_symptoms: splitList(form.symptoms),
      });
      setForm({ ...form, patient_ref: "", admission_reason: "", symptoms: "" });
      await load(); setSelectedId(c.id);
    } catch (err) { setError(explainError(err)); }
  }
  const selected = cases?.find((c) => c.id === selectedId);
  return (
    <section className="cases" aria-label="Patient cases">
      <div className="cases__layout">
        <div className="cases__panel glass">
          <h2>Patient cases</h2>
          <form className="cases__form" onSubmit={create} aria-label="Create case">
            <label>Patient reference (synthetic id)<input required pattern="[A-Za-z0-9._-]+" placeholder="PAT-DEMO-001" value={form.patient_ref} onChange={(e) => setForm({ ...form, patient_ref: e.target.value })} /></label>
            <label>Admission reason<input required maxLength={500} value={form.admission_reason} onChange={(e) => setForm({ ...form, admission_reason: e.target.value })} /></label>
            <label>Condition<select value={form.current_condition} onChange={(e) => setForm({ ...form, current_condition: e.target.value })}><option value="heart_disease">Heart disease</option></select></label>
            <label>Presenting symptoms (one per line)<textarea rows={2} value={form.symptoms} onChange={(e) => setForm({ ...form, symptoms: e.target.value })} /></label>
            <button type="submit">Create case</button>
          </form>
          <Msg error={error} />
          {cases === null ? <p>Loading…</p> : cases.length === 0 ? <p className="cases__empty">No cases yet. Create the first one above.</p> : (
            <ul className="cases__list">
              {cases.map((c) => (
                <li key={c.id}><button aria-current={c.id === selectedId} onClick={() => setSelectedId(c.id)}>{c.patient_ref} — {c.status}</button></li>
              ))}
            </ul>
          )}
        </div>
        {selected ? <CaseDetail token={token} caseItem={selected} onChanged={load} />
          : <div className="cases__panel glass"><p className="cases__empty">Select or create a case to enter data and run an analysis.</p></div>}
      </div>
    </section>
  );
}
