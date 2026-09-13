# Module 5 — Model Zoo & Task Router

## What this module is for

Rather than one model trying to handle every diagnostic task, this is a
library of **specialist** models — one per data modality — behind one
common interface, with a router that sends each case only to the
specialist actually built for it. The whole point: running the wrong
specialist on an input produces a *confident, meaningless* answer, which
is worse than an explicit "I don't have a specialist for this" error.

## How it works internally

**Files:**
- `base.py` — `SpecialistModel` (the common interface every specialist
  implements: `.predict(case) -> PredictionResult`) and `PredictionResult`
  (includes `is_stub`, so downstream consumers always know whether a
  result came from a real trained model or a placeholder).
- `registry.py` — builds the modality → candidate-specialists map. For
  every modality, it tries the **current-tier** model first (e.g.
  BiomedCLIP + CNN/ViT hybrid for imaging), falls back to the **legacy**
  model (e.g. DenseNet201) if the current tier's dependencies aren't
  installed, and falls back further to a clearly-labeled
  `StubSpecialistModel` if *neither* real dependency chain is available.
  This three-tier fallback is the module's central safety property: the
  rest of the system (router, fusion, synthesis) never needs to know or
  care which tier actually answered — it just checks `is_stub`.
- `router.py` — `MetadataRouter`, which routes purely on a declared
  `modality` field (e.g. from a DICOM tag or an upload form's dropdown) —
  **never** inferred from raw pixel/feature data, again to avoid a
  confident wrong guess. Raises `UnroutableCaseError` for an unregistered
  modality rather than silently falling through. `ClassifierBasedRouter`
  is a stub for a future "learn to route from raw input" option — not
  implemented; needs labeled modality-classification training data that
  doesn't exist yet.
- `fusion.py` — combines multiple specialists' `PredictionResult`s for
  the same case (e.g. vitals + a chest X-ray from the same visit) into
  one `FusedAssessment`, carrying forward `used_any_stub_models` so
  nothing downstream loses that signal.
- `models/` — one file per specialist:
  - `tabular_vitals.py` (XGBoost) / `tabular_vitals_tabpfn.py` (TabPFN v2)
    — **these are genuinely installable and runnable with no GPU**, the
    most realistic "real model" in the zoo today.
  - `imaging_chest_xray.py`, `imaging_retina.py`, `imaging_skin.py`
    (DenseNet201/ResNet50/EfficientNet-B0 legacy tier) and
    `imaging_segmentation.py` (custom U-Net legacy tier) — architecturally
    complete, correct transfer-learning setups, but **need
    `torch`/`torchvision` installed and have never been run or trained in
    this environment**.
  - `foundation_biomedclip.py`, `foundation_nnunet.py`, `foundation_evo2.py`,
    `foundation_radfm.py`, `foundation_segvol.py`, `foundation_omiclip.py`,
    `foundation_biomedparse.py` — current-tier foundation-model upgrades.
    Each needs a GPU and/or Hugging Face Hub access not available in this
    sandbox; each degrades cleanly to its legacy fallback or a stub via
    the same `ImportError`/`OSError`/`NotImplementedError` path.
    `foundation_radfm.py` and `foundation_omiclip.py` additionally raise
    `NotImplementedError` explicitly even when their repos are reachable
    — see each file's own docstring for exactly what's blocking it.
  - `stub.py` — `StubSpecialistModel`, the honest placeholder: implements
    the same interface, always returns `is_stub=True`, so nothing
    downstream can mistake it for a real diagnosis.
- `demo.py` — runnable example exercising the registry/router/fusion
  chain end-to-end with a mix of real and stub specialists.

## How to run it

```bash
cd module5-modelzoo
pip install -r requirements.txt   # installs tabpfn/xgboost/lightgbm/sklearn
                                   # by default; see requirements.txt's
                                   # comments for the (larger) torch/GPU
                                   # dependencies needed to run the
                                   # imaging/foundation tiers for real
python demo.py
```

There's no HTTP service here — this module is imported directly by
Module 6 and Module 8 (via `sys.path` insertion) as a library, not run
as its own server.

## How it depends on / is depended on by other modules

- **Imported by:** Module 6 (condition router, for shared base classes
  and some specialist reuse) and Module 8 (synthesis, via `fusion.py`'s
  `FusedAssessment`).
- **Depends on:** nothing else in the platform at runtime — it's a pure
  model/inference library.

## Known limitations / current status

- **No specialist in the imaging/foundation tiers has actually been run
  or trained yet** — this environment lacks the required
  `torch`/`transformers`/GPU/network-to-HuggingFace access. Every one of
  them currently answers via its stub fallback in practice. This is
  correct, safe behavior (nothing pretends to be a real answer when it
  isn't) but means real validation work remains before any of these can
  be called a working diagnostic model.
- `docs/model-algorithm-catalog.md` and `docs/foundation-models-status.md`,
  referenced repeatedly in this module's own comments and the root
  README, don't currently exist in the repo — they need to be written
  (see this project's `DEVELOPMENT_PLAN.md`).
- `ClassifierBasedRouter` is unimplemented by design — no training data
  exists for it yet.
- No automated tests yet.
