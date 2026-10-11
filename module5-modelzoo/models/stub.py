"""
A placeholder that implements the same interface as a real specialist, so
the router and fusion layer keep working end-to-end even in an environment
where torch/torchvision aren't installed (like this sandbox). Every
PredictionResult it returns has is_stub=True — the dashboard/clinician UI
should visibly flag this, never present it as a real prediction.
"""
from base import PredictionResult, SpecialistModel


class StubSpecialistModel(SpecialistModel):
    """Unavailable status-only stand-in; never fabricates a model finding."""

    is_stub = True
    is_fallback = True          # always a stand-in for a real model
    training_status = "none"    # there is no model behind this
    model_version = "stub"

    def __init__(self, name: str, modality: str, task: str, class_names: list[str], real_model_name: str):
        self.name = f"stub-{name}"
        self.modality = modality
        self.task = task
        self.class_names = class_names
        self.real_model_name = real_model_name

    def is_available(self) -> bool:
        return False

    def predict(self, case: dict) -> PredictionResult:
        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="analysis unavailable: no validated model",
            confidence=0.0,
            raw_output=None,
            is_stub=True,
            **self.provenance(),
            metadata={"stands_in_for": self.real_model_name,
                      "reason": "no validated specialist model is available"},
        )
