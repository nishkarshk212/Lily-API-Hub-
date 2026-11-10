"""Subscription lifecycle and unique API key management linked to the Master Gateway."""

from datetime import timedelta
import re
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_api_key_secret,
    sha256_hex,
    utc_now,
)
from app.models.api_key import ApiKey
from app.models.gateway import MasterGatewayConfig
from app.models.plan import Subscription, SubscriptionPlan
from app.models.user import User
from app.services.auth_service import as_utc
from app.services.branding_service import get_effective_branding


def compute_master_link_tag(db: Session) -> str:
    """Create a safe non-secret identifier linking issued customer keys to the Master Gateway profile."""
    brand = get_effective_branding(db)
    slug = re.sub(r"[^a-z0-9]+", "-", brand["company_name"].lower()).strip("-") or "hub"
    gw = db.get(MasterGatewayConfig, 1)
    if not gw:
        return f"{slug}-master-default"
    fp_hash = sha256_hex(f"{gw.gateway_mode}:{gw.upstream_base_url}:{gw.master_key_fingerprint}")[:10]
    return f"{slug}-gw-{fp_hash}"


def expire_due_subscriptions(db: Session, user_id: Optional[str] = None) -> int:
    """Automatically transition expired active subscriptions to 'expired'."""
    now = utc_now()
    query = select(Subscription).where(Subscription.status == "active", Subscription.expires_at <= now)
    if user_id:
        query = query.where(Subscription.user_id == user_id)
    due = db.scalars(query).all()
    for sub in due:
        sub.status = "expired"
    if due:
        db.flush()
    return len(due)


def get_active_subscription(db: Session, user_id: str) -> Optional[Subscription]:
    expire_due_subscriptions(db, user_id=user_id)
    return db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == "active")
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )


def get_latest_subscription(db: Session, user_id: str) -> Optional[Subscription]:
    expire_due_subscriptions(db, user_id=user_id)
    return db.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )


def build_key_record(
    db: Session,
    user_id: str,
    subscription_id: str,
    name: str,
    is_free_tier: bool = False,
) -> Tuple[ApiKey, str]:
    brand = get_effective_branding(db)
    prefix = brand["api_key_prefix_test"] if is_free_tier else brand["api_key_prefix_live"]
    raw_key = generate_api_key_secret(prefix=prefix)
    record = ApiKey(
        user_id=user_id,
        subscription_id=subscription_id,
        name=name.strip()[:80] or "Primary API Key",
        key_prefix=raw_key[: len(prefix) + 4],
        key_last4=raw_key[-4:],
        key_hash=sha256_hex(raw_key),
        encrypted_key=encrypt_secret(raw_key),
        master_link_tag=compute_master_link_tag(db),
        status="active",
    )
    db.add(record)
    db.flush()
    return record, raw_key


def provision_subscription_and_key(
    db: Session,
    user: User,
    plan: SubscriptionPlan,
    action: str = "new",
    key_name: str = "Primary API Key",
) -> Tuple[Subscription, ApiKey]:
    """Activate or renew a subscription and ensure an active unique API key is provisioned."""
    now = utc_now()
    today_str = now.strftime("%Y-%m-%d")
    is_free = plan.price_paise == 0

    if action == "renew":
        existing_same = db.scalar(
            select(Subscription)
            .where(Subscription.user_id == user.id, Subscription.plan_id == plan.id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        if existing_same:
            current_exp = as_utc(existing_same.expires_at)
            if existing_same.status == "active" and current_exp and current_exp > now:
                existing_same.expires_at = current_exp + timedelta(days=plan.billing_cycle_days)
            else:
                existing_same.status = "active"
                existing_same.starts_at = now
                existing_same.expires_at = now + timedelta(days=plan.billing_cycle_days)
                existing_same.cycle_requests_used = 0
                existing_same.daily_requests_used = 0
                existing_same.daily_usage_date = today_str
                existing_same.cancelled_at = None

            active_key = db.scalar(
                select(ApiKey)
                .where(ApiKey.subscription_id == existing_same.id, ApiKey.status == "active")
                .order_by(ApiKey.created_at.desc())
                .limit(1)
            )
            if not active_key:
                active_key, _ = build_key_record(
                    db, user.id, existing_same.id, f"{plan.name} Key", is_free_tier=is_free
                )
            db.flush()
            return existing_same, active_key

    # For new/upgrade (or renew when no prior sub exists): deactivate previous active subs
    prior_active = db.scalars(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
    ).all()
    for prior in prior_active:
        prior.status = "cancelled"
        prior.cancelled_at = now
        # Revoke keys on superseded subscription so only purchased plan limits apply
        prior_keys = db.scalars(
            select(ApiKey).where(ApiKey.subscription_id == prior.id, ApiKey.status == "active")
        ).all()
        for pk in prior_keys:
            pk.status = "revoked"
            pk.revoked_at = now

    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=plan.billing_cycle_days),
        cycle_requests_used=0,
        daily_requests_used=0,
        daily_usage_date=today_str,
    )
    db.add(sub)
    db.flush()

    api_key, _ = build_key_record(db, user.id, sub.id, key_name or f"{plan.name} Key", is_free_tier=is_free)
    return sub, api_key


def create_additional_key(db: Session, user: User, name: str) -> ApiKey:
    sub = get_active_subscription(db, user.id)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active subscription plan is required to create API keys.",
        )

    plan = db.get(SubscriptionPlan, sub.plan_id)
    active_count = db.scalar(
        select(func.count(ApiKey.id)).where(ApiKey.subscription_id == sub.id, ApiKey.status == "active")
    ) or 0
    if active_count >= plan.max_api_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Plan limit reached: your {plan.name} plan allows up to {plan.max_api_keys} active API keys.",
        )

    key, _ = build_key_record(db, user.id, sub.id, name, is_free_tier=(plan.price_paise == 0))
    db.commit()
    db.refresh(key)
    return key


def serialize_api_key(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "masked_key": f"{key.key_prefix}••••••••••••{key.key_last4}",
        "key_prefix": key.key_prefix,
        "key_last4": key.key_last4,
        "status": key.status,
        "master_link_tag": key.master_link_tag,
        "total_requests": key.total_requests,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
        "created_at": key.created_at,
        "subscription_id": key.subscription_id,
    }


def list_user_keys(db: Session, user_id: str) -> List[ApiKey]:
    return list(
        db.scalars(select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())).all()
    )


def reveal_user_key(db: Session, user: User, key_id: str) -> str:
    key = db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if key.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Revoked API keys cannot be revealed.")
    plaintext = decrypt_secret(key.encrypted_key)
    if not plaintext:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to decrypt API key.")
    return plaintext


def regenerate_user_key(db: Session, user: User, key_id: str) -> Tuple[ApiKey, str]:
    key = db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if key.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot regenerate a revoked key.")

    sub = db.get(Subscription, key.subscription_id)
    expire_due_subscriptions(db, user_id=user.id)
    db.refresh(sub)
    if not sub or sub.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is no longer active.")

    brand = get_effective_branding(db)
    plan = db.get(SubscriptionPlan, sub.plan_id)
    prefix = brand["api_key_prefix_test"] if (plan and plan.price_paise == 0) else brand["api_key_prefix_live"]
    new_raw = generate_api_key_secret(prefix=prefix)
    key.key_prefix = new_raw[: len(prefix) + 4]
    key.key_last4 = new_raw[-4:]
    key.key_hash = sha256_hex(new_raw)
    key.encrypted_key = encrypt_secret(new_raw)
    key.master_link_tag = compute_master_link_tag(db)
    db.commit()
    db.refresh(key)
    return key, new_raw


def revoke_user_key(db: Session, user: User, key_id: str) -> ApiKey:
    key = db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if key.status == "revoked":
        return key
    key.status = "revoked"
    key.revoked_at = utc_now()
    db.commit()
    db.refresh(key)
    return key

