"""User balance and ledger endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..auth import Principal, get_principal, hash_password, require_admin, require_self_or_admin
from ..db import get_db
from ..errors import AlreadyExistsError, DomainError, NotFoundError
from ..models import LedgerEntry, Sale, User, UserRole, Withdrawal
from ..schemas import BalanceOut, LedgerEntryOut, UserCreate, UserSummary

router = APIRouter(tags=["users"])


def _to_summary(user: User) -> UserSummary:
    return UserSummary(
        user_id=user.id,
        role=user.role.value,
        withdrawable_balance_rupees=money.paise_to_rupees(
            user.withdrawable_balance_paise
        ),
        created_at=user.created_at,
    )


@router.post("/users", response_model=UserSummary, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: Principal = Depends(require_admin),
) -> UserSummary:
    """Provision a user with login credentials (admin only)."""
    user_id = payload.user_id.strip()
    if not user_id:
        raise DomainError("user_id must not be empty")
    try:
        role = UserRole(payload.role)
    except ValueError:
        raise DomainError("role must be 'admin' or 'user'")

    existing = db.get(User, user_id)
    if existing is not None and existing.password_hash:
        raise AlreadyExistsError(f"User '{user_id}' already exists")

    if existing is None:
        db.add(User(id=user_id, role=role, password_hash=hash_password(payload.password)))
    else:
        # User was auto-created by a sale but never had a login; grant one now.
        existing.role = role
        existing.password_hash = hash_password(payload.password)
    db.commit()
    user = db.get(User, user_id)
    return _to_summary(user)


@router.get("/users", response_model=list[UserSummary])
def list_users(
    db: Session = Depends(get_db),
    _admin: Principal = Depends(require_admin),
) -> list[UserSummary]:
    """List all users, newest first, with their withdrawable balances (admin only)."""
    users = db.scalars(
        select(User).order_by(User.created_at.desc(), User.id)
    ).all()
    return [_to_summary(u) for u in users]


@router.get("/users/{user_id}/balance", response_model=BalanceOut)
def get_balance(
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> BalanceOut:
    """Return a user's withdrawable balance and full ledger (self or admin)."""
    require_self_or_admin(user_id, principal)
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


@router.post("/users/{user_id}/reset")
def reset_user_data(
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> dict:
    """Clear a single user's own activity (self or admin).

    Deletes the user's sales, withdrawals, and ledger entries and zeroes their
    withdrawable balance. The account itself (login + role) is preserved, and
    other users are untouched.
    """
    require_self_or_admin(user_id, principal)
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found")

    # Delete in FK-safe order (ledger references sales/withdrawals).
    db.query(LedgerEntry).filter(LedgerEntry.user_id == user_id).delete()
    db.query(Withdrawal).filter(Withdrawal.user_id == user_id).delete()
    db.query(Sale).filter(Sale.user_id == user_id).delete()
    user.withdrawable_balance_paise = 0
    db.commit()
    return {"status": "reset", "user_id": user_id}
