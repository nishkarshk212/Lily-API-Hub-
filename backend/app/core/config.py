"""Core application settings loaded from environment variables."""

from functools import lru_cache
import os
import secrets
from typing import List
from urllib.parse import urlparse

from fastapi import Request
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    cleaned = (url or "").strip()
    if os.getenv("VERCEL") == "1" and (not cleaned or cleaned.startswith("sqlite:///./")):
        # Vercel /var/task is read-only; fall back to writable /tmp when no external DB is configured.
        return "sqlite:////tmp/beta_hub.db"
    if cleaned.startswith("postgres://"):
        return "postgresql+psycopg://" + cleaned[len("postgres://"):]
    if cleaned.startswith("postgresql://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://"):]
    return cleaned or "sqlite:///./beta_hub.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_NAME: str = "Beta API Hub"
    COMPANY_NAME: str = "Sonic Network"
    BRAND_BADGE_LETTER: str = ""
    SUPPORT_EMAIL: str = "support@sonicnetwork.dev"
    SITE_META_DESCRIPTION: str = "Purchase API access plans, manage unique developer keys linked to a Master Gateway, test live endpoints, and scale seamlessly with Razorpay."
    API_KEY_PREFIX_LIVE: str = "beta_live_"
    API_KEY_PREFIX_TEST: str = "beta_test_"
    RECEIPT_PREFIX: str = "BETA"
    APP_ENV: str = "development"
    APP_PUBLIC_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = ""
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    SECRET_KEY: str = Field(default="", validate_default=True)
    ENCRYPTION_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    SESSION_EXPIRE_HOURS: int = 168  # 7 days

    DATABASE_URL: str = Field(default="sqlite:///./beta_hub.db", validate_default=True)

    # Master / Upstream Gateway settings
    GATEWAY_MODE: str = "hybrid"  # builtin | proxy | hybrid
    UPSTREAM_API_BASE_URL: str = ""
    MASTER_API_KEY: str = ""
    UPSTREAM_AUTH_HEADER: str = "Authorization"
    UPSTREAM_AUTH_SCHEME: str = "Bearer"
    UPSTREAM_TIMEOUT_MS: int = 10000

    # Razorpay settings
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_API_BASE_URL: str = "https://api.razorpay.com/v1"

    # Google OAuth2
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # SMTP Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@sonicnetwork.dev"
    SMTP_FROM_NAME: str = ""
    SMTP_USE_TLS: bool = True

    # Initial Admin Seed
    INITIAL_ADMIN_EMAIL: str = "admin@sonicnetwork.dev"
    INITIAL_ADMIN_PASSWORD: str = "SonicAdmin!2026ChangeMe"
    INITIAL_ADMIN_NAME: str = "Sonic Network Admin"

    COOKIE_SECURE: bool = False
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def ensure_secret_key(cls, v: str) -> str:
        if v and v.strip() and not v.startswith("replace-with"):
            return v.strip()
        # Ephemeral dev fallback when not explicitly set; production should always supply SECRET_KEY.
        return secrets.token_urlsafe(48)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        return normalize_database_url(v)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def is_serverless(self) -> bool:
        return os.getenv("VERCEL") == "1"

    @property
    def brand_letter(self) -> str:
        raw = (self.BRAND_BADGE_LETTER or self.APP_NAME[:1] or "A").strip()
        return raw[:1].upper()

    @property
    def effective_from_name(self) -> str:
        return self.SMTP_FROM_NAME.strip() or f"{self.APP_NAME} by {self.COMPANY_NAME}"

    def resolve_api_base_url(self, request: Request) -> str:
        if self.APP_ENV == "development":
            base = str(request.base_url).rstrip("/")
            if os.getenv("VERCEL") == "1" and base.startswith("http://"):
                proto = request.headers.get("x-forwarded-proto", "https").split(",")[0].strip() or "https"
                host = request.headers.get("host")
                if host:
                    return f"{proto}://{host}/v1"
            return f"{base}/v1"
        vercel_url = (os.getenv("VERCEL_PROJECT_PRODUCTION_URL") or os.getenv("VERCEL_URL") or "").strip()
        if vercel_url and self.APP_PUBLIC_URL.startswith("http://localhost"):
            return f"https://{vercel_url}/v1"
        return f"{self.APP_PUBLIC_URL.rstrip('/')}/v1"

    @property
    def effective_frontend_url(self) -> str:
        return (self.FRONTEND_URL.strip() or self.APP_PUBLIC_URL).rstrip("/")

    @property
    def is_cross_origin_frontend(self) -> bool:
        fe = self.FRONTEND_URL.strip()
        if not fe:
            return False
        fe_parsed = urlparse(fe)
        be_parsed = urlparse(self.APP_PUBLIC_URL)
        return bool(fe_parsed.netloc and fe_parsed.netloc.lower() != be_parsed.netloc.lower())

    @property
    def cors_origin_list(self) -> List[str]:
        origins = [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip() and o.strip() != "*"]
        fe = self.FRONTEND_URL.strip().rstrip("/")
        if fe and fe not in origins:
            origins.append(fe)
        return origins

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID.strip() and self.RAZORPAY_KEY_SECRET.strip())

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID.strip() and self.GOOGLE_CLIENT_SECRET.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

