import numpy as np

from client import HospitalClient
from model import build_model, get_model_parameters
from server import build_networked_candidate_payload


def _fit(hospital_id, request_id, count=10):
    return count, {
        "hospital_id": hospital_id,
        "retraining_request_id": request_id,
        "validated_training_examples": count,
        "hospital_label_training_examples": count,
    }


def _evaluate(hospital_id, request_id, count, accuracy, positives):
    return count, {
        "hospital_id": hospital_id,
        "retraining_request_id": request_id,
        "accuracy": accuracy,
        "positive_label_count": positives,
    }


def test_networked_fit_and_evaluation_messages_are_ids_counts_and_metrics_only():
    X = np.zeros((6, 8))
    y = np.array([0, 1, 0, 1, 0, 1])
    client = HospitalClient(
        "hospital-1", X, y, X, y,
        training_provenance={
            "validated_training_examples": len(X),
            "hospital_label_training_examples": len(X),
        },
        retraining_request_id="request-1",
    )

    weights, n_train, fit_metrics = client.fit(get_model_parameters(build_model()), {})
    loss, n_eval, eval_metrics = client.evaluate(weights, {})

    assert n_train == n_eval == len(X)
    assert all(isinstance(weight, np.ndarray) for weight in weights)
    assert set(fit_metrics) == {
        "hospital_id", "retraining_request_id",
        "validated_training_examples", "hospital_label_training_examples",
    }
    assert set(eval_metrics) == {
        "hospital_id", "retraining_request_id", "accuracy", "positive_label_count",
    }
    assert eval_metrics["positive_label_count"] == int(y.sum())


def test_networked_candidate_uses_verified_provenance_and_only_aggregate_payload():
    parameters = [np.zeros((1, 8)), np.zeros(1)]
    payload, reason = build_networked_candidate_payload(
        training_round=4,
        parameters=parameters,
        fit_results=[_fit("hospital-1", "request-1"), _fit("hospital-2", "request-2")],
        evaluate_results=[
            _evaluate("hospital-1", "request-1", 5, 0.8, 3),
            _evaluate("hospital-2", "request-2", 7, 0.6, 2),
        ],
        transport_encryption="server-authenticated TLS",
    )

    assert reason is None
    assert payload["training_round"] == 4
    assert payload["participating_hospitals"] == ["hospital-1", "hospital-2"]
    assert payload["training_metadata"]["retraining_request_ids"] == ["request-1", "request-2"]
    assert payload["training_metadata"]["validated_records_only"] is True
    assert payload["training_metadata"]["labels_from_hospital_only"] is True
    assert payload["training_metadata"]["transport_encryption"] == "server-authenticated TLS"
    assert payload["metrics"]["accuracy"] == (0.8 * 5 + 0.6 * 7) / 12
    assert payload["metrics"]["n_eval"] == 12
    assert np.isclose(payload["metrics"]["majority_class_floor"], 7 / 12)
    assert payload["metrics"]["eval_set"] == "pooled hospital-local test partitions"
    assert payload["artifact_hash"]
    assert payload["input_spec"]["feature_schema_version"] == "v1"
    assert "parameters" in payload
    assert "local_only_baseline_accuracy" not in payload["metrics"]


def test_networked_candidate_is_skipped_if_provenance_or_request_ids_are_missing():
    parameters = [np.zeros((1, 8)), np.zeros(1)]
    good_fit = _fit("hospital-1", "request-1")
    dirty_fit = (10, {
        **_fit("hospital-2", "request-2")[1],
        "validated_training_examples": 9,
    })
    evaluations = [
        _evaluate("hospital-1", "request-1", 5, 0.8, 3),
        _evaluate("hospital-2", "request-2", 5, 0.8, 3),
    ]

    missing_request, request_reason = build_networked_candidate_payload(
        training_round=1, parameters=parameters,
        fit_results=[good_fit, (10, {**good_fit[1], "hospital_id": "hospital-2",
                                    "retraining_request_id": ""})],
        evaluate_results=evaluations, transport_encryption="plaintext",
    )
    incomplete_provenance, provenance_reason = build_networked_candidate_payload(
        training_round=1, parameters=parameters,
        fit_results=[good_fit, dirty_fit], evaluate_results=evaluations,
        transport_encryption="plaintext",
    )

    assert missing_request is None and "request id" in request_reason
    assert incomplete_provenance is None and "provenance counts" in provenance_reason
