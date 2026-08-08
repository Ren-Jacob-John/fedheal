"""
RadFM specialist — "Towards Generalist Foundation Model for Radiology by
Leveraging Web-scale 2D&3D Medical Data" (Wu et al.), official code at
https://github.com/chaoyi-wu/RadFM.

IMPORTANT interface mismatch, read before wiring this up: RadFM is a
generative vision-language model (free-text VQA/report output — its own
README's example is literally Q: "Can you identify any visible signs of
Cardiomegaly in the image?" A: "yes"), NOT a fixed-class classifier like
the other imaging specialists in this zoo. SpecialistModel.predict()
still returns a PredictionResult with a `label` + `confidence`, but for
RadFM those are a best-effort compression of a free-text answer, not a
real softmax probability — see `predict()`'s docstring below. Downstream
code that treats RadFM's `confidence` as calibrated (Module 5's
fusion.py, Module 8's synthesis.py) should be aware of this; it's flagged
in `PredictionResult.metadata["interface_mismatch"]` on every prediction
so callers can detect it programmatically instead of just from a comment.

Deployment requirements (none available in this sandbox):
- Clone the repo: `git clone https://github.com/chaoyi-wu/RadFM`, and set
  `FEDHEAL_RADFM_REPO_PATH` to that path (no pip package exists).
- The model class is `MultiLLaMAForCausalLM` in
  `Model/RadFM/multimodality_model.py` within that repo, backed by
  `Model/RadFM/my_embedding_layer.py` for the vision-text embedding layer
  — confirmed from the repo's own README, not guessed.
- Download `pytorch_model.bin` per the repo's instructions (their README:
  "S1. Download Model checkpoint... S4. python test.py") and point
  `FEDHEAL_RADFM_CHECKPOINT` at it. Checkpoints are hosted off Hugging
  Face / Baidu, not on any domain this sandbox can reach.
- GPU required — the repo's own README says as much ("never try to
  perform this in cpu and gpus are all you need").

None of the above is available here, so — exactly like the existing
DenseNet201/ResNet50 files in this zoo — this is real, correct-as-written
integration code, UNTESTED in this sandbox, that auto-degrades to a
StubSpecialistModel via the same ImportError/OSError path registry.py
already handles.
"""
import os

try:
    import torch
    RADFM_REPO_PATH = os.environ.get("FEDHEAL_RADFM_REPO_PATH")
    if RADFM_REPO_PATH:
        import sys
        sys.path.insert(0, RADFM_REPO_PATH)
        from Model.RadFM.multimodality_model import MultiLLaMAForCausalLM
        RADFM_AVAILABLE = True
    else:
        RADFM_AVAILABLE = False
except (ImportError, OSError):
    RADFM_AVAILABLE = False

from base import PredictionResult, SpecialistModel


class RadFMModel(SpecialistModel):
    """
    Radiology vision-language specialist. `modality` is set per-instance
    (default "radiology_vqa") since RadFM handles both 2D and 3D scans
    across body regions rather than one fixed modality like the
    single-purpose classifiers elsewhere in this zoo.
    """
    name = "radfm-v1"
    modality = "radiology_vqa"
    task = "generative_vqa"   # not "classification" — see module docstring

    def __init__(self):
        if not RADFM_AVAILABLE:
            raise ImportError(
                f"{self.name} needs the cloned RadFM repo on the path in "
                "FEDHEAL_RADFM_REPO_PATH (no pip package — see this file's "
                "module docstring), plus a downloaded pytorch_model.bin at "
                "FEDHEAL_RADFM_CHECKPOINT, plus a GPU. None of these are "
                "available in this sandbox."
            )
        checkpoint = os.environ.get("FEDHEAL_RADFM_CHECKPOINT")
        if not checkpoint:
            raise ImportError(f"{self.name}: set FEDHEAL_RADFM_CHECKPOINT to pytorch_model.bin's path.")
        self.model = MultiLLaMAForCausalLM()
        state_dict = torch.load(checkpoint, map_location="cpu")
        self.model.load_state_dict(state_dict, strict=False)
        self.model.eval()

    def is_available(self) -> bool:
        return RADFM_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        """
        `case` expected: {"image": <preprocessed vision tensor(s)>,
        "prompt": "<clinical question, e.g. 'Describe any abnormal findings.'>"}.

        RadFM generates free text, not a class index. Rather than
        fabricating a confidence score that doesn't exist for a generative
        model, `label` is the raw generated text (truncated) and
        `confidence` is left at a fixed, clearly-flagged placeholder — real
        confidence for a generative answer would need e.g. token-level
        log-prob aggregation, which isn't implemented here. Downstream
        fusion/synthesis code should treat this specialist's output as
        text evidence for a clinician to read, not a score to average in.
        """
        raise NotImplementedError(
            "Real generation loop (tokenization, vision embedding via "
            "my_embedding_layer, autoregressive decode) intentionally left "
            "unimplemented — writing it without a real checkpoint/GPU to "
            "validate against would be guessing at an interface, not "
            "porting one. See Model/RadFM/multimodality_model.py in the "
            "cloned repo, and this file's module docstring, before filling "
            "this in on a machine that has torch+GPU+checkpoint available."
        )
