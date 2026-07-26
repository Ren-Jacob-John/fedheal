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


class SpecialistModel(ABC):
    """
    One entry in the model zoo. `modality` and `task` are how the router
    decides "does this specialist handle this case?" — see router.py.
    """

    name: str = "unnamed-model"
    modality: str = "unknown"        # e.g. "vitals", "chest_xray", "retina", "skin", "ct_scan"
    task: str = "classification"     # "classification" | "segmentation" | "regression"

    @abstractmethod
    def predict(self, case: dict) -> PredictionResult:
        """
        `case` is a dict of already-preprocessed input for this modality —
        e.g. {"features": [...]}  for vitals, {"image": <tensor/array>} for imaging.
        Preprocessing/loading raw files is intentionally out of scope here;
        that belongs in Module 2 (validation/ingestion), not the model zoo.
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """
        Override to return False if this specialist's dependencies aren't
        installed (e.g. torch missing) — lets the registry register a model
        as "known but currently unavailable" instead of crashing at import.
        """
        return True
