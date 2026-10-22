"""
BiomedParse specialist — "A Foundation Model for Joint Segmentation,
Detection, and Recognition of Biomedical Objects Across Nine Modalities"
(Microsoft Research), official code at
https://github.com/microsoft/BiomedParse, model card at
https://huggingface.co/microsoft/BiomedParse.

Unlike this zoo's existing UNetSegmentationModel (one fixed binary mask
task), BiomedParse is *prompted* segmentation: you pass a text prompt per
object type ("neoplastic cells", "liver", ...) and get a mask for each —
closer to the "Spatial / Mask coordinates ... route to BiomedParse/SegVol"
routing rule than the existing single-purpose U-Net.

Deployment requirements (none available in this sandbox):
- `git clone https://github.com/microsoft/BiomedParse`, set
  `FEDHEAL_BIOMEDPARSE_REPO_PATH` to that path — the loading API
  (`modeling.BaseModel`, `modeling.build_model`, config-driven init) is
  local repo code, not a pip package.
- `pip install -r <repo>/assets/requirements/requirements.txt` — includes
  `detectron2`, which itself needs a matching CUDA/torch build; not
  something `pip install --break-system-packages` alone resolves.
- Weights (`biomedparse_v1.pt`) come from
  https://huggingface.co/microsoft/BiomedParse — outside this sandbox's
  allowed network domains, so `FEDHEAL_BIOMEDPARSE_CHECKPOINT` has nothing
  to point at here.
- GPU required (`.cuda()` in the repo's own quick-start snippet).

The loading calls below (`BaseModel`, `build_model`,
`load_opt_from_config_files`, `init_distributed`, and the
`BaseModel(...).from_pretrained(...).eval().cuda()` chain) are copied
verbatim from BiomedParse's own published quick-start example — verified,
not guessed. The one exception: `interactive_infer_image`'s exact module
path (`inference_utils.inference` below) is inferred from the repo's
notebook examples that call the function but don't show its import line
in what I could verify — confirm the actual path against the cloned
repo's example notebooks before relying on this import succeeding.

The whole chain is untested in this sandbox regardless, same as this
zoo's other real-but-unavailable-here specialists.
"""
import os

try:
    BIOMEDPARSE_REPO_PATH = os.environ.get("FEDHEAL_BIOMEDPARSE_REPO_PATH")
    if BIOMEDPARSE_REPO_PATH:
        import sys
        sys.path.insert(0, BIOMEDPARSE_REPO_PATH)
        from modeling.BaseModel import BaseModel
        from modeling import build_model
        from utilities.arguments import load_opt_from_config_files
        from utilities.distributed import init_distributed
        from inference_utils.inference import interactive_infer_image  # per repo's example notebooks
        BIOMEDPARSE_AVAILABLE = True
    else:
        BIOMEDPARSE_AVAILABLE = False
except (ImportError, OSError):
    BIOMEDPARSE_AVAILABLE = False

from base import PredictionResult, SpecialistModel


class BiomedParseModel(SpecialistModel):
    name = "biomedparse-v1"
    modality = "prompted_segmentation"
    task = "segmentation"

    def __init__(self, config_path: str = "configs/biomedparse_inference.yaml"):
        if not BIOMEDPARSE_AVAILABLE:
            raise ImportError(
                f"{self.name} needs the cloned BiomedParse repo (with detectron2 "
                "installed) on FEDHEAL_BIOMEDPARSE_REPO_PATH, a checkpoint at "
                "FEDHEAL_BIOMEDPARSE_CHECKPOINT, and a GPU — see this file's "
                "module docstring. None available in this sandbox."
            )
        checkpoint = os.environ.get("FEDHEAL_BIOMEDPARSE_CHECKPOINT")
        if not checkpoint:
            raise ImportError(f"{self.name}: set FEDHEAL_BIOMEDPARSE_CHECKPOINT.")

        opt = load_opt_from_config_files([config_path])
        opt = init_distributed(opt)
        self.model = BaseModel(opt, build_model(opt)).from_pretrained(checkpoint).eval().cuda()

    def is_available(self) -> bool:
        return BIOMEDPARSE_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        """
        `case` expected: {"image": <preprocessed image array, [0,255] range
        per the repo's preprocessing requirements>, "prompts": ["liver",
        "lesion", ...]} — a list of object-type text prompts, per
        BiomedParse's text-prompted design (see module docstring).

        Returns one mask per prompt in `raw_output`; `label`/`confidence`
        summarize the *count* of prompts that returned a non-empty mask,
        since (unlike the single-object UNetSegmentationModel) there's no
        single binary label for a multi-prompt result — a clinician needs
        the per-prompt masks, not a rolled-up score.
        """
        prompts = case.get("prompts", [])
        image = case["image"]
        pred_masks = interactive_infer_image(self.model, image, prompts)

        flagged = [p for p, m in zip(prompts, pred_masks) if m.sum() > 0]
        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="regions_flagged" if flagged else "no_regions_flagged",
            confidence=len(flagged) / len(prompts) if prompts else 0.0,
            raw_output={"prompts": prompts, "masks": pred_masks, "flagged": flagged},
            metadata={"per_prompt_masks": True},
        )
