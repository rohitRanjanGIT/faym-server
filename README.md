# User Payout Management System

A Low-Level Design + working implementation of a payout system for affiliate
sales: 10% advance payouts, reconciliation with final settlement, a
one-withdrawal-per-24h rule, and failed-payout recovery.

**Stack:** Python 3.13 · FastAPI · SQLAlchemy 2.0 · SQLite · pytest.

See **[DESIGN.md](./DESIGN.md)** for the full LLD: schema/ERD, class design, API
reference, edge cases, and trade-offs.

## Setup

```bash
uv sync
```

## Run the worked example (from the assignment)

Reproduces: 3 × ₹40 sales → **₹12 advance** → 1 rejected + 2 approved →
**₹68 final payout**.

```bash
uv run python seed.py
```

## Run the API

```bash
uv run main.py            # http://127.0.0.1:8000  (interactive docs at /docs)
```

Example flow:

```bash
# create three sales (repeat 3x)
curl -X POST localhost:8000/sales -H "content-type: application/json" \
  -d '{"user_id":"john_doe","brand":"brand_1","earning":40}'

# pay 10% advance (safe to run repeatedly)
curl -X POST "localhost:8000/jobs/advance-payout?user_id=john_doe"

# reconcile
curl -X POST localhost:8000/reconcile -H "content-type: application/json" \
  -d '{"items":[{"sale_id":1,"status":"rejected"},
                {"sale_id":2,"status":"approved"},
                {"sale_id":3,"status":"approved"}]}'

# check balance + audit ledger
curl localhost:8000/users/john_doe/balance
```

## Run the tests

```bash
uv run pytest
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sales` | Create a pending sale |
| `POST` | `/jobs/advance-payout` | Pay 10% advance (idempotent) |
| `POST` | `/reconcile` | Approve/reject sales, settle final payout |
| `POST` | `/withdrawals` | Initiate withdrawal (24h cap) |
| `POST` | `/withdrawals/{id}/complete` | Confirm payout |
| `POST` | `/withdrawals/{id}/fail` | Fail/cancel/reject → credit back |
| `GET` | `/users/{id}/balance` | Balance + ledger |
