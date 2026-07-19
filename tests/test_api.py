"""End-to-end API test exercising the assignment example over HTTP."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_full_flow_over_http(client):
    # Create 3 sales of Rs 40.
    for _ in range(3):
        r = client.post(
            "/sales",
            json={"user_id": "john_doe", "brand": "brand_1", "earning": 40},
        )
        assert r.status_code == 201

    # Advance payout: 10% of Rs 120 = Rs 12.
    r = client.post("/jobs/advance-payout", params={"user_id": "john_doe"})
    assert r.json()["total_advance_rupees"] == 12.0

    # Reconcile: reject sale 1, approve 2 and 3.
    r = client.post(
        "/reconcile",
        json={
            "items": [
                {"sale_id": 1, "status": "rejected"},
                {"sale_id": 2, "status": "approved"},
                {"sale_id": 3, "status": "approved"},
            ]
        },
    )
    assert r.status_code == 200

    # Final withdrawable balance = Rs 68.
    r = client.get("/users/john_doe/balance")
    assert r.json()["withdrawable_balance_rupees"] == 68.0


def test_withdrawal_cooldown_over_http(client):
    client.post(
        "/sales", json={"user_id": "amy", "brand": "brand_1", "earning": 100}
    )
    client.post(
        "/reconcile", json={"items": [{"sale_id": 1, "status": "approved"}]}
    )

    r1 = client.post("/withdrawals", json={"user_id": "amy", "amount": 10})
    assert r1.status_code == 201

    r2 = client.post("/withdrawals", json={"user_id": "amy", "amount": 10})
    assert r2.status_code == 429  # blocked by 24h rule
