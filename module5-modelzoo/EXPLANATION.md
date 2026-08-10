# Module 5 — Model Zoo & Task Router: Full Explanation

## What this module is for

No single model architecture is good at every kind of medical data. A
gradient-boosted tree is the right tool for a table of vitals; it's the
wrong tool for a chest X-ray. A CNN trained on chest X-rays is the wrong
tool for grading a retinal photo. Rather than trying to force one model to
do everything (which the original project outline briefly proposed and
which doesn't actually work — you can't "merge" a decision tree and a
CNN into one model), this module keeps a **library of specialist models**,
each good at exactly one job, and a **router** that sends each case to the
specialist built for it.

## How it works

- **`base.py`** defines the contract every specialist follows —
  `SpecialistModel`, with a single `predict()` method that returns a
  `PredictionResult` (label, confidence, and an optional explanation).
  Because every specialist implements the same interface, the router never
  needs to know or care which underlying architecture it's actually
  calling.
- **`models/`** holds nine specialists: XGBoost and TabPFN v2 for
  structured vitals (both fully real, no heavy dependencies), DenseNet201
  (chest X-ray), ResNet50 (retinal disease grading), EfficientNet-B0
  (skin lesion classification), and a custom U-Net (pixel-level
  segmentation) for imaging, plus four SOTA foundation-model additions —
  RadFM (radiology VQA), BiomedParse (text-prompted segmentation), SegVol
  (volumetric CT segmentation), and OmiCLIP (histopathology/omics
  alignment). The four original imaging models are real, correct
  torchvision transfer-learning code — but in the sandbox this was built
  in, `torch` wasn't installed (it's a multi-gigabyte dependency), so
  `registry.py` automatically detects that and substitutes a clearly
  labeled stub for each imaging specialist instead of skipping them. The
  four foundation-model additions need more than torch (cloned upstream
  repos, `huggingface.co`-hosted weights, or a GPU — see
  `docs/foundation-models-status.md`) and stub out the same way. Every
  stub result is tagged `is_stub=True` so nothing pretends to be a real
  prediction that isn't. Installing the real dependencies on a real
  machine switches each one back to its real implementation with zero
  code changes anywhere else — except RadFM, whose `predict()` is
  intentionally left unimplemented even when its repo is importable,
  since it's a generative model and writing its output logic without a
  real checkpoint to validate against would mean guessing at what
  "confidence" means for a generated sentence.
- **`router.py`** implements `MetadataRouter` — given a case that declares
  its own modality (e.g., `"modality": "chest_xray"`), it picks the
  specialist built for that modality. Metadata-based routing (not a
  learned classifier) was the deliberate choice for this stage, because
  running the *wrong* specialist on an input "would produce a confident,
  meaningless answer" — safer to require the modality be stated than to
  guess it without labeled training data for a modality classifier.
- **`fusion.py`** combines multiple specialists' outputs into one overall
  assessment, for cases that involve more than one data type.

## How other modules depend on it

- **Module 6** (condition router) imports this module's specialists and
  registry directly rather than duplicating them — module5 answers "what
  modality is this?", module6 answers "what disease is this, and which
  specialist(s) + reasoning method(s) does that imply?"
- Nothing else in the current build depends on this module yet; wiring
  Module 2's validated records into a case's `features`/`image` field
  (instead of hand-built demo cases) is listed as next-sprint work.

## What's real vs. what's a known prototype simplification

Real: the `SpecialistModel` interface, the XGBoost vitals specialist end
to end, the router and fusion logic, and the *code* for all four imaging
specialists (just not execution-tested without torch installed in this
environment). Documented as next-sprint work in this folder's
`README.md`: verifying the imaging specialists actually run forward
passes once torch is installed; wiring real (validated) data into cases
instead of demo inputs; federating each imaging specialist the same way
Module 3 federates the vitals model; wiring Grad-CAM into the imaging
specialists' `explanation` field (currently `None` — Module 6 has a
working Grad-CAM explainer, but it isn't connected to these specific
models yet); and training `ClassifierBasedRouter` once labeled modality
data exists.
