"""
The two functions that define what "federated vs solo" actually measures.

Extracted in Sprint A because `compare_uci_heart.py` needs exactly the same
aggregation and baseline as `simulate_real.py`, and a second copy of
weighted averaging is the kind of thing that drifts by a factor of
`len(clients)` six months from now and quietly changes every number in the
final report. One implementation, imported by both.

Deliberately free of `flwr` and `httpx` imports, so the offline comparison
script can use it with no network stack and no Flower install. The
networked path (`server.py` / `client_runner.py`) uses Flower's own
aggregate() instead — `test_client_runner_matches_simulation.py` is the
check that those two agree.
"""
import numpy as np

from model import build_model


def federated_average(client_params, client_sizes):
    """
    FedAvg (McMahan et al. 2017): average each layer across clients,
    weighted by how many examples each client trained on — so a hospital
    with 200 records counts for more than one with 20, which is the whole
    reason FedAvg works on unbalanced real-world partitions.
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
    The number federation has to beat: each hospital trains alone on its own
    data only, and is scored on the SAME global holdout the federated model
    is scored on.

    Scoring solo models on the global holdout rather than on their own local
    test split is the part that makes this comparison honest. A hospital's
    local test set shares its local skew, so a solo model looks strong on it
    for reasons that have nothing to do with generalizing — which is exactly
    the illusion federation is supposed to dispel.
    """
    accuracies = []
    for X_train, X_test, y_train, y_test in hospital_splits:
        model = build_model()
        model.partial_fit(X_train, y_train, classes=np.array([0, 1]))
        accuracies.append(model.score(X_global_holdout, y_global_holdout))
    return float(np.mean(accuracies))
