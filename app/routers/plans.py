"""Subscription plans, free trial activation, subscription status, and usage analytics."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import utc_now
from app.models.gateway import ApiRequestLog
from app.models.plan import Subscription, SubscriptionPlan
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.domain import PlanOut
from app.services.auth_service import record_audit
from app.services.key_service import (
    get_active_subscription,
    get_latest_subscription,
    provision_subscription_and_key,
    serialize_api_key,
)

router = APIRouter(tags=["Plans & Subscriptions"])


@router.get("/api/plans", response_model=list[PlanOut])
def list_public_plans(db: Session = Depends(get_db)):
    plans = db.scalars(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.sort_order.asc(), SubscriptionPlan.price_paise.asc())
    ).all()
    return plans


@router.get("/api/subscriptions/current")
def get_current_subscription_details(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cfg = get_settings()
    sub = get_latest_subscription(db, user.id)
    db.commit()
    base_url = cfg.resolve_api_base_url(request)

    if not sub:
        return {"subscription": None, "api_base_url": base_url}

    plan = db.get(SubscriptionPlan, sub.plan_id)
    today_str = utc_now().strftime("%Y-%m-%d")
    daily_used = sub.daily_requests_used if sub.daily_usage_date == today_str else 0
    return {
        "api_base_url": base_url,
        "subscription": {
            "id": sub.id,
            "status": sub.status,
            "starts_at": sub.starts_at,
            "expires_at": sub.expires_at,
            "daily_requests_used": daily_used,
            "daily_remaining": max(0, plan.daily_request_limit - daily_used) if plan else 0,
            "cycle_requests_used": sub.cycle_requests_used,
            "monthly_remaining": max(0, plan.monthly_request_limit - sub.cycle_requests_used) if plan else 0,
            "plan": PlanOut.model_validate(plan) if plan else None,
        },
    }


@router.post("/api/subscriptions/activate-free")
def activate_free_plan(
    plan_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = db.get(SubscriptionPlan, plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    if plan.price_paise != 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Paid plans must go through Razorpay checkout.")

    # Prevent repeated free sandbox abuse once already used
    prior_free = db.scalar(
        select(Subscription.id)
        .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .where(Subscription.user_id == user.id, SubscriptionPlan.price_paise == 0)
        .limit(1)
    )
    if prior_free:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Free trial plan has already been claimed on this account. Upgrade to Starter or Pro.",
        )

    sub, api_key = provision_subscription_and_key(db, user, plan, action="new", key_name=f"{plan.name} Key")
    record_audit(db, "subscription.free_activated", user.email, user.id, "subscription", sub.id, {"plan": plan.slug})
    db.commit()
    db.refresh(sub)
    db.refresh(api_key)
    return {
        "message": f"{plan.name} activated with a new API key!",
        "subscription_id": sub.id,
        "api_key": serialize_api_key(api_key),
    }


@router.post("/api/subscriptions/cancel")
def cancel_active_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = get_active_subscription(db, user.id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found.")
    now = utc_now()
    sub.status = "cancelled"
    sub.cancelled_at = now
    for key in sub.api_keys:
        if key.status == "active":
            key.status = "revoked"
            key.revoked_at = now
    record_audit(db, "subscription.cancelled_by_user", user.email, user.id, "subscription", sub.id)
    db.commit()
    return {"message": "Subscription cancelled and associated API keys revoked."}


@router.get("/api/dashboard/usage")
def get_user_usage_analytics(
    limit: int = Query(default=40, ge=5, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = db.scalars(
        select(ApiRequestLog)
        .where(ApiRequestLog.user_id == user.id)
        .order_by(ApiRequestLog.created_at.desc())
        .limit(limit)
    ).all()

    total_calls = db.scalar(select(func.count(ApiRequestLog.id)).where(ApiRequestLog.user_id == user.id)) or 0
    success_calls = (
        db.scalar(
            select(func.count(ApiRequestLog.id)).where(
                ApiRequestLog.user_id == user.id,
                ApiRequestLog.status_code >= 200,
                ApiRequestLog.status_code < 400,
            )
        )
        or 0
    )
    avg_latency = (
        db.scalar(select(func.avg(ApiRequestLog.latency_ms)).where(ApiRequestLog.user_id == user.id)) or 0.0
    )

    # Build 7-day usage series
    now = utc_now()
    seven_days_ago = now - timedelta(days=6)
    recent_logs = db.scalars(
        select(ApiRequestLog)
        .where(ApiRequestLog.user_id == user.id, ApiRequestLog.created_at >= seven_days_ago.replace(hour=0, minute=0, second=0, microsecond=0))
    ).all()

    day_map = {(seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d"): {"total": 0, "errors": 0} for i in range(7)}
    for entry in recent_logs:
        d = entry.created_at.strftime("%Y-%m-%d")
        if d in day_map:
            day_map[d]["total"] += 1
            if entry.status_code >= 400:
                day_map[d]["errors"] += 1

    series = [{"date": k, "requests": v["total"], "errors": v["errors"]} for k, v in sorted(day_map.items())]

    return {
        "summary": {
            "total_requests": total_calls,
            "success_requests": success_calls,
            "error_requests": max(0, total_calls - success_calls),
            "success_rate": round((success_calls / total_calls) * 100, 1) if total_calls else 100.0,
            "avg_latency_ms": round(float(avg_latency), 2),
        },
        "series": series,
        "logs": [
            {
                "id": log.id,
                "method": log.method,
                "path": log.path,
                "query_string": log.query_string,
                "status_code": log.status_code,
                "latency_ms": log.latency_ms,
                "gateway_mode": log.gateway_mode,
                "error_code": log.error_code,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }

