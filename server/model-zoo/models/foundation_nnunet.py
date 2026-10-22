"""
nnU-Net specialist — the current-tier replacement for the hand-written
`UNetSegmentationModel` (imaging_segmentation.py), per
docs/model-algorithm-catalog.md Section 2: "Not obsolete: 2026 papers keep
finding it competitive with or beating out-of-the-box SAM2 on task-
specific, well-labeled datasets. Self-configuring — picks its own
architecture/preprocessing per dataset." The catalog's own guidance is
this is the default *when a hospital has a reasonably sized labeled
segmentation dataset for one specific task* — for text/point-prompted
segmentation without much per-task labeled data, the already-scaffolded
`foundation_biomedparse.py` / `foundation_segvol.py` in this same
directory are the other current-tier options (see their module
docstrings); this file doesn't replace those, it fills the "we have real
labels" branch of the catalog's decision.

Official project: https://github.com/MIC-DKFZ/nnUNet (v2), pip package
`nnunetv2`. nnU-Net is a *training framework*, not a single pretrained
checkpoint you download and run zero-shot — a hospital (or this project's
own training pipeline) runs nnU-Net's `nnUNetv2_plan_and_preprocess` /
`nnUNetv2_train` once on its labeled data to produce a model folder, and
this specialist wraps *inference* against that already-trained model
folder, the same division of labor the catalog draws between "training"
and "this zoo's `predict()` contract."

Loading pattern (copied from nnU-Net v2's own documented inference API,
`nnunetv2.inference.predict_from_raw_data.nnUNetPredictor`):

    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    predictor = nnUNetPredictor(device=torch.device("cuda"))
    predictor.initialize_from_trained_model_folder(
        model_training_output_dir, use_folds=(0,), checkpoint_name="checkpoint_final.pth",
    )
    predictor.predict_single_npy_array(input_image, properties, ...)

`model_training_output_dir` is read from `FEDHEAL_NNUNET_MODEL_FOLDER` —
there's no default checkpoint to ship, since (per the docstring above)
nnU-Net only produces one once trained per-task on real labeled data;
until a hospital has run that training step, this specialist correctly
has nothing to load.

Needs `nnunetv2` (pip) + a real trained model folder + (per the repo's own
recommendation) a GPU for practical inference speed — none available in
this sandbox, so this degrades to the legacy `UNetSegmentationModel` (still
real, still usable, just not current-tier) exactly like every other
foundation-model upgrade in this zoo. Real, correct, untested here.
"""
import os

try:
    import torch
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    NNUNET_AVAILABLE = True
except (ImportError, OSError):
    NNUNET_AVAILABLE = False

from base import PredictionResult, SpecialistModel


class NNUNetSegmentationModel(SpecialistModel):
    name = "nnunet-v2-segmentation-v1"
    modality = "ct_scan"   # same modality string as the legacy UNetSegmentationModel it upgrades
    task = "segmentation"

    def __init__(self, use_folds: tuple = (0,), checkpoint_name: str = "checkpoint_final.pth"):
        if not NNUNET_AVAILABLE:
            raise ImportError(
                f"{self.name} needs the `nnunetv2` package and a GPU. Install with "
                "`pip install nnunetv2` — see this module's docstring and this "
                "module's requirements.txt."
            )
        model_folder = os.environ.get("FEDHEAL_NNUNET_MODEL_FOLDER")
        if not model_folder:
            raise ImportError(
                f"{self.name}: set FEDHEAL_NNUNET_MODEL_FOLDER to a trained nnU-Net "
                "model output directory (produced by `nnUNetv2_train` on this "
                "hospital's/task's labeled segmentation data) — see module docstring."
            )

        device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        self.predictor = nnUNetPredictor(device=device)
        self.predictor.initialize_from_trained_model_folder(
            model_folder, use_folds=use_folds, checkpoint_name=checkpoint_name,
        )

    def is_available(self) -> bool:
        return NNUNET_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        """
        `case["image"]` expected as a preprocessed numpy array in the
        channel-first shape nnU-Net's own preprocessing pipeline expects
        for this task (nnU-Net is self-configuring per dataset — the exact
        shape/spacing/normalization comes from the trained model folder's
        own `plans.json`, not a fixed contract this file can hardcode).
        `case["properties"]` carries the per-case metadata (spacing, etc.)
        nnU-Net's `predict_single_npy_array` requires alongside the image.
        """
        image = case["image"]
        properties = case.get("properties", {})
        mask = self.predictor.predict_single_npy_array(image, properties, None, None, False)

        coverage = float((mask > 0).mean())  # fraction of voxels flagged — same severity proxy as legacy U-Net

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="region_flagged" if coverage > 0.01 else "no_region_flagged",
            confidence=coverage,
            raw_output=mask,
            metadata={"self_configured": True},
        )
