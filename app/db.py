"""Database engine, session factory, and declarative base.

Local dev defaults to SQLite (zero-config, file-backed). In production set
``DATABASE_URL`` to a Postgres connection string (e.g. Vercel Postgres / Neon);
the URL is normalized to the psycopg (v3) driver and the engine is configured
for a serverless environment.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

_RAW_URL = os.getenv("DATABASE_URL", "sqlite:///./payouts.db")

# Vercel/Neon hand out "postgres://" or "postgresql://"; SQLAlchemy needs an
# explicit driver. Point them at psycopg v3.
if _RAW_URL.startswith("postgres://"):
    DATABASE_URL = _RAW_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif _RAW_URL.startswith("postgresql://"):
    DATABASE_URL = _RAW_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = _RAW_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")
_IS_SQLITE = IS_SQLITE  # backward-compatible alias

if _IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Serverless-friendly: NullPool avoids holding connections between function
    # invocations, and disabling psycopg's server-side prepared statements keeps
    # a pooled (pgbouncer) connection string working.
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


if _IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _record):
        """SQLite ignores FOREIGN KEY constraints unless explicitly enabled."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Session:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
