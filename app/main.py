"""FastAPI application wiring."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import payouts, sales, users, withdrawals
from .db import Base, engine
from .errors import DomainError

# Create tables on startup. For a real deployment this would be an Alembic
# migration rather than create_all.
Base.metadata.create_all(engine)

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


app.include_router(sales.router)
app.include_router(payouts.router)
app.include_router(withdrawals.router)
app.include_router(users.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the bare host to the dashboard."""
    return RedirectResponse(url="/ui/")


# Serve the simple dashboard (static single-page app) at /ui.
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/ui", StaticFiles(directory=str(_frontend_dir), html=True), name="ui")
