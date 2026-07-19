"""FastAPI application wiring."""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .api import admin, auth, payouts, sales, users, withdrawals
from .db import IS_SQLITE, Base, engine
from .errors import DomainError
from .seed import seed_default_accounts

# Create tables + seed on startup. For a real deployment this would be an
# Alembic migration rather than create_all.
#
# This is wrapped so a DB failure does NOT crash the whole serverless function
# at import time (which surfaces as an opaque FUNCTION_INVOCATION_FAILED on
# every route). Instead the app still boots and `/health` reports what went
# wrong, so the cause is diagnosable from the browser.
INIT_ERROR: str | None = None
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

# CORS: the React client is served from a different origin in production. Auth
# is a Bearer token (not a cookie), so allowing "*" is safe with credentials
# off. Restrict by setting CORS_ORIGINS (comma-separated) to the client URL(s).
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
    """Liveness + boot diagnostics.

    Reports which DB backend was selected and whether table creation / seeding
    succeeded. If ``db_backend`` is ``sqlite`` in production, ``DATABASE_URL``
    is not set for this environment (Vercel's filesystem is read-only, so
    SQLite cannot be used there).
    """
    return {
        "status": "degraded" if INIT_ERROR else "ok",
        "db_backend": "sqlite" if IS_SQLITE else "postgres",
        "init_error": INIT_ERROR,
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the bare host to the interactive API docs.

    The dashboard is now the separate React client (../client-faym-dashboard).
    """
    return RedirectResponse(url="/docs")
