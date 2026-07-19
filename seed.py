"""Reproduce the assignment's worked example end-to-end against the real DB.

Run with:  uv run python seed.py

Expected: advance = Rs 12, final payout = Rs 68 for john_doe.
"""
from app.db import Base, SessionLocal, engine
from app.models import Sale, SaleStatus, User
from app import money
from app.services import payout_service


def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def main():
    reset_db()
    db = SessionLocal()
    try:
        db.add(User(id="john_doe"))
        for _ in range(3):
            db.add(
                Sale(
                    user_id="john_doe",
                    brand="brand_1",
                    earning_paise=money.rupees_to_paise(40),
                    status=SaleStatus.pending,
                )
            )
        db.commit()

        # --- Advance payout (10% of Rs 120 = Rs 12) ---
        made = payout_service.run_advance_payout(db, user_id="john_doe")
        total_advance = sum(m["advance_paise"] for m in made)
        print(f"Advance paid on {len(made)} sales: Rs {total_advance / 100}")

        # --- Reconcile: 1 rejected, 2 approved ---
        sales = db.query(Sale).order_by(Sale.id).all()
        payout_service.reconcile_sale(db, sales[0].id, SaleStatus.rejected)
        payout_service.reconcile_sale(db, sales[1].id, SaleStatus.approved)
        payout_service.reconcile_sale(db, sales[2].id, SaleStatus.approved)

        user = db.get(User, "john_doe")
        final = user.withdrawable_balance_paise
        print(f"Final withdrawable payout: Rs {final / 100}")
        assert total_advance == 1200, total_advance
        assert final == 6800, final
        print("OK: matches expected Rs 12 advance and Rs 68 final payout.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
