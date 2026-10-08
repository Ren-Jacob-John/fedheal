"""
Alembic environment for Module 7 (admin/platform).

Module 7 shares a database with Module 1 in compose, so it keeps its OWN
version table (alembic_version_admin). Without that, the two services'
histories would overwrite each other's revision pointer.

URL comes from the same variables database.py reads
(FEDHEAL_ADMIN_DATABASE_URL, falling back to FEDHEAL_DATABASE_URL).
render_as_batch=True so SQLite (local default) can run the same migrations.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base, DATABASE_URL  # noqa: E402
import models  # noqa: E402,F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata
VERSION_TABLE = "alembic_version_admin"


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True, render_as_batch=True,
                      version_table=VERSION_TABLE)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = DATABASE_URL
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          render_as_batch=True, version_table=VERSION_TABLE)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
