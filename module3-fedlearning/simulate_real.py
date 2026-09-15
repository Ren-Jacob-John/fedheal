"""
Module 3 — FedAvg over REAL, validated hospital data.

Run: python simulate_real.py

Same federated-averaging loop as simulate.py, same HospitalClient, same
model — the only thing that changes is where (X, y) comes from: instead of
data.py's synthetic Dirichlet partitions, real_data.py pulls each active
hospital's own validated vitals from Module 1 (which got them from Module 2).

Prerequisites (this is real integration, not a standalone demo):
  1. Module 1 (auth/vitals) running on :8001
  2. Module 2 (validation) running on :8002
  3. At least 2 hospitals registered in Module 1, each with >= MIN_RECORDS
     validated vitals uploaded (via the dashboard's upload form, or curl
     against POST /vitals/upload — see module1-auth/README.md)
  4. Same FEDHEAL_SVC_KEY_M3_M1 exported here as Module 1's
     FEDHEAL_SVC_KEY_M3_M1, so GET /vitals/export authenticates.

If fewer than 2 hospitals have enough data yet, this exits with instructions
rather than silently falling back to synthetic data — pretending real
integration ran when it didn't would be worse than just saying so.
"""
import argparse
import os
import sys

import httpx
import numpy as np

from client import HospitalClient
from fedavg import federated_average, run_local_only_baseline
from data import train_test_split_per_hospital
from model import build_model, get_model_parameters
from real_data import (
    load_real_partitions,
    carve_global_holdout,
    UnlabeledDataError,
    N_FEATURES,
)

MIN_RECORDS = 10
N_ROUNDS = 8

ADMIN_API_URL = os.environ.get("FEDHEAL_ADMIN_API_URL", "http://localhost:8005")
ADMIN_SERVICE_KEY = os.environ.get("FEDHEAL_SVC_KEY_M3_M7", "dev-only-key-module3-to-module7")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FedAvg over real, validated hospital data pulled from Module 1."
    )
    parser.add_argument(
        "--allow-placeholder-labels",
        action="store_true",
        help="Include records with NO real clinical outcome, labelling them "
             "with real_data._placeholder_label's rule-based stand-in. Off by "
             "default as of Sprint A. Runs using this are stamped as "
             "non-clinical in the round report sent to Module 7.",
    )
    return parser.parse_args()


def report_round_to_admin(round_number: int, n_hospitals: int,
                           global_accuracy: float, baseline_accuracy: float,
                           notes: str = "reported by simulate_real.py (real hospital data)") -> None:
    try:
        httpx.post(
            f"{ADMIN_API_URL}/admin/rounds",
            json={
                "round_number": round_number,
                "n_hospitals": n_hospitals,
                "global_accuracy": global_accuracy,
                "baseline_accuracy": baseline_accuracy,
                "notes": notes,
            },
            headers={"X-Service-Key": ADMIN_SERVICE_KEY},
            timeout=2.0,
        )
    except httpx.HTTPError:
        pass


def main():
    args = parse_args()

    print("Pulling active hospitals + validated vitals from Module 1...\n")
    try:
        hospital_names, partitions, provenances = load_real_partitions(
            min_records_per_hospital=MIN_RECORDS,
            allow_placeholder_labels=args.allow_placeholder_labels,
        )
    except UnlabeledDataError as e:
        print(f"\nRefusing to train on unlabeled data:\n{e}")
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Could not reach Module 1 (is it running on :8001?): {e}")
        sys.exit(1)

    # One line per hospital, before anything is trained, so the label story
    # is on screen ahead of every accuracy number this script prints.
    for prov in provenances:
        print(f"  {prov.banner()}")
    any_placeholder = any(not p.is_clean for p in provenances)
    if any_placeholder:
        print(
            "\n  ** This run mixes rule-based placeholder labels into training. **\n"
            "  ** Its accuracy figures are NOT a clinical result and are       **\n"
            "  ** stamped as such in the round report sent to Module 7.        **"
        )
    print()

    if len(partitions) < 2:
        print(
            f"\nOnly {len(partitions)} hospital(s) have >= {MIN_RECORDS} validated vitals "
            "records right now — need at least 2 for a meaningful federated round.\n"
            "Upload more vitals via the dashboard (module4-dashboard-react) for a couple of "
            "hospitals, then re-run this script. (simulate.py's synthetic version still "
            "works standalone in the meantime.)"
        )
        sys.exit(0)

    partitions, X_global_holdout, y_global_holdout = carve_global_holdout(partitions)
    if len(np.unique(y_global_holdout)) < 2:
        print(
            "\nGlobal holdout ended up single-class — every held-out record has the "
            "same outcome, so accuracy against it would be meaningless. Upload vitals "
            "covering both outcomes and try again (seed_uci_heart.py produces a "
            "164/139 split across hospitals if you need a realistic starting point)."
        )
        sys.exit(0)

    hospital_splits = train_test_split_per_hospital(partitions)

    for name, (X_train, X_test, y_train, y_test) in zip(hospital_names, hospital_splits):
        pos_rate = y_train.mean() if len(y_train) else float("nan")
        print(f"  {name}: {len(X_train)} train / {len(X_test)} local-test records, "
              f"positive-class rate {pos_rate:.2f}")

    baseline_acc = run_local_only_baseline(hospital_splits, X_global_holdout, y_global_holdout)
    print(f"\nBaseline — each hospital trained ALONE, accuracy on the global holdout: "
          f"{baseline_acc:.3f}\n")

    clients = [
        HospitalClient(name, X_train, y_train, X_test, y_test)
        for name, (X_train, X_test, y_train, y_test) in zip(hospital_names, hospital_splits)
    ]

    global_params = get_model_parameters(build_model())

    # Stamped onto every round row Module 7 stores, so a placeholder run
    # can't be mistaken for a clean one later when someone is reading the
    # rounds table months from now with none of this context.
    round_notes = (
        "reported by simulate_real.py — NON-CLINICAL: includes placeholder labels"
        if any_placeholder
        else "reported by simulate_real.py (real hospital data, real outcome labels)"
    )

    print(f"{'round':>5} | {'global model acc. on global holdout':>36}")
    print("-" * 46)
    eval_model = build_model()
    global_acc = baseline_acc
    for round_num in range(1, N_ROUNDS + 1):
        client_params, client_sizes = [], []
        for client in clients:
            new_params, n_examples, _ = client.fit(global_params, config={})
            client_params.append(new_params)
            client_sizes.append(n_examples)

        global_params = federated_average(client_params, client_sizes)

        eval_model.coef_, eval_model.intercept_ = global_params[0], global_params[1]
        eval_model.classes_ = np.array([0, 1])
        global_acc = eval_model.score(X_global_holdout, y_global_holdout)

        print(f"{round_num:>5} | {global_acc:>36.3f}")
        report_round_to_admin(round_num, len(clients), global_acc, baseline_acc, notes=round_notes)

    print(f"\nFinal federated global model accuracy (global holdout): {global_acc:.3f}")
    print(f"Local-only baseline (global holdout):                    {baseline_acc:.3f}")

    total_real = sum(p.real for p in provenances)
    total_placeholder = sum(p.placeholder for p in provenances)
    if any_placeholder:
        print(
            f"\nLabel provenance: {total_real} real clinical outcomes, "
            f"{total_placeholder} rule-based PLACEHOLDER labels (see real_data.py).\n"
            "These numbers demonstrate the pipeline works end-to-end. They are NOT "
            "clinical performance, because part of what the model learned to predict "
            "was invented by a rule."
        )
    else:
        print(
            f"\nLabel provenance: all {total_real} labels are real clinical outcomes "
            "uploaded by the hospitals — no placeholders in this run.\n"
            "Still not a clinical claim: this is logistic regression on a small "
            "number of vitals features, and (if seeded from seed_uci_heart.py) only "
            "3 of the 8 feature slots carry real measurements — see uci_heart.py."
        )


if __name__ == "__main__":
    main()
