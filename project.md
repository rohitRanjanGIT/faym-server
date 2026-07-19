# Project Reference — Backend Routes & Functionality

This document is the practical reference for the **User Payout Management System**
backend: what each endpoint does, its request/response shape, and the business
rules it enforces. For the design rationale (schema, ledger model, trade-offs),
see [DESIGN.md](./DESIGN.md).

- **Base URL (local):** `http://127.0.0.1:8000`
- **Interactive docs:** `/docs` (Swagger) · `/redoc`
- **Dashboard UI:** the separate React client in `../client-faym-dashboard`
- **Money:** requests/responses use **rupees**; stored internally as integer paise.

---

## Domain concepts

| Concept | Meaning |
|---|---|
| **Sale** | One affiliate sale. Starts `pending`; reconciled to `approved` or `rejected`. |
| **Advance payout** | 10% of a sale's earning, paid up front **automatically when the sale is logged**. Idempotent. |
| **Reconciliation** | Admin sets a sale to approved/rejected; system settles the final payout. |
| **Withdrawable balance** | What the user can withdraw. Fed by final settlement, not by advances. |
| **Withdrawal** | User pulls money from the balance. Max one per 24h. |
| **Ledger** | Append-only log of every money movement; the audit source of truth. |

**Per-sale money math**

| Event | Effect on withdrawable balance |
|---|---|
| Advance paid (on logging) | `+ advance` (10%, credited immediately — withdrawable right away) |
| Approved | `+ (earning − advance_already_paid)` → net = full earning |
| Rejected | `− advance_already_paid` (clawback) → net = 0 |
| Withdrawal initiated | `− amount` |
| Withdrawal failed/cancelled/rejected | `+ amount` (credited back) |

---

## Endpoints

### 1. Create sale
`POST /sales`

Records a new sale. New sales always start `pending`, and the **10% advance is
paid automatically** as part of logging the sale (see §3 for the mechanics). The
user must already exist and the caller must be that user — admins do not create
sales.

**Request**
```json
{ "user_id": "john_doe", "brand": "brand_1", "earning": 40 }
```
`earning` is in rupees, must be > 0. `brand` is free text (reference data uses
`brand_1`..`brand_3`).

**Response** `201`
```json
{ "id": 1, "user_id": "john_doe", "brand": "brand_1",
  "earning_rupees": 40.0, "status": "pending",
  "advance_paid_rupees": 4.0, "reconciled": false }
```
`advance_paid_rupees` is already `4.0` (10% of ₹40) because the advance is paid
on logging, and it is **credited to the withdrawable balance immediately** — the
user's balance is already `4.0` and can be withdrawn before the sale is
reconciled. On approval the remaining `36.0` is added (net full ₹40); on
rejection the advance is clawed back (net ₹0).

---

### 2. List a user's sales
`GET /users/{user_id}/sales`

Returns all sales for the user, newest first (array of the sale object above).
Used by the dashboard to render the sales table.

---

### 3. Run advance payout job
`POST /jobs/advance-payout?user_id={user_id}`

> **Note:** advances are now paid automatically when a sale is logged (§1), so
> this job is a **legacy backstop** — in normal operation it finds nothing
> eligible and pays `0`. It remains only to advance any sale that somehow has no
> advance yet, and to preserve idempotency guarantees.

Pays a **10% advance** on every *eligible* pending sale (status `pending` and no
advance yet). `user_id` is optional — omit it to run for all users.

**Idempotent:** running it again pays nobody a second time (query filter +
`UNIQUE(sale_id, ADVANCE)` DB constraint). Advance is floored to whole paise.

**Response** `200`
```json
{ "advances_made": 3, "total_advance_rupees": 12.0,
  "details": [ { "sale_id": 1, "user_id": "john_doe",
                 "advance_paise": 400, "advance_rupees": 4.0 } ] }
```

---

### 4. Reconcile sales
`POST /reconcile`

Reconciles one or more sales to `approved`/`rejected` and settles each sale's
final payout into the withdrawable balance.

**Request**
```json
{ "items": [ { "sale_id": 1, "status": "rejected" },
             { "sale_id": 2, "status": "approved" } ] }
```

**Response** `200`
```json
{ "reconciled": [
    { "sale_id": 2, "user_id": "john_doe", "status": "approved",
      "final_adjustment_rupees": 36.0,
      "withdrawable_balance_rupees": 40.0 } ] }
```

**Errors**
- `400 InvalidStatusError` — status not `approved`/`rejected`.
- `404 NotFoundError` — sale doesn't exist.
- `409 AlreadyReconciledError` — sale already settled (settle-once rule).

---

### 5. Initiate withdrawal
`POST /withdrawals`

Reserves and debits `amount` from the withdrawable balance and creates an
`initiated` withdrawal.

**Request**
```json
{ "user_id": "john_doe", "amount": 40 }
```

**Response** `201`
```json
{ "id": 1, "user_id": "john_doe", "amount_rupees": 40.0,
  "status": "initiated", "failure_reason": null,
  "created_at": "2026-07-19T10:00:00" }
```

**Errors**
- `429 WithdrawalTooSoonError` — another withdrawal within the last 24h (message
  includes the next allowed time). Failed/cancelled/rejected withdrawals do **not**
  count toward this limit.
- `422 InsufficientBalanceError` — amount ≤ 0 or greater than the balance.

---

### 6. List a user's withdrawals
`GET /users/{user_id}/withdrawals`

Returns all withdrawals for the user, newest first (array of the withdrawal object).

---

### 7. Complete withdrawal
`POST /withdrawals/{id}/complete`

Marks an `initiated` withdrawal `completed` (the external transfer succeeded).
No balance change. **Error:** `409 InvalidWithdrawalStateError` if not `initiated`.

---

### 8. Fail withdrawal (failed-payout recovery)
`POST /withdrawals/{id}/fail`

Marks a withdrawal `failed`/`cancelled`/`rejected` and **credits the amount back**
to the withdrawable balance so the user can withdraw again.

**Request**
```json
{ "status": "failed", "reason": "bank rejected" }
```

- **Idempotent** — a duplicate failure event does not double-credit
  (`UNIQUE(withdrawal_id, WITHDRAWAL_REVERSAL)` + status check).
- **Error:** `409 InvalidWithdrawalStateError` — a `completed` withdrawal cannot be
  failed (funds already left).
- `status` must be one of `failed` / `cancelled` / `rejected`.

---

### 9. Get balance + ledger
`GET /users/{user_id}/balance`

Returns the withdrawable balance and the full ledger (audit trail).

**Response** `200`
```json
{ "user_id": "john_doe", "withdrawable_balance_rupees": 80.0,
  "ledger": [
    { "id": 1, "entry_type": "ADVANCE", "amount_rupees": 4.0,
      "affects_withdrawable": true, "balance_after_rupees": 4.0,
      "sale_id": 1, "withdrawal_id": null,
      "note": "10% advance credited to balance when sale was logged",
      "created_at": "2026-07-19T10:00:00" } ] }
```

**Error:** `404 NotFoundError` — unknown user.

---

### 10. Meta
- `GET /health` → `{ "status": "ok" }`
- `GET /` → redirects to `/docs` (interactive API docs)

---

## Error format

All business-rule violations return a consistent JSON body:
```json
{ "error": "WithdrawalTooSoonError", "detail": "Only one withdrawal allowed per 24h; ..." }
```

| HTTP | Error | Meaning |
|---|---|---|
| 400 | `InvalidStatusError` | Bad reconcile status |
| 404 | `NotFoundError` | User / sale / withdrawal not found |
| 409 | `AlreadyReconciledError` | Sale already settled |
| 409 | `InvalidWithdrawalStateError` | Illegal withdrawal state transition |
| 422 | `InsufficientBalanceError` | Amount ≤ 0 or exceeds balance |
| 429 | `WithdrawalTooSoonError` | 24h withdrawal cap hit |

---

## Ledger entry types

| `entry_type` | Sign | Affects balance | Trigger |
|---|---|---|---|
| `ADVANCE` | + | yes | sale logged (auto) |
| `FINAL_APPROVED` | + | yes | sale approved |
| `FINAL_CLAWBACK` | − | yes | sale rejected |
| `WITHDRAWAL` | − | yes | withdrawal initiated |
| `WITHDRAWAL_REVERSAL` | + | yes | withdrawal failed/cancelled/rejected |

---

## Typical flow (the assignment example)

1. `POST /sales` ×3 (`john_doe`, `brand_1`, ₹40 each) → each auto-credits a ₹4
   advance to the balance on logging (**₹12** total, withdrawable **₹12** now)
2. `POST /reconcile` → sale 1 rejected, sales 2 & 3 approved
3. `GET /users/john_doe/balance` → withdrawable **₹80** (2 approved × ₹40, rejected nets ₹0)
4. `POST /withdrawals` → initiate ₹68
5. (optional) `POST /withdrawals/1/fail` → ₹68 credited back, re-withdrawable immediately
