"""Shared pytest fixtures: an isolated in-memory database per test."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Sale, SaleStatus, User
from app import money


@pytest.fixture()
def db():
    """Fresh in-memory SQLite session per test.

    StaticPool keeps a single shared connection so the :memory: schema persists
    across the session's operations.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db):
    u = User(id="john_doe")
    db.add(u)
    db.commit()
    return u


def make_sale(db, earning_rupees=40, user_id="john_doe", brand="brand_1"):
    sale = Sale(
        user_id=user_id,
        brand=brand,
        earning_paise=money.rupees_to_paise(earning_rupees),
        status=SaleStatus.pending,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale
