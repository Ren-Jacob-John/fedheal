"""
Where Module 8's vitals specialist gets its fitted model from — and, just as
importantly, what it says about that.

Status of the model sources, in order of preference:

  1. FEDERATED GLOBAL MODEL (Module 3)   NOT AVAILABLE YET.
     Module 3 trains a global model in memory each round but does not
     persist or export it, so there is nothing for this service to load.
     When Module 3 gains an export step, integrate it HERE and set
     training_status="federated", is_fallback=False. Until then nothing in
     this service may describe any model as federated or hospital-trained.

  2. DEMO FALLBACK (this file)           available only when explicitly allowed.
     The vitals specialist is fitted on the vendored public UCI Heart Disease
     (Cleveland) records that Module 3 already uses for its demo
     (module3-fedlearning/uci_heart.py), expressed in Module 1's schema.
     Only 3 of the 8 features carry real values there (age, systolic BP,
     heart rate); the other 5 are constants (see that file's docstring), so
     the model can only ever learn from those 3. This is a development/demo
     model. It is reported as training_status="demo_fit", is_fallback=True.

     (The previous behaviour — fitting on numpy.random.normal noise with an
     arbitrary rule at import time and presenting the result as a
     heart-disease model — is gone.)

  3. NOTHING. The specialist stays unfitted, is_available() is False, and
     the API answers 503 `specialist_unavailable`. No silent fallback.

Outside local development the demo fallback must be ENABLED EXPLICITLY
(FEDHEAL_ALLOW_DEMO_MODEL=true); otherwise a staging/production deployment
returns 503 rather than serving a demo model's output to clinicians.
"""
import importlib.util
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

import config
from feature_mapper import VITALS_MAPPING, verify_mapping

UCI_MODULE_PATH = Path(__file__).resolve().parent.parent / "module3-fedlearning" / "uci_heart.py"
DEMO_MODEL_VERSION = "uci-cleveland-demo-1"


@dataclass
class ModelSourceInfo:
    source: str                 # "none" | "uci_cleveland_demo" | (future) "federated_global"
    federated: bool
    hospital_trained: bool
    description: str
    detail: str | None = None   # why it's unavailable, when it is

    def to_dict(self) -> dict:
        return asdict(self)


def demo_model_allowed() -> bool:
    raw = os.environ.get("FEDHEAL_ALLOW_DEMO_MODEL")
    if raw is None or raw.strip() == "":
        return config.is_local()          # on by default for development/test only
    return raw.strip().lower() == "true"


def _load_uci_records() -> list[dict]:
    spec = importlib.util.spec_from_file_location("fedheal_uci_heart", UCI_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)      # isolated: does not touch sys.path or sys.modules
    return module.load_vitals_records()


def fit_vitals_specialist(specialist) -> ModelSourceInfo:
    """Fit (or deliberately don't fit) the vitals specialist and return an
    honest description of what it now is."""
    verify_mapping(specialist.feature_names)

    if not demo_model_allowed():
        return ModelSourceInfo(
            source="none", federated=False, hospital_trained=False,
            description="No model is loaded.",
            detail="No federated global model exists yet, and the demo fallback is disabled "
                   "(set FEDHEAL_ALLOW_DEMO_MODEL=true to enable it explicitly).",
        )
    try:
        records = _load_uci_records()
        X = np.array([[float(r[rule.source_field]) for rule in VITALS_MAPPING] for r in records])
        y = np.array([int(r["label"]) for r in records])
    except Exception as e:  # missing dataset file, checksum mismatch, ...
        return ModelSourceInfo(
            source="none", federated=False, hospital_trained=False,
            description="No model is loaded.",
            detail=f"Demo fallback could not be built: {type(e).__name__}",
        )
    specialist.fit(X, y, training_status="demo_fit", model_version=DEMO_MODEL_VERSION, is_fallback=True)
    return ModelSourceInfo(
        source="uci_cleveland_demo", federated=False, hospital_trained=False,
        description=(
            "Development/demo model fitted on the public UCI Heart Disease (Cleveland) dataset "
            f"({len(records)} records). Only age, systolic_bp and heart_rate_bpm carry real values "
            "in that data; the other five features are constants. It is not hospital-trained and "
            "not federated."
        ),
    )
