"""Admin maintenance endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import Principal, require_admin
from ..db import get_db
from ..models import LedgerEntry, Sale, User, Withdrawal
from ..seed import seed_default_accounts

router = APIRouter(tags=["admin"])


@router.post("/admin/clear-database")
def clear_database(
    db: Session = Depends(get_db),
    _admin: Principal = Depends(require_admin),
) -> dict:
    """Wipe all data and reset to the seeded admin/user accounts (admin only).

    Destructive: removes every sale, withdrawal, ledger entry, and user, then
    re-seeds the default accounts. Intended for demos/testing.
    """
    # Delete in FK-safe order (children before parents).
    db.query(LedgerEntry).delete()
    db.query(Withdrawal).delete()
    db.query(Sale).delete()
    db.query(User).delete()
    db.commit()

    # Reset SQLite autoincrement counters so ids start from 1 again.
    try:
        db.execute(
            text(
                "DELETE FROM sqlite_sequence "
                "WHERE name IN ('sales', 'withdrawals', 'ledger_entries')"
            )
        )
        db.commit()
    except Exception:
        db.rollback()  # non-SQLite backend or no sequence table — harmless

    seeded = seed_default_accounts()
    return {"status": "cleared", "seeded_users": seeded}
