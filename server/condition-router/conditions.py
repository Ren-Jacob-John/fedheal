"""
The auto-switch table. Given a condition/disease name, this says which
specialist(s) (from condition_registry_builder.py) and which explainer(s)
(from explainers/) to run — this is the piece that makes "mention a
disease, get the right models automatically" actually work.

Extend this dict (plus condition_registry_builder.py for a brand-new
specialist, if needed) to add any condition from docs/model-algorithm-catalog.md.
Nothing in condition_router.py needs to change to add a new condition.
"""
from dataclasses import dataclass


@dataclass
class ConditionSpec:
    canonical_name: str
    aliases: list[str]
    specialist_ids: list[str]         # which registry entries this condition routes to
    explainer_names: list[str]        # which explainers to attach to each result
    notes: str = ""


CONDITION_REGISTRY: dict[str, ConditionSpec] = {
    "breast_cancer": ConditionSpec(
        canonical_name="breast_cancer",
        aliases=["breast cancer", "breast carcinoma", "brca"],
        specialist_ids=["histopathology_breast_cancer", "genomic_variant_breast_cancer",
                         "genomic_breast_cancer"],
        explainer_names=["grad_cam", "shap", "knowledge_graph"],
        notes="Histopathology (UNI2-h + CLAM-style MIL, current-tier — falls back to the "
              "legacy attention-MIL model, see foundation_pathology_mil.py) for tissue "
              "diagnosis + Evo 2 (genomic_variant_breast_cancer, current-tier — needs "
              "variant-call data) for BRCA1/2 variant-effect prediction + the Random "
              "Forest genomic_breast_cancer model (kept registered as the fallback for "
              "small cohorts / expression-panel-only data, per docs/model-algorithm-"
              "catalog.md Section 5) — see docs/model-algorithm-catalog.md Section 12.",
    ),
    "leukemia": ConditionSpec(
        canonical_name="leukemia",
        aliases=["leukaemia", "blood cancer", "aml", "all"],
        specialist_ids=["cbc_leukemia", "genomic_variant_leukemia", "genomic_leukemia"],
        explainer_names=["shap", "knowledge_graph"],
        notes="CBC/blood-count model for initial suspicion + Evo 2 (genomic_variant_"
              "leukemia, current-tier — cytogenetic/molecular variant calls) + the "
              "Random Forest genomic_leukemia model (kept registered as the fallback "
              "for small cohorts / expression-panel-only data) for subtyping (AML vs ALL).",
    ),
    "diabetic_retinopathy": ConditionSpec(
        canonical_name="diabetic_retinopathy",
        aliases=["diabetic retinopathy", "dr", "retinopathy"],
        specialist_ids=["retina"],
        explainer_names=["grad_cam", "knowledge_graph"],
    ),
    "pneumonia": ConditionSpec(
        canonical_name="pneumonia",
        aliases=["lung infection"],
        specialist_ids=["chest_xray"],
        explainer_names=["grad_cam", "knowledge_graph"],
    ),
    "tuberculosis": ConditionSpec(
        canonical_name="tuberculosis",
        aliases=["tb"],
        specialist_ids=["chest_xray"],
        explainer_names=["grad_cam", "knowledge_graph"],
    ),
    "skin_cancer": ConditionSpec(
        canonical_name="skin_cancer",
        aliases=["melanoma", "skin lesion"],
        specialist_ids=["skin"],
        explainer_names=["grad_cam", "knowledge_graph"],
    ),
    "heart_disease": ConditionSpec(
        canonical_name="heart_disease",
        aliases=["cardiac risk", "cardiovascular disease"],
        specialist_ids=["vitals"],
        explainer_names=["shap", "knowledge_graph"],
    ),
    "tumor_segmentation": ConditionSpec(
        canonical_name="tumor_segmentation",
        aliases=["ct scan", "tumor boundary", "organ segmentation"],
        specialist_ids=["ct_scan"],
        explainer_names=["knowledge_graph"],  # Grad-CAM doesn't apply to segmentation masks the same way
        notes="U-Net returns a mask, not a single label — see module5's fusion.py "
              "severity handling for segmentation-specific scoring.",
    ),
}


def resolve_condition(name: str):
    """Case-insensitive lookup by canonical name or any alias. Returns None
    (never raises) so callers can implement their own fallback behavior —
    see condition_router.py's handling of an unresolved condition."""
    normalized = name.strip().lower()
    for spec in CONDITION_REGISTRY.values():
        if normalized == spec.canonical_name or normalized in [a.lower() for a in spec.aliases]:
            return spec
    return None
