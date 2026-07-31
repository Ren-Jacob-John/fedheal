"""
Database for the Admin/Platform module's OWN data only: training-round
history and validation-flag summaries. Supabase (Postgres) in production,
SQLite fallback for local dev — see module1-auth/database.py's docstring
for the reasoning; this file mirrors that pattern exactly.

Deliberately does NOT store a copy of the hospitals table — hospital
identity/status lives in Module 1 and Module 7 always asks Module 1 for
the current truth (see hospitals_client.py). Duplicating that table here
would just create a second source of truth that can drift out of sync,
which is exactly the kind of bug that's easy to introduce and annoying to
find later.

This module's tables (training_rounds, validation_flags) can safely live
in the SAME Supabase project as Module 1's (hospitals, users,
vitals_records) — the table names don't collide, and Supabase happily
hosts multiple services' tables in one Postgres database, same as any
shared Postgres instance would.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()  # picks up .env in this folder if present — see module1-auth/README.md's "Using Supabase" section

DATABASE_URL = os.environ.get(
    "FEDHEAL_ADMIN_DATABASE_URL",
    os.environ.get("FEDHEAL_DATABASE_URL", "sqlite:///./fedheal_admin.db"),
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
