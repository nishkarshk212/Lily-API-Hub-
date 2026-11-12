"""Separate Admin Dashboard API: RBAC guard, analytics, users, keys, plans, payments, Master API config."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import invalidate_branding_cache, invalidate_plans_cache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decrypt_secret, encrypt_secret, mask_secret, utc_now
from app.models.api_key import ApiKey
from app.models.gateway import (
    ApiRequestLog,
    AuditLog,
    EmailOutbox,
    MasterGatewayConfig,
    MediaGatewayConfig,
    SiteBrandingConfig,
)
from app.models.payment import PaymentOrder, WebhookEvent
from app.models.plan import Subscription, SubscriptionPlan
from app.models.user import SupportMessage, User
from app.routers.deps import require_admin
from app.schemas.auth import LoginRequest, UserOut
from app.schemas.domain import (
    AdminBrandingUpdateRequest,
    AdminMasterConfigUpdateRequest,
    AdminMediaConfigUpdateRequest,
    AdminUserUpdateRequest,
    PlanCreateRequest,
    PlanOut,
    PlanUpdateRequest,
)
from app.services.branding_service import get_effective_branding
from app.services.auth_service import (
    authenticate_user,
    get_client_ip,
    record_audit,
    set_session_cookie,
)
from app.services.key_service import expire_due_subscriptions, serialize_api_key
from app.services.razorpay_service import format_inr, reconcile_payment_order

router = APIRouter(prefix="/api/admin", tags=["Admin Control Center"])


@router.post("/login")
def admin_login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    user, jwt_token = authenticate_user(db, payload.email, payload.password, ip, ua, require_admin=True)
    set_session_cookie(response, jwt_token)
    return {"user": UserOut.model_validate(user), "access_token": jwt_token, "message": "Admin session authenticated."}


@router.get("/analytics")
def get_admin_analytics(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    expire_due_subscriptions(db)
    db.commit()

    now = utc_now()
    last_24h = now - timedelta(hours=24)
    seven_days_ago = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

    total_users = db.scalar(select(func.count(User.id))) or 0
    suspended_users = db.scalar(select(func.count(User.id)).where(User.is_suspended.is_(True))) or 0
    active_subs = db.scalar(select(func.count(Subscription.id)).where(Subscription.status == "active")) or 0
    active_keys = db.scalar(select(func.count(ApiKey.id)).where(ApiKey.status == "active")) or 0

    total_revenue_paise = (
        db.scalar(select(func.sum(PaymentOrder.amount_paise)).where(PaymentOrder.status == "successful")) or 0
    )
    total_requests = db.scalar(select(func.count(ApiRequestLog.id))) or 0
    requests_24h = (
        db.scalar(select(func.count(ApiRequestLog.id)).where(ApiRequestLog.created_at >= last_24h)) or 0
    )
    error_requests_24h = (
        db.scalar(
            select(func.count(ApiRequestLog.id)).where(
                ApiRequestLog.created_at >= last_24h, ApiRequestLog.status_code >= 400
            )
        )
        or 0
    )
    avg_latency = db.scalar(select(func.avg(ApiRequestLog.latency_ms))) or 0.0

    # 7-day request & revenue breakdown
    day_buckets = {
        (seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d"): {"requests": 0, "errors": 0, "revenue_inr": 0.0}
        for i in range(7)
    }

    recent_reqs = db.scalars(select(ApiRequestLog).where(ApiRequestLog.created_at >= seven_days_ago)).all()
    for r in recent_reqs:
        d = r.created_at.strftime("%Y-%m-%d")
        if d in day_buckets:
            day_buckets[d]["requests"] += 1
            if r.status_code >= 400:
                day_buckets[d]["errors"] += 1

    recent_paid = db.scalars(
        select(PaymentOrder).where(PaymentOrder.status == "successful", PaymentOrder.paid_at >= seven_days_ago)
    ).all()
    for p in recent_paid:
        if p.paid_at:
            d = p.paid_at.strftime("%Y-%m-%d")
            if d in day_buckets:
                day_buckets[d]["revenue_inr"] += round(p.amount_paise / 100.0, 2)

    top_endpoints_rows = db.execute(
        select(
            ApiRequestLog.path,
            func.count(ApiRequestLog.id).label("hits"),
            func.avg(ApiRequestLog.latency_ms).label("avg_ms"),
        )
        .group_by(ApiRequestLog.path)
        .order_by(func.count(ApiRequestLog.id).desc())
        .limit(6)
    ).all()

    top_users_rows = db.execute(
        select(
            User.email,
            func.count(ApiRequestLog.id).label("hits"),
        )
        .join(User, User.id == ApiRequestLog.user_id)
        .group_by(User.email)
        .order_by(func.count(ApiRequestLog.id).desc())
        .limit(5)
    ).all()

    return {
        "kpis": {
            "total_users": total_users,
            "suspended_users": suspended_users,
            "active_subscriptions": active_subs,
            "active_api_keys": active_keys,
            "total_revenue_paise": int(total_revenue_paise),
            "total_revenue_display": format_inr(int(total_revenue_paise)),
            "total_requests": total_requests,
            "requests_24h": requests_24h,
            "error_requests_24h": error_requests_24h,
            "avg_latency_ms": round(float(avg_latency), 2),
        },
        "series": [{"date": k, **v} for k, v in sorted(day_buckets.items())],
        "top_endpoints": [
            {"path": row.path, "hits": row.hits, "avg_ms": round(float(row.avg_ms or 0), 2)}
            for row in top_endpoints_rows
        ],
        "top_users": [{"email": row.email, "hits": row.hits} for row in top_users_rows],
    }


@router.get("/users")
def list_users(
    search: str = Query(default=""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    expire_due_subscriptions(db)
    db.commit()

    query = select(User).order_by(User.created_at.desc())
    if search.strip():
        like = f"%{search.strip().lower()}%"
        query = query.where(func.lower(User.email).like(like) | func.lower(User.full_name).like(like))

    users = db.scalars(query).all()
    subs = db.scalars(select(Subscription).order_by(Subscription.created_at.desc())).all()
    plans = {p.id: p.name for p in db.scalars(select(SubscriptionPlan)).all()}
    key_counts = dict(
        db.execute(select(ApiKey.user_id, func.count(ApiKey.id)).where(ApiKey.status == "active").group_by(ApiKey.user_id)).all()
    )

    latest_sub_by_user = {}
    for s in subs:
        if s.user_id not in latest_sub_by_user:
            latest_sub_by_user[s.user_id] = s

    return {
        "users": [
            {
                **UserOut.model_validate(u).model_dump(),
                "active_keys_count": key_counts.get(u.id, 0),
                "subscription_status": latest_sub_by_user[u.id].status if u.id in latest_sub_by_user else "none",
                "plan_name": plans.get(latest_sub_by_user[u.id].plan_id, "-") if u.id in latest_sub_by_user else "-",
            }
            for u in users
        ]
    }


@router.patch("/users/{user_id}")
def update_user_admin(
    user_id: str,
    payload: AdminUserUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if target.id == admin.id and payload.is_suspended is True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot suspend your own admin account.")
    if target.id == admin.id and payload.role == "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot demote your own admin role.")

    if payload.is_suspended is not None:
        target.is_suspended = payload.is_suspended
        target.suspension_reason = payload.suspension_reason if payload.is_suspended else None
    if payload.role is not None:
        target.role = payload.role
    if payload.is_email_verified is not None:
        target.is_email_verified = payload.is_email_verified
    if payload.is_active is not None:
        target.is_active = payload.is_active

    record_audit(
        db,
        "admin.user_updated",
        admin.email,
        admin.id,
        "user",
        target.id,
        payload.model_dump(exclude_none=True),
        get_client_ip(request),
    )
    db.commit()
    db.refresh(target)
    return {"user": UserOut.model_validate(target), "message": "User updated."}


@router.get("/keys")
def list_all_keys(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    keys = db.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()).limit(250)).all()
    user_map = {u.id: u.email for u in db.scalars(select(User)).all()}
    return {
        "keys": [
            {
                **serialize_api_key(k),
                "user_id": k.user_id,
                "user_email": user_map.get(k.user_id, "unknown"),
            }
            for k in keys
        ]
    }


@router.post("/keys/{key_id}/revoke")
def admin_revoke_key(
    key_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    key = db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    key.status = "revoked"
    key.revoked_at = utc_now()
    record_audit(db, "admin.key_revoked", admin.email, admin.id, "api_key", key.id, {}, get_client_ip(request))
    db.commit()
    return {"message": "API key revoked by administrator.", "key": serialize_api_key(key)}


@router.get("/plans", response_model=list[PlanOut])
def admin_list_plans(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order.asc())).all()


@router.post("/plans", response_model=PlanOut, status_code=201)
def admin_create_plan(
    payload: PlanCreateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.slug == payload.slug)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan slug already exists.")
    plan = SubscriptionPlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    record_audit(db, "admin.plan_created", admin.email, admin.id, "plan", plan.id, {"slug": plan.slug}, get_client_ip(request))
    db.commit()
    db.refresh(plan)
    invalidate_plans_cache()
    return plan


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def admin_update_plan(
    plan_id: str,
    payload: PlanUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    plan = db.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(plan, k, v)
    record_audit(db, "admin.plan_updated", admin.email, admin.id, "plan", plan.id, updates, get_client_ip(request))
    db.commit()
    db.refresh(plan)
    invalidate_plans_cache()
    return plan


@router.delete("/plans/{plan_id}")
def admin_delete_or_archive_plan(
    plan_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    plan = db.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")
    in_use = db.scalar(select(Subscription.id).where(Subscription.plan_id == plan.id).limit(1))
    if in_use:
        plan.is_active = False
        record_audit(db, "admin.plan_archived", admin.email, admin.id, "plan", plan.id, {}, get_client_ip(request))
        db.commit()
        invalidate_plans_cache()
        return {"message": "Plan has historical subscriptions and was archived (marked inactive)."}
    db.delete(plan)
    record_audit(db, "admin.plan_deleted", admin.email, admin.id, "plan", plan_id, {}, get_client_ip(request))
    db.commit()
    invalidate_plans_cache()
    return {"message": "Plan permanently deleted."}


@router.get("/payments")
def admin_list_payments(
    status_filter: str = Query(default=""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(PaymentOrder).order_by(PaymentOrder.created_at.desc()).limit(250)
    if status_filter.strip():
        query = query.where(PaymentOrder.status == status_filter.strip())
    orders = db.scalars(query).all()
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    plans = {p.id: p.name for p in db.scalars(select(SubscriptionPlan)).all()}
    webhooks = db.scalars(select(WebhookEvent).order_by(WebhookEvent.created_at.desc()).limit(50)).all()

    return {
        "payments": [
            {
                "id": o.id,
                "receipt_number": o.receipt_number,
                "user_email": users.get(o.user_id, "unknown"),
                "plan_name": plans.get(o.plan_id, "unknown"),
                "action": o.action,
                "razorpay_order_id": o.razorpay_order_id,
                "razorpay_payment_id": o.razorpay_payment_id,
                "amount_paise": o.amount_paise,
                "amount_display": format_inr(o.amount_paise),
                "currency": o.currency,
                "status": o.status,
                "payment_method": o.payment_method,
                "verified_via": o.verified_via,
                "failure_reason": o.failure_reason,
                "paid_at": o.paid_at,
                "created_at": o.created_at,
            }
            for o in orders
        ],
        "webhooks": [
            {
                "id": w.id,
                "event_id": w.event_id,
                "event_type": w.event_type,
                "razorpay_order_id": w.razorpay_order_id,
                "razorpay_payment_id": w.razorpay_payment_id,
                "processed": w.processed,
                "processing_result": w.processing_result,
                "created_at": w.created_at,
            }
            for w in webhooks
        ],
    }


@router.post("/payments/{payment_id}/reconcile")
async def admin_reconcile_payment(
    payment_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.get(PaymentOrder, payment_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment order not found.")
    return await reconcile_payment_order(db, order)


@router.post("/payments/{payment_id}/mark-refunded")
def admin_mark_refunded(
    payment_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.get(PaymentOrder, payment_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment order not found.")
    now = utc_now()
    order.status = "refunded"
    order.refunded_at = now
    if order.subscription_id:
        sub = db.get(Subscription, order.subscription_id)
        if sub and sub.status == "active":
            sub.status = "cancelled"
            sub.cancelled_at = now
            for k in db.scalars(select(ApiKey).where(ApiKey.subscription_id == sub.id, ApiKey.status == "active")).all():
                k.status = "revoked"
                k.revoked_at = now
    record_audit(db, "admin.payment_refunded", admin.email, admin.id, "payment_order", order.id, {}, get_client_ip(request))
    db.commit()
    return {"message": "Payment marked refunded and linked subscription/keys revoked."}


@router.get("/requests")
def admin_monitor_requests(
    status_code: int | None = Query(default=None),
    limit: int = Query(default=100, ge=10, le=300),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(ApiRequestLog).order_by(ApiRequestLog.created_at.desc()).limit(limit)
    if status_code is not None:
        query = query.where(ApiRequestLog.status_code == status_code)
    logs = db.scalars(query).all()
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    keys = {k.id: k.key_prefix for k in db.scalars(select(ApiKey)).all()}

    return {
        "requests": [
            {
                "id": r.id,
                "user_email": users.get(r.user_id, "anonymous"),
                "key_prefix": keys.get(r.api_key_id, "-"),
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "upstream_status_code": r.upstream_status_code,
                "latency_ms": r.latency_ms,
                "client_ip": r.client_ip,
                "gateway_mode": r.gateway_mode,
                "error_code": r.error_code,
                "created_at": r.created_at,
            }
            for r in logs
        ]
    }


@router.get("/master-config")
def get_master_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    gw = db.get(MasterGatewayConfig, 1)
    if not gw:
        return {"gateway_mode": "hybrid", "upstream_base_url": "", "has_master_key": False}
    return {
        "gateway_mode": gw.gateway_mode,
        "upstream_base_url": gw.upstream_base_url,
        "has_master_key": bool(gw.encrypted_master_api_key),
        "master_key_fingerprint": gw.master_key_fingerprint,
        "auth_header_name": gw.auth_header_name,
        "auth_scheme": gw.auth_scheme,
        "timeout_ms": gw.timeout_ms,
        "forward_user_context_headers": gw.forward_user_context_headers,
        "updated_by_email": gw.updated_by_email,
        "updated_at": gw.updated_at,
    }


@router.put("/master-config")
def update_master_config(
    payload: AdminMasterConfigUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cfg = get_settings()
    gw = db.get(MasterGatewayConfig, 1)
    if not gw:
        gw = MasterGatewayConfig(id=1)
        db.add(gw)

    gw.gateway_mode = payload.gateway_mode
    gw.upstream_base_url = payload.upstream_base_url.strip().rstrip("/")
    gw.auth_header_name = payload.auth_header_name.strip()
    gw.auth_scheme = payload.auth_scheme.strip()
    gw.timeout_ms = payload.timeout_ms
    gw.forward_user_context_headers = payload.forward_user_context_headers
    gw.updated_by_email = admin.email

    if payload.master_api_key is not None and payload.master_api_key.strip():
        raw_master = payload.master_api_key.strip()
        gw.encrypted_master_api_key = encrypt_secret(raw_master, cfg)
        gw.master_key_fingerprint = mask_secret(raw_master, 6, 4)

    record_audit(
        db,
        "admin.master_config_updated",
        admin.email,
        admin.id,
        "master_gateway_config",
        "1",
        {"gateway_mode": gw.gateway_mode, "upstream_base_url": gw.upstream_base_url, "key_rotated": bool(payload.master_api_key)},
        get_client_ip(request),
    )
    db.commit()
    db.refresh(gw)
    return {
        "message": "Master Gateway configuration saved securely.",
        "master_key_fingerprint": gw.master_key_fingerprint,
        "gateway_mode": gw.gateway_mode,
        "upstream_base_url": gw.upstream_base_url,
    }


@router.post("/master-config/test")
async def test_upstream_connection(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_settings()
    gw = db.get(MasterGatewayConfig, 1)
    if not gw or not gw.upstream_base_url.strip():
        return {"ok": False, "detail": f"No Upstream Base URL is currently configured. Running in built-in {cfg.COMPANY_NAME} mode."}

    cfg = get_settings()
    master_key = decrypt_secret(gw.encrypted_master_api_key, cfg)
    headers = {}
    if master_key:
        headers[gw.auth_header_name] = f"{gw.auth_scheme} {master_key}".strip() if gw.auth_scheme else master_key

    try:
        async with httpx.AsyncClient(timeout=max(1.0, gw.timeout_ms / 1000.0)) as client:
            resp = await client.get(gw.upstream_base_url, headers=headers)
        return {
            "ok": resp.status_code < 500,
            "status_code": resp.status_code,
            "detail": f"Upstream responded with HTTP {resp.status_code}.",
        }
    except httpx.RequestError as exc:
        return {"ok": False, "detail": f"Connection failed: {type(exc).__name__}"}


@router.get("/media-config")
def get_media_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_settings()
    mgw = db.get(MediaGatewayConfig, 1)
    if not mgw:
        return {
            "media_enabled": cfg.MEDIA_API_ENABLED,
            "has_youtube_cookies": bool(cfg.YOUTUBE_COOKIES_B64.strip()),
            "cookies_fingerprint": "env-b64" if cfg.YOUTUBE_COOKIES_B64.strip() else "",
            "has_youtube_api_key": bool(cfg.YOUTUBE_API_KEY.strip()),
            "youtube_api_key_fingerprint": mask_secret(cfg.YOUTUBE_API_KEY.strip(), 6, 4) if cfg.YOUTUBE_API_KEY.strip() else "",
            "max_duration_seconds": cfg.MEDIA_MAX_DURATION_SECONDS,
            "max_file_size_mb": cfg.MEDIA_MAX_FILE_SIZE_MB,
            "default_audio_format": "mp3",
            "default_video_quality": "720p",
        }
    return {
        "media_enabled": mgw.media_enabled,
        "has_youtube_cookies": bool(mgw.encrypted_youtube_cookies or cfg.YOUTUBE_COOKIES_B64.strip()),
        "cookies_fingerprint": mgw.cookies_fingerprint,
        "has_youtube_api_key": bool(mgw.encrypted_youtube_api_key or cfg.YOUTUBE_API_KEY.strip()),
        "youtube_api_key_fingerprint": mgw.youtube_api_key_fingerprint,
        "max_duration_seconds": mgw.max_duration_seconds,
        "max_file_size_mb": mgw.max_file_size_mb,
        "default_audio_format": mgw.default_audio_format,
        "default_video_quality": mgw.default_video_quality,
        "updated_by_email": mgw.updated_by_email,
        "updated_at": mgw.updated_at,
    }


@router.put("/media-config")
def update_media_config(
    payload: AdminMediaConfigUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cfg = get_settings()
    mgw = db.get(MediaGatewayConfig, 1)
    if not mgw:
        mgw = MediaGatewayConfig(id=1)
        db.add(mgw)

    mgw.media_enabled = payload.media_enabled
    mgw.max_duration_seconds = payload.max_duration_seconds
    mgw.max_file_size_mb = payload.max_file_size_mb
    mgw.default_audio_format = payload.default_audio_format
    mgw.default_video_quality = payload.default_video_quality
    mgw.updated_by_email = admin.email

    if payload.clear_youtube_cookies:
        mgw.encrypted_youtube_cookies = None
        mgw.cookies_fingerprint = ""
    elif payload.youtube_cookies_txt is not None and payload.youtube_cookies_txt.strip():
        raw_cookies = payload.youtube_cookies_txt.strip()
        mgw.encrypted_youtube_cookies = encrypt_secret(raw_cookies, cfg)
        lines = [ln for ln in raw_cookies.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        mgw.cookies_fingerprint = f"{len(lines)} cookies ({len(raw_cookies)} bytes)"

    if payload.clear_youtube_api_key:
        mgw.encrypted_youtube_api_key = None
        mgw.youtube_api_key_fingerprint = ""
    elif payload.youtube_api_key is not None and payload.youtube_api_key.strip():
        raw_yt = payload.youtube_api_key.strip()
        mgw.encrypted_youtube_api_key = encrypt_secret(raw_yt, cfg)
        mgw.youtube_api_key_fingerprint = mask_secret(raw_yt, 6, 4)

    record_audit(
        db,
        "admin.media_config_updated",
        admin.email,
        admin.id,
        "media_gateway_config",
        "1",
        {
            "media_enabled": mgw.media_enabled,
            "has_cookies": bool(mgw.encrypted_youtube_cookies),
            "has_youtube_api_key": bool(mgw.encrypted_youtube_api_key),
            "max_duration_seconds": mgw.max_duration_seconds,
            "max_file_size_mb": mgw.max_file_size_mb,
        },
        get_client_ip(request),
    )
    db.commit()
    db.refresh(mgw)
    return {
        "message": "Media & YouTube API configuration saved securely.",
        "has_youtube_cookies": bool(mgw.encrypted_youtube_cookies),
        "cookies_fingerprint": mgw.cookies_fingerprint,
        "youtube_api_key_fingerprint": mgw.youtube_api_key_fingerprint,
    }


@router.post("/media-config/test")
async def test_media_runtime(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    import shutil
    from app.services.media_service import MediaServiceError, load_media_runtime_config, search_media

    cfg = get_settings()
    rt = load_media_runtime_config(db, cfg)
    ffmpeg_path = shutil.which("ffmpeg")
    yt_dlp_ver = None
    try:
        import yt_dlp  # type: ignore

        yt_dlp_ver = getattr(yt_dlp.version, "__version__", "installed")
    except Exception:
        pass

    search_ok = False
    search_detail = ""
    try:
        sr = await search_media(
            db,
            query="kesariya hindi song",
            limit=1,
            api_key_id="admin-probe",
            public_base_url=cfg.APP_PUBLIC_URL,
            settings=cfg,
        )
        search_ok = sr["count"] > 0
        first_title = sr["results"][0]["title"] if sr["results"] else "none"
        search_detail = f"Search ({sr['engine']}) matched: {first_title[:60]}"
    except MediaServiceError as exc:
        search_detail = f"{exc.error_code}: {exc.message}"
    except Exception as exc:
        search_detail = f"{type(exc).__name__}: {exc}"

    return {
        "ok": bool(yt_dlp_ver) and rt.media_enabled,
        "yt_dlp_version": yt_dlp_ver or "missing",
        "ffmpeg_available": bool(ffmpeg_path),
        "has_youtube_cookies": bool(rt.youtube_cookies),
        "has_youtube_api_key": bool(rt.youtube_api_key),
        "search_ok": search_ok,
        "detail": f"yt-dlp={yt_dlp_ver or 'missing'}, ffmpeg={'yes' if ffmpeg_path else 'no'} | {search_detail}",
    }


@router.get("/audit-logs")
def get_audit_logs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).all()
    return {"logs": logs}


@router.get("/support-tickets")
def get_support_tickets(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    tickets = db.scalars(select(SupportMessage).order_by(SupportMessage.created_at.desc()).limit(100)).all()
    return {"tickets": tickets}


@router.patch("/support-tickets/{ticket_id}")
def resolve_support_ticket(ticket_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ticket = db.get(SupportMessage, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    ticket.status = "resolved" if ticket.status == "open" else "open"
    db.commit()
    return {"ticket": ticket}


@router.get("/email-outbox")
def get_dev_email_outbox(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    emails = db.scalars(select(EmailOutbox).order_by(EmailOutbox.created_at.desc()).limit(50)).all()
    return {"emails": emails}


@router.get("/branding")
def get_admin_branding(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return get_effective_branding(db)


@router.put("/branding")
def update_admin_branding(
    payload: AdminBrandingUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(SiteBrandingConfig, 1)
    if not row:
        row = SiteBrandingConfig(id=1)
        db.add(row)

    row.app_name = payload.app_name.strip()
    row.company_name = payload.company_name.strip()
    row.brand_badge_letter = payload.brand_badge_letter.strip()[:1].upper()
    row.support_email = payload.support_email.strip()
    row.site_description = payload.site_description.strip()
    row.api_key_prefix_live = payload.api_key_prefix_live.strip()
    row.api_key_prefix_test = payload.api_key_prefix_test.strip()
    row.receipt_prefix = payload.receipt_prefix.strip().upper()
    row.updated_by_email = admin.email

    record_audit(
        db,
        "admin.branding_updated",
        admin.email,
        admin.id,
        "site_branding_config",
        "1",
        {"app_name": row.app_name, "company_name": row.company_name},
        get_client_ip(request),
    )
    db.commit()
    invalidate_branding_cache()
    return {"message": "Site & API branding saved live.", "branding": get_effective_branding(db)}


@router.post("/branding/reset")
def reset_admin_branding(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(SiteBrandingConfig, 1)
    if row:
        db.delete(row)
        record_audit(db, "admin.branding_reset", admin.email, admin.id, "site_branding_config", "1", {}, get_client_ip(request))
        db.commit()
    invalidate_branding_cache()
    return {"message": "Branding reset to .env defaults.", "branding": get_effective_branding(db)}

