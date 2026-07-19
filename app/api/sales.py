"""Sale creation, listing, and reconciliation endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..auth import (
    Principal,
    get_principal,
    require_admin,
    require_participant,
    require_self_or_admin,
)
from ..db import get_db
from ..errors import NotFoundError
from ..models import Sale, SaleStatus, User
from ..schemas import ReconcileRequest, SaleCreate, SaleOut
from ..services import payout_service

router = APIRouter(tags=["sales"])


def _to_out(sale: Sale) -> SaleOut:
    return SaleOut(
        id=sale.id,
        user_id=sale.user_id,
        brand=sale.brand,
        earning_rupees=money.paise_to_rupees(sale.earning_paise),
        status=sale.status.value,
        advance_paid_rupees=money.paise_to_rupees(sale.advance_paid_paise),
        reconciled=sale.reconciled,
    )


@router.post("/sales", response_model=SaleOut, status_code=201)
def create_sale(
    payload: SaleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> SaleOut:
    """Record a new sale for the signed-in user and pay its 10% advance.

    Self-service only: a user creates their own sales. Admins do not participate
    in sales — they manage users and settlement. The 10% advance is paid up
    front the moment the sale is logged (it does not enter the withdrawable
    balance); the remaining 90% settles on approval, or the advance is clawed
    back on rejection (leaving -10% of the earning).
    """
    require_participant(payload.user_id, principal)
    user = db.get(User, payload.user_id)
    if user is None:
        raise NotFoundError(f"User '{payload.user_id}' not found")

    sale = Sale(
        user_id=payload.user_id,
        brand=payload.brand,
        earning_paise=money.rupees_to_paise(payload.earning),
        status=SaleStatus.pending,
    )
    db.add(sale)
    db.flush()  # assign sale.id before writing the advance ledger entry
    payout_service.pay_advance_for_sale(db, sale, user)
    db.commit()
    db.refresh(sale)
    return _to_out(sale)


@router.get("/users/{user_id}/sales", response_model=list[SaleOut])
def list_sales(
    user_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[SaleOut]:
    """List all sales for a user, newest first (self or admin)."""
    require_self_or_admin(user_id, principal)
    sales = db.scalars(
        select(Sale).where(Sale.user_id == user_id).order_by(Sale.id.desc())
    ).all()
    return [_to_out(s) for s in sales]


@router.post("/reconcile")
def reconcile(
    payload: ReconcileRequest,
    db: Session = Depends(get_db),
    _admin: Principal = Depends(require_admin),
) -> dict:
    """Reconcile one or more sales to approved/rejected and settle each (admin only)."""
    results = [
        payout_service.reconcile_sale(db, item.sale_id, SaleStatus(item.status))
        for item in payload.items
    ]
    return {"reconciled": results}
