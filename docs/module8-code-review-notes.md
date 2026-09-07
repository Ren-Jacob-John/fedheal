# Code review notes — modules 1–7, checked against the 16-week plan

Scope: read every module's core files, ran Module 5's, Module 6's, and the
new Module 8's demos end-to-end with real (not stub) dependencies installed
(`xgboost`, `lightgbm`, `shap`) to confirm the pipeline actually executes,
not just reads plausibly.

## Fixed: fusion severity table didn't cover Module 6 modalities

`module5-modelzoo/fusion.py`'s `SEVERITY_WEIGHTS` dict only had entries for
`vitals`, `chest_xray`, `retina`, `skin`, `ct_scan` — the modality names
Module 5's own registry uses. Module 6's condition-specific specialists
report different modality strings (`genomic`, `histopathology`, `cbc` — see
`module6-condition-router/models/*.py`), none of which appeared in the
table.

Effect (as originally found): running `FusionLayer.combine()` on Module 6
findings (as Module 8's demo does for breast cancer / leukemia) silently
fell back to the "unknown label" neutral weight of `0.5` for *every*
finding, so the fused `overall_risk_score` collapsed toward 0.5 regardless
of how severe the actual findings were — confirmed by running the demo: a
`brca_high_risk` (0.71 confidence) + a stub `malignant` (0.66 confidence)
finding produced `overall_risk_score = 0.500`, which was uninformative.

**Fix applied:** added entries for all label values Module 6's specialists
actually emit (`histopathology`: benign/malignant; `genomic`: BRCA and
leukemia-subtype labels; `cbc`: leukemia-suspected/not) — see
`fusion.py`'s updated comment block for the reasoning and the exact
source (`condition_registry_builder.py`) the label strings were taken
from. Re-ran Module 8's demo after the fix: the same breast-cancer case
that previously fused to `0.500` now produces a materially different
score reflecting the actual finding severities (see "Verified after fix"
below).

These are still placeholder severities in the same spirit as the
pre-existing table (`fusion.py`'s own comment: "Clinically reviewed values
would replace these") — a clinician still needs to review and adjust the
actual numbers before this feeds any real decision. What changed is that
every Module 6 label now has *some* explicit, reviewable weight instead of
silently defaulting to neutral.

This isn't a crash — `.get((modality, label), 0.5)` degrades quietly —
which is exactly the "confident, meaningless answer" failure mode the
codebase's own docstrings warn about elsewhere (`UnroutableCaseError`,
`UnknownConditionError`). Worth considering for a future pass: having
`FusionLayer` warn (not necessarily raise) when it hits a genuinely unknown
`(modality, label)` pair, so a *new* specialist added later doesn't
silently repeat this same gap.

### Verified after fix

Re-ran `module8-synthesis/demo.py`:

```
# Review Packet — breast_cancer
Combined risk score (Module 5 fusion): 0.821 (high)
- histopathology_breast_cancer: malignant — confidence 0.51  [STUB]
- genomic_breast_cancer: brca_high_risk — confidence 0.71
```

versus `0.500 (moderate)` before the fix — confirms the fix changes the
fused score in the expected direction (toward "high," matching two
concerning findings) without touching Module 6's routing or Module 8's
synthesis logic at all. Note the stub's confidence value (0.51 here vs.
0.66 in the earlier run) isn't seeded/deterministic — `StubSpecialistModel`
draws a random confidence per run — so exact numbers will vary run to run;
what's stable is the direction of the fix (Module 6 findings now pull the
fused score toward their actual severity instead of sitting at neutral).

## Consistent, deliberate design pattern (not a bug — worth naming)

Every module that could take a shortcut declines to:
- `MetadataRouter` requires an explicit `modality` field rather than
  guessing from raw pixels (`router.py`'s docstring explains why).
- `ConditionRouter.route()` raises `UnknownConditionError` instead of
  falling back to a default specialist.
- `PredictionResult.is_stub` and `Explanation.is_stub` are threaded through
  every layer so a placeholder never gets silently presented as a real
  model's output.
- `module1-auth`'s `/vitals/export` is service-key-gated and only returns
  records that already passed Module 2's validation — Module 3 can't
  accidentally train on raw unvalidated uploads.

Module 8 (added this session) follows the same pattern: `ConditionRouter`
already refuses to guess a condition; Module 8 refuses to guess a diagnosis
or treatment on top of the condition's findings.

## Matches the plan's own "known gaps" section — nothing new to add there

`docs/16-week-development-plan.md`'s "Known gaps this plan is honest about"
already covers the imaging stubs, synthetic genomic panels, and placeholder
FL labels. Spot-checking confirms these are accurately described — e.g.
`module5-modelzoo/registry.py` really does auto-substitute
`StubSpecialistModel` when `torch`/`torchvision` aren't importable, and
`build_registry()`'s status rows correctly report `real: False` for those.

## Dev-only items already flagged in-repo (confirmed present, not new)

- `module1-auth/main.py`: CORS wide open (`allow_origins=["*"]`), with a
  comment marking it dev-only — matches week 13's "CORS lockdown" plan item.
- Token storage / `X-Service-Key` sharing — also week 13 plan items,
  confirmed still in place, not yet started (plan marks week 13 "⬜
  Planned").

## Smaller observations

- `module5-modelzoo/fusion.py`'s docstring already anticipates this
  limitation in spirit ("Clinically reviewed values would replace these —
  these are illustrative placeholders"), so the fix belongs with whoever
  owns clinical input on severity, not as an unreviewed engineering patch.
- `condition_router.py`'s per-explainer `try/except (ValueError, KeyError)`
  is scoped narrowly enough that a genuinely broken explainer (e.g. a typo
  causing an `AttributeError`) would still propagate and crash the whole
  report rather than being recorded as a skipped explainer — worth
  widening if that's not intentional, but left alone here since narrowing
  the catch further wasn't asked for and changing exception-handling scope
  without a clinician/owner's sign-off on the tradeoff felt out of scope
  for this pass.

## Fixed: `genomic_variant` missing from fusion + ontology tables

After the Evo 2 / `genomic_variant` track landed in Module 5/6, the same
gap repeated: `fusion.py`'s `SEVERITY_WEIGHTS` and
`knowledge_graph_reasoner.py`'s `ONTOLOGY_LOOKUP` had entries for
`genomic` (expression panel) but not for `genomic_variant` (variant-call
sequence data). Breast-cancer and leukemia demos that included Evo 2
findings fused those at the neutral 0.5 weight and returned stub ontology
explanations.

**Fix applied:** added placeholder entries for all three Evo 2 labels
(`likely_pathogenic`, `uncertain_significance`, `likely_benign`) in both
tables — same spirit as the Module 6 modality fix above, still needing
clinical review before production use.

## Remaining gaps (documented, not yet implemented)

- **Module 8 → Module 4 wiring** — `module8-synthesis/` runs standalone
  via `demo.py`; the React dashboard does not yet render a
  `SynthesisReport` (planned week-14 follow-up).
- **Module 8 persistence** — no DB table yet for storing a synthesis
  report with clinician sign-off/override (Module 7 is the natural home).
- **Week 14 frontend items still open** — CSV vitals upload, SHAP/Grad-CAM
  chart rendering in the dashboard UI.
- **`FusionLayer` unknown-pair warning** — still worth adding a log/warn
  when a genuinely new `(modality, label)` pair hits the 0.5 fallback, so
  future specialists don't silently repeat this gap pattern.

## Update (Sep 2026 sprint) — some of the above is now fixed

Revisiting this doc while working the Oct 20 plan: two items in "Dev-only
items already flagged in-repo" and one in "Week 14 frontend items still
open" are done, not just planned. Leaving the original notes above as the
historical record of what was found, but for anyone reading top-to-bottom:

- CORS is no longer `allow_origins=["*"]` in Module 1 or Module 7 — both
  now read from `FEDHEAL_DASHBOARD_ORIGIN`.
- The shared `X-Service-Key`/`FEDMED_SERVICE_KEY` is gone — replaced with
  a distinct key per caller (`FEDHEAL_SVC_KEY_M3_M1`, `FEDHEAL_SVC_KEY_M2_M7`,
  `FEDHEAL_SVC_KEY_M3_M7`).
- CSV vitals upload (listed under "Week 14 frontend items still open") is
  done: `POST /validate/vitals/csv` (Module 2) and `POST
  /vitals/upload/csv` (Module 1), with a matching tab in the dashboard's
  upload panel.
- Also added since the original review, not previously tracked here:
  `/token` rate limiting, an httpOnly session cookie replacing
  `localStorage` token storage, and a real validated `label` field with a
  human-review flow for flagged records (`GET /vitals/flagged` +
  `POST /vitals/{id}/review`).

Still genuinely open: SHAP/Grad-CAM chart rendering in the dashboard,
Module 8 → Module 4 wiring, Module 8 persistence, the `FusionLayer`
unknown-pair warning, and Alembic migrations.
