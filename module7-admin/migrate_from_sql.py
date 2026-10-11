"""
One-off: copy Module 7's data (training rounds, validation-flag summaries, the
model registry incl. weights) from the OLD SQL database into the document store
this service is now configured for. Same usage and guarantees as
module1-auth/migrate_from_sql.py: ids preserved, re-runnable (upserts), the
source is only read.

    pip install sqlalchemy psycopg2-binary
    python migrate_from_sql.py --source-url "postgresql://..." --dry-run
    python migrate_from_sql.py --source-url "postgresql://..."
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import models
from database import backend
from docstore import to_doc

TABLES = [("training_rounds", models.TrainingRound), ("validation_flags", models.ValidationFlag),
          ("model_versions", models.ModelVersion)]
JSON_COLS = {"participating_hospitals", "training_metadata", "metrics", "validation_report", "parameters", "input_spec"}


def _value(field, v, datetimes=frozenset()):
    if v is None:
        return None
    if field in datetimes:
        return _as_datetime(v)
    if field in JSON_COLS:
        return json.loads(v) if isinstance(v, (str, bytes)) else v
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--dry-run", action="store_true")
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
            names = set(cls.__dataclass_fields__)
            dts = _datetime_fields(cls)
            entities = [cls(**{k: _value(k, v, dts) for k, v in dict(r._mapping).items() if k in names})
                        for r in conn.execute(text(f"SELECT * FROM {table}"))]
            if not args.dry_run:
                backend.bulk_set(cls.COLLECTION, [(e.id, to_doc(e)) for e in entities])
            print(f"{table:20s} {len(entities):6d} {'would be copied' if args.dry_run else 'copied'}")
            total += len(entities)
    print(f"done: {total} documents{' (dry run — nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
