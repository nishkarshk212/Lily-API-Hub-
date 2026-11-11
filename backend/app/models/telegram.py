"""Telegram bot connection, user account linking, and bot activity event models."""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import utc_now


def _uuid() -> str:
    return str(uuid.uuid4())


class TelegramBot(Base):
    __tablename__ = "telegram_bots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    api_key_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )

    is_platform_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    bot_tg_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bot_username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    bot_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Beta Telegram Bot")

    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    webhook_secret: Mapped[str] = mapped_column(String(128), nullable=False)

    connection_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="webhook")  # webhook | polling
    access_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, default="owner_only"
    )  # owner_only | linked_users | public_gateway
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    welcome_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    custom_proxy_path: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    custom_proxy_method: Mapped[str] = mapped_column(String(10), nullable=False, default="POST")
    forward_plain_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_owner_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    pairing_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    paired_telegram_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    paired_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    paired_telegram_username: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    paired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    webhook_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    webhook_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_quota_alert_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")

    last_update_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_messages_handled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    owner = relationship("User", foreign_keys=[owner_user_id])
    api_key = relationship("ApiKey", foreign_keys=[api_key_id])
    user_links = relationship("TelegramUserLink", back_populates="bot", cascade="all, delete-orphan")
    events = relationship("TelegramBotEvent", back_populates="bot", cascade="all, delete-orphan")


class TelegramUserLink(Base):
    __tablename__ = "telegram_user_links"
    __table_args__ = (UniqueConstraint("bot_id", "user_id", name="uq_telegram_link_bot_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bot_id: Mapped[str] = mapped_column(String(36), ForeignKey("telegram_bots.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    telegram_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    telegram_username: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    telegram_first_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    notify_quota_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_security_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_payment_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_gateway_errors: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_quota_alert_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    bot = relationship("TelegramBot", back_populates="user_links")
    user = relationship("User")


class TelegramBotEvent(Base):
    __tablename__ = "telegram_bot_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bot_id: Mapped[str] = mapped_column(String(36), ForeignKey("telegram_bots.id", ondelete="CASCADE"), index=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    telegram_username: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    event_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="command"
    )  # command | callback | message | notification | error
    command_or_action: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")  # ok | denied | error
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    bot = relationship("TelegramBot", back_populates="events")
