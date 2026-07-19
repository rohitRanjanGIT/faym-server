"""Authentication: password hashing, signed tokens, and FastAPI guards.

Kept dependency-free on purpose — uses only the standard library:

* Passwords are hashed with PBKDF2-HMAC-SHA256 (``hashlib``).
* Tokens are compact HMAC-signed ``<payload>.<signature>`` strings (like a
  minimal JWT) carrying the user id, role, and an expiry.

For a production system you'd reach for a vetted library (passlib/bcrypt,
python-jose) and rotate ``AUTH_SECRET`` via your secret manager; this is a
self-contained, auditable equivalent for the demo.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Depends, Header

from .errors import AuthError, ForbiddenError

_SECRET = os.getenv("AUTH_SECRET", "dev-insecure-secret-change-me").encode()
_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL", str(24 * 60 * 60)))
_PBKDF2_ROUNDS = 200_000


# ---- base64url helpers ----------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---- password hashing -----------------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, rounds, salt_b64, hash_b64 = stored.split("$")
        salt, expected = _b64d(salt_b64), _b64d(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


# ---- tokens ---------------------------------------------------------------
def _sign(body: str) -> str:
    return _b64e(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())


def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}"


def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        raise AuthError("Malformed token")
    if not hmac.compare_digest(signature, _sign(body)):
        raise AuthError("Invalid token signature")
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        raise AuthError("Malformed token payload")
    if payload.get("exp", 0) < int(time.time()):
        raise AuthError("Token expired — please sign in again")
    return payload


# ---- FastAPI guards -------------------------------------------------------
@dataclass
class Principal:
    """The authenticated caller derived from a bearer token."""

    user_id: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    """Dependency: require and decode a ``Bearer <token>`` Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Missing bearer token")
    payload = decode_token(authorization[len("Bearer ") :])
    return Principal(user_id=payload["sub"], role=payload.get("role", "user"))


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    """Dependency: 403 unless the caller is an admin."""
    if not principal.is_admin:
        raise ForbiddenError("Admin privileges required")
    return principal


def require_self_or_admin(user_id: str, principal: Principal) -> None:
    """Allow admins through; otherwise the caller must be acting on themselves."""
    if not principal.is_admin and principal.user_id != user_id:
        raise ForbiddenError("You can only access your own data")


def require_participant(user_id: str, principal: Principal) -> None:
    """Only the account owner may perform this action — admins do NOT participate.

    Used for creating sales and initiating withdrawals: admins manage users and
    settlement, but never act as a participant in the earning/payout flow.
    """
    if principal.is_admin:
        raise ForbiddenError(
            "Admins manage users and settlement, not sales or withdrawals"
        )
    if principal.user_id != user_id:
        raise ForbiddenError("You can only act on your own account")
