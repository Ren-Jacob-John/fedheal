"""
OmiCLIP specialist — "A visual-omics foundation model to bridge
histopathology with spatial transcriptomics" (Chen et al., Nat Methods
2025). Confirmed real and published, but ships inside a larger repo
(`Loki`, https://github.com/GuangyuWangLab2021/Loki) rather than as its
own standalone package, with weights at
https://huggingface.co/WangGuangyuLab/Loki.

Honesty note, more so than the other three foundation-model files in this
directory: I could confirm OmiCLIP/Loki's existence and weight location,
but not a verified, published code snippet for its exact loading/
inference API the way I could for BiomedParse and SegVol (their model
cards show copy-pasteable usage examples; Loki's didn't surface one in
what I could check). Rather than fabricate an import path and function
signature that looks plausible but might not match the real repo, this
file stops at the same honest "unavailable, here's what's needed" stub
Module 5's registry.py already uses elsewhere (e.g. imaging_retina.py
before torch is installed) — filling in the real loading code is next-
sprint work, gated on someone actually cloning
https://github.com/GuangyuWangLab2021/Loki and reading its README/example
scripts directly, not on guessing here.

Deployment requirements (confirmed, even without the exact API):
- `git clone https://github.com/GuangyuWangLab2021/Loki`
- Weights from https://huggingface.co/WangGuangyuLab/Loki/ — outside this
  sandbox's allowed network domains, same as every other foundation model
  in this batch.
- Almost certainly a GPU, per the pattern of every other model in this file set.
"""
OMICLIP_AVAILABLE = False  # flip to a real availability check once the
                            # loading API below is filled in from the real repo

from base import PredictionResult, SpecialistModel


class OmiCLIPModel(SpecialistModel):
    name = "omiclip-v1"
    modality = "pathology_omics"
    task = "classification"

    def __init__(self):
        raise ImportError(
            f"{self.name}: not implemented — the Loki repo "
            "(https://github.com/GuangyuWangLab2021/Loki) needs to be cloned "
            "and its actual loading/inference API read directly before this "
            "can be written correctly. See this file's module docstring for "
            "why that step wasn't guessed at here."
        )

    def is_available(self) -> bool:
        return OMICLIP_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        raise NotImplementedError("See __init__ — not implemented pending real repo access.")
