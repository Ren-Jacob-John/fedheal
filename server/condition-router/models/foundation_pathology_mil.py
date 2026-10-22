"""
Foundation-model-backed histopathology specialist — the current-tier
replacement for `HistopathologyMILModel` (histopathology_mil.py), per
docs/model-algorithm-catalog.md Section 3 and the project's own
instructions: "UNI(v2)/Virchow2/Prov-GigaPath patch embeddings feeding a
CLAM-style MIL head." Per the catalog: "This is how you actually use the
[pathology foundation] models... in a diagnostic pipeline: extract patch
embeddings with UNI/Virchow2/Prov-GigaPath, then train a small MIL
aggregator (CLAM-style) on top — that MIL head is what federates cheaply."

`HistopathologyMILModel` already implements the *aggregator* half of that
pattern (an attention-MIL head) — what it was missing is a real, current-
generation patch encoder underneath it; its own docstring says as much:
"patch_features... the output of a separate patch-encoder CNN run over
every tile... that encoding step is a separate preprocessing concern, not
part of this model." This file supplies that encoder for real, and
upgrades the aggregator from plain softmax-attention to gated attention
(the actual mechanism CLAM — Lu et al. 2021 — uses), rather than adding a
second, disconnected model.

Patch encoder: UNI2-h (Mass General Brigham / Chen et al.), a pathology
foundation model self-supervised on 200M+ patches from 350K+ whole-slide
images. Ships as a `timm` model on the HF Hub — loading pattern copied
from the model card's own quick-start
(https://huggingface.co/MahmoodLab/UNI2-h):

    import timm
    model = timm.create_model(
        "hf-hub:MahmoodLab/UNI2-h", pretrained=True, init_values=1e-5, dynamic_img_size=True,
    )

That model card is gated (requires a Hugging Face account + accepting
MahmoodLab's terms + `huggingface-cli login` or an `HF_TOKEN`) on top of
the network access every other foundation-model file in this repo already
notes as unavailable in this sandbox — so, same as UNI2-h, Virchow2
(`hf-hub:paige-ai/Virchow2`) and Prov-GigaPath
(`hf-hub:prov-gigapath/prov-gigapath`) are real, equivalent-tier
alternatives (selectable via `FEDHEAL_PATHOLOGY_ENCODER_HUB_ID`) if a
different one is already approved/cached for a given deployment — the
loading call is the same `timm.create_model("hf-hub:...", pretrained=True)`
shape for all three per their respective model cards.

Needs `timm` (pip) + `huggingface.co` network access + HF Hub
authorization for the gated weights + (practically) a GPU for whole-slide
volumes. None available in this sandbox — degrades to the legacy
`HistopathologyMILModel` automatically via `condition_registry_builder.py`,
same auto-degrade pattern as module5's foundation-model additions. Real,
correct, untested here.
"""
try:
    import torch
    import torch.nn as nn
    import timm
    TIMM_AVAILABLE = True
except (ImportError, OSError):
    TIMM_AVAILABLE = False

import os

import paths  # noqa: F401  (adds module5-modelzoo to sys.path)
from base import PredictionResult, SpecialistModel

CLASS_NAMES = ["benign", "malignant"]
DEFAULT_ENCODER_HUB_ID = "hf-hub:MahmoodLab/UNI2-h"
UNI2_EMBED_DIM = 1536   # UNI2-h's published output dimension


if TIMM_AVAILABLE:
    class _GatedAttentionMIL(nn.Module):
        """
        The actual CLAM (Lu et al. 2021) gated-attention mechanism — a
        step up from the legacy HistopathologyMILModel's plain softmax
        attention: two parallel branches (a tanh branch and a sigmoid
        "gate" branch) are multiplied together before the attention
        softmax, letting the gate suppress irrelevant patches more
        expressively than a single tanh branch can.
        """

        def __init__(self, in_features: int, hidden: int = 256, num_classes: int = 2):
            super().__init__()
            self.attention_v = nn.Sequential(nn.Linear(in_features, hidden), nn.Tanh())
            self.attention_u = nn.Sequential(nn.Linear(in_features, hidden), nn.Sigmoid())
            self.attention_weights = nn.Linear(hidden, 1)
            self.classifier = nn.Linear(in_features, num_classes)

        def forward(self, patch_embeddings: "torch.Tensor"):
            # patch_embeddings: (num_patches, in_features) for ONE slide
            gated = self.attention_v(patch_embeddings) * self.attention_u(patch_embeddings)
            attn_scores = self.attention_weights(gated)             # (num_patches, 1)
            attn_weights = torch.softmax(attn_scores, dim=0)         # sums to 1 over patches
            slide_embedding = (attn_weights * patch_embeddings).sum(dim=0)
            logits = self.classifier(slide_embedding.unsqueeze(0))
            return logits, attn_weights


class FoundationPathologyMILModel(SpecialistModel):
    name = "uni2-clam-mil-histopathology-v1"
    modality = "histopathology"   # same modality string as the legacy model it upgrades
    task = "classification"

    def __init__(self, encoder_hub_id: str = None):
        if not TIMM_AVAILABLE:
            raise ImportError(
                f"{self.name} needs `timm` + `torch` + huggingface.co network access "
                "+ HF Hub authorization for the gated UNI2-h/Virchow2/Prov-GigaPath "
                "weights. Install with `pip install timm torch` and authenticate via "
                "`huggingface-cli login` — see this module's docstring."
            )
        self.encoder_hub_id = encoder_hub_id or os.environ.get(
            "FEDHEAL_PATHOLOGY_ENCODER_HUB_ID", DEFAULT_ENCODER_HUB_ID
        )
        self.encoder = timm.create_model(
            self.encoder_hub_id, pretrained=True, init_values=1e-5, dynamic_img_size=True,
        )
        self.encoder.eval()
        for param in self.encoder.parameters():
            param.requires_grad = False   # frozen — only the MIL head trains/federates

        self.mil_head = _GatedAttentionMIL(in_features=UNI2_EMBED_DIM, num_classes=len(CLASS_NAMES))
        self.mil_head.eval()

    def is_available(self) -> bool:
        return TIMM_AVAILABLE

    def encode_patches(self, patch_images: "torch.Tensor") -> "torch.Tensor":
        """`patch_images`: (num_patches, 3, H, W), already tiled from a whole-slide
        image (tissue detection + tiling is a Module 2 preprocessing concern,
        same division of labor as the legacy model). Returns (num_patches,
        UNI2_EMBED_DIM) frozen foundation-model embeddings."""
        with torch.no_grad():
            return self.encoder(patch_images)

    def predict(self, case: dict) -> PredictionResult:
        """
        `case["patch_images"]` — raw tiled patches for one slide, run
        through the frozen UNI2-h (or configured alternative) encoder
        here. If `case["patch_embeddings"]` is supplied instead (already
        encoded upstream, e.g. cached across rounds since the encoder is
        frozen and never changes per-hospital), that's used directly and
        the encoder isn't invoked at all — a real efficiency win this
        pattern enables that the legacy model's unspecified encoder
        contract didn't.
        """
        if "patch_embeddings" in case:
            patch_embeddings = case["patch_embeddings"]
        else:
            patch_embeddings = self.encode_patches(case["patch_images"])

        with torch.no_grad():
            logits, attn_weights = self.mil_head(patch_embeddings)
            probs = torch.softmax(logits, dim=1)[0]
            pred_idx = int(torch.argmax(probs).item())

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=CLASS_NAMES[pred_idx],
            confidence=float(probs[pred_idx].item()),
            raw_output=probs.tolist(),
            explanation={"attention_weights": attn_weights.squeeze().tolist(),
                         "patch_encoder": self.encoder_hub_id},
        )
