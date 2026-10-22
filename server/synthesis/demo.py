"""
Run: python demo.py

Exercises build_synthesis() against synthetic (fake, not-real-patient)
cases — the same scenarios Module 6's demo.py uses, plus a partial-data
case and an unknown-condition case, to prove the review packet degrades
gracefully rather than fabricating confidence where there's no data.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "module6-condition-router"))
sys.path.insert(0, str(Path(__file__).parent.parent / "module5-modelzoo"))

from condition_router import ConditionRouter, UnknownConditionError  # noqa: E402
from conditions import resolve_condition  # noqa: E402
from fusion import FusionLayer  # noqa: E402
from synthesis import build_synthesis  # noqa: E402


def run(router, condition_name, case_data, fuse=False):
    spec = resolve_condition(condition_name)
    report = router.route(condition_name, case_data)
    fused = None
    if fuse and report.findings:
        fused = FusionLayer().combine([f.prediction for f in report.findings])
    synthesis = build_synthesis(report, spec.specialist_ids, fused=fused)
    print(synthesis.to_markdown())
    print("\n" + "=" * 80 + "\n")


def main():
    router = ConditionRouter()
    rng = np.random.default_rng(7)

    # Full data, two specialists -> fused risk score
    run(router, "breast cancer", {
        "genomic_breast_cancer": {"expression": rng.normal(size=20).tolist()},
        "histopathology_breast_cancer": {"patch_features": None},
    }, fuse=True)

    # Full data, different condition
    run(router, "leukaemia", {
        "cbc_leukemia": {"features": rng.normal(size=8).tolist()},
        "genomic_leukemia": {"expression": rng.normal(size=20).tolist()},
    }, fuse=True)

    # Partial data on purpose: diabetic_retinopathy only defines one
    # specialist, so simulate a condition with two specialists but only
    # supply one, to prove `data_completeness` surfaces the gap.
    run(router, "breast cancer", {
        "genomic_breast_cancer": {"expression": rng.normal(size=20).tolist()},
        # histopathology_breast_cancer deliberately omitted
    })

    # Single-specialist condition
    vitals_specialist = router.specialists["vitals"]
    fit_X = rng.normal(size=(200, 8))
    fit_y = (fit_X[:, 0] + fit_X[:, 4] - fit_X[:, 3] > 0).astype(int)
    vitals_specialist.fit(fit_X, fit_y)
    run(router, "heart_disease", {"vitals": {"features": rng.normal(size=8).tolist()}})

    # Unknown condition -> synthesis layer never runs; router's explicit
    # error is the correct behavior, not something to paper over.
    try:
        router.route("alien flu", {})
    except UnknownConditionError as e:
        print(f"Unknown condition, no report generated (correct): {e}")


if __name__ == "__main__":
    main()
