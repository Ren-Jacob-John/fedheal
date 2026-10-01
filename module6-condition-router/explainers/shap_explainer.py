"""
SHAP explainer — real, works with any tree-based specialist (XGBoost,
LightGBM, Random Forest all supported by shap.TreeExplainer). This is the
rigorous version of the `feature_importances_` dict the tabular specialists
already return in their own `explanation` field: SHAP values are
per-PREDICTION (this patient, this case) rather than a single global
importance ranking, which is the more clinically useful form of "reason."
"""
import numpy as np

try:
    import shap
    SHAP_AVAILABLE = True
except (ImportError, OSError):  # pragma: no cover - exercised by tests via monkeypatch
    shap = None
    SHAP_AVAILABLE = False

from explainers.base import Explainer, Explanation


class ShapExplainer(Explainer):
    name = "shap"

    def is_available(self) -> bool:
        return SHAP_AVAILABLE

    def explain(self, specialist, case: dict, prediction) -> Explanation:
        underlying_model = getattr(specialist, "model", None)
        if underlying_model is None:
            raise ValueError(
                f"ShapExplainer needs a tree-based specialist with a `.model` "
                f"attribute (XGBoost/LightGBM/RandomForest) — got {specialist.name}"
            )

        # Pull the same feature array the specialist itself used for prediction.
        key = "features" if "features" in case else "expression"
        X = np.array(case[key]).reshape(1, -1)

        explainer = shap.TreeExplainer(underlying_model)
        shap_values = explainer.shap_values(X)

        # TreeExplainer's return shape varies by library/version (list-per-class
        # vs. a single array) — normalize to one row of per-feature contributions
        # for the predicted class.
        if isinstance(shap_values, list):
            pred_class_idx = 0 if len(shap_values) == 1 else 1
            contributions = shap_values[pred_class_idx][0]
        else:
            contributions = shap_values[0] if shap_values.ndim > 1 else shap_values

        # Names come ONLY from the specialist's declared contract. If they can't
        # be matched one-to-one with the contributions there is no honest
        # explanation to give: raise (the router records it as unavailable)
        # rather than zip-truncate or invent generic names.
        feature_names = getattr(specialist, "gene_names", None) or getattr(specialist, "feature_names", None)
        flat = np.ravel(contributions)
        if not feature_names or len(feature_names) != len(flat):
            raise ValueError(
                f"{specialist.name}: cannot label SHAP values — declared feature names "
                f"({0 if not feature_names else len(feature_names)}) do not match the "
                f"{len(flat)} contributions"
            )
        contribution_dict = dict(zip(feature_names, flat.tolist()))
        top_features = sorted(contribution_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]

        summary = (
            "Top contributing factors (toward the positive-class output): " + ", ".join(
                f"{name} ({'+' if val >= 0 else ''}{val:.3f})" for name, val in top_features
            )
        )

        return Explanation(
            method=self.name,
            summary=summary,
            details=contribution_dict,
            metadata={
                "data_driven": True,
                "feature_names": list(feature_names),
                # TreeExplainer on a binary XGBoost model returns log-odds
                # contributions toward the POSITIVE class, whatever class was predicted.
                "explained_output": "log-odds of the positive class",
                "predicted_label": prediction.label,
            },
        )

