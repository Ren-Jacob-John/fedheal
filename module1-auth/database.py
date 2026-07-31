"""
Database setup — Supabase (Postgres) in production, SQLite fallback for
quick local dev with no Supabase project configured.

Every domain table (hospitals, users, vitals_records) carries a
hospital_id foreign key so one tenant can never query another's rows —
that's enforced in application code (every query filters by the JWT's
hospital_id), not by the database engine, so it holds regardless of which
of these two backends is active.

Set FEDHEAL_DATABASE_URL to your Supabase connection string to use it —
see README.md's "Using Supabase" section for exactly where to find that
string and which format to copy. Leave it unset and this falls back to a
local SQLite file, so the module still runs with zero setup for anyone
who hasn't configured Supabase yet.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()  # picks up .env in this folder if present — see README.md's "Using Supabase" section

DATABASE_URL = os.environ.get("FEDHEAL_DATABASE_URL", "sqlite:///./fedmed_auth.db")

# Supabase (and most Postgres hosts) hand out "postgres://" connection
# strings, but SQLAlchemy 2.x's default driver needs "postgresql://" —
# fix it up here rather than making every teammate remember to edit it.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# connect_args differs by backend: SQLite needs check_same_thread=False
# for FastAPI's threaded request handling; Postgres needs nothing extra
# here (sslmode is passed as part of the connection string itself).
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
