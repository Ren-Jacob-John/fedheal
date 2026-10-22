"""
Chest X-ray DenseNet201 architecture. No validated clinical weights or
licensed/public task-specific training dataset are present, so this class
is deliberately unavailable and cannot emit a finding.

`torch` + `torchvision` are needed to instantiate the architecture, but are
not sufficient to make it available for inference. A validated artifact and
its dataset/license provenance are required before registry selection.
"""
try:
    import torch
    import torch.nn as nn
    import torchvision.models as tv_models
    TORCH_AVAILABLE = True
except (ImportError, OSError):
    TORCH_AVAILABLE = False

from base import PredictionResult, SpecialistModel

CLASS_NAMES = ["normal", "pneumonia", "tuberculosis"]


class DenseNet201ChestXrayModel(SpecialistModel):
    name = "densenet201-chest-xray-v1"
    modality = "chest_xray"
    task = "classification"
    model_version = "untrained"
    training_status = "untrained"

    def __init__(self, num_classes: int = len(CLASS_NAMES), freeze_backbone: bool = True):
        if not TORCH_AVAILABLE:
            raise ImportError(
                f"{self.name} needs torch + torchvision. Install with "
                "`pip install torch torchvision` on a machine with room for them "
                "(they're large) — see this module's requirements.txt."
            )
        # weights=None avoids requiring a network download in this constructor;
        # swap for weights=torchvision.models.DenseNet201_Weights.IMAGENET1K_V1
        # once you're on a machine that can fetch pretrained weights — standard
        # transfer-learning practice per the proposal.
        self.backbone = tv_models.densenet201(weights=None)
        in_features = self.backbone.classifier.in_features
        self.backbone.classifier = nn.Linear(in_features, num_classes)

        if freeze_backbone:
            for name, param in self.backbone.named_parameters():
                if not name.startswith("classifier"):
                    param.requires_grad = False

        self.backbone.eval()

    def is_available(self) -> bool:
        return False

    def predict(self, case: dict) -> PredictionResult:
        raise RuntimeError("analysis unavailable: no validated imaging model")
