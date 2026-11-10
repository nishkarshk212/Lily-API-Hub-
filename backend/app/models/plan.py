"""Subscription plan and customer subscription models."""

from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.security import utc_now


def _uuid() -> str:
    return str(uuid.uuid4())


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    tagline: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    price_paise: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    billing_cycle_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    daily_request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    monthly_request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=25000)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_api_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    allowed_methods: Mapped[str] = mapped_column(String(80), nullable=False, default="GET,POST")
    allowed_endpoints: Mapped[str] = mapped_column(Text, nullable=False, default="*")
    features_json: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    badge: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), index=True
    )

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    cycle_requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_usage_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")

    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    api_keys = relationship("ApiKey", back_populates="subscription", cascade="all, delete-orphan")

