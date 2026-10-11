from argparse import Namespace
from types import SimpleNamespace

import pytest
import numpy as np

import client_runner
from real_data import load_real_partitions


def _args(**overrides):
    values = {
        "poll_seconds": 1,
        "include_flagged": False,
        "allow_placeholder_labels": False,
        "min_records": 5,
    }
    values.update(overrides)
    return Namespace(**values)


def test_watch_mode_refuses_flagged_or_placeholder_labels():
    with pytest.raises(ValueError, match="excludes flagged"):
        client_runner.watch_retraining(_args(include_flagged=True), "hospital-1")
    with pytest.raises(ValueError, match="excludes flagged"):
        client_runner.watch_retraining(_args(allow_placeholder_labels=True), "hospital-1")


def test_central_process_cannot_pool_raw_hospital_records():
    with pytest.raises(RuntimeError, match="Centralized real-data pooling is disabled"):
        load_real_partitions()


def test_watch_reports_only_count_and_excludes_flagged_and_placeholder_data(monkeypatch):
    monkeypatch.setenv("FEDHEAL_SVC_TOKEN_M3_M7", "hospital-scoped-token")
    loader_calls = []
    sent = []

    def load_partition(hospital_id, **kwargs):
        loader_calls.append((hospital_id, kwargs))
        return [[1.0, 2.0]], [1], object()

    def report(method, path, *, headers, json_body=None):
        sent.append((method, path, json_body))
        return object()

    def stop(_seconds):
        raise RuntimeError("stop test loop")

    monkeypatch.setattr(client_runner, "load_single_hospital_partition", load_partition)
    monkeypatch.setattr(client_runner, "_retraining_request", report)
    monkeypatch.setattr(client_runner.time, "sleep", stop)
    with pytest.raises(RuntimeError, match="stop test loop"):
        client_runner.watch_retraining(_args(), "hospital-1")

    assert loader_calls == [("hospital-1", {
        "min_records": 1, "include_flagged": False, "allow_placeholder_labels": False,
    })]
    assert sent == [("POST", "/admin/retraining/eligibility", {"eligible_records": 1})]


@pytest.mark.parametrize("registered,expected_status", [(True, "COMPLETED"), (False, "FAILED")])
def test_watch_completes_only_after_candidate_is_registered(monkeypatch, registered, expected_status):
    monkeypatch.setenv("FEDHEAL_SVC_TOKEN_M3_M7", "hospital-scoped-token")
    calls = []
    completions = []
    partition = (np.zeros((10, 8)), np.array([0, 1] * 5), SimpleNamespace(is_clean=True))
    monkeypatch.setattr(client_runner, "load_single_hospital_partition", lambda *_args, **_kwargs: partition)
    monkeypatch.setattr(
        client_runner, "_execute_partition",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    def response(data):
        return SimpleNamespace(json=lambda: data)

    def request(method, path, *, headers, json_body=None):
        if path == "/admin/retraining/eligibility":
            return response({"status": "queued"})
        if path == "/admin/retraining/requests/next":
            return response({"id": "request-1"})
        if path.endswith("/candidate"):
            return response({"registered": registered})
        if path == "/admin/retraining/requests/complete":
            completions.append(json_body)
            raise RuntimeError("stop after completion")
        raise AssertionError(f"Unexpected Module 7 request: {method} {path}")

    monkeypatch.setattr(client_runner, "_retraining_request", request)
    with pytest.raises(RuntimeError, match="stop after completion"):
        client_runner.watch_retraining(_args(min_records=1), "hospital-1")

    assert calls and calls[0][1]["retraining_request_id"] == "request-1"
    assert completions == [{
        "request_id": "request-1",
        "status": expected_status,
        "eligible_records": 10,
    }]
