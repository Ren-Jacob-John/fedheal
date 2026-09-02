"""
Combines module5's modality-keyed registry (vitals, chest_xray, retina,
skin, ct_scan) with module6's new condition-specific specialists (genomic
models for breast cancer/leukemia, the leukemia CBC model, the
histopathology MIL model) into one lookup keyed by specialist_id — a more
specific key than modality alone, since two different conditions can share
a modality (genomic) but need different fitted models (different gene
panels, different labels).

Fitting genomic/CBC models on synthetic data here mirrors module3 and
module5's demo pattern — swap for real cohort data per condition when
it's available (see this module's README).
"""
import numpy as np

import paths  # noqa: F401
from registry import build_registry as build_module5_registry
from models.stub import StubSpecialistModel

from models.genomic_expression import GenomicExpressionModel
from models.leukemia_cbc import LeukemiaCBCModel

try:
    from models.histopathology_mil import HistopathologyMILModel
    HISTOPATH_IMPORT_OK = True
except (ImportError, OSError):
    HISTOPATH_IMPORT_OK = False

# --- Current-tier upgrade for the histopathology track (see
# models/foundation_pathology_mil.py's module docstring) — UNI2-h patch
# embeddings + a CLAM-style gated-attention MIL head, in place of the
# legacy model's unspecified 512-dim patch-feature contract. Degrades to
# the legacy HistopathologyMILModel independently, same pattern as every
# other foundation-model addition in this project.
try:
    from models.foundation_pathology_mil import FoundationPathologyMILModel
    FOUNDATION_PATHOLOGY_IMPORT_OK = True
except (ImportError, OSError):
    FOUNDATION_PATHOLOGY_IMPORT_OK = False

# --- New genomic variant track (Evo 2 — see module5-modelzoo's
# models/foundation_evo2.py module docstring for exactly how this
# complements, rather than in-place replaces, GenomicExpressionModel: it
# takes variant-call sequence data, not an expression panel, so it's wired
# in below as an additional specialist_id per condition rather than a
# swap of the existing genomic_* entries). Imported from module5 directly
# (paths.py already puts module5-modelzoo on sys.path) — one definition,
# reused here exactly like module5's own vitals/chest_xray/etc. entries
# already are a few lines down.
try:
    from models.foundation_evo2 import Evo2VariantModel
    EVO2_IMPORT_OK = True
except (ImportError, OSError):
    EVO2_IMPORT_OK = False

BREAST_CANCER_GENE_PANEL = [f"gene_{i}" for i in range(20)]  # placeholder panel — swap for a real BRCA/METABRIC gene list
LEUKEMIA_GENE_PANEL = [f"gene_{i}" for i in range(20)]        # placeholder panel — swap for a real leukemia subtyping panel


def _make_synthetic_genomic_model(name: str, class_labels: list[str], seed: int) -> GenomicExpressionModel:
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(200, len(BREAST_CANCER_GENE_PANEL)))
    y = (X[:, 0] - X[:, 5] + X[:, 12] > 0).astype(int)
    model = GenomicExpressionModel(name=name, gene_names=BREAST_CANCER_GENE_PANEL, class_labels=class_labels)
    model.fit(X, y)
    return model


def _make_synthetic_cbc_model(seed: int) -> LeukemiaCBCModel:
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(200, 8))
    y = (X[:, 4] + X[:, 0] - X[:, 2] > 0.5).astype(int)  # blast% + wbc - platelets, roughly
    model = LeukemiaCBCModel()
    model.fit(X, y)
    return model


def build_condition_registry() -> dict[str, object]:
    """Returns {specialist_id: SpecialistModel instance}."""
    module5_by_modality = build_module5_registry()

    registry: dict[str, object] = {
        "vitals": module5_by_modality["vitals"][0],
        "chest_xray": module5_by_modality["chest_xray"][0],
        "retina": module5_by_modality["retina"][0],
        "skin": module5_by_modality["skin"][0],
        "ct_scan": module5_by_modality["ct_scan"][0],

        "genomic_breast_cancer": _make_synthetic_genomic_model(
            "rf-genomic-breast-cancer-v1", ["brca_low_risk", "brca_high_risk"], seed=1),
        "genomic_leukemia": _make_synthetic_genomic_model(
            "rf-genomic-leukemia-v1", ["leukemia_subtype_all", "leukemia_subtype_aml"], seed=2),
        "cbc_leukemia": _make_synthetic_cbc_model(seed=3),
    }

    # Current-tier first (FoundationPathologyMILModel — UNI2-h + CLAM-style
    # gated attention), legacy attention-MIL as the registered fallback,
    # stub only if neither's real dependencies are available. Unlike
    # module5's registry.py (which keys modality -> list[SpecialistModel]),
    # this registry keys specialist_id -> one SpecialistModel — condition_
    # router.py calls `self.specialists[specialist_id]` directly (see its
    # `route()`), so the selection between tiers happens here at build
    # time rather than via a router-level candidates[0] convention.
    if FOUNDATION_PATHOLOGY_IMPORT_OK:
        try:
            registry["histopathology_breast_cancer"] = FoundationPathologyMILModel()
        except (ImportError, OSError):
            registry["histopathology_breast_cancer"] = _legacy_or_stub_histopathology()
    else:
        registry["histopathology_breast_cancer"] = _legacy_or_stub_histopathology()

    # Genomic variant track (Evo 2) — additional specialist_ids alongside
    # (not replacing) genomic_breast_cancer / genomic_leukemia above, since
    # Evo 2 needs variant-call sequence data rather than an expression
    # panel (see foundation_evo2.py's module docstring). Listed first in
    # conditions.py's specialist_ids for each condition so it's the
    # primary genomic finding whenever the caller has variant data to
    # supply; GenomicExpressionModel (Random Forest) remains the fallback
    # for hospitals that only have an expression panel / are running a
    # small cohort — per the project's own instruction to keep it
    # registered as the small-cohort fallback, not delete it.
    for specialist_id in ("genomic_variant_breast_cancer", "genomic_variant_leukemia"):
        if EVO2_IMPORT_OK:
            try:
                registry[specialist_id] = Evo2VariantModel()
                continue
            except (ImportError, OSError):
                pass
        registry[specialist_id] = StubSpecialistModel(
            specialist_id.replace("_", "-"), "genomic_variant", "classification",
            ["likely_benign", "uncertain_significance", "likely_pathogenic"], "Evo2VariantModel")

    return registry


def _legacy_or_stub_histopathology():
    if HISTOPATH_IMPORT_OK:
        try:
            return HistopathologyMILModel()
        except (ImportError, OSError):
            pass
    return StubSpecialistModel(
        "histopathology-breast-cancer", "histopathology", "classification",
        ["benign", "malignant"], "HistopathologyMILModel")
