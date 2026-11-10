"""SQLAlchemy database engine, session factory, and lifecycle helpers."""

import os
import sys
import threading
from typing import Generator, Optional, Tuple

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine(database_url: str):
    is_sqlite = database_url.startswith("sqlite")
    is_vercel = os.getenv("VERCEL") == "1"
    if is_sqlite:
        connect_args = {"check_same_thread": False}
    elif is_vercel:
        connect_args = {"connect_timeout": 8}
    else:
        connect_args = {}

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
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


settings = get_settings()
engine = _build_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

_init_lock = threading.Lock()
_initialized_db_url: Optional[str] = None
_last_init_error: Optional[str] = None


def init_db() -> None:
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def ensure_db_ready(force: bool = False) -> Tuple[bool, Optional[str]]:
    """Idempotently initialize schema and seed defaults once per process."""
    global _initialized_db_url, _last_init_error
    current_url = settings.DATABASE_URL
    if not force and _initialized_db_url == current_url and _last_init_error is None:
        return True, None

    with _init_lock:
        if not force and _initialized_db_url == current_url and _last_init_error is None:
            return True, None
        try:
            init_db()
            from app.core.seed import seed_initial_data

            with SessionLocal() as db:
                seed_initial_data(db)
            _initialized_db_url = current_url
            _last_init_error = None
            return True, None
        except Exception as exc:
            _last_init_error = f"{type(exc).__name__}: {exc}"
            print(f"[db_init_error] {_last_init_error}", file=sys.stderr)
            return False, _last_init_error


def get_db_init_status() -> Tuple[bool, Optional[str]]:
    return (_initialized_db_url == settings.DATABASE_URL and _last_init_error is None), _last_init_error


def get_db() -> Generator[Session, None, None]:
    if os.getenv("VERCEL") == "1":
        ensure_db_ready()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
