"""Withdrawal restrictions (Business Rule 3) and failed-payout recovery (Q2)."""
from datetime import datetime, timedelta

import pytest

from app.errors import (
    InsufficientBalanceError,
    InvalidWithdrawalStateError,
    WithdrawalTooSoonError,
)
from app.models import SaleStatus, WithdrawalStatus
from app.services import payout_service, withdrawal_service

from .conftest import make_sale


def _fund(db, rupees=100):
    """Give the user a positive withdrawable balance via an approved sale."""
    sale = make_sale(db, earning_rupees=rupees)
    payout_service.reconcile_sale(db, sale.id, SaleStatus.approved)


def test_withdrawal_reduces_balance(db, user):
    _fund(db, rupees=100)
    withdrawal_service.initiate_withdrawal(db, "john_doe", 4000)  # Rs 40
    db.refresh(user)
    assert user.withdrawable_balance_paise == 6000  # Rs 60 left


def test_cannot_withdraw_more_than_balance(db, user):
    _fund(db, rupees=10)
    with pytest.raises(InsufficientBalanceError):
        withdrawal_service.initiate_withdrawal(db, "john_doe", 5000)


def test_only_one_withdrawal_per_24h(db, user):
    _fund(db, rupees=100)
    now = datetime.utcnow()
    withdrawal_service.initiate_withdrawal(db, "john_doe", 1000, now=now)

    # A second attempt 1 hour later is blocked.
    with pytest.raises(WithdrawalTooSoonError):
        withdrawal_service.initiate_withdrawal(
            db, "john_doe", 1000, now=now + timedelta(hours=1)
        )

    # 24h later it is allowed.
    withdrawal_service.initiate_withdrawal(
        db, "john_doe", 1000, now=now + timedelta(hours=24, minutes=1)
    )


def test_failed_payout_is_credited_back(db, user):
    _fund(db, rupees=100)
    w = withdrawal_service.initiate_withdrawal(db, "john_doe", 4000)
    db.refresh(user)
    assert user.withdrawable_balance_paise == 6000

    withdrawal_service.fail_withdrawal(db, w.id, WithdrawalStatus.failed, reason="bank down")
    db.refresh(user)
    assert user.withdrawable_balance_paise == 10000  # fully restored


def test_recovered_amount_can_be_rewithdrawn_immediately(db, user):
    _fund(db, rupees=100)
    now = datetime.utcnow()
    w = withdrawal_service.initiate_withdrawal(db, "john_doe", 4000, now=now)
    withdrawal_service.fail_withdrawal(db, w.id, WithdrawalStatus.rejected)

    # Even though <24h have passed, the failed withdrawal no longer counts, so a
    # new withdrawal is permitted right away (Question 2).
    w2 = withdrawal_service.initiate_withdrawal(
        db, "john_doe", 4000, now=now + timedelta(minutes=5)
    )
    assert w2.status == WithdrawalStatus.initiated


def test_failure_credit_back_is_idempotent(db, user):
    _fund(db, rupees=100)
    w = withdrawal_service.initiate_withdrawal(db, "john_doe", 4000)
    withdrawal_service.fail_withdrawal(db, w.id, WithdrawalStatus.failed)
    # A duplicate failure event must not double-credit.
    withdrawal_service.fail_withdrawal(db, w.id, WithdrawalStatus.failed)
    db.refresh(user)
    assert user.withdrawable_balance_paise == 10000


def test_completed_withdrawal_cannot_be_failed(db, user):
    _fund(db, rupees=100)
    w = withdrawal_service.initiate_withdrawal(db, "john_doe", 4000)
    withdrawal_service.complete_withdrawal(db, w.id)
    with pytest.raises(InvalidWithdrawalStateError):
        withdrawal_service.fail_withdrawal(db, w.id, WithdrawalStatus.failed)
