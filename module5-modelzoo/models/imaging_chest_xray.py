"""
Chest X-ray specialist — DenseNet201, per the proposal ("DenseNet201 for
chest X-ray findings"). Real torchvision architecture, transfer-learning
setup (freeze the pretrained backbone, replace the classifier head).

Needs `torch` + `torchvision` installed. This sandbox is disk-constrained
and doesn't have them installed, so this file is written correctly but
UNTESTED here — see module5-modelzoo/README.md for how to verify it on a
real dev machine, and demo.py for how the registry falls back to a stub
when torch isn't available so the rest of the zoo still runs.
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
        return TORCH_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        # case["image"] expected as a preprocessed tensor, shape (1, 3, 224, 224),
        # already normalized to ImageNet mean/std — that preprocessing belongs
        # in Module 2's imaging-track validation step, not here.
        image = case["image"]
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
            explanation=None,  # wire in Grad-CAM here (see proposal's explainability layer)
        )
