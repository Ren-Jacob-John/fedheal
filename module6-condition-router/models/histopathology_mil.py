"""
Histopathology specialist — a simple attention-based Multiple Instance
Learning (MIL) model, per the catalog's whole-slide imaging section
("MIL/CLAM — handles gigapixel whole-slide images without patch-level
labels"). This is a compact, from-scratch attention-MIL implementation
(Ilse et al. 2018 style), not the full CLAM pipeline — a real starting
point, not production-grade WSI handling (that needs patch extraction,
tissue detection, and much more preprocessing than fits here).

Same torch dependency note as module5's imaging specialists: real code,
not execution-tested in this disk-constrained sandbox, falls back to a
stub automatically via registry construction (see condition_registry_builder.py).
"""
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except (ImportError, OSError):
    TORCH_AVAILABLE = False

import paths  # noqa: F401
from base import PredictionResult, SpecialistModel

CLASS_NAMES = ["benign", "malignant"]


if TORCH_AVAILABLE:
    class _AttentionMIL(nn.Module):
        """
        Takes a bag of patch embeddings (one whole-slide image = many patches,
        each already reduced to a feature vector by some CNN encoder — that
        encoding step is a separate preprocessing concern, not part of this
        model) and produces one slide-level prediction, weighted by a learned
        attention score over patches.
        """
        def __init__(self, in_features=512, hidden=128, num_classes=2):
            super().__init__()
            self.attention = nn.Sequential(
                nn.Linear(in_features, hidden), nn.Tanh(), nn.Linear(hidden, 1),
            )
            self.classifier = nn.Linear(in_features, num_classes)

        def forward(self, patch_features):
            # patch_features: (num_patches, in_features) for ONE slide
            attn_scores = self.attention(patch_features)               # (num_patches, 1)
            attn_weights = torch.softmax(attn_scores, dim=0)             # sum to 1 over patches
            slide_embedding = (attn_weights * patch_features).sum(dim=0)  # (in_features,)
            logits = self.classifier(slide_embedding.unsqueeze(0))       # (1, num_classes)
            return logits, attn_weights


class HistopathologyMILModel(SpecialistModel):
    name = "attention-mil-histopathology-v1"
    modality = "histopathology"
    task = "classification"

    def __init__(self, in_features: int = 512):
        if not TORCH_AVAILABLE:
            raise ImportError(
                f"{self.name} needs torch. See this module's requirements.txt."
            )
        self.net = _AttentionMIL(in_features=in_features, num_classes=len(CLASS_NAMES))
        self.net.eval()

    def is_available(self) -> bool:
        return TORCH_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        # case["patch_features"]: (num_patches, in_features) — the output of a
        # separate patch-encoder CNN run over every tile of one whole-slide
        # image. Extracting/encoding patches from a raw slide file is a
        # preprocessing step that belongs in Module 2, not here.
        patch_features = case["patch_features"]
        with torch.no_grad():
            logits, attn_weights = self.net(patch_features)
            probs = torch.softmax(logits, dim=1)[0]
            pred_idx = int(torch.argmax(probs).item())

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=CLASS_NAMES[pred_idx],
            confidence=float(probs[pred_idx].item()),
            raw_output=probs.tolist(),
            # which patches the model weighted most — the MIL-specific "reason",
            # distinct from Grad-CAM (which explains single-image CNNs, not bags of patches)
            explanation={"attention_weights": attn_weights.squeeze().tolist()},
        )
