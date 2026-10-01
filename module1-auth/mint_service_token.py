"""
Operator tool: mint a long-lived, hospital-scoped credential for Module 3.

    FEDHEAL_ENV=production FEDHEAL_SVC_SIGNING_KEY_M3_M1=... \
    FEDHEAL_DATABASE_URL=... \
    python mint_service_token.py --hospital-id <uuid> [--ttl-days 90]

The printed token goes to THAT hospital's Module 3 client as
FEDHEAL_SVC_TOKEN_M3_M1 (put it in the hospital's secrets store). It lets
the holder read that one hospital's validated vitals and nothing else —
Module 1 rejects it (403) for any other hospital_id. It is deliberately not
available over HTTP. Rotate by minting a new one; rotating
FEDHEAL_SVC_SIGNING_KEY_M3_M1 revokes every outstanding token at once.

The token is printed to stdout and nowhere else; this tool logs nothing.
"""
import argparse
import sys

import auth
import models
import service_auth
from database import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hospital-id", required=True)
    parser.add_argument("--ttl-days", type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.ttl_days <= 365:
        print("--ttl-days must be between 1 and 365", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        exists = db.query(models.Hospital.id).filter(models.Hospital.id == args.hospital_id).first()
    finally:
        db.close()
    if not exists:
        print("No hospital with that id exists in this database.", file=sys.stderr)
        return 1

    print(service_auth.mint_service_token(
        auth.M3_M1_SIGNING_KEY,
        caller="module3",
        audience=service_auth.AUD_VITALS_EXPORT,
        hospital_id=args.hospital_id,
        ttl_seconds=args.ttl_days * 86400,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
