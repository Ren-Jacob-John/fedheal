# Module 8 — Synthesis / Review-Packet Layer

## What this module is for

The last step of the diagnostic chain: it takes Module 6's raw
`ConditionReport` (specialist predictions + explanations) and optionally
Module 5's `FusedAssessment`, and aggregates them into one structured
`SynthesisReport` for a clinician to actually read. It deliberately does
**not** emit a diagnosis, a treatment plan, or a cross-modality confidence
score it can't justify. Every report hardcodes
`requires_clinician_review = True`, and every number in it traces back to
a real specialist's own confidence — this module never invents a number.

## How it works internally

**Files:**
- `synthesis.py` — the entire module.
- `demo.py` — a runnable example producing a full report from a mock
  condition query.

**Key types:**
- `FindingSummary` — one specialist's contribution: `specialist_id`,
  `model_name`, `model_impression` (deliberately named to avoid reading
  as a verdict — not called `label` or `diagnosis`), `confidence`,
  `is_stub`, plus its explanation summaries and any explainers that were
  unavailable for it. `explanation_details` (new in Sprint B) carries
  each real explainer's raw structured output (e.g. SHAP's
  `{feature_name: contribution}` dict) keyed by method name —
  `to_markdown()` never reads it, it exists for `to_dict()` /
  the dashboard's SHAP chart, which needs actual numbers, not just the
  one-line "top contributing factors" sentence built from them.
- `SynthesisReport` — the full packet: the condition queried, every
  `FindingSummary`, which specialists the condition *defines* but had no
  data supplied for this run (`data_completeness`), whether **any** input
  anywhere in the chain was a stub (`used_any_stub_models` — this
  propagates from both individual findings and, if supplied, Module 5's
  fusion result), an optional overall risk score/level **only if** Module
  5's fusion layer supplied one, any urgent-review flags, the always-true
  `requires_clinician_review` flag, and the fixed `DISCLAIMER` text.
- `DISCLAIMER` — stated plainly: this is computational decision-support
  output only, some findings may come from placeholder stub models
  (clearly marked), nothing here is a diagnosis or treatment
  recommendation, and it requires review, confirmation, and clinical
  judgment by a licensed clinician before informing any care decision.

**`build_synthesis(condition_report, all_specialist_ids_for_condition,
fused=None)`** is the module's one real function:
1. Compares which specialist IDs the condition's `ConditionSpec` (Module
   6) *defines* against which ones actually got a finding in this run —
   anything missing goes into `data_completeness`, so a clinician reading
   the report knows the picture is incomplete rather than assuming
   silence means "normal."
2. For each finding, walks its explanations and separates real ones
   (`explanation_summaries`) from unavailable/stub ones
   (`unavailable_explainers`) — so the report is explicit about what
   couldn't be explained, not just what could.
3. Rolls up `used_any_stub_models` across every finding **and** the
   fusion result, if supplied — a single `True` anywhere in the chain
   makes the whole report's flag `True`.
4. `SynthesisReport.to_markdown()` renders the whole thing as a
   clinician-readable markdown document: disclaimer up top, risk
   score/urgent flags if present, one bullet per specialist finding (with
   a visible `⚠️ STUB` marker on any placeholder result), missing-input
   section if the picture is incomplete, and the review-required line at
   the end.

## How to run it

```bash
cd module8-synthesis
pip install -r requirements.txt
python demo.py                              # library demo, no server
uvicorn main:app --reload --port 8006       # HTTP service (Sprint B)
```

Like Modules 5 and 6, `synthesis.py` itself is a plain library — it
imports Module 6's `condition_router.py` and Module 5's `fusion.py`
directly via `sys.path` insertion (see the top of `synthesis.py`).
`main.py` is new in Sprint B: a thin FastAPI wrapper around it, so the
dashboard has an HTTP endpoint to call instead of embedding Python
imports across services. See "HTTP surface" below.

## How it depends on / is depended on by other modules

- **Imports:** Module 6 (`ConditionReport`, `ConditionRouter`,
  `resolve_condition`) and Module 5 (`FusedAssessment`).
- **Depended on by:** Module 4 (dashboard) — its Synthesis view calls
  `POST /synthesize/record` to render a `SynthesisReport` in the
  browser (Sprint B; see `module4-dashboard-react/module4-dashboard-react.md`).

## HTTP surface (new in Sprint B)

`main.py` is a thin FastAPI wrapper — this module is still "the entire
job is `build_synthesis()`," the service just gives the dashboard
(Module 4) something to call instead of importing Python directly.
Deliberately scoped to the one condition/specialist pairing that's
genuinely real end-to-end today (per `docs/DEVELOPMENT_PLAN.md`'s own
instruction to scope the first version to "the minimum that makes the
vitals→SHAP→synthesis story demoable"):

- `POST /synthesize/record` — body `{"record_id": "...", "condition": "heart_disease"}`.
  Reads the stored record from Module 1 **as the calling user** (their own
  token is forwarded; this service holds no credential for it), requires
  `validation_status == "passed"`, maps it to the model's inputs through
  `feature_mapper.py`, routes it through Module 6 (specialist selection,
  required-input validation, SHAP) and returns `record`, `inputs`,
  `specialist`/`model` status (`is_stub`, `is_fallback`, `training_status`,
  `model_version`), `prediction`, `explanation` (`available`|`unavailable`),
  `warnings`, and the `synthesis` report. Every non-success outcome is an
  explicit structured error (`incomplete_data`, `record_not_validated`,
  `unknown_condition`, `unsupported_input`, `specialist_unavailable`, ...) —
  see **`docs/DATA_CONTRACT.md`** for the table and the field mapping.
- `GET /models/status?condition=...` — what would run for a condition and
  how real each piece is (stub / fallback / training status).
- `GET /health` — `{"status": "ok", "service": "module8-synthesis"}`.
- `POST /synthesize/heart_disease` — **retired (410)**. It took 8 hand-typed
  numbers in a legacy feature space that matched no stored data.

Requires a valid FedHeal session (any logged-in hospital user, not just
super_admin) via the same JWT/cookie Module 1 issues; see `auth.py`.

**The model is a labelled demo fallback, not a federated model.** Module 3
does not export a global model, so there is nothing to load. `model_provider.py`
fits the vitals specialist on the vendored public UCI Cleveland data (in
Module 1's schema; only 3 of the 8 features carry real values there) and
reports it as `training_status="demo_fit"`, `is_fallback=true`,
`federated=false`. It is on by default in development/test and must be
enabled explicitly (`FEDHEAL_ALLOW_DEMO_MODEL=true`) elsewhere; when off the
endpoint answers 503. (The earlier fit on `numpy.random.normal` noise at
import is gone.) Integrating Module 3 later is a change confined to
`model_provider.py`.

Only conditions whose specialists are all `vitals` can be driven from a
Module 1 record (`heart_disease`); the rest need imaging/genomic/CBC inputs
a vitals record does not contain and answer `unsupported_input`, with the
stub/fallback status of their specialists.

## Known limitations / current status

- ~~A `pass` in `build_synthesis` where an urgent-review flag from an
  individual finding's metadata (`flag_for_urgent_review`) was read but
  not folded into `urgent_review_flags`~~ — **closed in Sprint B**: a
  finding's own urgent flag now appends directly to
  `urgent_review_flags`, independent of whether a fusion step ran.
- No automated tests yet — given this module's entire purpose is "never
  imply more certainty than the underlying models actually have,"
  it's a strong candidate for the most thorough test coverage in the
  project (see `DEVELOPMENT_PLAN.md`, section 4.1).
