import os
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


def _load_dotenv() -> None:
    if "pytest" in sys.modules:
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

_RAW_URL = os.getenv("DATABASE_URL", "")

if _RAW_URL.startswith("postgres://"):
    DATABASE_URL = _RAW_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif _RAW_URL.startswith("postgresql://"):
    DATABASE_URL = _RAW_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = _RAW_URL

ENGINE_ERROR: str | None = None
engine = None
if not DATABASE_URL:
    ENGINE_ERROR = (
        "DATABASE_URL is not set. This app requires a Postgres connection "
        "string (set it in the Vercel project's Environment Variables, or in "
        "a local .env loaded via `uv run --env-file .env main.py`)."
    )
elif not DATABASE_URL.startswith("postgresql+psycopg://"):
    _scheme = _RAW_URL.split("://", 1)[0] if "://" in _RAW_URL else _RAW_URL
    ENGINE_ERROR = (
        f"DATABASE_URL must be a Postgres URL; got scheme '{_scheme}'. "
        "SQLite and other backends are not supported."
    )
else:
    try:
        engine = create_engine(
            DATABASE_URL,
            poolclass=NullPool,
            pool_pre_ping=True,
            connect_args={"prepare_threshold": None},
        )
    except Exception as exc: 
        ENGINE_ERROR = f"{type(exc).__name__}: {exc}"

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Session:
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=ENGINE_ERROR or "Database is not configured.",
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
