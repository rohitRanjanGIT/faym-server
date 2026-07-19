"""Advance-payout rules, including idempotency (Business Rule 1)."""
from app.models import LedgerType, Sale, SaleStatus
from app.services import payout_service

from .conftest import make_sale


def test_advance_is_ten_percent(db, user):
    make_sale(db, earning_rupees=40)
    made = payout_service.run_advance_payout(db, user_id="john_doe")
    assert len(made) == 1
    assert made[0]["advance_paise"] == 400  # Rs 4


def test_advance_is_idempotent_across_multiple_runs(db, user):
    make_sale(db, earning_rupees=40)
    make_sale(db, earning_rupees=40)
    make_sale(db, earning_rupees=40)

    first = payout_service.run_advance_payout(db, user_id="john_doe")
    assert len(first) == 3  # Rs 12 total

    # Running again pays nobody a second time.
    second = payout_service.run_advance_payout(db, user_id="john_doe")
    assert second == []

    # Exactly one ADVANCE ledger entry per sale.
    advances = (
        db.query(payout_service.Sale).filter(Sale.advance_paid_paise > 0).count()
    )
    assert advances == 3


def test_advance_only_for_pending_sales(db, user):
    sale = make_sale(db, earning_rupees=40)
    sale.status = SaleStatus.approved  # already reconciled elsewhere
    db.commit()

    made = payout_service.run_advance_payout(db, user_id="john_doe")
    assert made == []


def test_advance_credits_withdrawable_balance(db, user):
    make_sale(db, earning_rupees=40)
    payout_service.run_advance_payout(db, user_id="john_doe")
    db.refresh(user)
    # The advance is credited to the withdrawable balance immediately.
    assert user.withdrawable_balance_paise == 400  # Rs 4
