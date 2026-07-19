"""Final-payout calculation on reconciliation (Business Rule 2)."""
import pytest

from app.errors import AlreadyReconciledError, InvalidStatusError
from app.models import SaleStatus
from app.services import payout_service

from .conftest import make_sale


def test_approved_pays_earning_minus_advance(db, user):
    # Assignment Case 1: earning Rs 30, advance Rs 3 -> remaining Rs 27.
    sale = make_sale(db, earning_rupees=30)
    payout_service.run_advance_payout(db, user_id="john_doe")
    result = payout_service.reconcile_sale(db, sale.id, SaleStatus.approved)
    assert result["final_adjustment_paise"] == 2700
    db.refresh(user)
    assert user.withdrawable_balance_paise == 2700


def test_rejected_claws_back_advance(db, user):
    # Assignment Case 2: earning Rs 50, advance Rs 5 -> adjustment -Rs 5.
    sale = make_sale(db, earning_rupees=50)
    payout_service.run_advance_payout(db, user_id="john_doe")
    result = payout_service.reconcile_sale(db, sale.id, SaleStatus.rejected)
    assert result["final_adjustment_paise"] == -500
    db.refresh(user)
    assert user.withdrawable_balance_paise == -500


def test_approved_without_advance_pays_full_earning(db, user):
    # Reconciled before the advance job ever ran.
    sale = make_sale(db, earning_rupees=40)
    result = payout_service.reconcile_sale(db, sale.id, SaleStatus.approved)
    assert result["final_adjustment_paise"] == 4000


def test_rejected_without_advance_has_no_adjustment(db, user):
    sale = make_sale(db, earning_rupees=40)
    result = payout_service.reconcile_sale(db, sale.id, SaleStatus.rejected)
    assert result["final_adjustment_paise"] == 0


def test_full_worked_example(db, user):
    """3 x Rs 40, one rejected + two approved -> advance Rs 12, final Rs 68."""
    sales = [make_sale(db, earning_rupees=40) for _ in range(3)]
    made = payout_service.run_advance_payout(db, user_id="john_doe")
    assert sum(m["advance_paise"] for m in made) == 1200  # Rs 12

    payout_service.reconcile_sale(db, sales[0].id, SaleStatus.rejected)
    payout_service.reconcile_sale(db, sales[1].id, SaleStatus.approved)
    payout_service.reconcile_sale(db, sales[2].id, SaleStatus.approved)

    db.refresh(user)
    assert user.withdrawable_balance_paise == 6800  # Rs 68


def test_cannot_reconcile_twice(db, user):
    sale = make_sale(db, earning_rupees=40)
    payout_service.reconcile_sale(db, sale.id, SaleStatus.approved)
    with pytest.raises(AlreadyReconciledError):
        payout_service.reconcile_sale(db, sale.id, SaleStatus.rejected)


def test_reconcile_rejects_invalid_status(db, user):
    sale = make_sale(db, earning_rupees=40)
    with pytest.raises(InvalidStatusError):
        payout_service.reconcile_sale(db, sale.id, SaleStatus.pending)
