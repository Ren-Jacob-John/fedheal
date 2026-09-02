"""
BiomedCLIP-backed imaging specialists — the current-tier replacement for
DenseNet201ChestXrayModel / ResNet50RetinaModel / EfficientNetSkinLesionModel
per docs/model-algorithm-catalog.md Section 1: "foundation-model embeddings
now consistently outperform ImageNet transfer learning on medical images
specifically, since ImageNet's photos are a poor match for medical image
statistics."

Model: microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224
(Zhang et al., "Large-Scale Domain-Specific Pretraining for Biomedical
Vision-Language Processing") — a ViT-B/16 vision-language foundation model
contrastive-pretrained on ~15M biomedical image-text pairs from PubMed
Central. Model card:
https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224

Loading pattern (copied from the model card's own published quick-start,
via the `open_clip` library the card itself specifies):

    import open_clip
    model, preprocess = open_clip.create_model_from_pretrained(
        "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
    )

The federation pattern this follows (per the catalog's framing at the top
of the document): freeze BiomedCLIP entirely and use it purely as a
feature extractor; federate only the small classification head below on
top of its embeddings. Nothing about `model3-fedlearning`'s FedAvg loop
needs to change for that — the head is just another small model with
weights to average.

## The CNN+ViT hybrid (per project instructions, item 4)

BiomedCLIP's own vision tower is already a ViT — the "hybrid" part is the
classification head, which is a small 1D CNN, not another transformer:
`encode_image()` is called once per crop across a standard five-crop
(center + 4 corners) of the input, giving 5 pooled embeddings per image,
which are stacked and run through a `nn.Conv1d` that locally mixes
across crops before a global-pool + linear classifier. This is a
genuinely fine-tuned CNN head sitting on top of a frozen, medically-
pretrained ViT backbone — not a CNN or ViT trained from scratch on
ImageNet-style data, per the catalog's explicit warning against that.
`encode_image()`'s pooled output is used (not raw per-patch tokens)
because that's BiomedCLIP's stable, documented public API; the exact
attribute path to the ViT's internal patch-token sequence isn't
guaranteed across `open_clip` versions — the same kind of "verified vs.
inferred" distinction this repo already draws explicitly for BiomedParse/
SegVol (see docs/foundation-models-status.md).

Needs `open_clip_torch` (pip) + `huggingface.co` network access to fetch
weights on first use, + `torch`. None of the three are available in this
sandbox (disk-constrained, no HF network access — same constraints as
every other foundation-model file in this directory) — so, like RadFM/
BiomedParse/SegVol/OmiCLIP, this degrades to `StubSpecialistModel` via
registry.py's existing try/except pattern. Real, correct, untested here.
"""
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import open_clip
    from torchvision.transforms.functional import five_crop
    OPEN_CLIP_AVAILABLE = True
except (ImportError, OSError):
    OPEN_CLIP_AVAILABLE = False

from base import PredictionResult, SpecialistModel

BIOMEDCLIP_HF_HUB_ID = "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
BIOMEDCLIP_EMBED_DIM = 512   # BiomedCLIP's published joint embedding dimension
CROP_SIZE = 224              # matches the model card's expected input resolution


if OPEN_CLIP_AVAILABLE:
    class _CNNViTHybridHead(nn.Module):
        """
        The fine-tuned head described in this file's module docstring: a
        1D conv mixing five BiomedCLIP crop-embeddings per image, then a
        linear classifier. Everything here is trainable; BiomedCLIP itself
        is frozen upstream in `_BiomedCLIPClassifierBase.embed()`.
        """

        def __init__(self, embed_dim: int, num_classes: int, hidden: int = 128):
            super().__init__()
            self.mix = nn.Conv1d(embed_dim, hidden, kernel_size=3, padding=1)
            self.classifier = nn.Linear(hidden, num_classes)

        def forward(self, crop_embeddings: "torch.Tensor") -> "torch.Tensor":
            # crop_embeddings: (num_crops, embed_dim) for ONE image
            x = crop_embeddings.t().unsqueeze(0)          # (1, embed_dim, num_crops)
            x = F.relu(self.mix(x))                        # (1, hidden, num_crops)
            x = x.mean(dim=2)                               # global pool over crops -> (1, hidden)
            return self.classifier(x)                       # (1, num_classes)


class _BiomedCLIPClassifierBase(SpecialistModel):
    """
    Shared loading + inference logic for every BiomedCLIP-backed imaging
    specialist. Subclasses just set `name`, `modality`, and `class_names`.
    Deliberately does NOT expose a `.backbone` attribute the way the
    legacy torchvision specialists do — `explainers/gradcam_explainer.py`
    (module6) keys off `.backbone` to find a Conv2d layer for pixel-level
    Grad-CAM, and BiomedCLIP's ViT tower isn't a meaningful Grad-CAM
    target the same way a CNN backbone is. Per this project's instruction
    to leave the explainability layer untouched, this class simply omits
    that attribute so `GradCamExplainer` takes its existing, already-
    implemented graceful-skip path (a stub `Explanation`, not a crash) —
    the correct behavior here is "not applicable," not a fabricated
    heatmap. Attention-visualization (catalog Section 10) is the fitting
    explanation method for a ViT-backed specialist like this one; wiring
    that in is future work, not something this pass touches.
    """

    task = "classification"

    def __init__(self, class_names: list[str]):
        if not OPEN_CLIP_AVAILABLE:
            raise ImportError(
                f"{self.name} needs `open_clip_torch` + `torch` + network access to "
                f"huggingface.co (to fetch {BIOMEDCLIP_HF_HUB_ID!r} on first use). "
                "Install with `pip install open_clip_torch torch` on a machine with "
                "internet access — see this module's docstring."
            )
        self.class_names = class_names
        # weights fetched from the HF hub on first construction — real network
        # call, not available in this sandbox (see module docstring).
        self.clip_model, self.preprocess = open_clip.create_model_from_pretrained(
            BIOMEDCLIP_HF_HUB_ID
        )
        self.clip_model.eval()
        for param in self.clip_model.parameters():
            param.requires_grad = False   # frozen — only the head below trains/federates

        self.head = _CNNViTHybridHead(BIOMEDCLIP_EMBED_DIM, len(class_names))
        self.head.eval()

    def is_available(self) -> bool:
        return OPEN_CLIP_AVAILABLE

    def embed(self, image: "torch.Tensor") -> "torch.Tensor":
        """
        `image` expected as a preprocessed (1, 3, H, W) tensor (BiomedCLIP's
        own `preprocess` transform, applied upstream in Module 2's imaging
        ingestion step — same division of labor as the legacy imaging
        specialists). Returns (5, BIOMEDCLIP_EMBED_DIM) — one pooled
        embedding per five-crop.
        """
        crops = five_crop(image, CROP_SIZE)                # tuple of 5x (1, 3, 224, 224)
        with torch.no_grad():
            embeddings = [self.clip_model.encode_image(c) for c in crops]
        return torch.cat(embeddings, dim=0)                 # (5, embed_dim)

    def predict(self, case: dict) -> PredictionResult:
        image = case["image"]
        crop_embeddings = self.embed(image)
        with torch.no_grad():
            logits = self.head(crop_embeddings)
            probs = torch.softmax(logits, dim=1)[0]
            pred_idx = int(torch.argmax(probs).item())

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=self.class_names[pred_idx],
            confidence=float(probs[pred_idx].item()),
            raw_output=probs.tolist(),
            explanation=None,  # see class docstring — attention-viz, not Grad-CAM, is the fit here
            metadata={"backbone": "BiomedCLIP (frozen)", "head": "cnn_vit_hybrid_v1"},
        )


class BiomedCLIPChestXrayModel(_BiomedCLIPClassifierBase):
    name = "biomedclip-chest-xray-v1"
    modality = "chest_xray"

    def __init__(self):
        from models.imaging_chest_xray import CLASS_NAMES
        super().__init__(class_names=CLASS_NAMES)


class BiomedCLIPRetinaModel(_BiomedCLIPClassifierBase):
    name = "biomedclip-retina-v1"
    modality = "retina"

    def __init__(self):
        from models.imaging_retina import CLASS_NAMES
        super().__init__(class_names=CLASS_NAMES)


class BiomedCLIPSkinModel(_BiomedCLIPClassifierBase):
    name = "biomedclip-skin-v1"
    modality = "skin"

    def __init__(self):
        from models.imaging_skin import CLASS_NAMES
        super().__init__(class_names=CLASS_NAMES)

    def predict(self, case: dict) -> PredictionResult:
        # Same melanoma-urgent-review flag EfficientNetSkinLesionModel sets —
        # preserved here so fusion.py's urgent_review_flags behavior and any
        # dashboard highlighting doesn't regress just because the backbone
        # changed underneath it.
        result = super().predict(case)
        result.metadata["flag_for_urgent_review"] = result.label == "melanoma"
        return result
