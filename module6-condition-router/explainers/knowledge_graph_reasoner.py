"""
Knowledge-graph / medical-ontology reasoner — real and fully working,
deliberately NOT machine learning. Per the catalog's Section 10: grounds a
prediction in structured medical knowledge (ICD-10-style codes + plain-
language reasoning + a suggested next step) rather than a learned
attribution. This is the most transparent reasoning method in the system —
useful as a baseline "reason" for every condition, and a fallback whenever
SHAP/Grad-CAM aren't available for a given specialist.

Extend ONTOLOGY_LOOKUP as new conditions/labels get added — this is meant
to grow alongside conditions.py, not be exhaustive on day one.
"""
from explainers.base import Explainer, Explanation

# (modality, label) -> (icd10_code, plain_language_reason, suggested_next_step)
ONTOLOGY_LOOKUP: dict[tuple[str, str], tuple[str, str, str]] = {
    ("genomic", "brca_high_risk"): (
        "Z15.01", "Expression pattern matches BRCA1/2-associated high-risk profile.",
        "Refer for genetic counseling and confirmatory germline testing."),
    ("genomic", "brca_low_risk"): (
        "Z15.09", "Expression pattern does not match known high-risk hereditary markers.",
        "Continue routine screening per standard guidelines."),
    ("genomic", "leukemia_subtype_aml"): (
        "C92.0", "Expression profile consistent with Acute Myeloid Leukemia markers.",
        "Confirm with cytogenetics/molecular panel; hematology-oncology referral."),
    ("genomic", "leukemia_subtype_all"): (
        "C91.0", "Expression profile consistent with Acute Lymphoblastic Leukemia markers.",
        "Confirm with flow cytometry and cytogenetics; hematology-oncology referral."),
    ("cbc", "leukemia_suspected"): (
        "C95.9", "Blood count pattern (elevated blasts/abnormal WBC differential) suggests leukemia.",
        "Order peripheral blood smear review and bone marrow biopsy."),
    ("cbc", "no_leukemia_suspected"): (
        "Z00.00", "Blood count pattern within expected ranges.",
        "No further hematologic workup indicated at this time."),
    ("vitals", "high_risk"): (
        "R94.39", "Combined vitals pattern (age, BP, glucose, medication load) indicates elevated risk.",
        "Recommend cardiology/endocrinology follow-up as appropriate."),
    ("vitals", "low_risk"): (
        "Z00.00", "Vitals pattern within expected ranges for this population.",
        "Continue routine monitoring."),
    ("chest_xray", "pneumonia"): (
        "J18.9", "Radiographic pattern consistent with pneumonia.",
        "Correlate with clinical symptoms and consider sputum/blood cultures."),
    ("chest_xray", "tuberculosis"): (
        "A15.9", "Radiographic pattern consistent with pulmonary tuberculosis.",
        "Isolate per infection-control protocol; confirm with sputum AFB/PCR testing."),
    ("chest_xray", "normal"): (
        "Z00.00", "No radiographic abnormality detected.", "No further imaging workup indicated."),
    ("retina", "proliferative_dr"): (
        "E11.359", "Retinal pattern consistent with proliferative diabetic retinopathy.",
        "Urgent ophthalmology referral — risk of vision loss."),
    ("retina", "no_dr"): (
        "Z00.00", "No diabetic retinopathy findings detected.", "Continue routine annual screening."),
    ("skin", "melanoma"): (
        "C43.9", "Lesion pattern consistent with melanoma.",
        "Urgent dermatology referral for biopsy — do not delay."),
    ("skin", "benign_nevus"): (
        "D22.9", "Lesion pattern consistent with a benign nevus.",
        "Routine monitoring; re-check if lesion changes."),
    ("histopathology", "malignant"): (
        "C50.9", "Tissue pattern consistent with malignant breast tissue.",
        "Confirm with pathologist review; stage and initiate oncology referral."),
    ("histopathology", "benign"): (
        "N60.9", "Tissue pattern consistent with benign breast tissue.",
        "Routine follow-up per screening guidelines."),
    # --- Genomic variant track (Evo 2 — module5 foundation_evo2.py) ---
    ("genomic_variant", "likely_pathogenic"): (
        "Z15.01", "Variant-effect score consistent with a likely pathogenic mutation.",
        "Refer for genetic counseling and confirmatory germline testing."),
    ("genomic_variant", "uncertain_significance"): (
        "Z15.09", "Variant-effect score is inconclusive (variant of uncertain significance).",
        "Consider reclassification with updated databases; genetic counseling if clinically indicated."),
    ("genomic_variant", "likely_benign"): (
        "Z00.00", "Variant-effect score consistent with a likely benign variant.",
        "No further genomic workup indicated based on this score alone."),
}


class KnowledgeGraphReasoner(Explainer):
    name = "knowledge_graph"

    def explain(self, specialist, case: dict, prediction) -> Explanation:
        key = (prediction.modality, prediction.label)
        if key not in ONTOLOGY_LOOKUP:
            return Explanation(
                method=self.name,
                summary=f"No ontology entry yet for ({prediction.modality}, {prediction.label}) — "
                        "add one to ONTOLOGY_LOOKUP in knowledge_graph_reasoner.py.",
                details=None,
                is_stub=True,
            )

        icd10_code, reason, next_step = ONTOLOGY_LOOKUP[key]
        return Explanation(
            method=self.name,
            summary=f"[{icd10_code}] {reason} Suggested next step: {next_step}",
            details={"icd10_code": icd10_code, "reason": reason, "suggested_next_step": next_step},
        )
