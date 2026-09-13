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
  unavailable for it.
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
pip install -r ../module6-condition-router/requirements.txt  # shares deps
python demo.py
```

Like Modules 5 and 6, this is a library, not its own HTTP service — it
imports Module 6's `condition_router.py` and Module 5's `fusion.py`
directly via `sys.path` insertion (see the top of `synthesis.py`).

## How it depends on / is depended on by other modules

- **Imports:** Module 6 (`ConditionReport`) and Module 5 (`FusedAssessment`).
- **Depended on by:** nothing downstream yet — this is the end of the
  pipeline; its markdown output is what a dashboard or export feature
  would eventually surface to a clinician.

## Known limitations / current status

- Functionally complete for its scope; the one placeholder worth noting
  is a `pass` in `build_synthesis` where an urgent-review flag from an
  individual finding's metadata (`flag_for_urgent_review`) is read but
  not yet folded into `urgent_review_flags` directly from the finding —
  currently `urgent_review_flags` only comes from the fusion result, if
  one was supplied. Worth closing this gap so a single ungraded finding
  can still surface an urgent flag even with no fusion step involved.
- No automated tests yet — given this module's entire purpose is "never
  imply more certainty than the underlying models actually have,"
  it's a strong candidate for the most thorough test coverage in the
  project (see `DEVELOPMENT_PLAN.md`, section 4.1).
