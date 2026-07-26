"""
Structured vitals specialist — XGBoost, per the proposal's "gradient-boosted
trees consistently outperform neural nets on small-to-medium tabular
clinical data" reasoning. This is the one specialist in the zoo that's
fully real and testable in a lightweight environment (no GPU/torch needed).
"""
import numpy as np
from xgboost import XGBClassifier

from base import PredictionResult, SpecialistModel

FEATURE_NAMES = [
    "age", "resting_bp", "cholesterol", "max_heart_rate",
    "bmi", "glucose", "num_medications", "prior_admissions",
]


class XGBoostVitalsModel(SpecialistModel):
    name = "xgboost-vitals-v1"
    modality = "vitals"
    task = "classification"

    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            eval_metric="logloss", random_state=42,
        )
        self._is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)
        self._is_fitted = True
        return self

    def predict(self, case: dict) -> PredictionResult:
        if not self._is_fitted:
            raise RuntimeError(
                f"{self.name}: called predict() before fit() — train on a "
                "hospital's local data first (see module3-fedlearning for the "
                "federated version of this same idea)."
            )
        features = np.array(case["features"]).reshape(1, -1)
        proba = self.model.predict_proba(features)[0]
        pred_class = int(np.argmax(proba))
        confidence = float(proba[pred_class])

        importances = dict(zip(FEATURE_NAMES, self.model.feature_importances_.tolist()))

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="high_risk" if pred_class == 1 else "low_risk",
            confidence=confidence,
            raw_output=proba.tolist(),
            explanation=importances,  # this specialist's answer to "which fields drove it"
        )
