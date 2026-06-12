"""
alembic/env.py
==============
Alembic migration environment.
Connects to Supabase/Postgres using SUPABASE_URL env var.
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# -- Alembic Config object ---------------------------------------------------
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -- Resolve database URL ----------------------------------------------------
def _get_db_url() -> str:
    """
    Build a synchronous psycopg2 URL from env vars.

    Priority:
      1. DATABASE_URL (direct postgres:// or postgresql:// URL)
      2. SUPABASE_URL: convert https://xxx.supabase.co → postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres
    """
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        # Alembic needs synchronous driver; strip +asyncpg if present
        return db_url.replace("postgresql+asyncpg://", "postgresql://")

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")  # service role key = DB password
    if supabase_url:
        # https://abcxyz.supabase.co → db.abcxyz.supabase.co
        host = supabase_url.replace("https://", "").replace("http://", "")
        db_host = f"db.{host}"
        db_pass = os.getenv("SUPABASE_DB_PASSWORD", supabase_key)
        return f"postgresql://postgres:{db_pass}@{db_host}:5432/postgres"

    # Fallback: local dev Postgres
    return "postgresql://postgres:postgres@localhost:5432/hp_proctoring"


# Set the sqlalchemy.url from environment
config.set_main_option("sqlalchemy.url", _get_db_url())

# -- Import ORM metadata (for autogenerate) ----------------------------------
# Register all models so Alembic can detect schema changes
target_metadata = None
try:
    from api.models.session import Session
    from api.models.candidate import Candidate
    from api.models.event import Event
    from api.models.report import Report
    from api.models.recording import Recording
    # Import Base to get all mapped tables
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass

    # Try to get metadata from models
    from sqlalchemy import MetaData
    target_metadata = MetaData()
except ImportError:
    target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a live connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to database directly."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
