"""Seed the default admin and user accounts.

Idempotent: only creates accounts that are missing. Credentials are overridable
via env vars (defaults: admin/admin123 and user/user123). Kept in its own module
so both app startup and the admin "clear database" action can call it without an
import cycle.
"""
import os

from sqlalchemy.exc import IntegrityError

from .auth import hash_password
from .db import SessionLocal
from .models import User, UserRole


def seed_default_accounts() -> list[str]:
    """Ensure the default admin and user exist. Returns the ids created."""
    defaults = [
        (os.getenv("ADMIN_USERNAME", "admin"),
         os.getenv("ADMIN_PASSWORD", "admin123"), UserRole.admin),
        (os.getenv("USER_USERNAME", "user"),
         os.getenv("USER_PASSWORD", "user123"), UserRole.user),
    ]
    db = SessionLocal()
    created: list[str] = []
    try:
        for uid, password, role in defaults:
            if db.get(User, uid) is None:
                db.add(User(id=uid, role=role, password_hash=hash_password(password)))
                created.append(uid)
        if created:
            try:
                db.commit()
            except IntegrityError:
                # Another serverless cold start seeded concurrently — fine.
                db.rollback()
                created = []
    finally:
        db.close()
    return created
