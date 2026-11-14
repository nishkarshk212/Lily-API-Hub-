"""Idempotent database seeding for default plans, master gateway config, and initial admin."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_secret, hash_password, mask_secret
from app.models.gateway import MasterGatewayConfig, MediaGatewayConfig
from app.models.plan import SubscriptionPlan
from app.models.user import User

DEFAULT_PLANS = [
    {
        "name": "2K Songs Free",
        "slug": "2k-free",
        "tagline": "2,000 Free Song Requests for Testing & Bots",
        "description": "Start instantly with 2,000 free song requests for Telegram music bots and apps.",
        "price_paise": 0,
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 2000,
        "monthly_request_limit": 2000,
        "rate_limit_per_minute": 60,
        "max_api_keys": 2,
        "allowed_methods": "GET,POST",
        "allowed_endpoints": "*",
        "features_json": [
            "2,000 Free Song Requests",
            "Up to 320kbps MP3 Audio Stream & Download",
            "Full YouTube & Hindi Music Search",
            "Telegram Music Bot (youtube.py) Compatible",
            "Real-time Quota & Usage Analytics",
        ],
        "badge": "Free Tier",
        "is_active": True,
        "is_featured": False,
        "sort_order": 1,
    },
    {
        "name": "3K Songs",
        "slug": "3k-songs",
        "tagline": "3,000 Song Requests for ₹29",
        "description": "Affordable entry plan for active Telegram music groups and solo bots.",
        "price_paise": 2900,  # ₹29
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 3000,
        "monthly_request_limit": 3000,
        "rate_limit_per_minute": 100,
        "max_api_keys": 3,
        "allowed_methods": "GET,POST",
        "allowed_endpoints": "*",
        "features_json": [
            "3,000 Song Requests / 30 Days",
            "₹29 One-Time or Monthly via UPI / Cards",
            "320kbps High-Bitrate MP3 Downloads",
            "Up to 3 Dedicated API Keys",
            "Zero Ad / Bot Block Protection",
        ],
        "badge": "Starter",
        "is_active": True,
        "is_featured": False,
        "sort_order": 2,
    },
    {
        "name": "5K Songs",
        "slug": "5k-songs",
        "tagline": "5,000 Song Requests for ₹65",
        "description": "Ideal for medium music communities and Telegram bot groups.",
        "price_paise": 6500,  # ₹65
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 5000,
        "monthly_request_limit": 5000,
        "rate_limit_per_minute": 150,
        "max_api_keys": 5,
        "allowed_methods": "GET,POST",
        "allowed_endpoints": "*",
        "features_json": [
            "5,000 Song Requests / 30 Days",
            "₹65 via Razorpay (UPI, QR, Netbanking)",
            "320kbps MP3 + 1080p Video Streams",
            "Up to 5 Dedicated API Keys",
            "High-Throughput Low-Latency Edge",
        ],
        "badge": "Popular",
        "is_active": True,
        "is_featured": False,
        "sort_order": 3,
    },
    {
        "name": "10K Songs",
        "slug": "10k-songs",
        "tagline": "10,000 Song Requests for ₹115",
        "description": "Great value plan for busy Telegram voice chat bots and multi-group networks.",
        "price_paise": 11500,  # ₹115
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 10000,
        "monthly_request_limit": 10000,
        "rate_limit_per_minute": 250,
        "max_api_keys": 8,
        "allowed_methods": "GET,POST,PUT",
        "allowed_endpoints": "*",
        "features_json": [
            "10,000 Song Requests / 30 Days",
            "₹115 Instant UPI Activation",
            "Ultra-Fast MP3 & M4A Audio Extraction",
            "Up to 8 Isolated API Keys",
            "Priority Queue Processing",
        ],
        "badge": "Best Value",
        "is_active": True,
        "is_featured": True,
        "sort_order": 4,
    },
    {
        "name": "25K Songs",
        "slug": "25k-songs",
        "tagline": "25,000 Song Requests for ₹250",
        "description": "High-volume tier for large music bot hosting networks and commercial bots.",
        "price_paise": 25000,  # ₹250
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 25000,
        "monthly_request_limit": 25000,
        "rate_limit_per_minute": 400,
        "max_api_keys": 12,
        "allowed_methods": "GET,POST,PUT,PATCH,DELETE",
        "allowed_endpoints": "*",
        "features_json": [
            "25,000 Song Requests / 30 Days",
            "₹250 One-Time or Monthly via Razorpay",
            "Up to 12 Environment-Scoped Keys",
            "All Audio & Video Format Extractions",
            "Dedicated Bandwidth & 99.9% Uptime",
        ],
        "badge": "Pro",
        "is_active": True,
        "is_featured": False,
        "sort_order": 5,
    },
    {
        "name": "50K Songs",
        "slug": "50k-songs",
        "tagline": "50,000 Song Requests for ₹450",
        "description": "Enterprise capacity for large music communities and high-scale music bot fleets.",
        "price_paise": 45000,  # ₹450
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 50000,
        "monthly_request_limit": 50000,
        "rate_limit_per_minute": 600,
        "max_api_keys": 20,
        "allowed_methods": "GET,POST,PUT,PATCH,DELETE",
        "allowed_endpoints": "*",
        "features_json": [
            "50,000 Song Requests / 30 Days",
            "₹450 Complete Package",
            "Up to 20 API Keys for Cluster Workloads",
            "Direct 320kbps Streams & Signed Tokens",
            "24/7 Priority Bot Support",
        ],
        "badge": "Mega Scale",
        "is_active": True,
        "is_featured": False,
        "sort_order": 6,
    },
    {
        "name": "100K Songs",
        "slug": "100k-songs",
        "tagline": "100,000 Song Requests for ₹850",
        "description": "Unlimited performance tier for top music bot networks, platforms, and SaaS providers.",
        "price_paise": 85000,  # ₹850
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 100000,
        "monthly_request_limit": 100000,
        "rate_limit_per_minute": 1200,
        "max_api_keys": 30,
        "allowed_methods": "GET,POST,PUT,PATCH,DELETE",
        "allowed_endpoints": "*",
        "features_json": [
            "100,000 Song Requests / 30 Days",
            "₹850 Maximum Value Tier",
            "Up to 30 Fleet API Keys",
            "Ultra-Low Latency Gateway Routing",
            "VIP Telegram Escalation & Full Support",
        ],
        "badge": "Ultimate",
        "is_active": True,
        "is_featured": False,
        "sort_order": 7,
    },
]


def seed_initial_data(db: Session) -> None:
    cfg = get_settings()

    # 1. Upsert default plans and deactivate obsolete legacy plans
    active_slugs = {p["slug"] for p in DEFAULT_PLANS}
    for legacy_plan in db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.slug.not_in(active_slugs))).all():
        legacy_plan.is_active = False

    existing_plans = {p.slug: p for p in db.scalars(select(SubscriptionPlan)).all()}
    for plan_data in DEFAULT_PLANS:
        slug = plan_data["slug"]
        if slug in existing_plans:
            existing = existing_plans[slug]
            for field, val in plan_data.items():
                setattr(existing, field, val)
        else:
            db.add(SubscriptionPlan(**plan_data))

    db.commit()

    try:
        from app.core.cache import get_plans_cache
        get_plans_cache().clear()
    except Exception:
        pass

    # 2. Seed singleton MasterGatewayConfig if not present
    gw = db.get(MasterGatewayConfig, 1)
    if gw is None:
        raw_master = cfg.MASTER_API_KEY.strip()
        gw = MasterGatewayConfig(
            id=1,
            gateway_mode=cfg.GATEWAY_MODE or "hybrid",
            upstream_base_url=cfg.UPSTREAM_API_BASE_URL.strip(),
            encrypted_master_api_key=encrypt_secret(raw_master, cfg) if raw_master else None,
            master_key_fingerprint=mask_secret(raw_master, 6, 4) if raw_master else "Not configured",
            auth_header_name=cfg.UPSTREAM_AUTH_HEADER or "Authorization",
            auth_scheme=cfg.UPSTREAM_AUTH_SCHEME or "Bearer",
            timeout_ms=cfg.UPSTREAM_TIMEOUT_MS or 10000,
            forward_user_context_headers=True,
            updated_by_email="system-bootstrap",
        )
        db.add(gw)

    # 2b. Seed singleton MediaGatewayConfig if not present
    mgw = db.get(MediaGatewayConfig, 1)
    if mgw is None:
        raw_yt_key = cfg.YOUTUBE_API_KEY.strip()
        mgw = MediaGatewayConfig(
            id=1,
            media_enabled=cfg.MEDIA_API_ENABLED,
            encrypted_youtube_api_key=encrypt_secret(raw_yt_key, cfg) if raw_yt_key else None,
            youtube_api_key_fingerprint=mask_secret(raw_yt_key, 6, 4) if raw_yt_key else "",
            max_duration_seconds=max(60, min(7200, int(cfg.MEDIA_MAX_DURATION_SECONDS or 1200))),
            max_file_size_mb=max(10, min(2048, int(cfg.MEDIA_MAX_FILE_SIZE_MB or 250))),
            default_audio_format="mp3",
            default_video_quality="720p",
            updated_by_email="system-bootstrap",
        )
        db.add(mgw)

    # 3. Seed initial admin if no admin user exists yet
    has_admin = db.scalar(select(User.id).where(User.role == "admin").limit(1))
    if not has_admin and cfg.INITIAL_ADMIN_EMAIL.strip():
        admin_email = cfg.INITIAL_ADMIN_EMAIL.strip().lower()
        existing_user = db.scalar(select(User).where(User.email == admin_email))
        if existing_user:
            existing_user.role = "admin"
            existing_user.is_email_verified = True
        else:
            db.add(
                User(
                    email=admin_email,
                    password_hash=hash_password(cfg.INITIAL_ADMIN_PASSWORD),
                    full_name=cfg.INITIAL_ADMIN_NAME or f"{cfg.COMPANY_NAME} Admin",
                    company=cfg.COMPANY_NAME,
                    role="admin",
                    is_email_verified=True,
                    is_active=True,
                    is_suspended=False,
                    auth_provider="email",
                )
            )

    try:
        db.commit()
    except IntegrityError:
        # Another worker/serverless cold start seeded concurrently.
        db.rollback()

