"""Authentication endpoints: login and current-principal lookup."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import Principal, create_token, get_principal, verify_password
from ..db import get_db
from ..errors import AuthError
from ..models import User
from ..schemas import LoginRequest, LoginResponse, MeResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Exchange a username/password for a signed bearer token."""
    user = db.get(User, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message for unknown user and wrong password (no user enumeration).
        raise AuthError("Invalid username or password")
    role = user.role.value
    return LoginResponse(
        token=create_token(user.id, role), user_id=user.id, role=role
    )


@router.get("/auth/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_principal)) -> MeResponse:
    """Return the caller identified by the bearer token."""
    return MeResponse(user_id=principal.user_id, role=principal.role)
