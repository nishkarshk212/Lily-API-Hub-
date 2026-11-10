"""Razorpay PaymentOrder and idempotent WebhookEvent models."""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import utc_now


def _uuid() -> str:
    return str(uuid.uuid4())


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), index=True
    )
    subscription_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(String(24), nullable=False, default="new")  # new | renew | upgrade
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(String(80), unique=True, index=True, nullable=True)
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(String(80), unique=True, index=True, nullable=True)
    razorpay_signature: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", index=True
    )  # pending | successful | failed | refunded | cancelled
    payment_method: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    receipt_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verified_via: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user = relationship("User", back_populates="payments")
    plan = relationship("SubscriptionPlan")
    subscription = relationship("Subscription")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="razorpay")
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processing_result: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

