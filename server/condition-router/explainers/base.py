"""
The reasoning/explainability side of "solution AND reason." Just like
SpecialistModel (module5/base.py) is the contract every solution model
implements, Explainer is the contract every reasoning method implements —
so the condition router can attach whichever explainer fits a given
specialist without hardcoding logic per model.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Explanation:
    method: str                      # e.g. "shap", "grad_cam", "knowledge_graph"
    summary: str                     # one-line, human-readable reasoning summary
    details: Any = None              # method-specific payload (SHAP values, heatmap, graph path)
    is_stub: bool = False
    metadata: dict = field(default_factory=dict)


class Explainer(ABC):
    name: str = "unnamed-explainer"

    @abstractmethod
    def explain(self, specialist, case: dict, prediction) -> Explanation:
        """
        `specialist` is the SpecialistModel instance that produced `prediction`
        (a PredictionResult) for `case` — explainers may need the model itself
        (e.g. SHAP needs the underlying sklearn/xgboost object), not just the output.
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        return True
