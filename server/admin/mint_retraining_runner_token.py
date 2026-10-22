"""Operator tool: mint a hospital-scoped M3 -> M7 retraining-queue token.

Keep the signing key on the trusted operator host. Deliver only the resulting
token to the named hospital's Module 3 runner as FEDHEAL_SVC_TOKEN_M3_M7.
"""
import argparse
import sys

import auth
import service_auth


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hospital-id", required=True)
    parser.add_argument("--ttl-days", type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.ttl_days <= 365:
        print("--ttl-days must be between 1 and 365", file=sys.stderr)
        return 2
    print(service_auth.mint_service_token(
        auth.M3_M7_SIGNING_KEY,
        caller="module3",
        audience="module7:retraining-runner",
        hospital_id=args.hospital_id,
        ttl_seconds=args.ttl_days * 86400,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
