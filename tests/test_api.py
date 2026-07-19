"""End-to-end API test exercising the assignment example over HTTP."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
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
        # Default to an admin identity. Tokens are stateless/signed, so no admin
        # row needs to exist in this isolated test DB.
        c.headers["Authorization"] = f"Bearer {create_token('admin', 'admin')}"
        yield c
    app.dependency_overrides.clear()


def _auth(user_id: str, role: str = "user") -> dict:
    return {"Authorization": f"Bearer {create_token(user_id, role)}"}


def _provision(client, user_id: str) -> dict:
    """Admin creates a user; return that user's auth header for self-service."""
    r = client.post(
        "/users", json={"user_id": user_id, "password": "pw", "role": "user"}
    )
    assert r.status_code == 201
    return _auth(user_id)


def test_full_flow_over_http(client):
    john = _provision(client, "john_doe")

    # The user creates their own 3 sales of Rs 40; the admin cannot.
    assert (
        client.post(
            "/sales", json={"user_id": "john_doe", "brand": "brand_1", "earning": 40}
        ).status_code
        == 403  # admin may not create sales
    )
    for _ in range(3):
        r = client.post(
            "/sales",
            json={"user_id": "john_doe", "brand": "brand_1", "earning": 40},
            headers=john,
        )
        assert r.status_code == 201
        # 10% advance is paid automatically the moment the sale is logged.
        assert r.json()["advance_paid_rupees"] == 4.0

    # The advance job is now redundant — everything is already advanced.
    r = client.post("/jobs/advance-payout", params={"user_id": "john_doe"})
    assert r.json()["total_advance_rupees"] == 0.0

    # Reconcile (admin): reject sale 1, approve 2 and 3.
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

    # Final withdrawable balance = Rs 80 (admin may view to settle): the advance
    # is credited to the balance, so approved sales pay full earning (2 x Rs 40)
    # and the rejected sale nets zero.
    r = client.get("/users/john_doe/balance")
    assert r.json()["withdrawable_balance_rupees"] == 80.0


def test_withdrawal_cooldown_over_http(client):
    amy = _provision(client, "amy")

    client.post(
        "/sales",
        json={"user_id": "amy", "brand": "brand_1", "earning": 100},
        headers=amy,
    )
    client.post(
        "/reconcile", json={"items": [{"sale_id": 1, "status": "approved"}]}
    )

    # Admins cannot initiate withdrawals — only the user can.
    assert (
        client.post("/withdrawals", json={"user_id": "amy", "amount": 10}).status_code
        == 403
    )

    r1 = client.post("/withdrawals", json={"user_id": "amy", "amount": 10}, headers=amy)
    assert r1.status_code == 201

    r2 = client.post("/withdrawals", json={"user_id": "amy", "amount": 10}, headers=amy)
    assert r2.status_code == 429  # blocked by 24h rule
