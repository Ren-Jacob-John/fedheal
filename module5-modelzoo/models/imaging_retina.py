"""
Retinal disease specialist — ResNet50, per the proposal ("ResNet50 as a
backbone for retinal or skin lesion classification"). Same transfer-learning
pattern as the DenseNet201 chest X-ray specialist. See that file's docstring
for the torch/torchvision dependency note — applies here too.
"""
try:
    import torch
    import torch.nn as nn
    import torchvision.models as tv_models
    TORCH_AVAILABLE = True
except (ImportError, OSError):
    TORCH_AVAILABLE = False

from base import PredictionResult, SpecialistModel

# Diabetic retinopathy grading, e.g. APTOS 2019's 5-class severity scale.
CLASS_NAMES = ["no_dr", "mild", "moderate", "severe", "proliferative_dr"]


class ResNet50RetinaModel(SpecialistModel):
    name = "resnet50-retina-v1"
    modality = "retina"
    task = "classification"

    def __init__(self, num_classes: int = len(CLASS_NAMES), freeze_backbone: bool = True):
        if not TORCH_AVAILABLE:
            raise ImportError(
                f"{self.name} needs torch + torchvision. See this module's requirements.txt."
            )
        self.backbone = tv_models.resnet50(weights=None)
        in_features = self.backbone.fc.in_features
        self.backbone.fc = nn.Linear(in_features, num_classes)

        if freeze_backbone:
            for name, param in self.backbone.named_parameters():
                if not name.startswith("fc"):
                    param.requires_grad = False

        self.backbone.eval()

    def is_available(self) -> bool:
        return TORCH_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        image = case["image"]  # (1, 3, 224, 224), preprocessed upstream
        with torch.no_grad():
            logits = self.backbone(image)
            probs = torch.softmax(logits, dim=1)[0]
            pred_idx = int(torch.argmax(probs).item())

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=CLASS_NAMES[pred_idx],
            confidence=float(probs[pred_idx].item()),
            raw_output=probs.tolist(),
        )
