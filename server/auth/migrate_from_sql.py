"""
One-off: copy Module 1's data from the OLD SQL database (Supabase/Postgres, or
a SQLite file) into the document store this service is now configured for.

    pip install sqlalchemy psycopg2-binary          # only needed for this script
    # point the destination at Firestore exactly as the service would be (see .env.example), then:
    python migrate_from_sql.py --source-url "postgresql://postgres.<ref>:<password>@<host>:5432/postgres" --dry-run
    python migrate_from_sql.py --source-url "postgresql://..."

* Ids are preserved, so existing JWTs, case links and Module 3's hospital-scoped
  service tokens keep working. Re-running is safe: every write is an upsert.
* Reads the source with plain SELECTs; it never writes to or alters it. Keep the
  Supabase project until you have verified the copy.
* Writes users, hospitals, their uniqueness index documents, vitals, cases,
  medical histories, clinician reviews and scan metadata (scan FILES are on disk
  under FEDHEAL_UPLOAD_STORAGE_PATH and are not touched).
* Module 7's tables are copied by module7-admin/migrate_from_sql.py.
* Password hashes are copied as they are (bcrypt), so nobody has to reset a password.
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import models
from database import backend
from docstore import to_doc
from repo import _key

# (table, entity class, how to build extra index docs)
TABLES = [
    ("hospitals", models.Hospital),
    ("users", models.User),
    ("vitals_records", models.VitalsRecord),
    ("cases", models.Case),
    ("medical_histories", models.MedicalHistory),
    ("clinician_reviews", models.ClinicianReview),
    ("scans", models.Scan),
]
JSON_LISTS = {"presenting_symptoms", "conditions", "previous_diagnoses", "surgeries", "allergies", "medications",
              "family_history", "previous_admissions", "symptoms"}
BOOLS = {"is_active", "requires_label"}


def _value(field: str, v, datetimes=frozenset()):
    if v is None:
        return None
    if field in datetimes:
        return _as_datetime(v)
    if field in JSON_LISTS:
        v = json.loads(v) if isinstance(v, (str, bytes)) else v
        return list(v or [])
    if field in BOOLS:
        return bool(v)
    return v


def _datetime_fields(cls) -> set:
    import typing

    return {name for name, hint in typing.get_type_hints(cls).items()
            if datetime in (typing.get_args(hint) or (hint,))}


def _as_datetime(v):
    """Naive UTC (the old columns) or ISO text (SQLite hands datetimes back as strings) -> aware datetime."""
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _role(v):
    s = str(v)
    for r in models.Role:                    # old rows store the member NAME (SUPER_ADMIN); accept either form
        if s in (r.name, r.value):
            return r
    raise ValueError(f"unknown role {v!r}")


def convert(cls, mapping):
    names = {f.name for f in cls.__dataclass_fields__.values()}
    dts = _datetime_fields(cls)
    kw = {k: _value(k, v, dts) for k, v in mapping.items() if k in names}
    if cls is models.User:
        kw["role"] = _role(mapping["role"])
    return cls(**kw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-url", required=True, help="SQLAlchemy URL of the old database")
    ap.add_argument("--dry-run", action="store_true", help="read and convert everything, write nothing")
    args = ap.parse_args()

    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(args.source_url)
    present = set(inspect(engine).get_table_names())
    total = 0
    with engine.connect() as conn:
        for table, cls in TABLES:
            if table not in present:
                print(f"{table:20s} (not in source — skipped)")
                continue
            entities = [convert(cls, dict(r._mapping)) for r in conn.execute(text(f"SELECT * FROM {table}"))]
            ops = []
            for e in entities:
                if cls is models.MedicalHistory:
                    ops.append((e.case_id, to_doc(e)))              # document id == case id
                else:
                    ops.append((e.id, to_doc(e)))
            if not args.dry_run:
                backend.bulk_set(cls.COLLECTION, ops)
                if cls is models.Hospital:
                    backend.bulk_set("hospital_names", [(_key(e.name), {"hospital_id": e.id}) for e in entities])
                if cls is models.User:
                    backend.bulk_set("user_emails", [(_key(e.email), {"user_id": e.id}) for e in entities])
            print(f"{table:20s} {len(entities):6d} {'would be copied' if args.dry_run else 'copied'}")
            total += len(entities)
    print(f"done: {total} documents{' (dry run — nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
