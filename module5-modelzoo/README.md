# Module 5 — Model Zoo & Task Router (Stage 2)

Implements the "model zoo + router" pattern from the proposal: instead of
one model trying to do everything, several specialist architectures
**coexist**, each handling only the task/modality it was built for, with a
router deciding which one sees a given case.

## Setup

```bash
pip install -r requirements.txt --break-system-packages
python demo.py
```

## What's in here

| File | Role |
|---|---|
| `base.py` | `SpecialistModel` interface + `PredictionResult` — the contract every specialist implements, so the router never needs to know which architecture it's talking to |
| `models/tabular_vitals.py` | **XGBoost** — structured vitals (real, fully working, no heavy dependency) |
| `models/imaging_chest_xray.py` | **DenseNet201** — chest X-ray findings (pneumonia/TB) |
| `models/imaging_retina.py` | **ResNet50** — diabetic retinopathy grading |
| `models/imaging_skin.py` | **EfficientNet-B0** — skin lesion classification |
| `models/imaging_segmentation.py` | **Custom U-Net** — pixel-level segmentation (tumor/organ boundaries) |
| `models/stub.py` | Placeholder used only when a real specialist's dependencies aren't installed |
| `registry.py` | Builds `{modality: [SpecialistModel, ...]}` — the model zoo itself |
| `router.py` | `MetadataRouter` — picks the right specialist(s) for a case |
| `fusion.py` | Combines multiple specialists' outputs into one overall risk assessment |
| `demo.py` | **Run this.** Proves all five specialists coexist and are correctly routed |

## Why the imaging specialists are stubs when you run this

This model zoo uses five different architectures. Only one — XGBoost for
vitals — is lightweight enough to actually install and run in every
environment. DenseNet201, ResNet50, EfficientNet, and U-Net need
`torch` + `torchvision`, which are large (multi-GB with CUDA
dependencies) and weren't installed when this was built (disk-constrained
sandbox). Rather than skip those four specialists, `registry.py` detects
whether `torch` imports cleanly and **automatically substitutes a clearly
labeled stub** (`is_stub=True` on every result) if it doesn't — so the
router/fusion logic is fully exercised end-to-end regardless.

**On your own machine**, install torch + torchvision:
```bash
pip install torch torchvision
```
Re-run `python demo.py` — the four imaging specialists switch from stubs
to their real architectures automatically, with zero code changes needed
in `router.py`, `fusion.py`, or `demo.py`. The model code itself
(`models/imaging_*.py`) is real, correct torchvision transfer-learning
setup — it just hasn't been execution-tested in this sandbox.

## Why routing is metadata-based, not a learned classifier

The proposal names two options: metadata (DICOM tags, upload form) or a
lightweight learned classifier. This sprint implements the metadata
option — a case must declare its own modality — because running the wrong
specialist on an input "would produce a confident, meaningless answer,"
per the proposal, and metadata-based routing is the safer default until
there's labeled data to train a modality classifier against. See
`ClassifierBasedRouter` in `router.py` for where that goes next.

## Try it yourself

```python
from registry import build_registry
from router import MetadataRouter
from fusion import FusionLayer

router = MetadataRouter(build_registry())
result = router.route({"modality": "vitals", "features": [0.9, 0.1, -0.2, -0.8, 0.7, 0.0, 1, 0]})
print(result.label, result.confidence)
```

## Next sprint (not yet done here, on purpose)

- Install torch/torchvision on a real dev machine and verify the four real
  imaging specialists actually run forward passes on real (or synthetic)
  images.
- Wire Module 2's validated records into `case["features"]` /
  `case["image"]` instead of hand-built demo cases.
- Federate each imaging specialist the same way Module 3 federates the
  vitals model — "federation still applies per-model," per the proposal:
  DenseNet201 federates across hospitals with chest X-ray data, the retina
  model federates across eye clinics, etc.
- Wire Grad-CAM into the imaging specialists' `explanation` field (the
  proposal's explainability layer) — currently `None`.
- Train `ClassifierBasedRouter` once there's labeled modality data.
