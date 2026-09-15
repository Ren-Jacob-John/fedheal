"""
Seed FedHeal's demo/eval data from the UCI Heart Disease (Cleveland)
dataset — Sprint A, docs/DEVELOPMENT_PLAN.md.

Run: python seed_uci_heart.py --hospitals 3

What this does, and why it does it the slow way
-----------------------------------------------
It splits the 303 real Cleveland records non-IID across N hospitals and
uploads them **through Module 1's real `POST /vitals/upload` endpoint**,
as a logged-in hospital user, exactly the way a hospital would.

It would be much faster to INSERT the rows straight into the database.
That's precisely why it doesn't: a direct insert proves nothing about the
system. Going through the front door means the seeded data has actually
passed Module 2's de-identification screen, schema validation, range
checks, cross-field consistency checks and isolation-forest outlier pass,
and has landed with correct `label_source` provenance — so the demo data
is subject to the same gate as production data instead of being a
privileged parallel path that hides breakage in the real one.

It also means running this script IS an end-to-end integration test of
the Module 1 -> Module 2 -> storage path, which is worth having.

Prerequisites
-------------
  1. Module 1 (auth/vitals) running on :8001
  2. Module 2 (validation) running on :8002
  3. Nothing else. Hospitals and their admin users are created by this
     script if they don't already exist.

Every seeded hospital is created with `requires_label=true`, since every
Cleveland record carries a real outcome. That means Module 2 will reject
any later unlabeled upload to these hospitals — which is the behaviour
Sprint A is introducing, demonstrated on the demo tenants themselves
rather than only described in a doc.

Idempotency: re-running is safe in the sense that it won't crash, but it
WILL upload a second copy of the records. Use --reset to delete previously
seeded records for these hospitals first (it only ever touches records
whose patient_ref carries this script's prefix).
"""
from __future__ import annotations

import argparse
import sys

import httpx
import numpy as np

import uci_heart

DEFAULT_AUTH_URL = "http://localhost:8001"
HOSPITAL_NAME_TEMPLATE = "UCI Cleveland Hospital {n}"
ADMIN_EMAIL_TEMPLATE = "seed-admin-{n}@fedheal.local"
# Dev-only credential for demo tenants created by this script. Fine because
# these hospitals hold a public research dataset and nothing else; do not
# reuse this pattern for a tenant holding anything real.
ADMIN_PASSWORD = "uci-seed-demo-password"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--hospitals", type=int, default=3,
                        help="How many hospitals to spread the 303 records across (default: 3).")
    parser.add_argument("--auth-url", default=DEFAULT_AUTH_URL,
                        help=f"Module 1 base URL (default: {DEFAULT_AUTH_URL}).")
    parser.add_argument("--alpha", type=float, default=3.0,
                        help="Dirichlet concentration for the non-IID label split. "
                             "Lower = more skew between hospitals (default: 3.0, "
                             "matching data.partition_for_hospitals).")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for the split (default: 42).")
    parser.add_argument("--iid", action="store_true",
                        help="Split uniformly instead of non-IID. The non-IID default is "
                             "the point of the exercise — hospitals that look alike make "
                             "federated learning look better than it is.")
    parser.add_argument("--reset", action="store_true",
                        help="Delete this script's previously seeded records from these "
                             "hospitals before uploading.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the split and validate the records locally, upload nothing.")
    return parser.parse_args()


def split_records(records: list[dict], n_hospitals: int, non_iid: bool,
                  alpha: float, seed: int) -> list[list[dict]]:
    """
    Non-IID split by outcome label, reusing the same Dirichlet scheme
    data.partition_for_hospitals() uses for synthetic data — so the real
    seeded data has the same *kind* of inter-hospital skew the synthetic
    simulation was designed around, and the two are comparable.

    Operates on record dicts rather than (X, y) arrays because these get
    POSTed as JSON, not fed to a model.
    """
    rng = np.random.default_rng(seed)
    idx = np.arange(len(records))

    if not non_iid:
        rng.shuffle(idx)
        return [[records[i] for i in part] for part in np.array_split(idx, n_hospitals)]

    labels = np.array([r["label"] for r in records])
    buckets: list[list[int]] = [[] for _ in range(n_hospitals)]

    for cls in np.unique(labels):
        cls_idx = idx[labels == cls]
        rng.shuffle(cls_idx)

        proportions = rng.dirichlet([alpha] * n_hospitals)
        # Same 5% floor as data.partition_for_hospitals: keep every hospital's
        # local class balance meaningful, so its solo baseline is worth
        # comparing the federated model against.
        proportions = np.clip(proportions, 0.05, None)
        proportions = proportions / proportions.sum()

        counts = (proportions * len(cls_idx)).astype(int)
        counts[-1] = len(cls_idx) - counts[:-1].sum()

        start = 0
        for h, count in enumerate(counts):
            buckets[h].extend(cls_idx[start:start + count].tolist())
            start += count

    return [[records[i] for i in sorted(bucket)] for bucket in buckets]


def ensure_hospital(client: httpx.Client, auth_url: str, name: str) -> dict:
    """Create the hospital if absent; return its record either way."""
    resp = client.get(f"{auth_url}/hospitals", timeout=10.0)
    resp.raise_for_status()
    for h in resp.json():
        if h["name"] == name:
            # Already exists — make sure the label requirement is on, in case
            # it was created before Sprint A or by an earlier run.
            if not h.get("requires_label"):
                client.patch(f"{auth_url}/hospitals/{h['id']}",
                             json={"requires_label": True}, timeout=10.0)
                h["requires_label"] = True
            return h

    resp = client.post(f"{auth_url}/hospitals", timeout=10.0,
                       json={"name": name, "requires_label": True})
    resp.raise_for_status()
    return resp.json()


def ensure_admin_token(client: httpx.Client, auth_url: str,
                       hospital_id: str, email: str) -> str:
    """Register the seed admin if needed, then log in and return a bearer token."""
    reg = client.post(f"{auth_url}/register", timeout=10.0, json={
        "email": email,
        "password": ADMIN_PASSWORD,
        "hospital_id": hospital_id,
        "role": "hospital_admin",
    })
    # 400 == already registered, which is the normal case on a re-run.
    if reg.status_code not in (200, 201, 400):
        reg.raise_for_status()

    login = client.post(f"{auth_url}/token", timeout=10.0,
                        data={"username": email, "password": ADMIN_PASSWORD})
    if login.status_code == 429:
        raise RuntimeError(
            "Module 1's login rate limiter rejected the seed login (5 attempts per "
            "60s per IP+user). Wait a minute and re-run — or seed fewer hospitals "
            "per run."
        )
    login.raise_for_status()
    return login.json()["access_token"]


def delete_seeded_records(client: httpx.Client, auth_url: str, token: str) -> int:
    """
    Remove records this script previously seeded, identified by patient_ref
    prefix. Only flagged records are deletable through the public API
    (POST /vitals/{id}/review with reject), so this is best-effort and
    reports what it couldn't remove rather than pretending it's clean.
    """
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"{auth_url}/vitals/flagged", headers=headers, timeout=10.0)
    resp.raise_for_status()
    removed = 0
    for rec in resp.json():
        if not rec["patient_ref"].startswith("UCI-CLE"):
            continue
        r = client.post(f"{auth_url}/vitals/{rec['id']}/review",
                        headers=headers, json={"decision": "reject"}, timeout=10.0)
        if r.status_code == 200:
            removed += 1
    return removed


def upload(client: httpx.Client, auth_url: str, token: str, records: list[dict]) -> dict:
    resp = client.post(
        f"{auth_url}/vitals/upload",
        headers={"Authorization": f"Bearer {token}"},
        json={"records": records},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    args = parse_args()

    try:
        records = uci_heart.load_vitals_records()
    except uci_heart.DatasetIntegrityError as e:
        print(f"Dataset check failed: {e}", file=sys.stderr)
        return 1

    info = uci_heart.summary()
    print("Seeding FedHeal from UCI Heart Disease (Cleveland)")
    print(f"  {info['records']} records, {info['positive']} positive / {info['negative']} negative")
    print(f"  {len(info['real_features'])} of 8 feature slots carry real measurements "
          f"({', '.join(info['real_features'])})")
    print(f"  {len(info['constant_features'])} are fixed constants — Cleveland does not "
          f"measure them (see uci_heart.py)")
    print(f"  all {info['records']} labels are REAL clinical outcomes\n")

    buckets = split_records(records, args.hospitals, non_iid=not args.iid,
                            alpha=args.alpha, seed=args.seed)

    print(f"Split across {args.hospitals} hospitals "
          f"({'IID' if args.iid else f'non-IID, Dirichlet alpha={args.alpha}'}):")
    for n, bucket in enumerate(buckets, start=1):
        pos = sum(r["label"] for r in bucket)
        rate = pos / len(bucket) if bucket else 0
        print(f"  {HOSPITAL_NAME_TEMPLATE.format(n=n)}: {len(bucket):>3} records, "
              f"positive rate {rate:.2f}")

    if args.dry_run:
        print("\n--dry-run: nothing uploaded.")
        return 0

    print()
    total_stored = 0
    total_rejected = 0
    with httpx.Client() as client:
        for n, bucket in enumerate(buckets, start=1):
            name = HOSPITAL_NAME_TEMPLATE.format(n=n)
            try:
                hospital = ensure_hospital(client, args.auth_url, name)
                token = ensure_admin_token(client, args.auth_url, hospital["id"],
                                           ADMIN_EMAIL_TEMPLATE.format(n=n))
            except httpx.HTTPError as e:
                print(f"Could not reach Module 1 at {args.auth_url} — is it running? ({e})",
                      file=sys.stderr)
                return 1
            except RuntimeError as e:
                print(f"{e}", file=sys.stderr)
                return 1

            if args.reset:
                removed = delete_seeded_records(client, args.auth_url, token)
                print(f"  {name}: removed {removed} previously seeded flagged record(s)")

            try:
                result = upload(client, args.auth_url, token, bucket)
            except httpx.HTTPError as e:
                print(f"  {name}: upload failed — {e}", file=sys.stderr)
                print("    If this is a 502, Module 2 (validation, :8002) isn't reachable.",
                      file=sys.stderr)
                return 1

            total_stored += result["stored"]
            total_rejected += result["rejected"]
            print(f"  {name}: {result['stored']} stored "
                  f"({result['passed']} passed, {result['flagged']} flagged), "
                  f"{result['rejected']} rejected, "
                  f"{result['stored_labeled']} with real labels")

            # Cleveland records are clean and pre-de-identified, so a rejection
            # here means something in the pipeline changed — surface it rather
            # than letting a quietly-shrinking dataset explain away a drop in
            # accuracy later.
            if result["rejected"]:
                for res in result["results"]:
                    if res["status"] == "rejected":
                        print(f"      ! {res['patient_ref']}: {'; '.join(res['reasons'])}")

    print(f"\nDone — {total_stored} records stored across {args.hospitals} hospitals, "
          f"{total_rejected} rejected.")
    if total_rejected:
        print("Non-zero rejections from a known-clean public dataset is a red flag; "
              "check the reasons above before trusting any accuracy number from this seed.")
    print("\nNext: run the federated-vs-solo comparison on it —")
    print("  python simulate_real.py")
    print("...or offline, with no services running —")
    print("  python compare_uci_heart.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
