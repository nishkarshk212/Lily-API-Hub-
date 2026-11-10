"""Customer API Key model (encrypted at rest, SHA-256 indexed for gateway validation)."""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import utc_now


def _uuid() -> str:
    return str(uuid.uuid4())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False, default="Primary API Key")
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    key_last4: Mapped[str] = mapped_column(String(8), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    master_link_tag: Mapped[str] = mapped_column(String(64), nullable=False, default="sonic-master-v1")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)  # active | revoked
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    user = relationship("User", back_populates="api_keys")
    subscription = relationship("Subscription", back_populates="api_keys")

