"""
Run: python demo.py

Proves the auto-switch behavior end to end: mention "breast_cancer" and
get histopathology + genomic specialists with Grad-CAM/SHAP/knowledge-graph
reasoning attached automatically; mention "leukemia" and get a completely
different pair of specialists (CBC + genomic) with SHAP + knowledge-graph;
mention an unregistered condition and get a clear, actionable error instead
of a silent wrong guess.
"""
import numpy as np

from condition_router import ConditionRouter, UnknownConditionError


def print_report(report):
    print(f"\n=== Condition: {report.condition} ===")
    if not report.findings:
        print("  (no findings — caller didn't supply data for any of this condition's specialists)")
    for finding in report.findings:
        pred = finding.prediction
        stub_note = "  [STUB]" if pred.is_stub else ""
        print(f"  specialist={finding.specialist_id:<28} model={pred.model_name:<30} "
              f"label={pred.label:<20} confidence={pred.confidence:.2f}{stub_note}")
        for exp in finding.explanations:
            stub_note = " [unavailable/stub]" if exp.is_stub else ""
            print(f"      [{exp.method}]{stub_note} {exp.summary}")


def main():
    router = ConditionRouter()

    # --- Breast cancer: auto-switches to histopathology (MIL) + genomic specialists ---
    # Now three specialist_ids: histopathology (UNI2-h/CLAM-current-tier, stub
    # here), genomic_variant (Evo 2, new — stub here, no GPU/HF access in this
    # sandbox) supplied with placeholder variant-window data, and the
    # existing Random Forest expression-panel model (real).
    rng = np.random.default_rng(7)
    report = router.route("breast cancer", {
        "genomic_breast_cancer": {"expression": rng.normal(size=20).tolist()},
        "genomic_variant_breast_cancer": {
            "reference_sequence": "ACGT" * 10,
            "alt_sequence": "ACGT" * 9 + "ACGA",
            "variant": {"chrom": "17", "pos": 43094692, "ref": "T", "alt": "A"},  # illustrative BRCA1-locus-shaped example, not a real call
        },
        "histopathology_breast_cancer": {"patch_features": None},  # stub ignores it in this sandbox
    })
    print_report(report)

    # --- Leukemia: a completely different pair of specialists, same router call shape ---
    report = router.route("leukaemia", {  # note: British spelling alias resolves correctly
        "cbc_leukemia": {"features": rng.normal(size=8).tolist()},
        "genomic_leukemia": {"expression": rng.normal(size=20).tolist()},
    })
    print_report(report)

    # --- Diabetic retinopathy: single imaging specialist ---
    report = router.route("diabetic retinopathy", {"retina": {"image": None}})
    print_report(report)

    # --- Heart disease: routes to the SAME vitals model module5 already had, with SHAP attached ---
    # Fit it here for the demo — in the real system this happens once via
    # module3's federated training loop, not per-request.
    vitals_specialist = router.specialists["vitals"]
    fit_X = rng.normal(size=(200, 8))
    fit_y = (fit_X[:, 0] + fit_X[:, 4] - fit_X[:, 3] > 0).astype(int)
    vitals_specialist.fit(fit_X, fit_y)

    report = router.route("heart_disease", {"vitals": {"features": rng.normal(size=8).tolist()}})
    print_report(report)

    # --- Unknown condition: clear error, not a silent wrong guess ---
    print("\n=== Condition: 'alien flu' (not registered) ===")
    try:
        router.route("alien flu", {})
    except UnknownConditionError as e:
        print(f"  {e}")


if __name__ == "__main__":
    main()
