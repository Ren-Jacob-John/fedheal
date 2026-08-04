"""
Structured vitals specialist — TabPFN v2, the current-generation tabular
foundation model (see docs/model-algorithm-catalog.md, Section 4).

Why this replaces XGBoostVitalsModel as the default: TabPFN v2 is
pretrained once on millions of synthetic tabular tasks and does in-context
learning at inference time — no per-hospital training loop, no
hyperparameter tuning. On small-to-medium clinical tabular data (this
project's whole vitals track), it now matches or beats tuned XGBoost.
v2.5 handles up to ~100K rows / ~2,000 features, which comfortably covers
a hospital's structured-vitals table.

Federation note: TabPFN doesn't "train" in the traditional sense, so the
FedAvg pattern in module3-fedlearning doesn't apply to it directly the way
it does to XGBoost/logistic regression. The practical federated pattern
for a foundation model like this is: each hospital calls TabPFN locally
on its own data (nothing to average — there are no weights to federate),
OR each hospital's local table becomes TabPFN's in-context "training set"
at prediction time, refreshed each round. Either way, raw data still never
leaves the hospital — see EXPLANATION.md for how this differs from the
XGBoost specialist's federation story.

XGBoostVitalsModel (tabular_vitals.py) is kept alongside this one, not
deleted — it's still current practice per the catalog (Section 4), useful
as an ensemble partner, and the right fallback for vitals tables that
outgrow TabPFN's row/feature ceiling (swap to TabICL v2 at that point).
"""
try:
    from tabpfn import TabPFNClassifier
    TABPFN_AVAILABLE = True
except (ImportError, OSError):
    TABPFN_AVAILABLE = False

import numpy as np

from base import PredictionResult, SpecialistModel

FEATURE_NAMES = [
    "age", "resting_bp", "cholesterol", "max_heart_rate",
    "bmi", "glucose", "num_medications", "prior_admissions",
]


class TabPFNVitalsModel(SpecialistModel):
    name = "tabpfn-v2-vitals-v1"
    modality = "vitals"
    task = "classification"

    def __init__(self):
        if not TABPFN_AVAILABLE:
            raise ImportError(
                f"{self.name} needs the `tabpfn` package. Install with "
                "`pip install tabpfn` — see this module's requirements.txt. "
                "No GPU strictly required for vitals-sized tables."
            )
        self.model = TabPFNClassifier()
        self._is_fitted = False

    def is_available(self) -> bool:
        return TABPFN_AVAILABLE

    def fit(self, X: np.ndarray, y: np.ndarray):
        # TabPFN's "fit" just stores the local table for in-context
        # inference — this is still the right call site for the
        # FedHeal pipeline (Module 4's local-training step), it just
        # doesn't do gradient-based training under the hood.
        self.model.fit(X, y)
        self._is_fitted = True
        return self

    def predict(self, case: dict) -> PredictionResult:
        if not self._is_fitted:
            raise RuntimeError(
                f"{self.name}: called predict() before fit() — call fit() "
                "with a hospital's local vitals table first."
            )
        features = np.array(case["features"]).reshape(1, -1)
        proba = self.model.predict_proba(features)[0]
        pred_class = int(np.argmax(proba))
        confidence = float(proba[pred_class])

        # TabPFN doesn't expose feature_importances_ the way a tree model
        # does — pair this specialist with SHAP's KernelExplainer (see
        # docs/model-algorithm-catalog.md Section 10) for a per-feature
        # explanation instead of the naive importances dict XGBoost gives.
        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="high_risk" if pred_class == 1 else "low_risk",
            confidence=confidence,
            raw_output=proba.tolist(),
            explanation=None,  # wire in SHAP KernelExplainer here
        )
