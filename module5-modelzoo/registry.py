"""
The model zoo itself: every specialist the system knows about, keyed by
modality. This is what lets DenseNet201, ResNet50, U-Net, EfficientNet, and
XGBoost all "coexist" — they're just entries in this dict, each wrapped in
the same SpecialistModel interface (base.py), never combined into one
network.

Real imaging specialists need torch/torchvision. When those aren't
installed (as in this sandbox), build_registry() automatically substitutes
a clearly-labeled StubSpecialistModel so the router/fusion code is still
fully exercised — swap `pip install torch torchvision` in and every stub
is replaced by the real architecture with zero changes to router.py,
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

    # --- Imaging specialists: real if torch/torchvision installed, else stub ---
    if IMAGING_IMPORTS_OK:
        try:
            registry["chest_xray"] = [DenseNet201ChestXrayModel()]
        except (ImportError, OSError):
            registry["chest_xray"] = [StubSpecialistModel(
                "chest-xray", "chest_xray", "classification", CXR_CLASSES, "DenseNet201ChestXrayModel")]
        try:
            registry["retina"] = [ResNet50RetinaModel()]
        except (ImportError, OSError):
            registry["retina"] = [StubSpecialistModel(
                "retina", "retina", "classification", RETINA_CLASSES, "ResNet50RetinaModel")]
        try:
            registry["skin"] = [EfficientNetSkinLesionModel()]
        except (ImportError, OSError):
            registry["skin"] = [StubSpecialistModel(
                "skin", "skin", "classification", SKIN_CLASSES, "EfficientNetSkinLesionModel")]
        try:
            registry["ct_scan"] = [UNetSegmentationModel()]
        except (ImportError, OSError):
            registry["ct_scan"] = [StubSpecialistModel(
                "ct-scan", "ct_scan", "segmentation", ["region_flagged", "no_region_flagged"], "UNetSegmentationModel")]
    else:
        registry["chest_xray"] = [StubSpecialistModel(
            "chest-xray", "chest_xray", "classification", CXR_CLASSES, "DenseNet201ChestXrayModel")]
        registry["retina"] = [StubSpecialistModel(
            "retina", "retina", "classification", RETINA_CLASSES, "ResNet50RetinaModel")]
        registry["skin"] = [StubSpecialistModel(
            "skin", "skin", "classification", SKIN_CLASSES, "EfficientNetSkinLesionModel")]
        registry["ct_scan"] = [StubSpecialistModel(
            "ct-scan", "ct_scan", "segmentation", ["region_flagged", "no_region_flagged"], "UNetSegmentationModel")]

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
