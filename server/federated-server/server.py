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

client_runner.py exists now and has been verified with local networked
clients. Server-authenticated TLS is available when all three certificate
paths are supplied. The corresponding client adapter does not support
client-certificate mTLS.
"""
import argparse
from pathlib import Path
from typing import List, Tuple

import flwr as fl
import numpy as np
from flwr.common import Metrics
from flwr.server.client_proxy import ClientProxy

import federation_registry
from model import build_model, get_model_parameters
from real_data import (
    FEATURE_KEYS,
    FEATURE_SCHEMA_VERSION,
    N_FEATURES,
    feature_transform,
)


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

    def __init__(self, *args, candidate_round: int, transport_encryption: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate_round = candidate_round
        self.transport_encryption = transport_encryption
        self.final_fit_round = None
        self.final_fit_results = None
        self.final_parameters = None
        self.final_fit_complete = False
        self.final_evaluate_round = None
        self.final_evaluate_results = None
        self.final_evaluate_complete = False

    @staticmethod
    def _sort_by_hospital_id(results):
        return sorted(results, key=lambda r: r[1].metrics.get("hospital_id", ""))

    def aggregate_fit(self, server_round, results: List[Tuple[ClientProxy, "fl.common.FitRes"]], failures):
        ordered = self._sort_by_hospital_id(results)
        aggregated = super().aggregate_fit(server_round, ordered, failures)
        parameters, _ = aggregated if aggregated is not None else (None, {})
        self.final_fit_round = server_round
        self.final_fit_complete = bool(parameters is not None and not failures)
        self.final_fit_results = [
            (int(result.num_examples), dict(result.metrics))
            for _, result in ordered
        ]
        self.final_parameters = (
            fl.common.parameters_to_ndarrays(parameters) if parameters is not None else None
        )
        return aggregated

    def aggregate_evaluate(self, server_round, results: List[Tuple[ClientProxy, "fl.common.EvaluateRes"]], failures):
        ordered = self._sort_by_hospital_id(results)
        aggregated = super().aggregate_evaluate(server_round, ordered, failures)
        self.final_evaluate_round = server_round
        self.final_evaluate_complete = bool(ordered and not failures)
        self.final_evaluate_results = [
            (int(result.num_examples), dict(result.metrics))
            for _, result in ordered
        ]
        if server_round == self.candidate_round:
            self.register_final_candidate()
        return aggregated

    def register_final_candidate(self) -> None:
        if (self.final_fit_round != self.final_evaluate_round
                or not self.final_fit_complete or not self.final_evaluate_complete
                or self.final_parameters is None):
            print("CANDIDATE_REGISTRATION_SKIPPED: final round lacks complete fit/evaluation results.")
            return
        candidate, reason = build_networked_candidate_payload(
            training_round=self.final_fit_round,
            parameters=self.final_parameters,
            fit_results=self.final_fit_results or [],
            evaluate_results=self.final_evaluate_results or [],
            transport_encryption=self.transport_encryption,
        )
        if candidate is None:
            print(f"CANDIDATE_REGISTRATION_SKIPPED: {reason}")
            return
        stored = federation_registry.register_candidate(candidate)
        if stored is None:
            print("CANDIDATE_REGISTRATION_FAILED: Module 7 is unreachable; no candidate was registered.")
        elif "error" in stored:
            print(f"CANDIDATE_REGISTRATION_FAILED: Module 7 refused the candidate: {stored}")
        else:
            print(f"Registered candidate {stored['version']} (status {stored['deployment_status']}). "
                  "It is not validated or deployed.")


def build_networked_candidate_payload(*, training_round: int, parameters: list[np.ndarray],
                                      fit_results: list[tuple[int, dict]],
                                      evaluate_results: list[tuple[int, dict]],
                                      transport_encryption: str) -> tuple[dict | None, str | None]:
    """Build a registry candidate only from complete count/ID provenance and aggregate metrics."""
    if not fit_results or len(fit_results) < 2:
        return None, "fewer than two hospital fit results"

    participants = {}
    request_ids = []
    for n_examples, metrics in fit_results:
        hospital_id = metrics.get("hospital_id")
        request_id = metrics.get("retraining_request_id")
        if (not isinstance(hospital_id, str) or not hospital_id
                or hospital_id in participants):
            return None, "fit results have missing or duplicate hospital ids"
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return None, "fit result is missing its retraining request id"
        validated_count = metrics.get("validated_training_examples")
        hospital_label_count = metrics.get("hospital_label_training_examples")
        if (isinstance(n_examples, bool) or not isinstance(n_examples, int) or n_examples <= 0
                or isinstance(validated_count, bool) or not isinstance(validated_count, int)
                or validated_count != n_examples
                or isinstance(hospital_label_count, bool) or not isinstance(hospital_label_count, int)
                or hospital_label_count != n_examples):
            return None, "fit result provenance counts do not cover the training examples"
        participants[hospital_id] = request_id
        request_ids.append(request_id)
    if len(set(request_ids)) != len(request_ids):
        return None, "retraining request ids are not unique per hospital"

    if not evaluate_results:
        return None, "no evaluation results"
    per_hospital_accuracy = {}
    total_eval = 0
    weighted_accuracy = 0.0
    positive_labels = 0
    for n_eval, metrics in evaluate_results:
        hospital_id = metrics.get("hospital_id")
        request_id = metrics.get("retraining_request_id")
        accuracy = metrics.get("accuracy")
        positive_count = metrics.get("positive_label_count")
        if (not isinstance(hospital_id, str) or hospital_id not in participants
                or hospital_id in per_hospital_accuracy):
            return None, "evaluation results do not uniquely match fit participants"
        if request_id != participants[hospital_id]:
            return None, "evaluation result does not match the hospital's retraining request"
        if (isinstance(n_eval, bool) or not isinstance(n_eval, int) or n_eval <= 0
                or isinstance(positive_count, bool) or not isinstance(positive_count, int)
                or positive_count < 0 or positive_count > n_eval):
            return None, "evaluation counts are missing or invalid"
        if (isinstance(accuracy, bool) or not isinstance(accuracy, (int, float))
                or not np.isfinite(accuracy) or not 0 <= accuracy <= 1):
            return None, "evaluation accuracy is missing or invalid"
        per_hospital_accuracy[hospital_id] = float(accuracy)
        total_eval += n_eval
        weighted_accuracy += float(accuracy) * n_eval
        positive_labels += positive_count
    if set(per_hospital_accuracy) != set(participants):
        return None, "not all fit participants supplied evaluation results"

    mean, scale = feature_transform(FEATURE_SCHEMA_VERSION)
    params = [np.asarray(value) for value in parameters]
    if (len(params) != 2 or params[0].shape != (1, N_FEATURES) or params[1].shape != (1,)
            or not all(np.isfinite(value).all() for value in params)):
        return None, "aggregated model parameters have an invalid shape or non-finite values"
    positive_rate = positive_labels / total_eval
    majority_floor = max(positive_rate, 1 - positive_rate)
    payload = federation_registry.build_candidate_payload(
        condition="heart_disease",
        training_round=training_round,
        hospital_labels=list(participants),
        global_accuracy=weighted_accuracy / total_eval,
        n_eval=total_eval,
        per_hospital_accuracy=per_hospital_accuracy,
        local_only_baseline=None,
        majority_class_floor=majority_floor,
        digest=federation_registry.artifact_hash(params),
        provenances=None,
        labels_from_hospital_only=True,
        data_source="hospital_validated_vitals_via_module1",
        params=params,
        input_spec={
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_names": list(FEATURE_KEYS),
            "center": [float(value) for value in mean],
            "scale": [float(value) for value in scale],
        },
        transport_encryption=transport_encryption,
        retraining_request_ids=request_ids,
        eval_set="pooled hospital-local test partitions",
    )
    return payload, None


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
    parser.add_argument("--ca-cert", help="PEM CA certificate used to configure Flower TLS.")
    parser.add_argument("--server-cert", help="PEM server certificate; requires --ca-cert and --server-key.")
    parser.add_argument("--server-key", help="PEM server private key; requires --ca-cert and --server-cert.")
    return parser.parse_args()


def load_tls_certificates(ca_cert: str | None, server_cert: str | None,
                          server_key: str | None) -> tuple[bytes, bytes, bytes] | None:
    paths = (ca_cert, server_cert, server_key)
    if not any(paths):
        return None
    if not all(paths):
        raise ValueError("--ca-cert, --server-cert, and --server-key must be provided together")
    return tuple(Path(path).read_bytes() for path in paths)


def main() -> None:
    args = parse_args()
    try:
        certificates = load_tls_certificates(args.ca_cert, args.server_cert, args.server_key)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Invalid Flower TLS configuration: {exc}") from exc
    if args.min_clients < 2:
        # FedAvg-ing 1 client's weights with itself isn't federation —
        # fail loudly rather than silently "running" something meaningless.
        raise SystemExit(
            f"--min-clients must be >= 2 (got {args.min_clients}); "
            "federated averaging needs at least 2 hospitals to mean anything."
        )

    initial_parameters = fl.common.ndarrays_to_parameters(get_model_parameters(build_model(N_FEATURES)))

    strategy = DeterministicFedAvg(
        candidate_round=args.rounds,
        transport_encryption="server-authenticated TLS" if certificates else "plaintext",
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
        certificates=certificates,
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
