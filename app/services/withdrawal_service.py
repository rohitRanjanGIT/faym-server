"""Withdrawals and failed-payout recovery — Question 1 (Rule 3) & Question 2."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..clock import utcnow
from ..errors import (
    InsufficientBalanceError,
    InvalidWithdrawalStateError,
    NotFoundError,
    WithdrawalTooSoonError,
)
from ..models import (
    REVERSIBLE_WITHDRAWAL_STATES,
    LedgerType,
    User,
    Withdrawal,
    WithdrawalStatus,
)
from .ledger import post_entry

WITHDRAWAL_COOLDOWN = timedelta(hours=24)

# Statuses that still "count" against the 24h rule. A failed/cancelled/rejected
# withdrawal is voided, so it must NOT block the user's next attempt — this is
# what lets a recovered payout (Question 2) be re-initiated immediately.
ACTIVE_WITHDRAWAL_STATES = (WithdrawalStatus.initiated, WithdrawalStatus.completed)


def _get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found")
    return user


def _last_active_withdrawal_at(db: Session, user_id: str) -> datetime | None:
    stmt = (
        select(Withdrawal.created_at)
        .where(
            Withdrawal.user_id == user_id,
            Withdrawal.status.in_(ACTIVE_WITHDRAWAL_STATES),
        )
        .order_by(Withdrawal.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def initiate_withdrawal(
    db: Session, user_id: str, amount_paise: int, *, now: datetime | None = None
) -> Withdrawal:
    """Initiate a withdrawal, enforcing the 24h cap and balance check."""
    now = now or utcnow()
    user = _get_user(db, user_id)

    if amount_paise <= 0:
        raise InsufficientBalanceError("Withdrawal amount must be positive")

    last = _last_active_withdrawal_at(db, user_id)
    if last is not None and now - last < WITHDRAWAL_COOLDOWN:
        next_allowed = last + WITHDRAWAL_COOLDOWN
        raise WithdrawalTooSoonError(
            f"Only one withdrawal allowed per 24h; next allowed at {next_allowed.isoformat()}Z"
        )

    if amount_paise > user.withdrawable_balance_paise:
        raise InsufficientBalanceError(
            f"Requested {money.paise_to_rupees(amount_paise)} exceeds balance "
            f"{money.paise_to_rupees(user.withdrawable_balance_paise)}"
        )

    withdrawal = Withdrawal(
        user_id=user_id,
        amount_paise=amount_paise,
        status=WithdrawalStatus.initiated,
        created_at=now,
    )
    db.add(withdrawal)
    db.flush()  # assign withdrawal.id for the ledger FK

    post_entry(
        db,
        user,
        LedgerType.WITHDRAWAL,
        -amount_paise,
        affects_withdrawable=True,
        withdrawal_id=withdrawal.id,
        note="Withdrawal initiated",
    )
    db.commit()
    return withdrawal


def complete_withdrawal(db: Session, withdrawal_id: int) -> Withdrawal:
    """Mark an initiated withdrawal as completed (transfer confirmed)."""
    withdrawal = db.get(Withdrawal, withdrawal_id)
    if withdrawal is None:
        raise NotFoundError(f"Withdrawal {withdrawal_id} not found")
    if withdrawal.status != WithdrawalStatus.initiated:
        raise InvalidWithdrawalStateError(
            f"Only an initiated withdrawal can be completed (is '{withdrawal.status.value}')"
        )
    withdrawal.status = WithdrawalStatus.completed
    db.commit()
    return withdrawal


def fail_withdrawal(
    db: Session,
    withdrawal_id: int,
    new_status: WithdrawalStatus,
    *,
    reason: str | None = None,
) -> Withdrawal:
    """Void a withdrawal and credit its amount back (Question 2).

    Valid ``new_status`` values are failed / cancelled / rejected. The amount is
    returned to the withdrawable balance so the user can withdraw it again. The
    unique (withdrawal_id, WITHDRAWAL_REVERSAL) ledger constraint makes this
    safe to call repeatedly for the same failure event (idempotent).
    """
    if new_status not in REVERSIBLE_WITHDRAWAL_STATES:
        raise InvalidWithdrawalStateError(
            "Failure status must be one of failed / cancelled / rejected"
        )

    withdrawal = db.get(Withdrawal, withdrawal_id)
    if withdrawal is None:
        raise NotFoundError(f"Withdrawal {withdrawal_id} not found")

    # Idempotency: if it is already in a reversed state, do nothing.
    if withdrawal.status in REVERSIBLE_WITHDRAWAL_STATES:
        return withdrawal
    if withdrawal.status == WithdrawalStatus.completed:
        raise InvalidWithdrawalStateError(
            "A completed withdrawal cannot be failed; funds have already left"
        )

    user = _get_user(db, withdrawal.user_id)
    withdrawal.status = new_status
    withdrawal.failure_reason = reason

    post_entry(
        db,
        user,
        LedgerType.WITHDRAWAL_REVERSAL,
        withdrawal.amount_paise,  # positive: credit back
        affects_withdrawable=True,
        withdrawal_id=withdrawal.id,
        note=f"Payout {new_status.value}; amount credited back",
    )
    db.commit()
    return withdrawal
