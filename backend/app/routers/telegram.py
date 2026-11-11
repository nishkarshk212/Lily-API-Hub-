"""Telegram Bot onboarding, webhooks, simulator, notifications, and Admin Bot Center."""

import hmac
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.api_key import ApiKey
from app.models.telegram import TelegramBot, TelegramBotEvent, TelegramUserLink
from app.models.user import User
from app.routers.deps import get_current_user, require_admin
from app.schemas.domain import (
    AdminPlatformTelegramRequest,
    AdminTelegramBroadcastRequest,
    TelegramBotConnectRequest,
    TelegramBotUpdateRequest,
    TelegramSimulateRequest,
    TelegramUserPreferencesRequest,
)
from app.core.security import encrypt_secret, mask_secret
from app.services.auth_service import get_client_ip, record_audit
from app.services.telegram_service import (
    TelegramApiError,
    _deliver_bot_message,
    _is_public_https_url,
    connect_telegram_bot,
    create_user_link_token,
    disconnect_telegram_bot,
    normalize_proxy_path,
    poll_bot_updates_once,
    process_telegram_update,
    serialize_telegram_bot,
    simulate_bot_command,
    sync_bot_with_telegram,
    telegram_api_call,
)

router = APIRouter(tags=["Telegram Bot"])


def _resolve_request_public_url(request: Request) -> str:
    cfg = get_settings()
    if _is_public_https_url(cfg.APP_PUBLIC_URL):
        return cfg.APP_PUBLIC_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if proto == "https" and host:
        return f"https://{host}".rstrip("/")
    base = str(request.base_url).rstrip("/")
    if _is_public_https_url(base):
        return base
    return (cfg.APP_PUBLIC_URL or base).rstrip("/")


def _get_owned_bot(db: Session, user: User, bot_id: str) -> TelegramBot:
    bot = db.get(TelegramBot, bot_id)
    if not bot or bot.is_platform_bot or bot.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram bot not found.")
    return bot


def _serialize_events(events: List[TelegramBotEvent]) -> List[Dict[str, Any]]:
    return [
        {
            "id": ev.id,
            "bot_id": ev.bot_id,
            "telegram_user_id": ev.telegram_user_id,
            "telegram_username": ev.telegram_username,
            "chat_id": ev.chat_id,
            "event_type": ev.event_type,
            "command_or_action": ev.command_or_action,
            "status": ev.status,
            "latency_ms": ev.latency_ms,
            "detail": ev.detail,
            "created_at": ev.created_at,
        }
        for ev in events
    ]


@router.post("/api/telegram/webhook/{bot_id}")
async def telegram_webhook_receiver(
    bot_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    bot = db.get(TelegramBot, bot_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram bot not registered.")

    provided_secret = request.headers.get("x-telegram-bot-api-secret-token", "").strip()
    if not provided_secret or not hmac.compare_digest(provided_secret, bot.webhook_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Telegram webhook secret token.")

    try:
        update_payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Telegram JSON update.")

    if not isinstance(update_payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update payload must be a JSON object.")

    return await process_telegram_update(db, bot, update_payload)


@router.get("/api/telegram/status")
def get_my_telegram_status(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    public_url = _resolve_request_public_url(request)
    pbot = db.scalar(
        select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True), TelegramBot.is_active.is_(True)).limit(1)
    )
    platform_info: Dict[str, Any] = {"configured": False}
    if pbot:
        link = db.scalar(
            select(TelegramUserLink).where(
                TelegramUserLink.bot_id == pbot.id,
                TelegramUserLink.user_id == user.id,
                TelegramUserLink.is_active.is_(True),
            )
        )
        token_code, deep_link = create_user_link_token(user, pbot)
        platform_info = {
            "configured": True,
            "bot_username": pbot.bot_username,
            "bot_name": pbot.bot_name,
            "bot_url": f"https://t.me/{pbot.bot_username}",
            "linked": bool(link),
            "connect_deep_link": deep_link,
            "manual_link_command": f"/link {token_code}",
            "link": (
                {
                    "telegram_user_id": link.telegram_user_id,
                    "telegram_username": link.telegram_username,
                    "telegram_first_name": link.telegram_first_name,
                    "notify_quota_alerts": link.notify_quota_alerts,
                    "notify_security_alerts": link.notify_security_alerts,
                    "notify_payment_alerts": link.notify_payment_alerts,
                    "notify_gateway_errors": link.notify_gateway_errors,
                    "updated_at": link.updated_at,
                }
                if link
                else None
            ),
        }

    my_bots = db.scalars(
        select(TelegramBot)
        .where(TelegramBot.owner_user_id == user.id, TelegramBot.is_platform_bot.is_(False))
        .order_by(TelegramBot.created_at.desc())
    ).all()

    return {
        "public_https_ready": _is_public_https_url(public_url),
        "recommended_mode": "webhook" if _is_public_https_url(public_url) else "polling",
        "webhook_base_url": public_url,
        "platform_bot": platform_info,
        "bots": [serialize_telegram_bot(db, b) for b in my_bots],
    }


@router.post("/api/telegram/platform/link-token")
def generate_platform_link_token(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(
        select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True), TelegramBot.is_active.is_(True)).limit(1)
    )
    if not pbot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Official Platform Telegram Bot is not configured by the administrator yet.",
        )
    token_code, deep_link = create_user_link_token(user, pbot)
    return {
        "bot_username": pbot.bot_username,
        "connect_deep_link": deep_link,
        "manual_link_command": f"/link {token_code}",
        "expires_in_seconds": 900,
    }


@router.patch("/api/telegram/platform/preferences")
def update_platform_link_preferences(
    payload: TelegramUserPreferencesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    if not pbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform Telegram bot not configured.")
    link = db.scalar(
        select(TelegramUserLink).where(
            TelegramUserLink.bot_id == pbot.id,
            TelegramUserLink.user_id == user.id,
            TelegramUserLink.is_active.is_(True),
        )
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Your Telegram account is not linked yet.")

    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(link, k, v)
    db.commit()
    return {"message": "Telegram alert preferences updated."}


@router.post("/api/telegram/platform/test-alert")
async def send_platform_test_alert(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    if not pbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform Telegram bot not configured.")
    link = db.scalar(
        select(TelegramUserLink).where(
            TelegramUserLink.bot_id == pbot.id,
            TelegramUserLink.user_id == user.id,
            TelegramUserLink.is_active.is_(True),
        )
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Link your Telegram account first.")
    sent = await _deliver_bot_message(
        db,
        pbot,
        link.chat_id,
        f"🔔 <b>Test Notification</b>\nConnected to <b>{user.email}</b> via @{pbot.bot_username}.",
        category="alert:test",
    )
    if not sent:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Telegram delivery failed. Check bot logs.")
    return {"message": "Test notification delivered to your Telegram chat."}


@router.delete("/api/telegram/platform/unlink")
def unlink_platform_telegram(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    links = db.scalars(
        select(TelegramUserLink).where(TelegramUserLink.user_id == user.id, TelegramUserLink.is_active.is_(True))
    ).all()
    for link in links:
        link.is_active = False
    db.commit()
    return {"message": "Telegram account unlinked."}


@router.post("/api/telegram/bots", status_code=201)
async def connect_user_telegram_bot(
    payload: TelegramBotConnectRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    public_url = _resolve_request_public_url(request)
    try:
        bot, sync_res = await connect_telegram_bot(
            db,
            bot_token=payload.bot_token,
            owner_user=user,
            is_platform_bot=False,
            bot_name=payload.bot_name,
            api_key_id=payload.api_key_id,
            access_mode=payload.access_mode,
            connection_mode=payload.connection_mode,
            welcome_message=payload.welcome_message,
            custom_proxy_path=payload.custom_proxy_path,
            custom_proxy_method=payload.custom_proxy_method,
            forward_plain_text=payload.forward_plain_text,
            notify_owner_alerts=payload.notify_owner_alerts,
            public_base_url=public_url,
        )
    except TelegramApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    record_audit(
        db,
        "telegram.bot_connected",
        user.email,
        user.id,
        "telegram_bot",
        bot.id,
        {"bot_username": bot.bot_username, "connection_mode": bot.connection_mode},
        get_client_ip(request),
    )
    db.commit()
    return {
        "message": f"Connected @{bot.bot_username} successfully.",
        "bot": serialize_telegram_bot(db, bot),
        "sync": sync_res,
    }


@router.patch("/api/telegram/bots/{bot_id}")
async def update_user_telegram_bot(
    bot_id: str,
    payload: TelegramBotUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    public_url = _resolve_request_public_url(request)
    resync_needed = False

    if payload.bot_token is not None and payload.bot_token.strip():
        try:
            me = await telegram_api_call(payload.bot_token.strip(), "getMe", {})
        except TelegramApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        bot.bot_tg_id = str(me["id"])
        bot.bot_username = str(me["username"]).lstrip("@")
        bot.encrypted_token = encrypt_secret(payload.bot_token.strip())
        bot.token_fingerprint = mask_secret(payload.bot_token.strip(), 6, 4)
        resync_needed = True

    if payload.api_key_id is not None:
        if payload.api_key_id == "":
            bot.api_key_id = None
        else:
            key_row = db.get(ApiKey, payload.api_key_id)
            if not key_row or key_row.user_id != user.id or key_row.status != "active":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected API key is invalid or inactive.")
            bot.api_key_id = key_row.id

    if payload.bot_name is not None and payload.bot_name.strip():
        bot.bot_name = payload.bot_name.strip()
    if payload.access_mode is not None:
        bot.access_mode = payload.access_mode
    if payload.is_active is not None:
        bot.is_active = payload.is_active
    if payload.welcome_message is not None:
        bot.welcome_message = payload.welcome_message.strip()
    if payload.custom_proxy_path is not None:
        bot.custom_proxy_path = normalize_proxy_path(payload.custom_proxy_path)
    if payload.custom_proxy_method is not None:
        bot.custom_proxy_method = payload.custom_proxy_method
    if payload.forward_plain_text is not None:
        bot.forward_plain_text = payload.forward_plain_text
    if payload.notify_owner_alerts is not None:
        bot.notify_owner_alerts = payload.notify_owner_alerts
    if payload.connection_mode is not None and payload.connection_mode != bot.connection_mode:
        bot.connection_mode = payload.connection_mode
        resync_needed = True

    db.commit()
    sync_res = None
    if resync_needed:
        try:
            sync_res = await sync_bot_with_telegram(db, bot, public_base_url=public_url)
        except TelegramApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {"message": f"Updated @{bot.bot_username}.", "bot": serialize_telegram_bot(db, bot), "sync": sync_res}


@router.post("/api/telegram/bots/{bot_id}/sync")
async def sync_user_telegram_bot(
    bot_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    public_url = _resolve_request_public_url(request)
    try:
        sync_res = await sync_bot_with_telegram(db, bot, public_base_url=public_url)
    except TelegramApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"message": "Webhook & Telegram commands synchronized.", "bot": serialize_telegram_bot(db, bot), "sync": sync_res}


@router.post("/api/telegram/bots/{bot_id}/poll")
async def poll_user_telegram_bot(
    bot_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    try:
        count = await poll_bot_updates_once(db, bot, timeout_sec=0)
    except TelegramApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"message": f"Processed {count} incoming update(s).", "processed_count": count, "bot": serialize_telegram_bot(db, bot)}


@router.post("/api/telegram/bots/{bot_id}/test-message")
async def test_user_bot_message(
    bot_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    if not bot.paired_chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pair the bot in Telegram first using the Pair in Telegram button.",
        )
    sent = await _deliver_bot_message(
        db,
        bot,
        bot.paired_chat_id,
        f"🔔 <b>Test Ping from Website</b>\n@{bot.bot_username} is connected to <b>{user.email}</b>.",
        category="alert:test",
    )
    if not sent:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Telegram sendMessage failed.")
    return {"message": "Test message sent to your paired Telegram chat."}


@router.post("/api/telegram/bots/{bot_id}/simulate")
async def simulate_user_telegram_bot(
    bot_id: str,
    payload: TelegramSimulateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    replies = await simulate_bot_command(db, bot, user, payload.text, as_owner=payload.as_owner)
    return {"bot_username": bot.bot_username, "input": payload.text, "replies": replies}


@router.get("/api/telegram/bots/{bot_id}/events")
def get_user_telegram_bot_events(
    bot_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    events = db.scalars(
        select(TelegramBotEvent)
        .where(TelegramBotEvent.bot_id == bot.id)
        .order_by(TelegramBotEvent.created_at.desc())
        .limit(50)
    ).all()
    return {"events": _serialize_events(events)}


@router.delete("/api/telegram/bots/{bot_id}")
async def delete_user_telegram_bot(
    bot_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_bot(db, user, bot_id)
    uname = bot.bot_username
    await disconnect_telegram_bot(db, bot)
    record_audit(db, "telegram.bot_disconnected", user.email, user.id, "telegram_bot", bot_id, {"bot_username": uname}, get_client_ip(request))
    db.commit()
    return {"message": f"Disconnected @{uname} cleanly."}


# ---------------------------------------------------------------------------
# Admin Platform Bot Management Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/admin/telegram")
def admin_get_telegram_center(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    public_url = _resolve_request_public_url(request)
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    links = []
    if pbot:
        raw_links = db.scalars(
            select(TelegramUserLink).where(TelegramUserLink.bot_id == pbot.id).order_by(TelegramUserLink.updated_at.desc()).limit(100)
        ).all()
        user_emails = {u.id: u.email for u in db.scalars(select(User)).all()}
        links = [
            {
                "id": l.id,
                "user_email": user_emails.get(l.user_id, "unknown"),
                "telegram_user_id": l.telegram_user_id,
                "telegram_username": l.telegram_username,
                "telegram_first_name": l.telegram_first_name,
                "is_active": l.is_active,
                "notify_quota_alerts": l.notify_quota_alerts,
                "notify_security_alerts": l.notify_security_alerts,
                "notify_payment_alerts": l.notify_payment_alerts,
                "notify_gateway_errors": l.notify_gateway_errors,
                "updated_at": l.updated_at,
            }
            for l in raw_links
        ]

    custom_bots_count = db.scalar(select(func.count(TelegramBot.id)).where(TelegramBot.is_platform_bot.is_(False))) or 0
    recent_events = db.scalars(select(TelegramBotEvent).order_by(TelegramBotEvent.created_at.desc()).limit(60)).all()
    bot_names = {b.id: f"@{b.bot_username}" for b in db.scalars(select(TelegramBot)).all()}

    return {
        "public_https_ready": _is_public_https_url(public_url),
        "recommended_mode": "webhook" if _is_public_https_url(public_url) else "polling",
        "webhook_base_url": public_url,
        "platform_bot": serialize_telegram_bot(db, pbot) if pbot else None,
        "linked_users": links,
        "custom_bots_count": custom_bots_count,
        "events": [
            {**ev_dict, "bot_username": bot_names.get(ev_dict["bot_id"], "-")}
            for ev_dict in _serialize_events(recent_events)
        ],
    }


@router.put("/api/admin/telegram/platform-bot")
async def admin_upsert_platform_bot(
    payload: AdminPlatformTelegramRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    public_url = _resolve_request_public_url(request)
    existing = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))

    if payload.bot_token and payload.bot_token.strip():
        try:
            bot, sync_res = await connect_telegram_bot(
                db,
                bot_token=payload.bot_token.strip(),
                owner_user=admin,
                is_platform_bot=True,
                bot_name=payload.bot_name,
                connection_mode=payload.connection_mode,
                welcome_message=payload.welcome_message,
                custom_proxy_path=payload.custom_proxy_path,
                custom_proxy_method=payload.custom_proxy_method,
                forward_plain_text=payload.forward_plain_text,
                public_base_url=public_url,
            )
            bot.is_active = payload.is_active
            record_audit(
                db,
                "admin.telegram_platform_bot_saved",
                admin.email,
                admin.id,
                "telegram_bot",
                bot.id,
                {"bot_username": bot.bot_username, "mode": bot.connection_mode},
                get_client_ip(request),
            )
            db.commit()
            return {"message": f"Official Platform Bot @{bot.bot_username} connected.", "platform_bot": serialize_telegram_bot(db, bot), "sync": sync_res}
        except TelegramApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a BotFather token to connect the Official Platform Telegram Bot.",
        )

    if payload.bot_name and payload.bot_name.strip():
        existing.bot_name = payload.bot_name.strip()
    existing.is_active = payload.is_active
    existing.welcome_message = payload.welcome_message.strip()
    existing.custom_proxy_path = normalize_proxy_path(payload.custom_proxy_path)
    existing.custom_proxy_method = payload.custom_proxy_method
    existing.forward_plain_text = payload.forward_plain_text
    if payload.connection_mode:
        existing.connection_mode = payload.connection_mode
    db.commit()
    try:
        sync_res = await sync_bot_with_telegram(db, existing, public_base_url=public_url)
    except TelegramApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {"message": "Official Platform Bot updated.", "platform_bot": serialize_telegram_bot(db, existing), "sync": sync_res}


@router.post("/api/admin/telegram/platform-bot/sync")
async def admin_sync_platform_bot(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    if not pbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform bot not configured.")
    try:
        sync_res = await sync_bot_with_telegram(db, pbot, public_base_url=_resolve_request_public_url(request))
    except TelegramApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"message": "Platform bot synced with Telegram.", "platform_bot": serialize_telegram_bot(db, pbot), "sync": sync_res}


@router.post("/api/admin/telegram/platform-bot/poll")
async def admin_poll_platform_bot(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    if not pbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform bot not configured.")
    try:
        count = await poll_bot_updates_once(db, pbot, timeout_sec=0)
    except TelegramApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"message": f"Processed {count} platform bot update(s).", "processed_count": count}


@router.post("/api/admin/telegram/platform-bot/broadcast")
async def admin_broadcast_telegram(
    payload: AdminTelegramBroadcastRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    if not pbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform bot not configured.")

    query = select(TelegramUserLink).where(TelegramUserLink.bot_id == pbot.id, TelegramUserLink.is_active.is_(True))
    if payload.test_only:
        query = query.where(TelegramUserLink.user_id == admin.id)
    targets = db.scalars(query).all()
    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No linked Telegram users found for broadcast." if not payload.test_only else "Link your admin Telegram account first for test broadcast.",
        )

    sent_count = 0
    for target in targets:
        if await _deliver_bot_message(db, pbot, target.chat_id, payload.message, category="admin:broadcast"):
            sent_count += 1

    record_audit(
        db,
        "admin.telegram_broadcast",
        admin.email,
        admin.id,
        "telegram_bot",
        pbot.id,
        {"recipients": len(targets), "sent": sent_count, "test_only": payload.test_only},
        get_client_ip(request),
    )
    db.commit()
    return {"message": f"Delivered announcement to {sent_count}/{len(targets)} chat(s).", "sent": sent_count, "total": len(targets)}


@router.delete("/api/admin/telegram/platform-bot")
async def admin_disconnect_platform_bot(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    pbot = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
    if not pbot:
        return {"message": "Platform bot was not configured."}
    bot_id = pbot.id
    uname = pbot.bot_username
    await disconnect_telegram_bot(db, pbot)
    record_audit(
        db,
        "admin.telegram_platform_bot_removed",
        admin.email,
        admin.id,
        "telegram_bot",
        bot_id,
        {"bot_username": uname},
        get_client_ip(request),
    )
    db.commit()
    return {"message": f"Platform bot @{uname} disconnected."}
