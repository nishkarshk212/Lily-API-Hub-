"""SQLAlchemy database engine, session factory, and lifecycle helpers."""

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine(database_url: str):
    is_sqlite = database_url.startswith("sqlite")
    is_vercel = os.getenv("VERCEL") == "1"
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine_kwargs = {
        "pool_pre_ping": True,
        "future": True,
    }
    if not is_sqlite:
        if is_vercel:
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs.update({"pool_size": 10, "max_overflow": 20})
    engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


settings = get_settings()
engine = _build_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

