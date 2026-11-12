"""Gateway request logging, Master API configuration, Audit logs, and Dev Email outbox."""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.security import utc_now


def _uuid() -> str:
    return str(uuid.uuid4())


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    api_key_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    method: Mapped[str] = mapped_column(String(12), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    query_string: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    upstream_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    gateway_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="builtin")
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    __table_args__ = (
        Index("ix_api_request_logs_user_created", "user_id", "created_at"),
        Index("ix_api_request_logs_key_created", "api_key_id", "created_at"),
    )


class MasterGatewayConfig(Base):
    __tablename__ = "master_gateway_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    gateway_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="hybrid")
    upstream_base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    encrypted_master_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    master_key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    auth_header_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Authorization")
    auth_scheme: Mapped[str] = mapped_column(String(32), nullable=False, default="Bearer")
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    forward_user_context_headers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SiteBrandingConfig(Base):
    __tablename__ = "site_branding_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    app_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    company_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    brand_badge_letter: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    support_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    site_description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_key_prefix_live: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    api_key_prefix_test: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    receipt_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    details_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    sent_via: Mapped[str] = mapped_column(String(24), nullable=False, default="local_outbox")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class MediaGatewayConfig(Base):
    """Singleton configuration & encrypted credentials for the built-in /v1/media/* engine."""

    __tablename__ = "media_gateway_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    media_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    encrypted_youtube_cookies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cookies_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    encrypted_youtube_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    youtube_api_key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    max_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=250)
    default_audio_format: Mapped[str] = mapped_column(String(16), nullable=False, default="mp3")
    default_video_quality: Mapped[str] = mapped_column(String(16), nullable=False, default="720p")
    updated_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

