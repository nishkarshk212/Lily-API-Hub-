"""Public platform overview, documentation catalog, support form, and health endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.gateway import MasterGatewayConfig
from app.models.plan import SubscriptionPlan
from app.models.telegram import TelegramBot
from app.models.user import SupportMessage, User
from app.routers.deps import get_optional_user
from app.schemas.auth import SupportTicketRequest
from app.services.auth_service import get_client_ip, record_audit
from app.services.branding_service import get_effective_branding

router = APIRouter(prefix="/api/public", tags=["Public"])

BUILTIN_ENDPOINTS_CATALOG = [
    {
        "method": "GET",
        "path": "/v1/status",
        "title": "Gateway Health & Plan Telemetry",
        "description": "Verify your API key, active plan limits, and Master Gateway link tag.",
        "sample_query": {},
        "sample_body": None,
    },
    {
        "method": "POST",
        "path": "/v1/network/echo",
        "title": "Echo & Request Inspector",
        "description": "Inspect parsed JSON payloads, sanitized headers, and edge routing timestamps.",
        "sample_query": {"env": "prod"},
        "sample_body": {"service": "sonic-node", "ping": True},
    },
    {
        "method": "POST",
        "path": "/v1/crypto/hash",
        "title": "Cryptographic Digest & HMAC",
        "description": "Compute SHA-256, SHA-512, or BLAKE2b digests and HMAC signatures server-side.",
        "sample_query": {},
        "sample_body": {"text": "sonic-network-payload", "algorithm": "sha256"},
    },
    {
        "method": "GET",
        "path": "/v1/crypto/uuid",
        "title": "Secure UUIDv4 Batch Generator",
        "description": "Generate up to 25 cryptographically random UUIDv4 identifiers per call.",
        "sample_query": {"count": "3"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/geo/ip-parse",
        "title": "IPv4 / IPv6 Address Inspector",
        "description": "Classify public/private/loopback ranges and reverse PTR pointers.",
        "sample_query": {"ip": "8.8.8.8"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/network/dns",
        "title": "Real-Time DNS Resolver",
        "description": "Resolve A and AAAA DNS records directly from the Sonic Network gateway.",
        "sample_query": {"domain": "example.com"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/utils/timestamp",
        "title": "Atomic UTC Time & Epoch Sync",
        "description": "Fetch synchronized ISO-8601 UTC and Unix second/millisecond timestamps.",
        "sample_query": {},
        "sample_body": None,
    },
    {
        "method": "POST",
        "path": "/v1/utils/json-validate",
        "title": "JSON Schema & Payload Validator",
        "description": "Validate JSON payloads and inspect object key counts and byte sizes.",
        "sample_query": {},
        "sample_body": {"network": "Sonic", "hub": "Beta", "version": 2},
    },
    {
        "method": "GET",
        "path": "/v1/media/search",
        "title": "Search Songs & Videos (YouTube)",
        "description": "Search songs, tracks, or videos by title/query and receive metadata + ready-to-download links.",
        "sample_query": {"q": "kesariya hindi song", "limit": "5"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/media/info",
        "title": "Full Media Details & All Formats",
        "description": "Fetch full video/song metadata: music tags, channel stats, chapters, captions, thumbnails, audio/video streams & signed download links.",
        "sample_query": {"q": "kesariya hindi song"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/media/audio",
        "title": "Download / Stream Song Audio (MP3 / M4A / Original)",
        "description": "Download or stream audio from a URL, video ID, or song search query. Pass mode=json for signed link metadata.",
        "sample_query": {"q": "kesariya hindi song", "format": "mp3", "bitrate": "192", "mode": "json"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/media/video",
        "title": "Download / Stream Video (360p / 720p / 1080p / Best)",
        "description": "Download or stream MP4/WebM video at chosen resolution. Automatically merges HD video+audio streams server-side.",
        "sample_query": {"q": "kesariya hindi song", "quality": "720p", "format": "mp4", "mode": "json"},
        "sample_body": None,
    },
    {
        "method": "GET",
        "path": "/v1/media/download",
        "title": "Unified Song / Video / Details Downloader",
        "description": "Single endpoint accepting type=audio|video|info, format, quality, and url|id|q.",
        "sample_query": {"q": "kesariya hindi song", "type": "audio", "format": "mp3", "mode": "json"},
        "sample_body": None,
    },
]

FAQS = [
    {
        "q": "How do customer API keys link to Sonic Network's Master Backend?",
        "a": "Every purchased plan provisions a unique customer key (beta_live_...) linked to our Master Gateway profile. When your apps call our /v1/* endpoint URL, our gateway validates your key, enforces your exact rate limits and quotas, and securely proxies upstream using server-side master credentials that are never exposed.",
    },
    {
        "q": "When is my API key activated after a Razorpay payment?",
        "a": "Immediately upon server-side HMAC-SHA256 verification of the Razorpay signature (or idempotent payment.captured webhook confirmation). No manual approval is required.",
    },
    {
        "q": "Which payment methods are supported via Razorpay?",
        "a": "We support UPI (GPay, PhonePe, Paytm, BHIM), Visa/Mastercard/RuPay Credit & Debit Cards, Indian Netbanking across 50+ banks, and popular wallets.",
    },
    {
        "q": "Can I rotate or revoke a compromised API key without losing my plan?",
        "a": "Yes. Inside your Developer Dashboard, you can regenerate any key instantaneously or revoke individual keys while creating additional keys up to your plan limit.",
    },
    {
        "q": "What happens when my daily quota or subscription expires?",
        "a": "Daily counters automatically reset at 00:00 UTC. If a subscription reaches its expiry date, the gateway transitions it to expired and returns HTTP 403 SUBSCRIPTION_EXPIRED until renewed.",
    },
]

TESTIMONIALS = [
    {
        "quote": "Switching our analytics ingestion to Beta API Hub cut gateway latency under 18ms and gave our clients clean per-key quotas right out of the box.",
        "author": "Aarav Mehta",
        "role": "CTO, PulseGrid Telemetry",
    },
    {
        "quote": "Razorpay UPI checkout activated our Pro Velocity key in under two seconds. The built-in playground saved hours of Postman setup.",
        "author": "Rhea Nair",
        "role": "Staff Engineer, FinVerve Labs",
    },
    {
        "quote": "Master key isolation and instant revocation gave our security team total confidence before rolling out external developer access.",
        "author": "Vikramaditya Rao",
        "role": "VP Infrastructure, NexaCloud",
    },
]


@router.get("/overview")
def get_public_overview(request: Request, db: Session = Depends(get_db)):
    cfg = get_settings()
    brand = get_effective_branding(db, cfg)
    gw = db.get(MasterGatewayConfig, 1)
    pbot = db.scalar(
        select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True), TelegramBot.is_active.is_(True)).limit(1)
    )
    active_plans_count = db.scalar(select(func.count(SubscriptionPlan.id)).where(SubscriptionPlan.is_active.is_(True))) or 0
    base_url = cfg.resolve_api_base_url(request)
    faqs = [
        {
            "q": f"How do customer API keys link to {brand['company_name']}'s Master Backend?",
            "a": f"Every purchased plan provisions a unique customer key ({brand['api_key_prefix_live']}...) linked to our Master Gateway profile. When your apps call our /v1/* endpoint URL, our gateway validates your key, enforces your exact rate limits and quotas, and securely proxies upstream using server-side master credentials that are never exposed.",
        },
        *FAQS[1:],
    ]
    testimonials = [
        {
            **TESTIMONIALS[0],
            "quote": f"Switching our analytics ingestion to {brand['app_name']} cut gateway latency under 18ms and gave our clients clean per-key quotas right out of the box.",
        },
        *TESTIMONIALS[1:],
    ]
    endpoints = [
        (
            {**ep, "description": f"Resolve A and AAAA DNS records directly from the {brand['company_name']} gateway."}
            if ep["path"] == "/v1/network/dns"
            else {**ep, "sample_body": {"provider": brand["company_name"], "hub": brand["app_name"], "version": 2}}
            if ep["path"] == "/v1/utils/json-validate"
            else ep
        )
        for ep in BUILTIN_ENDPOINTS_CATALOG
    ]
    return {
        "brand": brand["app_name"],
        "company": brand["company_name"],
        "brand_letter": brand["brand_letter"],
        "support_email": brand["support_email"],
        "site_description": brand["site_description"],
        "key_prefix_live": brand["api_key_prefix_live"],
        "key_prefix_test": brand["api_key_prefix_test"],
        "api_base_url": base_url,
        "gateway_mode": gw.gateway_mode if gw else "hybrid",
        "google_oauth_enabled": cfg.google_oauth_configured,
        "razorpay_enabled": cfg.razorpay_configured,
        "smtp_enabled": bool(cfg.SMTP_HOST.strip()),
        "telegram_platform_bot_enabled": bool(pbot),
        "telegram_platform_bot_username": pbot.bot_username if pbot else "",
        "active_plans_count": active_plans_count,
        "endpoints": endpoints,
        "faqs": faqs,
        "testimonials": testimonials,
    }


@router.post("/support")
def submit_support_ticket(
    payload: SupportTicketRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    brand = get_effective_branding(db)
    ticket = SupportMessage(
        user_id=user.id if user else None,
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        subject=payload.subject.strip(),
        message=payload.message.strip(),
    )
    db.add(ticket)
    record_audit(
        db,
        "support.ticket_submitted",
        ticket.email,
        user.id if user else None,
        "support_message",
        ticket.id,
        {"subject": ticket.subject},
        get_client_ip(request),
    )
    db.commit()
    return {"message": f"Support request received. {brand['company_name']} engineers will respond shortly.", "ticket_id": ticket.id}

