"""
SegVol specialist — "Universal and Interactive Volumetric Medical Image
Segmentation" (Du et al., BAAI), official code at
https://github.com/BAAI-DCAI/SegVol, model card at
https://huggingface.co/BAAI/SegVol.

Unlike RadFM/BiomedParse above, SegVol ships as a standard `transformers`
custom-code model (`trust_remote_code=True`), so no manual repo clone is
needed — just `pip install transformers` plus the model-specific deps
below. It's for CT specifically (200+ anatomical categories via
point/box/text prompts), narrower than BiomedParse's nine modalities.

Deployment requirements (none available in this sandbox):
- `pip install 'monai[all]==0.9.0' einops==0.6.1 transformers==4.18.0
  matplotlib` — exact pinned versions per the model card; a newer
  `transformers` may not load a `trust_remote_code` model built against
  4.18.0's API.
- `AutoModel.from_pretrained("BAAI/SegVol", trust_remote_code=True, ...)`
  fetches both code and weights from Hugging Face — outside this
  sandbox's allowed network domains.
- GPU strongly implied (the model card's own snippet defaults to
  `cuda:0`), though the loading call itself doesn't hard-require it the
  way RadFM's does.

The loading snippet below (`AutoTokenizer`/`AutoModel.from_pretrained`
through `model.to(device)`) is copied verbatim from the model card's own
published usage example — verified, not guessed. `predict()`'s inference
call (`preprocess_ct_gt`, then a per-category `forward_test` call) is
inferred from the same example, which shows preprocessing clearly but
stops before showing the actual per-prompt inference call in what I could
verify — confirm the exact inference method name against the cloned
model's real code (or its example notebook) before relying on it.

Untested in this sandbox for the network-access reason above regardless.
"""
import os

try:
    from transformers import AutoModel, AutoTokenizer
    import torch
    TRANSFORMERS_AVAILABLE = True
except (ImportError, OSError):
    TRANSFORMERS_AVAILABLE = False

from base import PredictionResult, SpecialistModel


class SegVolModel(SpecialistModel):
    name = "segvol-v1"
    modality = "ct_volumetric"   # distinct from module5's existing 2D-slice "ct_scan" modality
    task = "segmentation"

    def __init__(self):
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                f"{self.name} needs `transformers` (plus monai/einops per this "
                "file's module docstring) and network access to huggingface.co "
                "to fetch BAAI/SegVol's code+weights — unavailable in this sandbox."
            )
        # trust_remote_code=True runs code shipped in the model repo, not this
        # codebase — acceptable for a named, reviewed model from a known org,
        # but worth a security sign-off before this ever runs against real
        # patient data in a real deployment, not just installed for a demo.
        self.tokenizer = AutoTokenizer.from_pretrained("BAAI/SegVol")
        self.model = AutoModel.from_pretrained("BAAI/SegVol", trust_remote_code=True, test_mode=True)
        self.model.model.text_encoder.tokenizer = self.tokenizer
        self.model.eval()
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model.to(device)

    def is_available(self) -> bool:
        return TRANSFORMERS_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        """
        `case` expected: {"ct_path": "<path to .nii.gz CT volume>",
        "categories": ["liver", "kidney", ...]} — text-prompted category
        names per the model card's usage pattern (point/box prompts are
        also supported upstream but not wired here; text-only for now).
        """
        ct_path = case["ct_path"]
        categories = case.get("categories", [])
        ct_npy, _ = self.model.processor.preprocess_ct_gt(ct_path, gt_path=None)

        flagged = []
        for category in categories:
            mask = self.model.forward_test(ct_npy, text_prompt=category)  # per model card's documented flow
            if mask.sum() > 0:
                flagged.append(category)

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="regions_flagged" if flagged else "no_regions_flagged",
            confidence=len(flagged) / len(categories) if categories else 0.0,
            raw_output={"categories": categories, "flagged": flagged},
            metadata={"per_category_masks": True},
        )
