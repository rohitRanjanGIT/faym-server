"""FastAPI application wiring."""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .api import admin, auth, payouts, sales, users, withdrawals
from .db import ENGINE_ERROR, Base, engine
from .errors import DomainError
from .seed import seed_default_accounts

INIT_ERROR: str | None = ENGINE_ERROR
if engine is not None:
    try:
        Base.metadata.create_all(engine)
        seed_default_accounts()
    except Exception as exc:  # noqa: BLE001 - surface any boot failure via /health
        INIT_ERROR = f"{type(exc).__name__}: {exc}"

app = FastAPI(
    title="User Payout Management System",
    description="Affiliate-sales payout system: advances, reconciliation, "
    "withdrawals, and failed-payout recovery.",
    version="1.0.0",
)

_cors_origins = os.getenv("CORS_ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",")] if _cors_origins else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Translate business-rule violations into clean HTTP error responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "detail": exc.message},
    )


app.include_router(auth.router)
app.include_router(sales.router)
app.include_router(payouts.router)
app.include_router(withdrawals.router)
app.include_router(users.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
def health() -> dict:

    return {
        "status": "degraded" if INIT_ERROR else "ok",
        "db": "postgres",
        "init_error": INIT_ERROR,
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:

    return RedirectResponse(url="/docs")
