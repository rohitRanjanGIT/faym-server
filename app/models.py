"""SQLAlchemy ORM models — the database schema.

Money is stored everywhere as an integer number of paise (1 rupee = 100
paise). Integers avoid floating-point rounding errors that would otherwise
corrupt balances over many operations.

The ``LedgerEntry`` table is the heart of the design: every movement of money
is an immutable, append-only row. A user's withdrawable balance is the sum of
the balance-affecting ledger rows, which makes the system fully auditable and
reconcilable.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class SaleStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class WithdrawalStatus(str, enum.Enum):
    initiated = "initiated"   # money reserved, transfer in flight
    completed = "completed"   # transfer confirmed
    failed = "failed"         # transfer failed  -> reversed
    cancelled = "cancelled"   # user/admin cancelled -> reversed
    rejected = "rejected"     # payment provider rejected -> reversed


# The three terminal states that trigger a credit-back (Question 2).
REVERSIBLE_WITHDRAWAL_STATES = {
    WithdrawalStatus.failed,
    WithdrawalStatus.cancelled,
    WithdrawalStatus.rejected,
}


class LedgerType(str, enum.Enum):
    ADVANCE = "ADVANCE"                        # 10% advance transferred to user
    FINAL_APPROVED = "FINAL_APPROVED"          # earning - advance, on approval
    FINAL_CLAWBACK = "FINAL_CLAWBACK"          # -advance, on rejection
    WITHDRAWAL = "WITHDRAWAL"                   # user pulls from balance
    WITHDRAWAL_REVERSAL = "WITHDRAWAL_REVERSAL"  # failed payout credited back


class User(Base):
    __tablename__ = "users"

    # The natural id from the reference data, e.g. "john_doe".
    id: Mapped[str] = mapped_column(String, primary_key=True)
    # Materialized withdrawable balance for O(1) reads and cheap guards.
    # Always kept equal to SUM(ledger.amount_paise WHERE affects_withdrawable).
    withdrawable_balance_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sales: Mapped[list["Sale"]] = relationship(back_populates="user")
    withdrawals: Mapped[list["Withdrawal"]] = relationship(back_populates="user")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="user")


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    brand: Mapped[str] = mapped_column(String, nullable=False)
    earning_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SaleStatus] = mapped_column(
        Enum(SaleStatus), default=SaleStatus.pending, nullable=False
    )

    # Advance-payout bookkeeping. advance_paid_paise > 0 (or advance_paid_at set)
    # means the advance has already been transferred for this sale.
    advance_paid_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    advance_paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reconciliation bookkeeping — a sale is settled exactly once.
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sales")

    __table_args__ = (
        # The advance job filters on (user, status, advance not yet paid);
        # this index keeps that scan cheap.
        Index("ix_sales_user_status", "user_id", "status"),
    )


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus), default=WithdrawalStatus.initiated, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="withdrawals")

    __table_args__ = (
        # The 24h rule queries the user's most recent non-failed withdrawal.
        Index("ix_withdrawals_user_created", "user_id", "created_at"),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    entry_type: Mapped[LedgerType] = mapped_column(Enum(LedgerType), nullable=False)

    # Signed amount: credits are positive, debits negative.
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)

    # Whether this entry moves the *withdrawable* balance. ADVANCE payouts are
    # transferred directly to the user and do NOT feed the withdrawable balance,
    # so they are recorded for audit with affects_withdrawable = False.
    affects_withdrawable: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Running withdrawable balance after this entry (None for non-affecting rows).
    balance_after_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), nullable=True)
    withdrawal_id: Mapped[int | None] = mapped_column(
        ForeignKey("withdrawals.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="ledger_entries")

    __table_args__ = (
        # Idempotency backstop: at most one ledger row of a given type per sale.
        # Guarantees an advance (or final settlement) can never be booked twice,
        # even under concurrent job runs.
        UniqueConstraint("sale_id", "entry_type", name="uq_ledger_sale_type"),
        # At most one reversal per withdrawal — a failed payout is credited back
        # exactly once even if the failure webhook fires repeatedly.
        UniqueConstraint(
            "withdrawal_id", "entry_type", name="uq_ledger_withdrawal_type"
        ),
        Index("ix_ledger_user", "user_id"),
    )
