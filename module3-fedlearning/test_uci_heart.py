"""
Checks on the vendored UCI Heart Disease dataset and its mapping onto the
vitals schema.

Run: python test_uci_heart.py     (exit 0 = pass, 1 = fail)

Plain asserts and a main(), matching this folder's existing convention
(`test_client_runner_matches_simulation.py`) rather than introducing pytest
mid-sprint. Dedicated per-module unit testing is Sprint C.

The two tests that earn their place here:

  * the fidelity tests, because "is this actually the cited dataset or a
    Kaggle re-derivation?" is not answerable by reading the file, and
  * test_unsupplied_fields_normalize_to_zero, because the claim that the
    5 constant features contribute nothing is load-bearing for how every
    accuracy number from this data gets described. It's true only as long
    as those constants match real_data._FEATURE_MEAN — a relationship
    spanning two files with nothing but a comment to hold it together.
"""
import sys
import traceback

import numpy as np

import uci_heart
from real_data import _FEATURE_MEAN, _record_to_features, FEATURE_KEYS


def test_dataset_integrity():
    """The vendored file is the exact one datasets/README.md documents."""
    digest = uci_heart.verify_dataset()
    assert digest == uci_heart.DATASET_SHA256


def test_published_fidelity_markers():
    """
    Published characteristics of the Cleveland subset. A file that matches
    all four is the real dataset; the circulating Kaggle variants fail at
    least one (the 1025-row version has duplicated rows; the 303-row
    version has no missing values because they were imputed away).
    """
    rows = uci_heart.load_raw_rows()
    assert len(rows) == uci_heart.EXPECTED_ROWS, len(rows)

    positives = sum(r["label"] for r in rows)
    assert positives == uci_heart.EXPECTED_POSITIVE, positives
    assert len(rows) - positives == uci_heart.EXPECTED_NEGATIVE

    assert min(r["age"] for r in rows) == 29.0
    assert max(r["age"] for r in rows) == 77.0
    assert min(r["trestbps"] for r in rows) == 94.0
    assert max(r["trestbps"] for r in rows) == 200.0
    assert min(r["thalach"] for r in rows) == 71.0
    assert max(r["thalach"] for r in rows) == 202.0

    # Exactly 6 missing values, 4 in `ca` and 2 in `thal`. Their survival
    # is the strongest single signal this wasn't run through someone's
    # cleaning notebook before it reached us.
    assert sum(1 for r in rows if r["ca"] is None) == uci_heart.EXPECTED_MISSING["Ca"]
    assert sum(1 for r in rows if r["thal"] is None) == uci_heart.EXPECTED_MISSING["Thal"]


def test_every_record_has_a_real_label():
    """
    The entire reason for the Sprint A swap: no record from this dataset
    should ever reach Module 3's placeholder-label path.
    """
    records = uci_heart.load_vitals_records()
    assert len(records) == uci_heart.EXPECTED_ROWS
    assert all(r["label"] in (0, 1) for r in records)
    assert not [r for r in records if r.get("label") is None]


def test_unsupplied_fields_normalize_to_zero():
    """
    The load-bearing invariant. The 5 features Cleveland doesn't measure
    are set to constants pinned to real_data._FEATURE_MEAN, so after
    normalization they are exactly 0.0 and contribute nothing to any
    gradient.

    If someone retunes _FEATURE_MEAN without updating NOT_SUPPLIED_BY_UCI,
    this fails — instead of quietly reintroducing a constant non-zero bias
    term into every model trained on seeded data, while every doc in the
    repo keeps claiming the contribution is zero.
    """
    records = uci_heart.load_vitals_records()
    X = np.stack([_record_to_features(r) for r in records])

    for field in uci_heart.NOT_SUPPLIED_BY_UCI:
        col = FEATURE_KEYS.index(field)
        assert np.allclose(X[:, col], 0.0), (
            f"{field} (column {col}) does not normalize to zero. "
            f"NOT_SUPPLIED_BY_UCI[{field}]={uci_heart.NOT_SUPPLIED_BY_UCI[field]} "
            f"but _FEATURE_MEAN[{col}]={_FEATURE_MEAN[col]} — these must match."
        )

    # ...and the real ones must NOT be constant, or the seed carries no signal.
    for field in uci_heart.REAL_FEATURE_KEYS:
        col = FEATURE_KEYS.index(field)
        assert X[:, col].std() > 0.01, f"{field} is constant — the mapping is broken"


def test_constants_pass_module2_cross_field_rules():
    """
    The seed only works if these constants survive Module 2's validator.
    Re-checks the specific rules they were chosen against, so a rule change
    in Module 2 surfaces here rather than as 303 mystery rejections during
    a demo seed run.
    """
    c = uci_heart.NOT_SUPPLIED_BY_UCI
    records = uci_heart.load_vitals_records()

    # diastolic < systolic, for every real trestbps in the file
    assert c["diastolic_bp"] < min(r["systolic_bp"] for r in records)

    # implied BMI inside Module 2's [8, 90] sanity band
    bmi = c["weight_kg"] / (c["height_cm"] / 100) ** 2
    assert 8 <= bmi <= 90, bmi

    # medication_count and medication_mg_total must agree (both zero or both non-zero)
    assert (c["medication_count"] > 0) == (c["medication_mg_total"] > 0)

    # the under-2s medication rule can't trip: Cleveland's youngest is 29
    assert min(r["age_years"] for r in records) >= 2


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
        else:
            print(f"pass  {test.__name__}")

    print()
    if failures:
        print(f"{failures} of {len(tests)} tests FAILED")
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
