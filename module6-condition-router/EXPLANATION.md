# Module 6 — Condition Router: Full Explanation

## What this module is for

Module 5 answers "what kind of data is this, and which specialist handles
it?" This module answers a different, higher-level question: **"a
clinician mentions a specific disease by name — which specialist(s) and
which reasoning method(s) does that actually require?"** Say "breast
cancer" and the system should automatically pull in both a histopathology
model and a genomic-risk model, plus SHAP and knowledge-graph explanations
— without anyone manually wiring that combination together each time.
That auto-switching is what this module implements.

## How it works

- **`conditions.py`** is the actual lookup table — the piece you'd edit to
  add support for a new disease. Each entry maps a condition name (plus
  aliases, so "leukaemia" and "leukemia" both resolve) to the
  specialist(s) and reasoning method(s) it requires.
- **`condition_registry_builder.py`** combines Module 5's existing
  specialists (vitals, chest X-ray, retina, skin, CT) with condition-
  specific ones this module adds: Random Forest genomic-expression
  classifiers (reused for both breast-cancer risk and leukemia subtyping
  via two separately fitted instances), Evo 2 genomic-variant specialists
  (imported from Module 5), a LightGBM blood-count (CBC) classifier for
  leukemia, and histopathology MIL models (current-tier UNI2-h + CLAM-
  style gated attention, with legacy attention-MIL as fallback).
- **`condition_router.py`** does the actual routing: given a condition
  name and case data, it looks the condition up, runs every specialist it
  maps to, and attaches every reasoning method it calls for.
- **`explainers/`** holds three real, working explanation methods: SHAP
  (per-prediction feature attribution for any tree-based specialist),
  Grad-CAM (pixel-level attribution for imaging specialists — falls back
  gracefully rather than erroring when torch isn't available), and a
  rule-based knowledge-graph reasoner that returns an ICD-10-style code, a
  plain-language reason, and a suggested next step, with no ML dependency
  at all.

## Why an unknown condition raises an error instead of guessing

This follows the same reasoning Module 5 applies one level down: running
the wrong specialist on data it wasn't built for produces a confident,
meaningless answer. Guessing which specialist an *unrecognized* condition
should route to would be worse — so `condition_router.py` raises a clear
error listing every condition it does know about, rather than silently
picking something plausible-looking.

## Verified working (from `demo.py`)

"breast cancer" → histopathology + genomic Random Forest, with Grad-CAM,
SHAP, and knowledge-graph reasoning all attached (SHAP correctly skips the
histopathology stub rather than crashing on it). "leukaemia" (British
spelling) → CBC LightGBM + genomic Random Forest, both explainers firing
with real values. "diabetic retinopathy" → single imaging specialist with
knowledge-graph reasoning (Grad-CAM auto-skips since torch isn't
available in this environment, which is a graceful skip, not an error).
"heart_disease" → reuses Module 5's exact vitals specialist with real SHAP
attributions. An unregistered condition like "alien flu" → a clear error
listing every known condition instead of a wrong guess.

## This pass's modernization (per docs/model-algorithm-catalog.md)

`condition_registry_builder.py` now builds the histopathology entry as a
current-tier/legacy pair rather than one fixed model: it tries
`FoundationPathologyMILModel` (real UNI2-h patch embeddings feeding an
actual CLAM-style gated-attention head, replacing the legacy model's
unspecified 512-dim patch-feature input and simpler softmax attention)
first, and falls back to the legacy `HistopathologyMILModel` only if
UNI2-h's dependencies aren't available — same `histopathology` modality
string either way, so nothing downstream (fusion severity weights, the
knowledge-graph ontology lookup) needed to change.

It also now builds two new specialist_ids, `genomic_variant_breast_cancer`
and `genomic_variant_leukemia`, from module5-modelzoo's new
`Evo2VariantModel` (imported directly, the same way this module already
reuses module5's vitals/chest_xray/retina/skin/ct_scan specialists). These
are wired into `conditions.py`'s `breast_cancer`/`leukemia`
`ConditionSpec`s *alongside* the existing Random Forest
`genomic_breast_cancer`/`genomic_leukemia` entries, not in place of them —
Evo 2 needs variant-call sequence data, the RF model needs an expression
panel, and `condition_router.route()`'s existing "skip specialist_ids the
caller didn't supply data for" behavior means both simply fire when their
matching data is present, with no changes needed to `condition_router.py`
itself. The RF models stay registered specifically because the project's
own instructions call for keeping them as the fallback for small
cohorts/expression-panel-only hospital deployments.

One explicit gap that was fixed after this pass: `fusion.py`'s
`SEVERITY_WEIGHTS` and `knowledge_graph_reasoner.py`'s `ONTOLOGY_LOOKUP`
now include `genomic_variant` entries (see `docs/module8-code-review-notes.md`).

Everything else about how this module works — the auto-switch table, the
condition-router logic, all three explainer implementations — is
unchanged: new specialists plug into the existing
`specialist_id -> SpecialistModel` registry and `ConditionSpec.specialist_ids`
list, exactly the extension path this module's own README already
documents for adding any new condition or specialist.

## How other modules depend on it

- **Module 8** (synthesis) imports this module's `condition_router`
  directly and aggregates its `ConditionReport` output (raw specialist
  predictions + explanations) into a clinician-facing review packet —
  this module never talks to Module 8, Module 8 pulls from it.
- It depends on Module 5 for the underlying specialist implementations
  and registry pattern.
- No UI calls into it yet — it's still the layer a future
  clinician-facing "search by disease" screen would call directly, in
  addition to Module 8's synthesis path.

## What's real vs. what's a known prototype simplification

Real: the entire auto-switch mechanism, the CBC/genomic models, all three
explainer implementations. Documented as next-sprint work in this folder's
`README.md`: genomic models are fit on synthetic data with placeholder
gene panels rather than real BRCA/METABRIC or leukemia cytogenetic panels;
the knowledge-graph's ontology lookup covers only the conditions
registered so far, not the full ICD-10/SNOMED CT ontology; the
histopathology model is a compact attention-MIL implementation, not the
full CLAM pipeline (which needs patch-extraction preprocessing that
belongs in Module 2); and survival analysis (time-to-relapse/prognosis) is
planned but not yet wired to a specialist.
