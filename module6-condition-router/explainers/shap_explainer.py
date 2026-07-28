"""
SHAP explainer — real, works with any tree-based specialist (XGBoost,
LightGBM, Random Forest all supported by shap.TreeExplainer). This is the
rigorous version of the `feature_importances_` dict the tabular specialists
already return in their own `explanation` field: SHAP values are
per-PREDICTION (this patient, this case) rather than a single global
importance ranking, which is the more clinically useful form of "reason."
"""
import numpy as np
import shap

from explainers.base import Explainer, Explanation


class ShapExplainer(Explainer):
    name = "shap"

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

        feature_names = getattr(specialist, "gene_names", None) or _default_feature_names(specialist)
        contribution_dict = dict(zip(feature_names, np.ravel(contributions).tolist()))
        top_features = sorted(contribution_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]

        summary = "Top contributing factors: " + ", ".join(
            f"{name} ({'+' if val >= 0 else ''}{val:.3f})" for name, val in top_features
        )

        return Explanation(
            method=self.name,
            summary=summary,
            details=contribution_dict,
        )


def _default_feature_names(specialist) -> list[str]:
    # Falls back to generic names if the specialist doesn't expose real ones —
    # every specialist SHOULD expose FEATURE_NAMES/gene_names for this to be
    # genuinely readable; see leukemia_cbc.py and tabular_vitals.py for the pattern.
    module = __import__(specialist.__class__.__module__, fromlist=["FEATURE_NAMES"])
    return getattr(module, "FEATURE_NAMES", [f"feature_{i}" for i in range(20)])
