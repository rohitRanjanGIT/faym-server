"""Withdrawal and failed-payout-recovery endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..db import get_db
from ..models import Withdrawal, WithdrawalStatus
from ..schemas import WithdrawalCreate, WithdrawalFail, WithdrawalOut
from ..services import withdrawal_service

router = APIRouter(tags=["withdrawals"])


def _to_out(w: Withdrawal) -> WithdrawalOut:
    return WithdrawalOut(
        id=w.id,
        user_id=w.user_id,
        amount_rupees=money.paise_to_rupees(w.amount_paise),
        status=w.status.value,
        failure_reason=w.failure_reason,
        created_at=w.created_at,
    )


@router.post("/withdrawals", response_model=WithdrawalOut, status_code=201)
def initiate(payload: WithdrawalCreate, db: Session = Depends(get_db)) -> WithdrawalOut:
    """Initiate a withdrawal (max one per user per 24 hours)."""
    w = withdrawal_service.initiate_withdrawal(
        db, payload.user_id, money.rupees_to_paise(payload.amount)
    )
    return _to_out(w)


@router.get("/users/{user_id}/withdrawals", response_model=list[WithdrawalOut])
def list_withdrawals(user_id: str, db: Session = Depends(get_db)) -> list[WithdrawalOut]:
    """List all withdrawals for a user, newest first."""
    rows = db.scalars(
        select(Withdrawal)
        .where(Withdrawal.user_id == user_id)
        .order_by(Withdrawal.id.desc())
    ).all()
    return [_to_out(w) for w in rows]


@router.post("/withdrawals/{withdrawal_id}/complete", response_model=WithdrawalOut)
def complete(withdrawal_id: int, db: Session = Depends(get_db)) -> WithdrawalOut:
    """Confirm a withdrawal's transfer succeeded."""
    return _to_out(withdrawal_service.complete_withdrawal(db, withdrawal_id))


@router.post("/withdrawals/{withdrawal_id}/fail", response_model=WithdrawalOut)
def fail(
    withdrawal_id: int, payload: WithdrawalFail, db: Session = Depends(get_db)
) -> WithdrawalOut:
    """Mark a withdrawal failed/cancelled/rejected and credit the amount back."""
    w = withdrawal_service.fail_withdrawal(
        db,
        withdrawal_id,
        WithdrawalStatus(payload.status),
        reason=payload.reason,
    )
    return _to_out(w)
