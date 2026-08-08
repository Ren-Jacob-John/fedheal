# Code review notes — modules 1–7, checked against the 16-week plan

Scope: read every module's core files, ran Module 5's, Module 6's, and the
new Module 8's demos end-to-end with real (not stub) dependencies installed
(`xgboost`, `lightgbm`, `shap`) to confirm the pipeline actually executes,
not just reads plausibly.

## Confirmed bug: fusion severity table doesn't cover Module 6 modalities

`module5-modelzoo/fusion.py`'s `SEVERITY_WEIGHTS` dict only has entries for
`vitals`, `chest_xray`, `retina`, `skin`, `ct_scan` — the modality names
Module 5's own registry uses. Module 6's condition-specific specialists
report different modality strings (`genomic`, `histopathology`, `cbc` — see
`module6-condition-router/models/*.py`), none of which appear in the table.

Effect: running `FusionLayer.combine()` on Module 6 findings (as Module 8's
demo does for breast cancer / leukemia) silently falls back to the
"unknown label" neutral weight of `0.5` for *every* finding, so the fused
`overall_risk_score` collapses toward 0.5 regardless of how severe the
actual findings are — confirmed by running the demo: a `brca_high_risk`
(0.71 confidence) + a stub `malignant` (0.66 confidence) finding produced
`overall_risk_score = 0.500`, which is uninformative.

This isn't a crash — `.get((modality, label), 0.5)` degrades quietly — which
is exactly the "confident, meaningless answer" failure mode the codebase's
own docstrings warn about elsewhere (`UnroutableCaseError`,
`UnknownConditionError`). Fusion should probably raise/warn on an unknown
modality rather than defaulting silently, or `SEVERITY_WEIGHTS` needs
entries for the condition-router's modalities. Left unfixed here since the
actual severity values need a clinician's input, not an engineering guess
— flagged in Module 8's README as a known limitation instead of silently
worked around.

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
