"""Advance payouts and reconciliation — Question 1 core logic."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..clock import utcnow
from ..errors import AlreadyReconciledError, InvalidStatusError, NotFoundError
from ..models import LedgerType, Sale, SaleStatus, User
from .ledger import post_entry


def _get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found")
    return user


def pay_advance_for_sale(db: Session, sale: Sale, user: User) -> int:
    """Pay the 10% advance for a single sale. Returns the paise paid (0 if none).

    Idempotent: a sale that already has an advance (``advance_paid_at`` set) is
    left untouched, and the ledger's UNIQUE (sale_id, ADVANCE) constraint is a
    backstop. The advance is credited to the user's **withdrawable balance**
    immediately on logging, so it can be withdrawn right away. On approval the
    remaining 90% is added (total = the full earning); on rejection the advance
    is clawed back (net 0, or negative if it was already withdrawn).

    The caller commits the surrounding transaction.
    """
    if sale.advance_paid_at is not None:
        return 0
    advance = money.advance_of(sale.earning_paise)
    if advance <= 0:
        return 0  # nothing to pay (e.g. sub-10-paise earning)

    sale.advance_paid_paise = advance
    sale.advance_paid_at = utcnow()
    post_entry(
        db,
        user,
        LedgerType.ADVANCE,
        advance,
        affects_withdrawable=True,
        sale_id=sale.id,
        note="10% advance credited to balance when sale was logged",
    )
    return advance


def run_advance_payout(db: Session, user_id: str | None = None) -> list[dict]:
    """Pay a 10% advance on every eligible pending sale.

    Eligible = status is ``pending`` AND no advance has been paid yet. Because
    the query itself excludes already-advanced sales — and the ledger has a
    unique (sale_id, ADVANCE) constraint as a backstop — running this job any
    number of times pays each sale exactly once (idempotent, Business Rule 1).

    Returns a list describing each advance actually made this run.
    """
    stmt = select(Sale).where(
        Sale.status == SaleStatus.pending,
        Sale.advance_paid_at.is_(None),
    )
    if user_id is not None:
        stmt = stmt.where(Sale.user_id == user_id)

    made: list[dict] = []
    for sale in db.scalars(stmt).all():
        user = _get_user(db, sale.user_id)
        advance = pay_advance_for_sale(db, sale, user)
        if advance <= 0:
            continue
        made.append(
            {
                "sale_id": sale.id,
                "user_id": sale.user_id,
                "advance_paise": advance,
                "advance_rupees": money.paise_to_rupees(advance),
            }
        )

    db.commit()
    return made


def reconcile_sale(db: Session, sale_id: int, new_status: SaleStatus) -> dict:
    """Reconcile a single sale to approved/rejected and settle its final payout.

    Per-sale contribution to the final payout (Business Rule 2):
      * Approved -> +(earning - advance_already_paid)
      * Rejected -> -(advance_already_paid)   [clawback]

    A sale is reconciled exactly once; re-reconciling raises.
    """
    if new_status not in (SaleStatus.approved, SaleStatus.rejected):
        raise InvalidStatusError(
            "Reconciliation status must be 'approved' or 'rejected'"
        )

    sale = db.get(Sale, sale_id)
    if sale is None:
        raise NotFoundError(f"Sale {sale_id} not found")
    if sale.reconciled:
        raise AlreadyReconciledError(f"Sale {sale_id} is already reconciled")

    user = _get_user(db, sale.user_id)
    sale.status = new_status
    sale.reconciled = True
    sale.reconciled_at = utcnow()

    if new_status == SaleStatus.approved:
        final = sale.earning_paise - sale.advance_paid_paise
        post_entry(
            db,
            user,
            LedgerType.FINAL_APPROVED,
            final,
            affects_withdrawable=True,
            sale_id=sale.id,
            note="Approved: earning minus advance already paid",
        )
    else:  # rejected
        final = -sale.advance_paid_paise  # 0 if no advance was paid
        if final != 0:
            post_entry(
                db,
                user,
                LedgerType.FINAL_CLAWBACK,
                final,
                affects_withdrawable=True,
                sale_id=sale.id,
                note="Rejected: clawback of advance the user was not entitled to",
            )

    db.commit()
    return {
        "sale_id": sale.id,
        "user_id": sale.user_id,
        "status": new_status.value,
        "final_adjustment_paise": final,
        "final_adjustment_rupees": money.paise_to_rupees(final),
        "withdrawable_balance_paise": user.withdrawable_balance_paise,
        "withdrawable_balance_rupees": money.paise_to_rupees(
            user.withdrawable_balance_paise
        ),
    }
