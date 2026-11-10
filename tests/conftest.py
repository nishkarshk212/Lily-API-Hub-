"""Pytest fixtures providing isolated database, configured settings, and TestClient."""

import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.seed import seed_initial_data
from app.main import app as fastapi_app
from app.services.gateway_service import rate_limiter


@pytest.fixture()
def test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "test_lily_hub.db"
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-lily-api-hub-pytest-1234567890")
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("MASTER_API_KEY", "sn_master_ultra_secret_test_key_9988")
    monkeypatch.setenv("UPSTREAM_API_BASE_URL", "")
    monkeypatch.setenv("UPSTREAM_AUTH_HEADER", "Authorization")
    monkeypatch.setenv("UPSTREAM_AUTH_SCHEME", "Bearer")
    monkeypatch.setenv("GATEWAY_MODE", "hybrid")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_lilyhub_123")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_secret_abc987")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "rzp_webhook_secret_xyz654")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@sonicnetwork.dev")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "SonicAdmin!2026")
    monkeypatch.setenv("SMTP_HOST", "")

    get_settings.cache_clear()
    rate_limiter.reset()

    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        seed_initial_data(db)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal
    fastapi_app.dependency_overrides.clear()
    rate_limiter.reset()
    get_settings.cache_clear()


@pytest.fixture()
def client(test_env) -> TestClient:
    with TestClient(fastapi_app) as c:
        yield c
