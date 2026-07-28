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

    if HISTOPATH_IMPORT_OK:
        try:
            registry["histopathology_breast_cancer"] = HistopathologyMILModel()
        except ImportError:
            registry["histopathology_breast_cancer"] = StubSpecialistModel(
                "histopathology-breast-cancer", "histopathology", "classification",
                ["benign", "malignant"], "HistopathologyMILModel")
    else:
        registry["histopathology_breast_cancer"] = StubSpecialistModel(
            "histopathology-breast-cancer", "histopathology", "classification",
            ["benign", "malignant"], "HistopathologyMILModel")

    return registry
