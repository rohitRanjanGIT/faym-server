"""Advance-payout job endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import payout_service

router = APIRouter(tags=["payouts"])


@router.post("/jobs/advance-payout")
def run_advance_payout(
    user_id: str | None = None, db: Session = Depends(get_db)
) -> dict:
    """Run the advance-payout job.

    Pays a 10% advance on every eligible pending sale (optionally scoped to one
    user). Safe to run repeatedly — already-advanced sales are skipped.
    """
    made = payout_service.run_advance_payout(db, user_id=user_id)
    total = sum(m["advance_paise"] for m in made)
    return {
        "advances_made": len(made),
        "total_advance_rupees": total / 100,
        "details": made,
    }
