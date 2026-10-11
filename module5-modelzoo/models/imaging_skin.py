"""
Skin lesion specialist — EfficientNet-B0, per the proposal's "EfficientNet /
InceptionV3" line for skin lesion classification. Same transfer-learning
pattern as the other imaging specialists — see imaging_chest_xray.py's
docstring for the torch/torchvision dependency note.
"""
try:
    import torch
    import torch.nn as nn
    import torchvision.models as tv_models
    TORCH_AVAILABLE = True
except (ImportError, OSError):
    TORCH_AVAILABLE = False

from base import PredictionResult, SpecialistModel

# ISIC-style categories (simplified).
CLASS_NAMES = ["benign_nevus", "melanoma", "basal_cell_carcinoma", "other"]


class EfficientNetSkinLesionModel(SpecialistModel):
    name = "efficientnet-b0-skin-lesion-v1"
    modality = "skin"
    task = "classification"
    model_version = "untrained"
    training_status = "untrained"

    def __init__(self, num_classes: int = len(CLASS_NAMES), freeze_backbone: bool = True):
        if not TORCH_AVAILABLE:
            raise ImportError(
                f"{self.name} needs torch + torchvision. See this module's requirements.txt."
            )
        self.backbone = tv_models.efficientnet_b0(weights=None)
        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier[1] = nn.Linear(in_features, num_classes)

        if freeze_backbone:
            for name, param in self.backbone.named_parameters():
                if not name.startswith("classifier"):
                    param.requires_grad = False

        self.backbone.eval()

    def is_available(self) -> bool:
        return False

    def predict(self, case: dict) -> PredictionResult:
        raise RuntimeError("analysis unavailable: no validated imaging model")
