"""
Real (networked) Flower client — the piece server.py's docstring calls out
as "next-sprint work" and simulate.py/simulate_real.py's docstrings both
point to. Run one of these per hospital, in that hospital's own process
(or, for a real deployment, that hospital's own machine), pointed at the
central server.py. It reuses the exact same HospitalClient class the
in-process simulations use — only fit()/evaluate()'s caller changes, from
a manual Python loop to Flower's real gRPC server. As always: only model
weights ever cross this wire, never this hospital's (X, y).

Prerequisites (same shape as simulate_real.py's):
  1. Module 1 (auth/vitals) reachable at FEDHEAL_AUTH_API_URL
     (default http://localhost:8001).
  2. This hospital already has >= --min-records validated vitals uploaded
     (dashboard upload form, or POST /vitals/upload / /validate/vitals/csv).
  3. FEDHEAL_SVC_TOKEN_M3_M1 exported here (a token scoped to THIS hospital, minted with module1-auth/mint_service_token.py), so
     GET /vitals/export authenticates (see real_data.py).

Usage — start the server once:
    python server.py

...then one process per hospital, each pointed at that same server:
    python client_runner.py --hospital-name "General Hospital" --server localhost:8080
    python client_runner.py --hospital-id 3f9c2e11-... --server localhost:8080

Need 2+ of these running (server.py's FedAvg strategy sets
min_available_clients=2) before a round will actually start.

TLS defaults to insecure/plaintext for compatibility with a localhost demo.
For server-authenticated TLS, start server.py with its CA/server certificate
and private key, then pass --secure and (for a private CA) --root-certificates.
Client-certificate mTLS is not supported by this Flower client adapter.
"""
import argparse
import os
import sys
import time

import httpx
import numpy as np
from sklearn.model_selection import train_test_split

import flwr as fl

from client import HospitalClient
from real_data import load_single_hospital_partition, resolve_hospital_id

ADMIN_API_URL = os.environ.get("FEDHEAL_ADMIN_API_URL", "http://localhost:8005")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one hospital's real, networked Flower client."
    )
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument(
        "--hospital-id",
        help="Hospital's DB id (UUID), as returned by GET /hospitals.",
    )
    id_group.add_argument(
        "--hospital-name",
        help="Hospital's display name — resolved to its id via GET /hospitals.",
    )
    parser.add_argument(
        "--server",
        default="localhost:8080",
        help="Flower server address (default: localhost:8080, matching server.py).",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        default=10,
        help="Refuse to start if this hospital has fewer validated records "
             "than this (default: 10, matching simulate_real.py's MIN_RECORDS).",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Fraction of this hospital's own data held out locally for "
             "evaluate() — never shared with the server (default: 0.2).",
    )
    parser.add_argument(
        "--include-flagged",
        action="store_true",
        help="Train on this hospital's flagged-but-not-yet-reviewed records "
             "too, not just passed ones. Off by default — flagged records "
             "haven't been human-approved yet (see FlaggedReview.jsx).",
    )
    parser.add_argument(
        "--allow-placeholder-labels",
        action="store_true",
        help="Train on records that have NO real clinical outcome, using "
             "real_data._placeholder_label's rule-based stand-in. Off by "
             "default as of Sprint A: without this, unlabeled records are "
             "excluded server-side and an all-unlabeled hospital fails "
             "loudly. Only for demos on a hospital that hasn't wired up "
             "outcomes yet — any accuracy from such a run is NOT clinical.",
    )
    parser.add_argument(
        "--secure",
        dest="insecure",
        action="store_false",
        help="Use TLS instead of plaintext gRPC. The server must be started with TLS certificates.",
    )
    parser.add_argument(
        "--root-certificates",
        help="Optional PEM root CA file for verifying a private Flower server certificate.",
    )
    parser.add_argument(
        "--watch-retraining",
        action="store_true",
        help="Poll Module 7 for durable hospital-scoped retraining requests. "
             "Requires FEDHEAL_SVC_TOKEN_M3_M7; queue thresholds are OFF by default.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=60,
        help="Seconds between retraining queue checks in watch mode (default: 60).",
    )
    parser.set_defaults(insecure=True)
    return parser.parse_args()


def _retraining_headers() -> dict[str, str]:
    token = os.environ.get("FEDHEAL_SVC_TOKEN_M3_M7", "").strip()
    if not token:
        raise RuntimeError(
            "Watch mode requires a hospital-scoped FEDHEAL_SVC_TOKEN_M3_M7 "
            "minted by module7-admin/mint_retraining_runner_token.py."
        )
    return {"X-Service-Key": token}


def _retraining_request(method: str, path: str, *, headers: dict, json_body: dict | None = None) -> httpx.Response:
    response = httpx.request(method, f"{ADMIN_API_URL}{path}", headers=headers, json=json_body, timeout=10)
    response.raise_for_status()
    return response


def _execute_partition(args: argparse.Namespace, hospital_id: str, X, y, provenance,
                       retraining_request_id: str | None = None) -> None:
    print(f"  {provenance.banner()}")
    classes, counts = np.unique(y, return_counts=True)
    stratify = y if len(classes) > 1 and counts.min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=42, stratify=stratify,
    )
    print(
        f"  {len(X_train)} train / {len(X_test)} local-test records, "
        f"positive-class rate {y_train.mean():.2f} — this data never leaves this process."
    )
    client = HospitalClient(
        hospital_id, X_train, y_train, X_test, y_test,
        training_provenance={
            "validated_training_examples": 0 if args.include_flagged else len(X_train),
            "hospital_label_training_examples": 0 if not provenance.is_clean else len(X_train),
        },
        retraining_request_id=retraining_request_id,
    )
    print(f"Connecting to Flower server at {args.server} "
          f"({'insecure' if args.insecure else 'TLS'})...")
    fl.client.start_client(
        server_address=args.server,
        client=client.to_client(),
        insecure=args.insecure,
        root_certificates=args.root_certificates,
    )
    print("Disconnected from server (training finished or connection closed).")


def watch_retraining(args: argparse.Namespace, hospital_id: str) -> None:
    if args.poll_seconds < 1:
        raise ValueError("--poll-seconds must be >= 1")
    if args.include_flagged or args.allow_placeholder_labels:
        raise ValueError(
            "watch mode excludes flagged and placeholder-labeled records; "
            "these options are available only for explicit local demos"
        )
    headers = _retraining_headers()
    print(f"Watching Module 7 for retraining requests scoped to hospital {hospital_id}.")
    while True:
        try:
            X, y, provenance = load_single_hospital_partition(
                hospital_id,
                min_records=1,
                include_flagged=False,
                allow_placeholder_labels=False,
            )
        except ValueError as exc:
            print(f"Eligible local dataset not ready: {exc}")
            time.sleep(args.poll_seconds)
            continue
        _retraining_request(
            "POST", "/admin/retraining/eligibility", headers=headers,
            json_body={"eligible_records": int(len(y))},
        )
        if len(y) < args.min_records:
            time.sleep(args.poll_seconds)
            continue
        request = _retraining_request(
            "GET", "/admin/retraining/requests/next", headers=headers,
        ).json()
        if request is None:
            time.sleep(args.poll_seconds)
            continue
        request_id = request["id"]
        status = "FAILED"
        try:
            _execute_partition(args, hospital_id, X, y, provenance, retraining_request_id=request_id)
            candidate_status = _retraining_request(
                "GET", f"/admin/retraining/requests/{request_id}/candidate", headers=headers,
            ).json()
            if not candidate_status.get("registered"):
                raise RuntimeError(
                    "Flower run ended without a provenance-linked candidate in Module 7; "
                    "the request will be marked FAILED and its eligibility baseline will not advance."
                )
            status = "COMPLETED"
        finally:
            try:
                _, completed_y, _ = load_single_hospital_partition(
                    hospital_id, min_records=1, include_flagged=False,
                    allow_placeholder_labels=False,
                )
                completed_count = int(len(completed_y))
            except ValueError:
                completed_count = 0
            except httpx.HTTPError:
                completed_count = None
            _retraining_request(
                "POST", "/admin/retraining/requests/complete", headers=headers,
                json_body={"request_id": request_id, "status": status,
                           "eligible_records": completed_count},
            )


def main() -> None:
    args = parse_args()

    hospital_id = args.hospital_id
    if args.hospital_name:
        try:
            hospital_id = resolve_hospital_id(args.hospital_name)
        except (httpx.HTTPError, ValueError) as e:
            print(f"Could not resolve hospital name {args.hospital_name!r}: {e}")
            sys.exit(1)

    if args.watch_retraining:
        try:
            watch_retraining(args, hospital_id)
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            print(f"Retraining watch stopped: {e}")
            sys.exit(1)
        return

    print(f"Loading validated vitals for hospital {hospital_id} from Module 1...")
    try:
        X, y, provenance = load_single_hospital_partition(
            hospital_id,
            min_records=args.min_records,
            include_flagged=args.include_flagged,
            allow_placeholder_labels=args.allow_placeholder_labels,
        )
    except (httpx.HTTPError, ValueError) as e:
        print(f"Could not load this hospital's data: {e}")
        sys.exit(1)

    _execute_partition(args, hospital_id, X, y, provenance)


if __name__ == "__main__":
    main()
