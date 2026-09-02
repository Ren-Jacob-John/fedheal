"""
The model zoo itself: every specialist the system knows about, keyed by
modality. This is what lets DenseNet201, ResNet50, U-Net, EfficientNet,
XGBoost, BiomedCLIP, nnU-Net, and Evo 2 all "coexist" — they're just
entries in this dict, each wrapped in the same SpecialistModel interface
(base.py), never combined into one network. This is item 1 of the
project's own modernization instructions, kept deliberately intact: new
architectures (including a CNN+ViT hybrid — see foundation_biomedclip.py)
plug in as ONE additional specialist behind this registry + router.py's
MetadataRouter, never as a replacement for the router/fusion pattern
itself.

Per-modality candidate lists are ordered current-tier-first: index 0 is
what `MetadataRouter.route()` actually calls (see router.py), so a
current-generation foundation model (BiomedCLIP/nnU-Net/Evo 2 — added per
docs/model-algorithm-catalog.md) is preferred automatically when its real
dependencies are available, falling back to the legacy architecture, and
only falling back further to StubSpecialistModel when neither real
dependency chain is available. When torch/torchvision/open_clip/etc.
aren't installed (as in this sandbox), build_registry() automatically
substitutes a clearly-labeled StubSpecialistModel so the router/fusion
code is still fully exercised — install the real dependencies and every
stub is replaced by the real architecture with zero changes to router.py,
fusion.py, or demo.py.
"""
from models.stub import StubSpecialistModel
from models.tabular_vitals import XGBoostVitalsModel

try:
    from models.tabular_vitals_tabpfn import TabPFNVitalsModel
    TABPFN_IMPORT_OK = True
except (ImportError, OSError):
    TABPFN_IMPORT_OK = False

try:
    from models.imaging_chest_xray import DenseNet201ChestXrayModel, CLASS_NAMES as CXR_CLASSES
    from models.imaging_retina import ResNet50RetinaModel, CLASS_NAMES as RETINA_CLASSES
    from models.imaging_skin import EfficientNetSkinLesionModel, CLASS_NAMES as SKIN_CLASSES
    from models.imaging_segmentation import UNetSegmentationModel
    IMAGING_IMPORTS_OK = True
except (ImportError, OSError):
    IMAGING_IMPORTS_OK = False
    CXR_CLASSES = ["normal", "pneumonia", "tuberculosis"]
    RETINA_CLASSES = ["no_dr", "mild", "moderate", "severe", "proliferative_dr"]
    SKIN_CLASSES = ["benign_nevus", "melanoma", "basal_cell_carcinoma", "other"]

# --- Current-tier upgrades for the four legacy imaging specialists above ---
# (see docs/model-algorithm-catalog.md's "What's actually outdated" table).
# Each degrades independently of its legacy counterpart — BiomedCLIP/nnU-Net
# missing doesn't affect DenseNet201/ResNet50/EfficientNet/U-Net still being
# registered as the fallback tier, and vice versa.
try:
    from models.foundation_biomedclip import (
        BiomedCLIPChestXrayModel, BiomedCLIPRetinaModel, BiomedCLIPSkinModel,
    )
    BIOMEDCLIP_IMPORT_OK = True
except (ImportError, OSError):
    BIOMEDCLIP_IMPORT_OK = False

try:
    from models.foundation_nnunet import NNUNetSegmentationModel
    NNUNET_IMPORT_OK = True
except (ImportError, OSError):
    NNUNET_IMPORT_OK = False

# --- New genomic variant track (fills the gap noted in the catalog — see
# foundation_evo2.py's module docstring for how this differs from and
# complements module6's Random Forest GenomicExpressionModel). ---
try:
    from models.foundation_evo2 import Evo2VariantModel
    EVO2_IMPORT_OK = True
except (ImportError, OSError):
    EVO2_IMPORT_OK = False

# --- SOTA foundation-model specialists (see docs/foundation-models-status.md) ---
# None of these have their real dependencies/weights available in this
# sandbox (no huggingface.co network access, no GPU) — every one degrades
# to StubSpecialistModel exactly like the imaging specialists above.
# RadFM additionally raises NotImplementedError even when its repo *is*
# importable, since its predict() is deliberately left unwritten pending
# a real checkpoint to validate the generation loop against — see
# foundation_radfm.py's module docstring. OmiCLIP's import always fails
# (OMICLIP_AVAILABLE is hardcoded False) since its loading API couldn't be
# verified against the real Loki repo — see foundation_omiclip.py.
try:
    from models.foundation_radfm import RadFMModel
    RADFM_IMPORT_OK = True
except (ImportError, OSError):
    RADFM_IMPORT_OK = False

try:
    from models.foundation_biomedparse import BiomedParseModel
    BIOMEDPARSE_IMPORT_OK = True
except (ImportError, OSError):
    BIOMEDPARSE_IMPORT_OK = False

try:
    from models.foundation_segvol import SegVolModel
    SEGVOL_IMPORT_OK = True
except (ImportError, OSError):
    SEGVOL_IMPORT_OK = False

try:
    from models.foundation_omiclip import OmiCLIPModel
    OMICLIP_IMPORT_OK = True
except (ImportError, OSError):
    OMICLIP_IMPORT_OK = False


def build_registry(fitted_vitals_model=None) -> dict[str, list]:
    """
    Returns {modality: [SpecialistModel, ...]}. Most modalities map to a
    single specialist; nothing stops a modality having more than one
    candidate model later (e.g. two vendors' chest-X-ray models) — the
    router just needs a way to pick among them (see router.py).
    """
    registry: dict[str, list] = {}

    # --- Structured vitals ---
    # TabPFN v2 is the current-generation default per
    # docs/model-algorithm-catalog.md (Section 4) — a tabular foundation
    # model that now matches/beats XGBoost on data this size. XGBoost
    # stays registered alongside it as a still-current fallback/ensemble
    # partner, and as what runs when `tabpfn` isn't installed.
    if fitted_vitals_model is not None:
        registry["vitals"] = [fitted_vitals_model]
    elif TABPFN_IMPORT_OK:
        try:
            registry["vitals"] = [TabPFNVitalsModel(), XGBoostVitalsModel()]
        except (ImportError, OSError):
            registry["vitals"] = [XGBoostVitalsModel()]
    else:
        registry["vitals"] = [XGBoostVitalsModel()]

    # --- Imaging specialists: current-tier foundation model first (index 0 —
    # what MetadataRouter.route() actually picks, per router.py's own comment
    # that candidates[0] is "the simplest case: one specialist per modality"),
    # legacy ImageNet-pretrained architecture as the registered fallback for
    # low-resource/no-GPU/no-HF-access hospital deployments (per the catalog's
    # own guidance: "Keep as the ... fallback tier, not the primary path"),
    # StubSpecialistModel only if NEITHER real dependency chain is available.
    def _build_imaging_candidates(biomedclip_ctor, legacy_ctor, stub_id, stub_modality,
                                   stub_task, stub_classes, legacy_model_name):
        candidates = []
        if BIOMEDCLIP_IMPORT_OK:
            try:
                candidates.append(biomedclip_ctor())
            except (ImportError, OSError):
                pass  # BiomedCLIP's own deps/network access missing — fall through to legacy
        if IMAGING_IMPORTS_OK:
            try:
                candidates.append(legacy_ctor())
            except (ImportError, OSError):
                pass
        if not candidates:
            candidates.append(StubSpecialistModel(stub_id, stub_modality, stub_task, stub_classes, legacy_model_name))
        return candidates

    registry["chest_xray"] = _build_imaging_candidates(
        BiomedCLIPChestXrayModel if BIOMEDCLIP_IMPORT_OK else None,
        DenseNet201ChestXrayModel if IMAGING_IMPORTS_OK else None,
        "chest-xray", "chest_xray", "classification", CXR_CLASSES, "DenseNet201ChestXrayModel",
    )
    registry["retina"] = _build_imaging_candidates(
        BiomedCLIPRetinaModel if BIOMEDCLIP_IMPORT_OK else None,
        ResNet50RetinaModel if IMAGING_IMPORTS_OK else None,
        "retina", "retina", "classification", RETINA_CLASSES, "ResNet50RetinaModel",
    )
    registry["skin"] = _build_imaging_candidates(
        BiomedCLIPSkinModel if BIOMEDCLIP_IMPORT_OK else None,
        EfficientNetSkinLesionModel if IMAGING_IMPORTS_OK else None,
        "skin", "skin", "classification", SKIN_CLASSES, "EfficientNetSkinLesionModel",
    )

    # --- Segmentation: nnU-Net (current, needs real labeled training data +
    # a trained model folder — see foundation_nnunet.py) first, custom U-Net
    # as the no-training-required fallback, stub if neither is available.
    # For prompted/volumetric segmentation without a per-task labeled
    # dataset, see the separately-registered `prompted_segmentation` /
    # `ct_volumetric` modalities below (BiomedParse / SegVol) instead — this
    # ct_scan slot specifically covers the "we have real labels" branch.
    ct_scan_candidates = []
    if NNUNET_IMPORT_OK:
        try:
            ct_scan_candidates.append(NNUNetSegmentationModel())
        except (ImportError, OSError):
            pass
    if IMAGING_IMPORTS_OK:
        try:
            ct_scan_candidates.append(UNetSegmentationModel())
        except (ImportError, OSError):
            pass
    if not ct_scan_candidates:
        ct_scan_candidates.append(StubSpecialistModel(
            "ct-scan", "ct_scan", "segmentation", ["region_flagged", "no_region_flagged"], "UNetSegmentationModel"))
    registry["ct_scan"] = ct_scan_candidates

    # --- SOTA foundation-model specialists — new modalities, additive to the
    # ones above (not replacements: chest_xray/retina/skin/ct_scan keep
    # working exactly as before). See docs/foundation-models-status.md for
    # what's real vs. blocked vs. unresolved among these six.
    try:
        registry["radiology_vqa"] = [RadFMModel()]
    except (ImportError, OSError, NotImplementedError):
        registry["radiology_vqa"] = [StubSpecialistModel(
            "radfm", "radiology_vqa", "generative_vqa", ["finding_present", "no_finding"], "RadFMModel")]

    try:
        registry["prompted_segmentation"] = [BiomedParseModel()]
    except (ImportError, OSError):
        registry["prompted_segmentation"] = [StubSpecialistModel(
            "biomedparse", "prompted_segmentation", "segmentation",
            ["regions_flagged", "no_regions_flagged"], "BiomedParseModel")]

    try:
        registry["ct_volumetric"] = [SegVolModel()]
    except (ImportError, OSError):
        registry["ct_volumetric"] = [StubSpecialistModel(
            "segvol", "ct_volumetric", "segmentation",
            ["regions_flagged", "no_regions_flagged"], "SegVolModel")]

    try:
        registry["pathology_omics"] = [OmiCLIPModel()]
    except (ImportError, OSError, NotImplementedError):
        registry["pathology_omics"] = [StubSpecialistModel(
            "omiclip", "pathology_omics", "classification",
            ["concordant", "discordant"], "OmiCLIPModel")]

    # --- Genomic variant track (new — see docs/model-algorithm-catalog.md's
    # "still missing entirely" row and foundation_evo2.py's module docstring
    # for how this complements, rather than replaces in-place, module6's
    # Random Forest GenomicExpressionModel). No legacy fallback registered
    # here since nothing in this zoo previously covered variant-level
    # genomic input — only the stub-degrade tier applies.
    try:
        registry["genomic_variant"] = [Evo2VariantModel()]
    except (ImportError, OSError):
        registry["genomic_variant"] = [StubSpecialistModel(
            "evo2", "genomic_variant", "classification",
            ["likely_benign", "uncertain_significance", "likely_pathogenic"], "Evo2VariantModel")]

    return registry


def registry_status(registry: dict[str, list]) -> list[dict]:
    """Human-readable summary for a dashboard/admin view: what's real vs. stubbed."""
    rows = []
    for modality, models in registry.items():
        for m in models:
            rows.append({
                "modality": modality,
                "model_name": m.name,
                "task": m.task,
                "real": not getattr(m, "is_stub", False) and not m.name.startswith("stub-"),
            })
    return rows
