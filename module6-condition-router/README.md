# Module 6 — Condition Router (Stage 3 / Week 3)

**The auto-switch layer.** Mention a disease/condition by name and get
routed automatically to the right specialist model(s) *and* the right
reasoning method(s) — no manual model selection. This is the direct
answer to "models auto-switch according to the disease/condition
mentioned" from the brief.

## Setup

```bash
pip install -r requirements.txt --break-system-packages
python demo.py
```

## How it fits with module5

- **module5's `MetadataRouter`** answers "what modality is this input?" →
  picks one specialist per modality.
- **module6's `ConditionRouter`** answers "what disease is this?" → picks
  one or more specialist(s) **and** one or more reasoning method(s),
  reusing module5's specialists (`vitals`, `chest_xray`, `retina`, `skin`,
  `ct_scan`) plus new condition-specific ones added here.

module6 imports module5 directly (see `paths.py`) rather than duplicating
`SpecialistModel`/`PredictionResult`/the registry pattern — one source of
truth for the model-zoo contract.

## What's new in this module

| File | Role |
|---|---|
| `conditions.py` | **The actual auto-switch table.** Disease name/alias → specialist(s) + explainer(s). Extend this to add any condition. |
| `condition_registry_builder.py` | Combines module5's specialists with module6's new ones into one `{specialist_id: model}` lookup |
| `condition_router.py` | `ConditionRouter.route(condition_name, case_data)` — the auto-switch logic itself |
| `models/genomic_expression.py` | **Random Forest** — gene-expression classifier, reused for both breast cancer (BRCA risk) and leukemia (subtyping) via two different fitted instances. **Kept as the small-cohort/expression-panel-only fallback** alongside the new Evo 2 variant track (see module5's `foundation_evo2.py`) — different input contract, not a strict replacement |
| `models/leukemia_cbc.py` | **LightGBM** — blood-count (CBC) classifier, a deliberately different algorithm from the vitals model's XGBoost |
| `models/histopathology_mil.py` | **Attention-based MIL** — whole-slide breast-tissue classifier (real torch code, stub-falls-back like module5's imaging models). **Legacy** — kept registered as the auto-degrade fallback for `foundation_pathology_mil.py` |
| `models/foundation_pathology_mil.py` | **UNI2-h + CLAM-style gated-attention MIL** — current-tier histopathology upgrade: a real pathology foundation-model patch encoder feeding the MIL aggregator, in place of the legacy model's unspecified patch-feature contract. Real loading + inference code, untested here (needs `timm`, HF Hub authorization, GPU) |
| `explainers/shap_explainer.py` | **SHAP** — real, per-prediction feature attribution for any tree-based specialist |
| `explainers/knowledge_graph_reasoner.py` | **Rule-based ontology lookup** (ICD-10-style code + plain-language reason + suggested next step) — real, no ML dependency, always available |
| `explainers/gradcam_explainer.py` | **Grad-CAM** — real pixel-attribution for imaging specialists, stub-falls-back without torch |

## Verified this sprint (ran `demo.py`, all of these actually work)

- `"breast cancer"` → histopathology (stub here, real torch code) + genomic Random Forest (real), with Grad-CAM/SHAP/knowledge-graph attached — SHAP correctly *skips itself* on the histopathology stub (no `.model` attribute) rather than crashing.
- `"leukaemia"` (British spelling, resolves via alias) → CBC LightGBM (real) + genomic Random Forest (real), SHAP + knowledge-graph both firing with real per-prediction values.
- `"diabetic retinopathy"` → single imaging specialist, knowledge-graph reasoning (Grad-CAM auto-skips since it's unavailable, not an error).
- `"heart_disease"` → reuses module5's exact `vitals` XGBoost specialist, SHAP fires with real feature attributions.
- `"alien flu"` (unregistered) → clear, actionable error listing every known condition, **not** a silent wrong guess.

## Why an unknown condition raises instead of guessing

Per the proposal's own reasoning about the model zoo: running the wrong
specialist on an input "would produce a confident, meaningless answer."
The same logic applies one level up — guessing a condition is worse than
telling the caller exactly what's missing and where to add it
(`conditions.py`).

## Extending to a new condition (the whole point of this architecture)

1. Check `docs/model-algorithm-catalog.md` for which model family fits the
   data you have (imaging? tabular? genomic? something else?).
2. If an existing specialist fits (e.g. another imaging condition uses
   `chest_xray`), just add a `ConditionSpec` in `conditions.py` pointing at
   it — no new model code needed.
3. If it needs a new specialist, add one under `models/` following the
   `SpecialistModel` pattern (see any existing file here or in module5),
   register it in `condition_registry_builder.py`, then add the
   `ConditionSpec`.
4. `condition_router.py` needs zero changes either way.

## This pass's modernization (per docs/model-algorithm-catalog.md)

- **Histopathology upgraded**: `histopathology_breast_cancer` now prefers
  `FoundationPathologyMILModel` (`models/foundation_pathology_mil.py` —
  UNI2-h patch embeddings + a real CLAM-style *gated*-attention MIL head,
  a step up from the legacy model's plain softmax attention), falling
  back to the legacy `HistopathologyMILModel` automatically when UNI2-h's
  dependencies (`timm`, HF Hub auth, GPU) aren't available. Same
  `histopathology` modality string, so `fusion.py`'s existing severity
  weights for `(histopathology, benign/malignant)` apply unchanged.
- **New genomic variant track**: `genomic_variant_breast_cancer` and
  `genomic_variant_leukemia` (Evo 2, imported from module5-modelzoo's
  `foundation_evo2.py`) are now part of the `breast_cancer`/`leukemia`
  `ConditionSpec.specialist_ids`, alongside — not replacing — the existing
  `genomic_breast_cancer`/`genomic_leukemia` Random Forest specialists.
  Evo 2 takes variant-call sequence data (a different input contract than
  the RF model's expression panel), so both fire whenever the caller
  supplies the matching kind of data for each — see `conditions.py`'s
  updated notes. The RF models are explicitly kept per the project's own
  instruction, as the fallback for small cohorts / expression-panel-only
  hospital deployments.
- **Known gap this introduces**: `fusion.py`'s `SEVERITY_WEIGHTS` table
  and `knowledge_graph_reasoner.py`'s `ONTOLOGY_LOOKUP` have no entries
  yet for the new `genomic_variant` modality/labels — per the project's
  instruction not to touch either file this pass, those findings
  currently fuse at the neutral 0.5 weight and get a "no ontology entry
  yet" stub explanation. Extending both tables is flagged as follow-up
  work, the same way `docs/module8-code-review-notes.md` documents doing
  for `genomic`/`histopathology`/`cbc` when they were first added.

## Known simplifications (next sprint)

- Genomic models are fit on synthetic data with placeholder gene panels
  (`gene_0`...`gene_19`) — swap for real BRCA/METABRIC or leukemia
  cytogenetic panels once real cohort data is available.
- `ONTOLOGY_LOOKUP` in `knowledge_graph_reasoner.py` covers the conditions
  registered so far, not the full ICD-10/SNOMED CT ontology — extend it
  alongside `conditions.py` (now also including `genomic_variant` labels,
  see above).
- `HistopathologyMILModel` (legacy fallback) is a compact attention-MIL
  implementation, not the full CLAM pipeline; `FoundationPathologyMILModel`
  (current tier) uses real CLAM-style gated attention over real UNI2-h
  patch embeddings but still expects already-tiled patches — tissue
  detection/tiling itself belongs in Module 2, same division of labor as
  before.
- Survival analysis (`lifelines`, installed but not yet wired to a
  specialist) is next: prognosis/time-to-relapse conditions would use
  `CoxPHFitter` following the same `SpecialistModel` pattern.
