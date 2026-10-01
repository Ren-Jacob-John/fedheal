"""
Operator tool: create the FIRST super_admin (there is deliberately no HTTP
path for that — POST /register only ever makes clinicians, and POST
/admin/users needs a super_admin already).

    python create_super_admin.py --email ops@yourorg.example
    # password is read from a hidden prompt, or from
    # FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD for non-interactive provisioning.

Run it on the machine that has the production database credentials
(FEDHEAL_DATABASE_URL). The password is never printed or logged; nothing is
written if the e-mail already exists.
"""
import argparse
import getpass
import os
import sys

import auth
import models
from database import SessionLocal

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = os.environ.get("FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        if db.query(models.User).filter(models.User.email == args.email).first():
            print("A user with that e-mail already exists; nothing changed.", file=sys.stderr)
            return 1
        db.add(models.User(
            email=args.email,
            hashed_password=auth.hash_password(password),
            role=models.Role.SUPER_ADMIN,
            hospital_id=None,
        ))
        db.commit()
    finally:
        db.close()
    print("super_admin created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
