"""Vercel Serverless ASGI entrypoint for Lily API Hub by Sonic Network."""

import os

from app.core.database import SessionLocal, init_db
from app.core.seed import seed_initial_data
from app.main import app

if os.getenv("VERCEL") == "1" and os.getenv("DATABASE_URL", "").strip():
    init_db()
    with SessionLocal() as db:
        seed_initial_data(db)

__all__ = ["app"]

