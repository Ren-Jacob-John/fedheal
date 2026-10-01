"""
Structured vitals specialist — XGBoost, per the proposal's "gradient-boosted
trees consistently outperform neural nets on small-to-medium tabular
clinical data" reasoning. This is the one specialist in the zoo that's
fully real and testable in a lightweight environment (no GPU/torch needed).
"""
import numpy as np
from xgboost import XGBClassifier

from base import PredictionResult, SpecialistModel

# The specialist's input contract IS Module 1's stored vitals record — the
# same 8 fields Module 3's real_data.FEATURE_KEYS trains on, in the same
# order, in natural units. (These used to be the names "age, resting_bp,
# cholesterol, max_heart_rate, bmi, glucose, num_medications,
# prior_admissions": labels from the synthetic make_classification data,
# three of which — cholesterol, glucose, prior_admissions — exist nowhere in
# Module 1 and were never real inputs. See docs/DATA_CONTRACT.md.)
FEATURE_NAMES = [
    "age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
    "weight_kg", "height_cm", "medication_count", "medication_mg_total",
]


class XGBoostVitalsModel(SpecialistModel):
    name = "xgboost-vitals-v1"
    modality = "vitals"
    task = "classification"
    feature_names = FEATURE_NAMES
    training_status = "untrained"

    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            eval_metric="logloss", random_state=42,
        )
        self._is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray, *, training_status: str = "demo_fit",
            model_version: str | None = None, is_fallback: bool | None = None):
        """
        `training_status` says what the data was ("demo_fit" = public/demo
        data, "federated" = Module 3's global model). It defaults to the
        LESS flattering value on purpose. A caller that trains on hospital
        data must say so explicitly.
        """
        if np.asarray(X).shape[1] != len(FEATURE_NAMES):
            raise ValueError(f"{self.name}: expected {len(FEATURE_NAMES)} features "
                             f"({FEATURE_NAMES}), got {np.asarray(X).shape[1]}")
        self.model.fit(X, y)
        self._is_fitted = True
        self.training_status = training_status
        if model_version is not None:
            self.model_version = model_version
        if is_fallback is not None:
            self.is_fallback = is_fallback
        return self

    def is_available(self) -> bool:
        return self._is_fitted   # an unfitted model cannot answer

    def predict(self, case: dict) -> PredictionResult:
        if not self._is_fitted:
            raise RuntimeError(
                f"{self.name}: called predict() before fit() — train on a "
                "hospital's local data first (see module3-fedlearning for the "
                "federated version of this same idea)."
            )
        features = np.array(case["features"], dtype=float).reshape(1, -1)
        if features.shape[1] != len(FEATURE_NAMES) or np.isnan(features).any():
            raise ValueError(f"{self.name}: needs {len(FEATURE_NAMES)} non-missing features {FEATURE_NAMES}")
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
            **self.provenance(),
        )
