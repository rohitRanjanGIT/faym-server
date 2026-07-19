"""Time source. Kept naive-UTC to match SQLite's naive DATETIME storage.

Centralizing "now" also makes it trivial to inject a fixed clock in tests.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (no tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
