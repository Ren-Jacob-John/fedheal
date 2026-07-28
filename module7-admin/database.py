"""
SQLite database for the Admin/Platform module's OWN data only:
training-round history and validation-flag summaries.

Deliberately does NOT store a copy of the hospitals table — hospital
identity/status lives in Module 1 and Module 7 always asks Module 1 for
the current truth (see hospitals_client.py). Duplicating that table here
would just create a second source of truth that can drift out of sync,
which is exactly the kind of bug that's easy to introduce and annoying to
find later.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./fedheal_admin.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
