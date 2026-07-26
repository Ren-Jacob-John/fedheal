"""
A placeholder that implements the same interface as a real specialist, so
the router and fusion layer keep working end-to-end even in an environment
where torch/torchvision aren't installed (like this sandbox). Every
PredictionResult it returns has is_stub=True — the dashboard/clinician UI
should visibly flag this, never present it as a real prediction.
"""
import random

from base import PredictionResult, SpecialistModel


class StubSpecialistModel(SpecialistModel):
    """Stands in for `real_model_name` until its real dependencies are installed."""

    def __init__(self, name: str, modality: str, task: str, class_names: list[str], real_model_name: str):
        self.name = f"stub-{name}"
        self.modality = modality
        self.task = task
        self.class_names = class_names
        self.real_model_name = real_model_name

    def predict(self, case: dict) -> PredictionResult:
        label = random.choice(self.class_names)
        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=label,
            confidence=round(random.uniform(0.5, 0.99), 2),
            raw_output=None,
            is_stub=True,
            metadata={"stands_in_for": self.real_model_name,
                      "reason": "torch/torchvision not installed in this environment"},
        )
