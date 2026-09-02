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
| `models/tabular_vitals_tabpfn.py` | **TabPFN v2** — structured vitals, in-context tabular foundation model; current default per `docs/model-algorithm-catalog.md`, XGBoost stays registered alongside it |
| `models/imaging_chest_xray.py` | **DenseNet201** — chest X-ray findings (pneumonia/TB). **Legacy** — kept registered as the auto-degrade fallback; see `foundation_biomedclip.py` |
| `models/imaging_retina.py` | **ResNet50** — diabetic retinopathy grading. **Legacy** — same fallback role |
| `models/imaging_skin.py` | **EfficientNet-B0** — skin lesion classification. **Legacy** — same fallback role |
| `models/imaging_segmentation.py` | **Custom U-Net** — pixel-level segmentation (tumor/organ boundaries). **Legacy** — kept registered as the auto-degrade fallback; see `foundation_nnunet.py` |
| `models/foundation_biomedclip.py` | **BiomedCLIP** — current-tier chest X-ray / retina / skin specialist: frozen BiomedCLIP ViT + a fine-tuned CNN+ViT-hybrid head (a small `Conv1d` mixing five-crop embeddings). Real loading + inference code, untested here (no HF access) |
| `models/foundation_nnunet.py` | **nnU-Net** — current-tier segmentation specialist for `ct_scan`, self-configuring per trained-model-folder. Real loading + inference code, untested here (needs a hospital's own trained model folder + GPU) |
| `models/foundation_evo2.py` | **Evo 2** — new genomic-variant specialist (`genomic_variant` modality), fills a gap the catalog flagged as missing entirely, not an upgrade of an existing file. Real loading + inference code, untested here (no GPU/HF access) |
| `models/foundation_radfm.py` | **RadFM** — radiology vision-language specialist; loading code real, `predict()` intentionally unimplemented (generative model, no checkpoint to validate against here) — see `docs/foundation-models-status.md` |
| `models/foundation_biomedparse.py` | **BiomedParse** — text-prompted segmentation across 9 imaging modalities; real loading + inference code, untested here (no GPU/HF access) |
| `models/foundation_segvol.py` | **SegVol** — volumetric CT segmentation via `transformers`; real loading code, untested here |
| `models/foundation_omiclip.py` | **OmiCLIP** — histopathology/omics alignment; confirmed real upstream, left as an honest stub pending verified loading API — see `docs/foundation-models-status.md` |
| `models/stub.py` | Placeholder used only when a real specialist's dependencies aren't installed |
| `registry.py` | Builds `{modality: [SpecialistModel, ...]}` — the model zoo itself. Candidate lists are current-tier-first, legacy-fallback-second (see registry.py's own module docstring) |
| `router.py` | `MetadataRouter` — picks the right specialist(s) for a case. **Unchanged this pass** — every new model plugs in as a registry entry, not a router change |
| `fusion.py` | Combines multiple specialists' outputs into one overall risk assessment — see `docs/module8-code-review-notes.md` for a severity-table gap found and fixed here, and for remaining `genomic_variant` ontology follow-up. **Unchanged this pass** (per the project's own instruction — late fusion here is a deliberate design choice, not outdated) |
| `demo.py` | **Run this.** Proves all specialists coexist and are correctly routed |

**10 registry modalities** in `registry.py` (`vitals`, `chest_xray`,
`retina`, `skin`, `ct_scan`, `radiology_vqa`, `prompted_segmentation`,
`ct_volumetric`, `pathology_omics`, `genomic_variant` — imaging/
segmentation slots each carry a current-tier + legacy pair where
applicable) and **14+ model implementations** under `models/` — up from
the original five modalities / nine specialist files.
See `docs/foundation-models-status.md` for exactly which of the
foundation-model additions are real-but-unavailable-here vs. genuinely
blocked upstream (MeDiM) vs. unresolved (Mamba-Health/MICViT, requested
but not yet matched to a real published model), and
`docs/model-algorithm-catalog.md`'s "What's actually outdated in your
running code right now" table for this pass's before/after per specialist.

## This pass: current-tier upgrades, legacy kept as fallback (not deleted)

Per the project's own modernization instructions and
`docs/model-algorithm-catalog.md`'s guidance ("Keep as the ... fallback
tier, not the primary path"), every upgrade below is **additive** — the
legacy model stays registered, one slot down in each modality's candidate
list, for low-resource/no-GPU/no-HF-access hospital deployments:

| Modality | Current-tier (primary, index 0) | Legacy (fallback, index 1) |
|---|---|---|
| `chest_xray` | `BiomedCLIPChestXrayModel` | `DenseNet201ChestXrayModel` |
| `retina` | `BiomedCLIPRetinaModel` | `ResNet50RetinaModel` |
| `skin` | `BiomedCLIPSkinModel` | `EfficientNetSkinLesionModel` |
| `ct_scan` | `NNUNetSegmentationModel` | `UNetSegmentationModel` |
| `genomic_variant` | `Evo2VariantModel` | *(none — new capability, no prior specialist to fall back to; degrades straight to `StubSpecialistModel`)* |

`registry.py` tries the current-tier constructor first, the legacy
constructor second, and only falls back to `StubSpecialistModel` if
*neither* real dependency chain is available — so a hospital with torch
but no `huggingface.co` access still gets a real (legacy) model, not a
stub, and `MetadataRouter.route()`'s existing `candidates[0]` selection
means the current tier is used automatically, with zero changes to
`router.py`, `fusion.py`, or `demo.py`.

**Audited and confirmed absent (nothing to delete):** Inception v3/v4,
VGG16/19, Capsule Networks, Mask R-CNN, DeepLab v3/v3+, early-fusion
(raw feature concatenation), TabNet, plain MLP-on-tabular, and SVM-on-
tabular code paths were all checked for across this module (and the
whole repo) — none of them were ever actually implemented here, only
mentioned in `docs/model-algorithm-catalog.md`'s reference menu of what
*not* to use going forward. There was no legacy code matching those
families to remove.

## Why the imaging specialists are stubs when you run this

This model zoo now spans **10 registry modalities** and **14+ model
files** under `models/`. Only two lightweight tabular specialists —
XGBoost and TabPFN for vitals — are guaranteed to install and run in
every environment. DenseNet201, ResNet50, EfficientNet, and U-Net need
`torch` + `torchvision`, which are large (multi-GB with CUDA
dependencies) and weren't installed when this was built (disk-constrained
sandbox). The four foundation-model additions (RadFM, BiomedParse, SegVol,
OmiCLIP) go further still — beyond torch, they need either a cloned
upstream repo, `huggingface.co` network access for weights, or a GPU, none
of which this sandbox has. Rather than skip any of them, `registry.py`
detects each one's real dependency and **automatically substitutes a
clearly labeled stub** (`is_stub=True` on every result) when it's missing
— so the router/fusion logic is fully exercised end-to-end regardless.

**On your own machine**, install torch + torchvision:
```bash
pip install torch torchvision
```
Re-run `python demo.py` — the four original imaging specialists switch
from stubs to their real architectures automatically, with zero code
changes needed in `router.py`, `fusion.py`, or `demo.py`. The model code
itself (`models/imaging_*.py`) is real, correct torchvision
transfer-learning setup — it just hasn't been execution-tested in this
sandbox.

The four foundation-model additions need more than torch — see each
`models/foundation_*.py` file's module docstring and
`docs/foundation-models-status.md` for exact requirements per model
(cloned repos, `huggingface.co` weights, GPU). They won't switch on just
from installing torch/torchvision.

The same is true of this pass's three new/upgraded foundation-model files
(`foundation_biomedclip.py`, `foundation_nnunet.py`, `foundation_evo2.py`)
— each needs its own package (`open_clip_torch`, `nnunetv2`, `evo2`
respectively) plus `huggingface.co` access and, practically, a GPU. Until
those are available, `registry.py` automatically falls back to the
**legacy** model for `chest_xray`/`retina`/`skin`/`ct_scan` (still a real,
correct, running model — just not current-tier) rather than jumping
straight to a stub, and to a stub only for the brand-new `genomic_variant`
modality, which has no legacy predecessor to fall back to.

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
