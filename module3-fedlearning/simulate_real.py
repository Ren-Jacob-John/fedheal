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
import os
import sys

import httpx
import numpy as np

from client import HospitalClient
from data import train_test_split_per_hospital
from model import build_model, get_model_parameters
from real_data import load_real_partitions, carve_global_holdout, N_FEATURES

MIN_RECORDS = 10
N_ROUNDS = 8

ADMIN_API_URL = os.environ.get("FEDHEAL_ADMIN_API_URL", "http://localhost:8005")
ADMIN_SERVICE_KEY = os.environ.get("FEDHEAL_SVC_KEY_M3_M7", "dev-only-key-module3-to-module7")


def report_round_to_admin(round_number: int, n_hospitals: int,
                           global_accuracy: float, baseline_accuracy: float) -> None:
    try:
        httpx.post(
            f"{ADMIN_API_URL}/admin/rounds",
            json={
                "round_number": round_number,
                "n_hospitals": n_hospitals,
                "global_accuracy": global_accuracy,
                "baseline_accuracy": baseline_accuracy,
                "notes": "reported by simulate_real.py (real hospital data)",
            },
            headers={"X-Service-Key": ADMIN_SERVICE_KEY},
            timeout=2.0,
        )
    except httpx.HTTPError:
        pass


def federated_average(client_params, client_sizes):
    total = sum(client_sizes)
    averaged = []
    for layer_idx in range(len(client_params[0])):
        weighted_sum = sum(
            params[layer_idx] * (size / total)
            for params, size in zip(client_params, client_sizes)
        )
        averaged.append(weighted_sum)
    return averaged


def run_local_only_baseline(hospital_splits, X_global_holdout, y_global_holdout) -> float:
    accuracies = []
    for X_train, X_test, y_train, y_test in hospital_splits:
        model = build_model()
        model.partial_fit(X_train, y_train, classes=np.array([0, 1]))
        accuracies.append(model.score(X_global_holdout, y_global_holdout))
    return float(np.mean(accuracies))


def main():
    print("Pulling active hospitals + validated vitals from Module 1...\n")
    try:
        hospital_names, partitions = load_real_partitions(min_records_per_hospital=MIN_RECORDS)
    except httpx.HTTPError as e:
        print(f"Could not reach Module 1 (is it running on :8001?): {e}")
        sys.exit(1)

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
            "\nGlobal holdout ended up single-class (all records look the same under the "
            "placeholder label — see real_data.py's docstring on why there's a placeholder "
            "label at all). Upload more varied vitals and try again."
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
        report_round_to_admin(round_num, len(clients), global_acc, baseline_acc)

    print(f"\nFinal federated global model accuracy (global holdout): {global_acc:.3f}")
    print(f"Local-only baseline (global holdout):                    {baseline_acc:.3f}")
    print(
        "\nReminder: labels here come from a rule-based PLACEHOLDER (see real_data.py) "
        "wherever a hospital hasn't uploaded a real diagnosis/outcome yet — these accuracy "
        "numbers demonstrate the pipeline works end-to-end, not clinical performance."
    )


if __name__ == "__main__":
    main()
