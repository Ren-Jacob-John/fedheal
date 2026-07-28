"""
Leukemia CBC (complete blood count) specialist — LightGBM, per the
catalog's note that leukemia diagnosis often starts from structured lab
data (blood counts, blast percentage) before imaging/genomics get
involved. Deliberately a DIFFERENT algorithm than the vitals model's
XGBoost, to prove auto-switching picks the right tool per condition, not
just the same one relabeled.
"""
import numpy as np
from lightgbm import LGBMClassifier

import paths  # noqa: F401
from base import PredictionResult, SpecialistModel

FEATURE_NAMES = [
    "wbc_count", "rbc_count", "platelet_count", "hemoglobin",
    "blast_percentage", "neutrophil_percentage", "lymphocyte_percentage", "age",
]
CLASS_LABELS = ["no_leukemia_suspected", "leukemia_suspected"]


class LeukemiaCBCModel(SpecialistModel):
    name = "lightgbm-leukemia-cbc-v1"
    modality = "cbc"
    task = "classification"

    def __init__(self):
        self.model = LGBMClassifier(n_estimators=150, max_depth=5, learning_rate=0.1,
                                     random_state=42, verbosity=-1)
        self._is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)
        self._is_fitted = True
        return self

    def predict(self, case: dict) -> PredictionResult:
        if not self._is_fitted:
            raise RuntimeError(f"{self.name}: called predict() before fit().")

        features = np.array(case["features"]).reshape(1, -1)
        proba = self.model.predict_proba(features)[0]
        pred_idx = int(np.argmax(proba))

        importances = dict(zip(FEATURE_NAMES, self.model.feature_importances_.tolist()))

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=CLASS_LABELS[pred_idx],
            confidence=float(proba[pred_idx]),
            raw_output=proba.tolist(),
            explanation=importances,
        )
