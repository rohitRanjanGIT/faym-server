"""FastAPI application wiring."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .api import admin, auth, payouts, sales, users, withdrawals
from .db import Base, engine
from .errors import DomainError
from .seed import seed_default_accounts

# Create tables on startup. For a real deployment this would be an Alembic
# migration rather than create_all.
Base.metadata.create_all(engine)
seed_default_accounts()

app = FastAPI(
    title="User Payout Management System",
    description="Affiliate-sales payout system: advances, reconciliation, "
    "withdrawals, and failed-payout recovery.",
    version="1.0.0",
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
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the bare host to the interactive API docs.

    The dashboard is now the separate React client (../client-faym-dashboard).
    """
    return RedirectResponse(url="/docs")
