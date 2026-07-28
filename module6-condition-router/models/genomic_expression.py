"""
Genomic / gene-expression specialist — Random Forest, per the catalog's
genomics section ("Random Forest/SVM on gene expression — classic
approach, still competitive on small-N high-dimensional omics data").

Applies to any condition with a genomic subtyping angle — breast cancer
(BRCA1/2 risk, expression subtyping) and leukemia (cytogenetic/molecular
subtyping) both route here, distinguished by which condition's gene panel
and label set is used, not by a different algorithm.
"""
import numpy as np
from sklearn.ensemble import RandomForestClassifier

import paths  # noqa: F401  (adds module5-modelzoo to sys.path)
from base import PredictionResult, SpecialistModel


class GenomicExpressionModel(SpecialistModel):
    """
    One instance per condition's gene panel — pass `gene_names` and
    `class_labels` specific to that condition (e.g. BRCA subtypes vs.
    leukemia subtypes) rather than hardcoding one panel here.
    """

    modality = "genomic"
    task = "classification"

    def __init__(self, name: str, gene_names: list[str], class_labels: list[str]):
        self.name = name
        self.gene_names = gene_names
        self.class_labels = class_labels
        self.model = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42)
        self._is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)
        self._is_fitted = True
        return self

    def predict(self, case: dict) -> PredictionResult:
        if not self._is_fitted:
            raise RuntimeError(f"{self.name}: called predict() before fit().")

        expression = np.array(case["expression"]).reshape(1, -1)
        proba = self.model.predict_proba(expression)[0]
        pred_idx = int(np.argmax(proba))

        importances = dict(zip(self.gene_names, self.model.feature_importances_.tolist()))

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=self.class_labels[pred_idx],
            confidence=float(proba[pred_idx]),
            raw_output=proba.tolist(),
            explanation=importances,  # which genes drove this — the "reason"
        )
