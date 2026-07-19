"""Vercel serverless entrypoint.

Vercel's Python runtime serves the ASGI application exported as ``app``. All
requests are routed here by vercel.json, and FastAPI dispatches by path.
"""
from app.main import app  # noqa: F401  (re-exported for the Vercel runtime)
