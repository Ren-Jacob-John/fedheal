"""
Module 3 — Local Training + Federated Aggregation (FedAvg simulation)

Run: python simulate.py

WHY THIS DOESN'T USE flwr.simulation.start_simulation():
Flower's built-in simulation runner needs Ray for process-level isolation
between simulated clients, which is a heavy dependency and a common source
of version-conflict pain (protobuf, in particular) for very little benefit
at this stage — we don't need real multiprocessing to prove FedAvg works.

Instead, this script drives the federated rounds manually in a single
process, calling the exact same HospitalClient (fl.client.NumPyClient)
class you'd use in a real deployment. When you're ready for actual
networked hospitals, this same HospitalClient plugs into
fl.client.start_numpy_client() unchanged — only the round-driving loop
below gets replaced by Flower's real server (see server.py).

What this proves: 3 "hospitals" each train locally on their own (non-IID)
partition of data, only their model weights are ever centralized, the
server averages those weights (FedAvg), and the resulting global model
outperforms what any single hospital could train alone — the whole point
of the project.
"""
import os

import httpx
import numpy as np

from client import HospitalClient
from data import load_full_dataset, partition_for_hospitals, train_test_split_per_hospital
from model import build_model, get_model_parameters

N_HOSPITALS = 3
N_ROUNDS = 8

# Module 7 (Admin/Platform) integration — best-effort, same principle as
# Module 2's: this simulation must run identically whether or not the
# admin service is up. We're only ever sending round number / hospital
# count / accuracy numbers here, never any training data.
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
                "notes": "reported by simulate.py",
            },
            headers={"X-Service-Key": ADMIN_SERVICE_KEY},
            timeout=2.0,
        )
    except httpx.HTTPError:
        pass  # admin dashboard is a nice-to-have view, not a dependency of training itself


def federated_average(client_params: list[list[np.ndarray]], client_sizes: list[int]) -> list[np.ndarray]:
    """
    The FedAvg step: weighted average of each hospital's model update,
    weighted by how many local examples it trained on. This is the only
    thing that ever crosses the hospital -> server boundary — numbers, not data.
    """
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
    """
    What each hospital could achieve completely on its own, no federation —
    each hospital's model evaluated on the GLOBAL holdout (general patient
    population), not its own local test slice. This is the fair comparison:
    a hospital's model tested only against patients like its own looks
    artificially strong; federation's whole value proposition is
    generalizing to patients it never personally saw.
    """
    accuracies = []
    for X_train, X_test, y_train, y_test in hospital_splits:
        model = build_model()
        model.partial_fit(X_train, y_train, classes=np.array([0, 1]))
        accuracies.append(model.score(X_global_holdout, y_global_holdout))
    return float(np.mean(accuracies))


def main():
    print(f"Simulating {N_HOSPITALS} hospitals, {N_ROUNDS} federated rounds\n")

    X_pool, y_pool, X_global_holdout, y_global_holdout = load_full_dataset()
    partitions = partition_for_hospitals(X_pool, y_pool, n_hospitals=N_HOSPITALS, non_iid=True)
    hospital_splits = train_test_split_per_hospital(partitions)

    for i, (X_train, X_test, y_train, y_test) in enumerate(hospital_splits):
        pos_rate = y_train.mean()
        print(f"  hospital-{i}: {len(X_train)} train / {len(X_test)} local-test "
              f"records, positive-class rate {pos_rate:.2f}  (non-IID by design)")

    baseline_acc = run_local_only_baseline(hospital_splits, X_global_holdout, y_global_holdout)
    print(f"\nBaseline — each hospital trained ALONE, accuracy on the GLOBAL holdout "
          f"(patients unlike their own): {baseline_acc:.3f}")
    print("(this is what federation needs to beat — the fair comparison, not a hospital's own easy local slice)\n")

    clients = [
        HospitalClient(f"hospital-{i}", X_train, y_train, X_test, y_test)
        for i, (X_train, X_test, y_train, y_test) in enumerate(hospital_splits)
    ]

    global_params = get_model_parameters(build_model())

    print(f"{'round':>5} | {'global model acc. on global holdout':>36}")
    print("-" * 46)
    eval_model = build_model()
    for round_num in range(1, N_ROUNDS + 1):
        # --- one federated round: every hospital trains locally, only weights travel ---
        client_params, client_sizes = [], []
        for client in clients:
            new_params, n_examples, _ = client.fit(global_params, config={})
            client_params.append(new_params)
            client_sizes.append(n_examples)

        global_params = federated_average(client_params, client_sizes)

        # --- evaluate the new global model against the population no hospital fully represents ---
        eval_model.coef_, eval_model.intercept_ = global_params[0], global_params[1]
        eval_model.classes_ = np.array([0, 1])
        global_acc = eval_model.score(X_global_holdout, y_global_holdout)

        print(f"{round_num:>5} | {global_acc:>36.3f}")
        report_round_to_admin(round_num, N_HOSPITALS, global_acc, baseline_acc)

    print(f"\nFinal federated global model accuracy (global holdout): {global_acc:.3f}")
    print(f"Local-only baseline (global holdout):                    {baseline_acc:.3f}")
    if global_acc > baseline_acc:
        print("-> Federation generalizes better than any single hospital training alone. "
              "This is the result the whole project is built to demonstrate.")
    else:
        print("-> Federation did not beat the local-only baseline this run. With only "
              f"{N_ROUNDS} rounds and {N_HOSPITALS} hospitals on a synthetic dataset this can "
              "happen — try more rounds, more hospitals, or a lower Dirichlet alpha/higher alpha "
              "in data.py to see how skew affects convergence.")


if __name__ == "__main__":
    main()
