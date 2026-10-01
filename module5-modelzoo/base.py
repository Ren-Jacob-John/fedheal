"""
The common interface every specialist model implements. This is what makes
"many different architectures coexisting" actually work in code: the router
and fusion layer never need to know whether they're talking to XGBoost,
DenseNet201, or a U-Net — they only ever call .predict(case) and get back
a PredictionResult.

Add a new specialist by subclassing SpecialistModel and registering an
instance in registry.py — nothing else in this module needs to change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PredictionResult:
    model_name: str
    modality: str
    task: str
    label: str                      # e.g. "pneumonia_suspected", "high_risk", "benign"
    confidence: float                # 0.0-1.0
    raw_output: Any = None           # logits/probabilities/segmentation mask, model-specific
    explanation: Optional[Any] = None  # e.g. a Grad-CAM heatmap, feature importances
    is_stub: bool = False            # True if this came from a placeholder, not a real trained model
    metadata: dict = field(default_factory=dict)
    # --- Model provenance (added in the integration pass; all defaulted so
    # every existing caller/constructor keeps working). Never leave these
    # implied: a consumer must be able to tell a stub, a fallback and a
    # trained model apart from the result alone.
    model_version: str = "unversioned"
    is_fallback: bool = False        # True if this is NOT the model the system would prefer to run
    training_status: str = "unknown"  # see SpecialistModel.training_status


class SpecialistModel(ABC):
    """
    One entry in the model zoo. `modality` and `task` are how the router
    decides "does this specialist handle this case?" — see router.py.
    """

    name: str = "unnamed-model"
    modality: str = "unknown"        # e.g. "vitals", "chest_xray", "retina", "skin", "ct_scan"
    task: str = "classification"     # "classification" | "segmentation" | "regression"

    # --- Provenance / status (see describe()) ------------------------------
    model_version: str = "unversioned"
    is_stub: bool = False            # a placeholder that returns made-up output
    is_fallback: bool = False        # a real or stub model standing in for a preferred one
    # "unknown"            nobody declared it
    # "untrained"          real model class, not fitted yet — predict() refuses
    # "none"               stub: there is no model
    # "pretrained"         weights from a public pretrained model, not trained on FedHeal data
    # "demo_fit"           fitted on public/demo data for development — NOT hospital-trained
    # "federated"          fitted from Module 3's federated global model (hospital data)
    training_status: str = "unknown"
    # Ordered input feature names for tabular specialists (None for imaging etc.).
    # This is THE contract for `case["features"]`: position i is feature_names[i].
    feature_names: Optional[list] = None

    @abstractmethod
    def predict(self, case: dict) -> PredictionResult:
        """
        `case` is a dict of already-preprocessed input for this modality —
        e.g. {"features": [...]}  for vitals, {"image": <tensor/array>} for imaging.
        Preprocessing/loading raw files is intentionally out of scope here;
        that belongs in Module 2 (validation/ingestion), not the model zoo.
        """
        raise NotImplementedError

    def describe(self) -> dict:
        """Status card for dashboards / routers. Never claims more than the
        attributes declare, and never hides a stub or fallback."""
        return {
            "model_name": self.name,
            "model_version": self.model_version,
            "modality": self.modality,
            "task": self.task,
            "is_stub": bool(self.is_stub),
            "is_fallback": bool(self.is_fallback),
            "training_status": self.training_status,
            "available": bool(self.is_available()),
            "feature_names": list(self.feature_names) if self.feature_names else None,
        }

    def provenance(self) -> dict:
        """The three PredictionResult fields every predict() must copy over."""
        return {
            "model_version": self.model_version,
            "is_fallback": bool(self.is_fallback),
            "training_status": self.training_status,
        }

    def is_available(self) -> bool:
        """
        Override to return False if this specialist's dependencies aren't
        installed (e.g. torch missing) — lets the registry register a model
        as "known but currently unavailable" instead of crashing at import.
        """
        return True
