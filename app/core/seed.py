"""Idempotent database seeding for default plans, master gateway config, and initial admin."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_secret, hash_password, mask_secret
from app.models.gateway import MasterGatewayConfig
from app.models.plan import SubscriptionPlan
from app.models.user import User

DEFAULT_PLANS = [
    {
        "name": "Free Sandbox",
        "slug": "free-sandbox",
        "tagline": "Instant trial access for testing & prototyping",
        "description": "Explore API gateway endpoints with a zero-cost sandbox API key and real-time playground access.",
        "price_paise": 0,
        "currency": "INR",
        "billing_cycle_days": 7,
        "daily_request_limit": 200,
        "monthly_request_limit": 1000,
        "rate_limit_per_minute": 20,
        "max_api_keys": 1,
        "allowed_methods": "GET,POST",
        "allowed_endpoints": "*",
        "features_json": [
            "1,000 total trial API calls (7 days)",
            "200 requests/day · 20 req/min burst",
            "1 unique API key with reveal & rotate",
            "Full interactive API Playground access",
            "Real-time request logs & latency metrics",
        ],
        "badge": "Free Tier",
        "is_active": True,
        "is_featured": False,
        "sort_order": 1,
    },
    {
        "name": "Starter Pulse",
        "slug": "starter-pulse",
        "tagline": "Built for solo builders & early-stage apps",
        "description": "Reliable production API access with multi-key isolation, daily quota scaling, and priority routing.",
        "price_paise": 49900,  # ₹499
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 5000,
        "monthly_request_limit": 100000,
        "rate_limit_per_minute": 60,
        "max_api_keys": 3,
        "allowed_methods": "GET,POST,PUT",
        "allowed_endpoints": "*",
        "features_json": [
            "100,000 API requests / 30 days",
            "5,000 requests/day · 60 req/min rate limit",
            "Up to 3 isolated API keys",
            "GET, POST & PUT endpoint methods",
            "Downloadable GST-ready Razorpay receipts",
        ],
        "badge": "Starter",
        "is_active": True,
        "is_featured": False,
        "sort_order": 2,
    },
    {
        "name": "Pro Velocity",
        "slug": "pro-velocity",
        "tagline": "High-throughput access for growing SaaS teams",
        "description": "Our flagship developer tier featuring full REST verbs, 1M monthly quota, and 300 req/min edge bursts.",
        "price_paise": 199900,  # ₹1,999
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 50000,
        "monthly_request_limit": 1000000,
        "rate_limit_per_minute": 300,
        "max_api_keys": 10,
        "allowed_methods": "GET,POST,PUT,PATCH,DELETE",
        "allowed_endpoints": "*",
        "features_json": [
            "1,000,000 API requests / 30 days",
            "50,000 requests/day · 300 req/min bursts",
            "Up to 10 environment-scoped API keys",
            "All HTTP methods (GET, POST, PUT, PATCH, DELETE)",
            "99.95% SLA & priority gateway routing",
        ],
        "badge": "Most Popular",
        "is_active": True,
        "is_featured": True,
        "sort_order": 3,
    },
    {
        "name": "Enterprise Nova",
        "slug": "enterprise-nova",
        "tagline": "Dedicated throughput & ultra-high rate ceiling",
        "description": "Mission-critical capacity for high-volume pipelines, multi-region workloads, and dedicated support.",
        "price_paise": 699900,  # ₹6,999
        "currency": "INR",
        "billing_cycle_days": 30,
        "daily_request_limit": 500000,
        "monthly_request_limit": 10000000,
        "rate_limit_per_minute": 1500,
        "max_api_keys": 25,
        "allowed_methods": "GET,POST,PUT,PATCH,DELETE",
        "allowed_endpoints": "*",
        "features_json": [
            "10,000,000 API requests / 30 days",
            "500,000 requests/day · 1,500 req/min ceiling",
            "Up to 25 team API keys & full audit logs",
            "Dedicated upstream failover & zero throttling",
            "24/7 engineering escalation channel",
        ],
        "badge": "High Scale",
        "is_active": True,
        "is_featured": False,
        "sort_order": 4,
    },
]


def seed_initial_data(db: Session) -> None:
    cfg = get_settings()

    # 1. Seed plans if missing by slug
    existing_slugs = set(db.scalars(select(SubscriptionPlan.slug)).all())
    for plan_data in DEFAULT_PLANS:
        if plan_data["slug"] not in existing_slugs:
            db.add(SubscriptionPlan(**plan_data))

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

