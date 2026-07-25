"""
SQLite database setup. Every domain table (later: vitals, scans, model_versions)
must carry a hospital_id foreign key so one tenant can never query another's rows.
Swap the URL for a real Postgres connection string when you move past prototyping.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./fedmed_auth.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
