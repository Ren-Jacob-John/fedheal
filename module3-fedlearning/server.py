"""
Real (networked) Flower server — what Module 3 graduates to once hospitals
are actual separate machines instead of one simulate.py process. Not used
by simulate.py; kept here so the jump from "simulation on my laptop" to
"real server + real hospital clients" is a small, obvious step rather than
a rewrite.

Run the server:
    python server.py
Run a client (from a "hospital" machine — see client_runner.py):
    python client_runner.py --hospital-name "General Hospital" --server localhost:8080

client_runner.py exists now (was next-sprint work as of this docstring's
last version) — verified end-to-end with 2, then 3+, real networked
clients. TLS is still explicitly out of scope; see
docs/development-plan-to-oct20.md's cut list.
"""
import argparse
from typing import List, Tuple

import flwr as fl
from flwr.common import Metrics
from flwr.server.client_proxy import ClientProxy

from model import build_model, get_model_parameters


def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    """
    Flower's FedAvg aggregates weights by default but NOT the custom
    metrics HospitalClient.evaluate() returns (accuracy, hospital_id) —
    without this, `history.metrics_distributed` stays empty and nobody
    watching the server (or a script checking its work, e.g.
    test_client_runner_matches_simulation.py) can see a global accuracy
    number, only per-round loss. Same weighted-by-example-count math as
    simulate.py/simulate_real.py's federated_average() uses for weights.
    """
    total_examples = sum(n for n, _ in metrics)
    if total_examples == 0:
        return {"accuracy": 0.0}
    weighted_acc = sum(m["accuracy"] * n for n, m in metrics) / total_examples
    return {"accuracy": weighted_acc}


class DeterministicFedAvg(fl.server.strategy.FedAvg):
    """
    Plain FedAvg aggregates client results in whatever order they arrive
    over the network — a race depending on connection/response timing,
    not something the server controls. That's invisible with a
    well-separated model, but this sprint's sanity-check test
    (test_client_runner_matches_simulation.py) surfaced that with THIS
    model (SGDClassifier via partial_fit, small feature/sample counts,
    predictions often landing near the 0.5 decision boundary) floating-
    point summation order ALONE — same clients, same data, same code —
    was enough to swing a single round's reported accuracy by double
    digits. Not a correctness bug in the averaging math, but bad for a
    healthcare system either way: "same inputs, same result" is a
    reasonable bar for something that will inform care decisions, and
    right now plain FedAvg can't promise it.

    Sorting by hospital_id (not Flower's own per-connection ClientProxy.cid,
    which is a connection identifier, not our identity) before aggregating
    makes a run's result depend only on the data and the code, not on
    network timing — and is what makes comparing a real run against an
    in-process reproduction meaningful at all.
    """

    @staticmethod
    def _sort_by_hospital_id(results):
        return sorted(results, key=lambda r: r[1].metrics.get("hospital_id", ""))

    def aggregate_fit(self, server_round, results: List[Tuple[ClientProxy, "fl.common.FitRes"]], failures):
        return super().aggregate_fit(server_round, self._sort_by_hospital_id(results), failures)

    def aggregate_evaluate(self, server_round, results: List[Tuple[ClientProxy, "fl.common.EvaluateRes"]], failures):
        return super().aggregate_evaluate(server_round, self._sort_by_hospital_id(results), failures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the real Flower FL server.")
    parser.add_argument(
        "--min-clients",
        type=int,
        default=2,
        help="Minimum hospitals that must be connected before a round "
             "starts, and minimum results required to aggregate (default: 2 "
             "— below that, FedAvg isn't averaging anything meaningful). "
             "Applied to min_fit_clients, min_evaluate_clients, and "
             "min_available_clients alike.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=8,
        help="Number of federated rounds to run (default: 8).",
    )
    parser.add_argument(
        "--address",
        default="0.0.0.0:8080",
        help="Address the server listens on (default: 0.0.0.0:8080).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.min_clients < 2:
        # FedAvg-ing 1 client's weights with itself isn't federation —
        # fail loudly rather than silently "running" something meaningless.
        raise SystemExit(
            f"--min-clients must be >= 2 (got {args.min_clients}); "
            "federated averaging needs at least 2 hospitals to mean anything."
        )

    initial_parameters = fl.common.ndarrays_to_parameters(get_model_parameters(build_model()))

    strategy = DeterministicFedAvg(
        fraction_fit=1.0,                       # use all connected hospitals every round
        fraction_evaluate=1.0,
        min_fit_clients=args.min_clients,
        min_evaluate_clients=args.min_clients,
        min_available_clients=args.min_clients,
        initial_parameters=initial_parameters,
        evaluate_metrics_aggregation_fn=weighted_average,
    )

    print(f"Starting Flower server on {args.address} — "
          f"waiting for >= {args.min_clients} hospital clients, {args.rounds} rounds.")

    history = fl.server.start_server(
        server_address=args.address,
        config=fl.server.ServerConfig(num_rounds=args.rounds),
        strategy=strategy,
    )

    # Printed in a fixed, greppable shape so both humans watching the log and
    # scripts (run_local_smoke_test.sh, test_client_runner_matches_simulation.py)
    # can pull the final number out without parsing Flower's own log formatting.
    if history.metrics_distributed.get("accuracy"):
        final_round, final_acc = history.metrics_distributed["accuracy"][-1]
        print(f"FINAL_ACCURACY: {final_acc:.4f} (round {final_round})")
    else:
        print("FINAL_ACCURACY: unavailable (no evaluate rounds completed)")


if __name__ == "__main__":
    main()
