"""Sale creation, listing, and reconciliation endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import money
from ..db import get_db
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
def create_sale(payload: SaleCreate, db: Session = Depends(get_db)) -> SaleOut:
    """Record a new sale. New sales always start as ``pending``.

    The user is created on first sight for convenience in this demo.
    """
    if db.get(User, payload.user_id) is None:
        db.add(User(id=payload.user_id))

    sale = Sale(
        user_id=payload.user_id,
        brand=payload.brand,
        earning_paise=money.rupees_to_paise(payload.earning),
        status=SaleStatus.pending,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return _to_out(sale)


@router.get("/users/{user_id}/sales", response_model=list[SaleOut])
def list_sales(user_id: str, db: Session = Depends(get_db)) -> list[SaleOut]:
    """List all sales for a user, newest first."""
    sales = db.scalars(
        select(Sale).where(Sale.user_id == user_id).order_by(Sale.id.desc())
    ).all()
    return [_to_out(s) for s in sales]


@router.post("/reconcile")
def reconcile(payload: ReconcileRequest, db: Session = Depends(get_db)) -> dict:
    """Reconcile one or more sales to approved/rejected and settle each."""
    results = [
        payout_service.reconcile_sale(db, item.sale_id, SaleStatus(item.status))
        for item in payload.items
    ]
    return {"reconciled": results}
