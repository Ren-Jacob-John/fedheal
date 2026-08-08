"""
Fusion layer — combines outputs from multiple specialist models (e.g. this
patient's vitals model AND their chest X-ray model) into one overall
assessment, per the proposal's "Ensemble/multi-modal fusion: separate
specialized models... each produce a prediction, and a final fusion layer
combines them."

Deliberately simple for this sprint: a severity-weighted combination, not a
learned fusion network — a learned fusion layer needs labeled multi-modal
outcome data to train against, which doesn't exist yet. This version is
transparent (every input to the final score is visible) which matters more
right now than squeezing out extra accuracy.
"""
from dataclasses import dataclass, field

from base import PredictionResult

# How concerning each (modality, label) combination is, on a 0-1 scale.
# Clinically reviewed values would replace these — these are illustrative
# placeholders so the fusion math has something real to combine.
#
# Originally only covered module5's own modalities (vitals/chest_xray/
# retina/skin/ct_scan). Module 6 added condition-specific specialists
# reporting different modality strings (genomic/histopathology/cbc — see
# module6-condition-router/models/*.py and condition_registry_builder.py
# for the exact label sets), which had no entries here — every one of
# their findings silently fell back to the "unknown label" neutral weight
# below, so a fused score across e.g. genomic + histopathology findings
# collapsed toward 0.5 regardless of actual severity. See
# docs/module8-code-review-notes.md for how this was found. The values
# below are placeholders in the same spirit as the rest of this table —
# ordered so malignant/high-risk/AML-positive findings score higher than
# their benign/low-risk counterparts — and still need clinical review
# before this feeds any real fusion.
SEVERITY_WEIGHTS: dict[tuple[str, str], float] = {
    ("vitals", "high_risk"): 0.8,
    ("vitals", "low_risk"): 0.1,
    ("chest_xray", "pneumonia"): 0.7,
    ("chest_xray", "tuberculosis"): 0.9,
    ("chest_xray", "normal"): 0.05,
    ("retina", "severe"): 0.8,
    ("retina", "proliferative_dr"): 0.95,
    ("retina", "moderate"): 0.5,
    ("retina", "mild"): 0.2,
    ("retina", "no_dr"): 0.05,
    ("skin", "melanoma"): 0.95,
    ("skin", "basal_cell_carcinoma"): 0.6,
    ("skin", "benign_nevus"): 0.05,
    ("skin", "other"): 0.3,
    ("ct_scan", "region_flagged"): 0.7,
    ("ct_scan", "no_region_flagged"): 0.05,
    # --- Module 6 condition-specific specialists (added with Module 8) ---
    ("histopathology", "malignant"): 0.85,
    ("histopathology", "benign"): 0.05,
    ("genomic", "brca_high_risk"): 0.8,
    ("genomic", "brca_low_risk"): 0.1,
    ("genomic", "leukemia_subtype_aml"): 0.75,
    ("genomic", "leukemia_subtype_all"): 0.75,
    ("cbc", "leukemia_suspected"): 0.75,
    ("cbc", "no_leukemia_suspected"): 0.05,
}


@dataclass
class FusedAssessment:
    overall_risk_score: float          # 0-1, weighted combination across specialists
    risk_level: str                    # "low" | "moderate" | "high"
    contributing_findings: list[dict] = field(default_factory=list)
    used_any_stub_models: bool = False  # True if any input was a placeholder, not a real model
    urgent_review_flags: list[str] = field(default_factory=list)


class FusionLayer:
    def combine(self, results: list[PredictionResult]) -> FusedAssessment:
        if not results:
            raise ValueError("FusionLayer.combine() called with no specialist results")

        findings = []
        weighted_sum, weight_total = 0.0, 0.0
        used_any_stub = False
        urgent_flags = []

        for r in results:
            severity = SEVERITY_WEIGHTS.get((r.modality, r.label), 0.5)  # unknown label -> neutral
            contribution = severity * r.confidence
            weighted_sum += contribution
            weight_total += r.confidence
            used_any_stub = used_any_stub or r.is_stub

            if r.metadata.get("flag_for_urgent_review"):
                urgent_flags.append(f"{r.model_name}: {r.label}")

            findings.append({
                "model_name": r.model_name,
                "modality": r.modality,
                "label": r.label,
                "confidence": r.confidence,
                "severity_weight": severity,
                "is_stub": r.is_stub,
            })

        overall = weighted_sum / weight_total if weight_total > 0 else 0.0
        risk_level = "high" if overall >= 0.6 else "moderate" if overall >= 0.3 else "low"

        return FusedAssessment(
            overall_risk_score=round(overall, 3),
            risk_level=risk_level,
            contributing_findings=findings,
            used_any_stub_models=used_any_stub,
            urgent_review_flags=urgent_flags,
        )
