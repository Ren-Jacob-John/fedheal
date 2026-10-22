"""
Module 5 — Model Zoo & Task Router (Stage 2)

Run: python demo.py

Demonstrates the "many specialist models, one router" pattern end to end:
  1. Build the registry (XGBoost for vitals is always real; imaging
     specialists are real if torch/torchvision are installed, otherwise a
     clearly labeled stub stands in — see registry.py).
  2. Route several different-modality cases through MetadataRouter, each
     to its own specialist, proving they coexist without interfering.
  3. Fuse two specialists' results for one "patient" (vitals + a chest
     X-ray finding) into one overall risk assessment via FusionLayer.
"""
import numpy as np

from fusion import FusionLayer
from models.tabular_vitals import XGBoostVitalsModel
from registry import build_registry, registry_status
from router import MetadataRouter


def make_synthetic_vitals_model() -> XGBoostVitalsModel:
    """
    Quick local fit so the vitals specialist is real and usable in this demo
    — same synthetic-data idea as module3-fedlearning's simulation, kept
    independent here since this module's job is proving the ROUTER works,
    not re-deriving the federated training loop.
    """
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 8))
    y = (X[:, 0] + X[:, 4] - X[:, 3] > 0).astype(int)  # arbitrary separable rule
    model = XGBoostVitalsModel()
    model.fit(X, y)
    return model


def print_registry_table(registry):
    print("Model zoo contents:")
    print(f"  {'modality':<12} {'model_name':<32} {'task':<15} {'real?'}")
    for row in registry_status(registry):
        print(f"  {row['modality']:<12} {row['model_name']:<32} {row['task']:<15} {row['real']}")
    print()


def main():
    vitals_model = make_synthetic_vitals_model()
    registry = build_registry(fitted_vitals_model=vitals_model)
    print_registry_table(registry)

    router = MetadataRouter(registry)

    # --- Route a batch of single-modality cases, proving specialists coexist ---
    cases = [
        {"modality": "vitals", "features": [0.9, 0.1, -0.2, -0.8, 0.7, 0.0, 1, 0]},
        {"modality": "chest_xray", "image": None},   # real model needs a tensor; stub ignores it
        {"modality": "retina", "image": None},
        {"modality": "skin", "image": None},
        {"modality": "ct_scan", "image": None},
    ]

    print("Routing individual cases:\n")
    results = []
    for case in cases:
        result = router.route(case)
        results.append(result)
        stub_note = "  [STUB — real model not installed in this env]" if result.is_stub else ""
        print(f"  modality={result.modality:<10} -> {result.model_name:<32} "
              f"label={result.label:<20} confidence={result.confidence:.2f}{stub_note}")

    # --- Fuse vitals + chest_xray results for one patient into an overall assessment ---
    print("\nFusing vitals + chest_xray for one patient:")
    patient_results = [results[0], results[1]]  # vitals + chest_xray from above
    assessment = FusionLayer().combine(patient_results)

    print(f"  overall_risk_score = {assessment.overall_risk_score}")
    print(f"  risk_level         = {assessment.risk_level}")
    print(f"  used_any_stub_models = {assessment.used_any_stub_models}")
    for f in assessment.contributing_findings:
        print(f"    - {f['model_name']}: {f['label']} "
              f"(confidence={f['confidence']:.2f}, severity_weight={f['severity_weight']})")
    if assessment.urgent_review_flags:
        print(f"  URGENT REVIEW FLAGS: {assessment.urgent_review_flags}")


if __name__ == "__main__":
    main()
