"""User balance and ledger endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..db import get_db
from ..errors import NotFoundError
from ..models import LedgerEntry, User
from ..schemas import BalanceOut, LedgerEntryOut

router = APIRouter(tags=["users"])


@router.get("/users/{user_id}/balance", response_model=BalanceOut)
def get_balance(user_id: str, db: Session = Depends(get_db)) -> BalanceOut:
    """Return a user's withdrawable balance and full ledger (audit trail)."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found")

    entries = db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.id)
    ).all()

    ledger = [
        LedgerEntryOut(
            id=e.id,
            entry_type=e.entry_type.value,
            amount_rupees=money.paise_to_rupees(e.amount_paise),
            affects_withdrawable=e.affects_withdrawable,
            balance_after_rupees=(
                money.paise_to_rupees(e.balance_after_paise)
                if e.balance_after_paise is not None
                else None
            ),
            sale_id=e.sale_id,
            withdrawal_id=e.withdrawal_id,
            note=e.note,
            created_at=e.created_at,
        )
        for e in entries
    ]

    return BalanceOut(
        user_id=user.id,
        withdrawable_balance_rupees=money.paise_to_rupees(
            user.withdrawable_balance_paise
        ),
        ledger=ledger,
    )
