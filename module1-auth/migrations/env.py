"""
Alembic environment for Module 1.

Two things here are deliberate and worth not "cleaning up" later:

1. The database URL is read from FEDHEAL_DATABASE_URL — the SAME env var
   database.py reads, with the SAME postgres:// -> postgresql:// fixup —
   rather than from alembic.ini. One source of truth for "which database",
   so `alembic upgrade head` can never migrate a different database than
   the one the app is about to write to. It also keeps the Supabase
   password out of version control.

2. render_as_batch=True. SQLite (the zero-setup local fallback) cannot
   ALTER TABLE to add constraints or alter columns; Alembic's batch mode
   works around this by rebuilding the table. Without it, any migration
   more interesting than a plain nullable ADD COLUMN works against
   Supabase/Postgres and fails for every teammate running the SQLite
   default — which is the worst possible place to discover it.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Module 1's code isn't a package — it's flat modules imported by name
# (`import models`), matching how uvicorn runs it. Put this folder on the
# path so `import models` resolves the same way here as it does in main.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base  # noqa: E402
import models  # noqa: E402,F401  (imported for its side effect: registering tables on Base)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = os.environ.get("FEDHEAL_DATABASE_URL", "sqlite:///./fedmed_auth.db")
    # Same fixup as database.py — Supabase hands out postgres://, SQLAlchemy
    # 2.x wants postgresql://.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it — useful for review before
    anything touches staging/prod. `alembic upgrade head --sql`."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
