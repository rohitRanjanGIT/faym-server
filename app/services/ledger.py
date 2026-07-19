"""Central helper for writing ledger entries and keeping balances consistent.

Every balance movement in the system goes through ``post_entry`` so that the
materialized ``User.withdrawable_balance_paise`` and the append-only ledger can
never drift apart — they are always updated together in the same transaction.
"""
from sqlalchemy.orm import Session

from ..models import LedgerEntry, LedgerType, User


def post_entry(
    db: Session,
    user: User,
    entry_type: LedgerType,
    amount_paise: int,
    *,
    affects_withdrawable: bool,
    sale_id: int | None = None,
    withdrawal_id: int | None = None,
    note: str | None = None,
) -> LedgerEntry:
    """Append a ledger row and, if it affects the balance, update the user.

    The caller is responsible for committing the surrounding transaction.
    """
    if affects_withdrawable:
        user.withdrawable_balance_paise += amount_paise
        balance_after = user.withdrawable_balance_paise
    else:
        balance_after = None

    entry = LedgerEntry(
        user_id=user.id,
        entry_type=entry_type,
        amount_paise=amount_paise,
        affects_withdrawable=affects_withdrawable,
        balance_after_paise=balance_after,
        sale_id=sale_id,
        withdrawal_id=withdrawal_id,
        note=note,
    )
    db.add(entry)
    return entry
