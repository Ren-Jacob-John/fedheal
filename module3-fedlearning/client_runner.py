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
  3. FEDHEAL_SVC_KEY_M3_M1 exported here matching Module 1's, so
     GET /vitals/export authenticates (see real_data.py).

Usage — start the server once:
    python server.py

...then one process per hospital, each pointed at that same server:
    python client_runner.py --hospital-name "General Hospital" --server localhost:8080
    python client_runner.py --hospital-id 3f9c2e11-... --server localhost:8080

Need 2+ of these running (server.py's FedAvg strategy sets
min_available_clients=2) before a round will actually start.

TLS is explicitly out of scope for this pass — see
docs/development-plan-to-oct20.md's cut list ("TLS/production-grade
multi-host security" is deferred past Oct 20). --insecure defaults to True,
matching server.py's plaintext 0.0.0.0:8080 listener; this is fine for a
localhost/LAN demo and not fine for real hospital traffic over the
open internet.
"""
import argparse
import sys

import httpx
from sklearn.model_selection import train_test_split

import flwr as fl

from client import HospitalClient
from real_data import load_single_hospital_partition, resolve_hospital_id


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
        "--secure",
        dest="insecure",
        action="store_false",
        help="Use a TLS connection instead of plaintext gRPC. Not supported "
             "by server.py yet (see module docstring) — only pass this once "
             "the server actually terminates TLS.",
    )
    parser.set_defaults(insecure=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    hospital_id = args.hospital_id
    if args.hospital_name:
        try:
            hospital_id = resolve_hospital_id(args.hospital_name)
        except (httpx.HTTPError, ValueError) as e:
            print(f"Could not resolve hospital name {args.hospital_name!r}: {e}")
            sys.exit(1)

    print(f"Loading validated vitals for hospital {hospital_id} from Module 1...")
    try:
        X, y = load_single_hospital_partition(
            hospital_id,
            min_records=args.min_records,
            include_flagged=args.include_flagged,
        )
    except (httpx.HTTPError, ValueError) as e:
        print(f"Could not load this hospital's data: {e}")
        sys.exit(1)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=args.test_size,
        random_state=42,
        stratify=y if len(set(y)) > 1 else None,
    )
    print(
        f"  {len(X_train)} train / {len(X_test)} local-test records, "
        f"positive-class rate {y_train.mean():.2f} — this data never leaves this process."
    )

    client = HospitalClient(hospital_id, X_train, y_train, X_test, y_test)

    print(f"Connecting to Flower server at {args.server} "
          f"({'insecure' if args.insecure else 'TLS'})...")
    fl.client.start_client(
        server_address=args.server,
        client=client.to_client(),
        insecure=args.insecure,
    )
    print("Disconnected from server (training finished or connection closed).")


if __name__ == "__main__":
    main()
