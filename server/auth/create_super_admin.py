"""
Operator tool: create the FIRST super_admin (there is deliberately no HTTP
path for that — POST /register only ever makes clinicians, and POST
/admin/users needs a super_admin already).

    python create_super_admin.py --email ops@yourorg.example
    # password is read from a hidden prompt, or from
    # FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD for non-interactive provisioning.

Run it somewhere that has the production Firestore credentials
(FEDHEAL_FIREBASE_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS, or an attached
service account). The password is never printed or logged; nothing is written
if the e-mail already exists.
"""
import argparse
import getpass
import os
import sys

import auth
import models
from database import repo
from repo import DuplicateError

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = os.environ.get("FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 2

    if repo.get_user_by_email(args.email):
        print("A user with that e-mail already exists; nothing changed.", file=sys.stderr)
        return 1
    try:
        repo.create_user(models.User(
            email=args.email,
            hashed_password=auth.hash_password(password),
            role=models.Role.SUPER_ADMIN,
            hospital_id=None,
        ))
    except DuplicateError:
        print("A user with that e-mail already exists; nothing changed.", file=sys.stderr)
        return 1
    print("super_admin created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
