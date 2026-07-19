"""Pydantic request/response models.

The public contract is expressed in rupees for readability; the service layer
works in paise. Responses generally include both.
"""
from datetime import datetime

from pydantic import BaseModel, Field


# ---- Sales ----------------------------------------------------------------
class SaleCreate(BaseModel):
    user_id: str = Field(examples=["john_doe"])
    brand: str = Field(examples=["brand_1"])
    earning: float = Field(gt=0, examples=[40], description="Sale earning in rupees")


class SaleOut(BaseModel):
    id: int
    user_id: str
    brand: str
    earning_rupees: float
    status: str
    advance_paid_rupees: float
    reconciled: bool


# ---- Reconciliation -------------------------------------------------------
class ReconcileItem(BaseModel):
    sale_id: int
    status: str = Field(examples=["approved", "rejected"])


class ReconcileRequest(BaseModel):
    items: list[ReconcileItem]


# ---- Withdrawals ----------------------------------------------------------
class WithdrawalCreate(BaseModel):
    user_id: str
    amount: float = Field(gt=0, description="Amount to withdraw in rupees")


class WithdrawalFail(BaseModel):
    status: str = Field(examples=["failed", "cancelled", "rejected"])
    reason: str | None = None


class WithdrawalOut(BaseModel):
    id: int
    user_id: str
    amount_rupees: float
    status: str
    failure_reason: str | None = None
    created_at: datetime


# ---- Balance / ledger -----------------------------------------------------
class LedgerEntryOut(BaseModel):
    id: int
    entry_type: str
    amount_rupees: float
    affects_withdrawable: bool
    balance_after_rupees: float | None
    sale_id: int | None
    withdrawal_id: int | None
    note: str | None
    created_at: datetime


class BalanceOut(BaseModel):
    user_id: str
    withdrawable_balance_rupees: float
    ledger: list[LedgerEntryOut]
