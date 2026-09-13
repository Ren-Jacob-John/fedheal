# Module 6 — Condition Router

## What this module is for

Module 5 answers "what modality is this input?" → "which specialist?".
Module 6 answers the finer-grained, clinically meaningful question:
"what **disease** is being asked about?" → "which specialist(s) **and**
which explanation method(s)?" Given a condition name (e.g. "breast
cancer", "leukemia"), it automatically pulls in every specialist model
and every explainer (SHAP, Grad-CAM, knowledge-graph reasoning) that
condition requires — no one has to wire that combination together by
hand each time a case comes in.

## How it works internally

**Files:**
- `conditions.py` — `CONDITION_REGISTRY`, the "auto-switch table": a dict
  from condition name (plus aliases, e.g. "leukaemia"/"blood cancer"/
  "aml"/"all" all resolving to `leukemia`) to a `ConditionSpec` listing
  which `specialist_id`s and which explainer names apply. Adding a new
  condition is adding one dict entry here (plus a new specialist to
  `condition_registry_builder.py` if it needs one that doesn't exist
  yet) — `condition_router.py` itself never needs to change.
- `condition_registry_builder.py` — merges Module 5's modality-keyed
  registry with Module 6's own condition-specific specialists (genomic
  expression models, the leukemia CBC model, the histopathology MIL
  model) into one lookup keyed by the more specific `specialist_id`
  (since two different conditions can share a modality — e.g. genomic —
  but need different fitted models with different gene panels and
  labels).
- `condition_router.py` — `ConditionRouter.route(condition_name,
  case_data)`: resolves the condition name/alias, runs every specialist
  the condition needs against whatever input data the caller supplied
  for it, attaches every relevant explainer's output to each finding,
  and returns a `ConditionReport`. Raises `UnknownConditionError` for an
  unrecognized name rather than guessing — same "explicit failure beats
  a confident wrong guess" principle as Module 5's router.
- `models/` — condition-specific specialists not already in Module 5:
  `genomic_expression.py` (Random Forest, breast cancer risk / leukemia
  subtyping), `leukemia_cbc.py` (LightGBM, blood-count-based), and the
  histopathology track: `histopathology_mil.py` (legacy attention-based
  MIL) with `foundation_pathology_mil.py` as its current-tier upgrade
  (UNI2-h patch embeddings + CLAM-style gated-attention MIL).
- `explainers/` — one file per explanation method, all implementing the
  common `Explainer` interface in `base.py` (which, like Module 5's
  `SpecialistModel`, carries an `is_stub` flag):
  - `shap_explainer.py` — SHAP feature attribution, for
    tabular/tree-based specialists.
  - `gradcam_explainer.py` — Grad-CAM pixel-level attribution for
    imaging specialists; degrades to a labeled stub if `torch` isn't
    installed.
  - `knowledge_graph_reasoner.py` — a rule-based reasoner producing
    ICD-10-style codes, plain-language reasoning, and suggested next
    steps; always available (no heavy dependency), but explicitly marked
    `is_stub=True` since it's rule-based rather than learned.
- `paths.py` — path-setup helper so this module can import Module 5's
  `registry.py`/`models/` without a package install.
- `demo.py` — a runnable example: routes a condition, prints each
  specialist's prediction and each explainer's output, with stub notes.

## How to run it

```bash
cd module6-condition-router
pip install -r requirements.txt
python demo.py
```

Like Module 5, this is a library, not an HTTP service — it's imported
directly by Module 8 (synthesis).

## How it depends on / is depended on by other modules

- **Imports:** Module 5 (`registry.py`, `models/stub.py`, and shared base
  classes via `condition_registry_builder.py` and `paths.py`).
- **Imported by:** Module 8 (`condition_router.ConditionReport` is the
  primary input to Module 8's synthesis step).

## Known limitations / current status

- The histopathology and genomic-variant (Evo 2) current-tier specialists
  need GPU/Hugging Face Hub access not available in this sandbox — they
  degrade to their legacy/stub fallback automatically, same caveat as
  Module 5's imaging tier.
- Grad-CAM is real but untested here (needs `torch`); SHAP is the one
  explainer most likely to run against real (non-stub) output today,
  since it pairs with Module 5's TabPFN/XGBoost vitals specialist.
- The knowledge-graph reasoner is intentionally rule-based, not learned —
  this is a design choice (transparent, auditable reasoning), not a gap.
- No automated tests yet.
