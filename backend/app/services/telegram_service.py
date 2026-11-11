"""Telegram Bot integration engine: BotFather onboarding, webhooks, polling, commands, menus, and alerts."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import html
import json
import secrets
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import HTTPException
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    create_signed_state,
    decrypt_secret,
    encrypt_secret,
    mask_secret,
    utc_now,
    verify_signed_state,
)
from app.models.api_key import ApiKey
from app.models.gateway import ApiRequestLog, MasterGatewayConfig
from app.models.payment import PaymentOrder
from app.models.plan import Subscription, SubscriptionPlan
from app.models.telegram import TelegramBot, TelegramBotEvent, TelegramUserLink
from app.models.user import User
from app.services.branding_service import get_effective_branding
from app.services.gateway_service import execute_gateway_core
from app.services.key_service import (
    create_additional_key,
    get_active_subscription,
    list_user_keys,
    provision_subscription_and_key,
    regenerate_user_key,
    reveal_user_key,
    revoke_user_key,
)
from app.services.razorpay_service import format_inr

TELEGRAM_TEXT_LIMIT = 3900

DEFAULT_BOT_COMMANDS = [
    {"command": "start", "description": "Open menu & connect account"},
    {"command": "menu", "description": "Interactive command buttons"},
    {"command": "quota", "description": "Daily & monthly quota usage"},
    {"command": "keys", "description": "View, create & rotate API keys"},
    {"command": "status", "description": "Test GET /v1/status gateway"},
    {"command": "plans", "description": "Compare API plans & limits"},
    {"command": "logs", "description": "Recent API gateway requests"},
    {"command": "uuid", "description": "Generate UUIDv4 batch (/uuid 3)"},
    {"command": "hash", "description": "Hash text (/hash sha256 hello)"},
    {"command": "ip", "description": "Inspect IP (/ip 8.8.8.8)"},
    {"command": "dns", "description": "DNS lookup (/dns example.com)"},
    {"command": "time", "description": "Sync atomic UTC time"},
    {"command": "json", "description": "Validate JSON (/json {\"ok\":true})"},
    {"command": "call", "description": "Call any /v1/* endpoint"},
    {"command": "ask", "description": "Query custom proxy endpoint"},
    {"command": "alerts", "description": "Manage real-time alerts"},
    {"command": "profile", "description": "Account & plan details"},
    {"command": "help", "description": "Show all commands"},
]


class TelegramApiError(RuntimeError):
    """Raised when the Telegram Bot API rejects a request or is unreachable."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _e(val: Any) -> str:
    return html.escape(str(val if val is not None else ""))


def _progress_bar(used: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "░" * width + " 0%"
    ratio = max(0.0, min(1.0, used / total))
    filled = round(ratio * width)
    pct = round(ratio * 100)
    return f"{'█' * filled}{'░' * (width - filled)} {pct}%"


def _chunk_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _build_main_menu_keyboard(
    *,
    is_privileged: bool,
    frontend_url: str,
    is_platform_bot: bool,
) -> Dict[str, Any]:
    rows: List[List[Dict[str, str]]] = [
        [
            {"text": "⚡ Quick API Tools", "callback_data": "m:tools"},
            {"text": "💎 Plans & Pricing", "callback_data": "m:plans"},
        ]
    ]
    if is_privileged:
        rows.insert(
            0,
            [
                {"text": "📊 Quota & Usage", "callback_data": "m:quota"},
                {"text": "🔑 API Keys", "callback_data": "m:keys"},
            ],
        )
        rows.append(
            [
                {"text": "📜 Recent Logs", "callback_data": "m:logs"},
                {"text": "🔔 Alert Settings", "callback_data": "m:alerts"},
            ]
        )
        rows.append(
            [
                {"text": "👤 Profile", "callback_data": "m:prof"},
                {"text": "❓ Help", "callback_data": "m:help"},
            ]
        )
    else:
        rows.append([{"text": "❓ Commands Help", "callback_data": "m:help"}])

    if frontend_url and frontend_url.startswith("http"):
        target = f"{frontend_url.rstrip('/')}/#dashboard" if is_privileged or is_platform_bot else frontend_url.rstrip("/")
        rows.append([{"text": "🌐 Open Beta Web Portal", "url": target}])

    return {"inline_keyboard": rows}


def _resolve_public_url(explicit_public_url: str = "", cfg: Optional[Settings] = None) -> str:
    settings = cfg or get_settings()
    candidate = (explicit_public_url or settings.APP_PUBLIC_URL or "").strip().rstrip("/")
    return candidate


def _is_public_https_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    if not lowered.startswith("https://"):
        return False
    host = lowered[len("https://") :].split("/")[0].split(":")[0]
    return host not in ("", "localhost", "127.0.0.1", "0.0.0.0")


def _resolve_bot_token(bot: TelegramBot, cfg: Optional[Settings] = None) -> str:
    settings = cfg or get_settings()
    token = decrypt_secret(bot.encrypted_token, settings)
    if not token:
        raise TelegramApiError("Failed to decrypt stored Telegram bot token.", status_code=500)
    return token


async def telegram_api_call(
    bot_token: str,
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    timeout_sec: float = 15.0,
    settings: Optional[Settings] = None,
) -> Any:
    cfg = settings or get_settings()
    url = f"{cfg.TELEGRAM_API_BASE_URL.rstrip('/')}/bot{bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(url, json=payload or {})
    except httpx.RequestError as exc:
        raise TelegramApiError(f"Telegram API connection error: {type(exc).__name__}", status_code=502) from exc

    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "description": resp.text[:200]}

    if resp.status_code >= 400 or not data.get("ok"):
        desc = data.get("description") or f"Telegram API HTTP {resp.status_code}"
        code = 400 if resp.status_code in (400, 401, 403, 404) else 502
        raise TelegramApiError(desc, status_code=code)

    return data.get("result")


class BotResponder:
    """Unified output transport supporting live Telegram Bot API and in-browser simulation."""

    def __init__(
        self,
        *,
        bot_token: str = "",
        simulate: bool = False,
        settings: Optional[Settings] = None,
    ) -> None:
        self.bot_token = bot_token
        self.simulate = simulate
        self.settings = settings or get_settings()
        self.captured: List[Dict[str, Any]] = []

    async def send(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: Optional[str] = "HTML",
    ) -> None:
        chunks = _chunk_text(text)
        for idx, chunk in enumerate(chunks):
            markup = reply_markup if idx == len(chunks) - 1 else None
            if self.simulate:
                self.captured.append(
                    {"action": "sendMessage", "chat_id": chat_id, "text": chunk, "reply_markup": markup}
                )
                continue

            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if markup:
                payload["reply_markup"] = markup
            try:
                await telegram_api_call(self.bot_token, "sendMessage", payload, settings=self.settings)
            except TelegramApiError:
                if parse_mode:
                    payload.pop("parse_mode", None)
                    await telegram_api_call(self.bot_token, "sendMessage", payload, settings=self.settings)
                else:
                    raise

    async def edit_or_send(
        self,
        chat_id: str,
        message_id: Optional[int],
        text: str,
        *,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> None:
        if len(text) > TELEGRAM_TEXT_LIMIT or not message_id:
            await self.send(chat_id, text, reply_markup=reply_markup)
            return

        if self.simulate:
            self.captured.append(
                {
                    "action": "editMessageText",
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "reply_markup": reply_markup,
                }
            )
            return

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            await telegram_api_call(self.bot_token, "editMessageText", payload, settings=self.settings)
        except TelegramApiError as exc:
            if "message is not modified" in str(exc).lower():
                return
            await self.send(chat_id, text, reply_markup=reply_markup)

    async def answer_callback(self, callback_id: str, text: str = "", show_alert: bool = False) -> None:
        if not callback_id:
            return
        if self.simulate:
            if text:
                self.captured.append({"action": "answerCallbackQuery", "text": text, "show_alert": show_alert})
            return
        try:
            await telegram_api_call(
                self.bot_token,
                "answerCallbackQuery",
                {"callback_query_id": callback_id, "text": text[:190], "show_alert": show_alert},
                settings=self.settings,
            )
        except TelegramApiError:
            pass


def _record_tg_event(
    db: Session,
    *,
    bot_id: str,
    tg_user_id: str = "",
    tg_username: str = "",
    chat_id: str = "",
    event_type: str = "command",
    command_or_action: str = "",
    status_val: str = "ok",
    latency_ms: float = 0.0,
    detail: str = "",
) -> None:
    db.add(
        TelegramBotEvent(
            bot_id=bot_id,
            telegram_user_id=str(tg_user_id)[:64],
            telegram_username=str(tg_username)[:128],
            chat_id=str(chat_id)[:64],
            event_type=event_type[:24],
            command_or_action=command_or_action[:120],
            status=status_val[:20],
            latency_ms=round(latency_ms, 2),
            detail=detail[:500],
        )
    )


def normalize_proxy_path(path: str) -> str:
    cleaned = (path or "").strip()
    if not cleaned:
        return ""
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if cleaned == "/v1":
        return "/v1/status"
    if not cleaned.startswith("/v1/"):
        return f"/v1/{cleaned.lstrip('/')}"
    return cleaned


_normalize_proxy_path = normalize_proxy_path


async def sync_bot_with_telegram(
    db: Session,
    bot: TelegramBot,
    *,
    public_base_url: str = "",
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Configure Telegram webhook or polling + bot command menu."""
    cfg = settings or get_settings()
    token = _resolve_bot_token(bot, cfg)
    resolved_public = _resolve_public_url(public_base_url, cfg)
    webhook_url = f"{resolved_public}/api/telegram/webhook/{bot.id}" if resolved_public else ""

    webhook_info: Dict[str, Any] = {}
    commands_synced = False

    if bot.connection_mode == "webhook":
        if not cfg.TELEGRAM_WEBHOOK_ENABLED:
            raise TelegramApiError("Webhooks are disabled by server configuration (TELEGRAM_WEBHOOK_ENABLED=false).", 400)
        if not _is_public_https_url(webhook_url):
            raise TelegramApiError(
                f"Webhook mode requires a public HTTPS URL (current: {resolved_public or 'none'}). Use Polling mode for local HTTP testing.",
                400,
            )
        await telegram_api_call(
            token,
            "setWebhook",
            {
                "url": webhook_url,
                "secret_token": bot.webhook_secret,
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": False,
            },
            settings=cfg,
        )
        bot.webhook_url = webhook_url
        bot.webhook_active = True
        bot.last_error = ""
        try:
            webhook_info = await telegram_api_call(token, "getWebhookInfo", {}, settings=cfg) or {}
        except TelegramApiError:
            webhook_info = {"url": webhook_url}
    else:
        await telegram_api_call(token, "deleteWebhook", {"drop_pending_updates": False}, settings=cfg)
        bot.webhook_url = ""
        bot.webhook_active = False
        bot.last_error = ""

    commands_payload = list(DEFAULT_BOT_COMMANDS)
    if bot.is_platform_bot:
        commands_payload.extend(
            [
                {"command": "link", "description": "Link your website account (/link <code>)"},
                {"command": "unlink", "description": "Disconnect Telegram from account"},
                {"command": "adminstats", "description": "Admin platform overview"},
            ]
        )
    try:
        await telegram_api_call(token, "setMyCommands", {"commands": commands_payload}, settings=cfg)
        commands_synced = True
    except TelegramApiError as exc:
        bot.last_error = f"Commands sync warning: {exc}"

    bot.updated_at = utc_now()
    db.commit()
    db.refresh(bot)
    return {
        "connection_mode": bot.connection_mode,
        "webhook_active": bot.webhook_active,
        "webhook_url": bot.webhook_url,
        "commands_synced": commands_synced,
        "webhook_info": webhook_info,
    }


async def connect_telegram_bot(
    db: Session,
    *,
    bot_token: str,
    owner_user: User,
    is_platform_bot: bool = False,
    bot_name: Optional[str] = None,
    api_key_id: Optional[str] = None,
    access_mode: str = "owner_only",
    connection_mode: Optional[str] = None,
    welcome_message: str = "",
    custom_proxy_path: str = "",
    custom_proxy_method: str = "POST",
    forward_plain_text: bool = False,
    notify_owner_alerts: bool = True,
    public_base_url: str = "",
    settings: Optional[Settings] = None,
) -> Tuple[TelegramBot, Dict[str, Any]]:
    cfg = settings or get_settings()
    cleaned_token = (bot_token or "").strip()
    if ":" not in cleaned_token or len(cleaned_token) < 20:
        raise TelegramApiError("Invalid Telegram Bot Token format. Expected token from @BotFather.", 400)

    me = await telegram_api_call(cleaned_token, "getMe", {}, settings=cfg)
    if not me or not me.get("id") or not me.get("username"):
        raise TelegramApiError("Telegram getMe did not return valid bot identity.", 502)

    tg_id = str(me["id"])
    tg_username = str(me["username"]).lstrip("@")
    resolved_name = (bot_name or "").strip() or str(me.get("first_name") or tg_username)

    bound_key_id: Optional[str] = None
    if api_key_id and not is_platform_bot:
        key_row = db.get(ApiKey, api_key_id)
        if not key_row or key_row.user_id != owner_user.id:
            raise TelegramApiError("Selected API key does not belong to your account.", 404)
        if key_row.status != "active":
            raise TelegramApiError("Selected API key is revoked. Choose an active key.", 400)
        bound_key_id = key_row.id
    elif not is_platform_bot:
        active_key = db.scalar(
            select(ApiKey)
            .where(ApiKey.user_id == owner_user.id, ApiKey.status == "active")
            .order_by(ApiKey.created_at.desc())
            .limit(1)
        )
        bound_key_id = active_key.id if active_key else None

    resolved_public = _resolve_public_url(public_base_url, cfg)
    eff_mode = connection_mode or ("webhook" if (cfg.TELEGRAM_WEBHOOK_ENABLED and _is_public_https_url(resolved_public)) else "polling")

    if is_platform_bot:
        existing = db.scalar(select(TelegramBot).where(TelegramBot.is_platform_bot.is_(True)).limit(1))
        eff_access = "linked_users"
    else:
        conflict = db.scalar(
            select(TelegramBot).where(
                TelegramBot.bot_tg_id == tg_id,
                TelegramBot.is_platform_bot.is_(False),
                TelegramBot.owner_user_id != owner_user.id,
            )
        )
        if conflict:
            raise TelegramApiError("This Telegram bot is already connected to another developer account.", 409)
        existing = db.scalar(
            select(TelegramBot).where(
                TelegramBot.bot_tg_id == tg_id,
                TelegramBot.owner_user_id == owner_user.id,
                TelegramBot.is_platform_bot.is_(False),
            )
        )
        eff_access = access_mode if access_mode in ("owner_only", "public_gateway") else "owner_only"

    if existing:
        bot = existing
        bot.owner_user_id = owner_user.id
        bot.bot_tg_id = tg_id
        bot.bot_username = tg_username
        bot.bot_name = resolved_name
        bot.encrypted_token = encrypt_secret(cleaned_token, cfg)
        bot.token_fingerprint = mask_secret(cleaned_token, 6, 4)
        bot.api_key_id = bound_key_id
        bot.connection_mode = eff_mode
        bot.access_mode = eff_access
        bot.is_active = True
        bot.welcome_message = welcome_message.strip()
        bot.custom_proxy_path = _normalize_proxy_path(custom_proxy_path)
        bot.custom_proxy_method = custom_proxy_method.upper()
        bot.forward_plain_text = forward_plain_text
        bot.notify_owner_alerts = notify_owner_alerts
        bot.last_error = ""
    else:
        bot = TelegramBot(
            owner_user_id=owner_user.id,
            api_key_id=bound_key_id,
            is_platform_bot=is_platform_bot,
            bot_tg_id=tg_id,
            bot_username=tg_username,
            bot_name=resolved_name,
            encrypted_token=encrypt_secret(cleaned_token, cfg),
            token_fingerprint=mask_secret(cleaned_token, 6, 4),
            webhook_secret=secrets.token_urlsafe(32),
            connection_mode=eff_mode,
            access_mode=eff_access,
            is_active=True,
            welcome_message=welcome_message.strip(),
            custom_proxy_path=_normalize_proxy_path(custom_proxy_path),
            custom_proxy_method=custom_proxy_method.upper(),
            forward_plain_text=forward_plain_text,
            notify_owner_alerts=notify_owner_alerts,
            pairing_code=secrets.token_urlsafe(12),
        )
        db.add(bot)
        db.flush()

    sync_res = await sync_bot_with_telegram(db, bot, public_base_url=resolved_public, settings=cfg)
    return bot, sync_res


def create_user_link_token(user: User, bot: TelegramBot, settings: Optional[Settings] = None) -> Tuple[str, str]:
    token = create_signed_state({"uid": user.id, "bid": bot.id}, salt="tg-user-link", settings=settings)
    deep_link = f"https://t.me/{bot.bot_username}?start=link_{token}"
    return token, deep_link


def serialize_telegram_bot(db: Session, bot: TelegramBot, cfg: Optional[Settings] = None) -> Dict[str, Any]:
    key_summary = None
    if bot.api_key_id:
        key_row = db.get(ApiKey, bot.api_key_id)
        if key_row:
            key_summary = {
                "id": key_row.id,
                "name": key_row.name,
                "masked_key": f"{key_row.key_prefix}••••••••••••{key_row.key_last4}",
                "status": key_row.status,
            }
    return {
        "id": bot.id,
        "is_platform_bot": bot.is_platform_bot,
        "bot_tg_id": bot.bot_tg_id,
        "bot_username": bot.bot_username,
        "bot_url": f"https://t.me/{bot.bot_username}",
        "bot_name": bot.bot_name,
        "token_fingerprint": bot.token_fingerprint,
        "connection_mode": bot.connection_mode,
        "access_mode": bot.access_mode,
        "is_active": bot.is_active,
        "welcome_message": bot.welcome_message,
        "custom_proxy_path": bot.custom_proxy_path,
        "custom_proxy_method": bot.custom_proxy_method,
        "forward_plain_text": bot.forward_plain_text,
        "notify_owner_alerts": bot.notify_owner_alerts,
        "api_key_id": bot.api_key_id,
        "bound_key": key_summary,
        "is_paired": bool(bot.paired_telegram_user_id),
        "paired_telegram_user_id": bot.paired_telegram_user_id,
        "paired_telegram_username": bot.paired_telegram_username,
        "paired_at": bot.paired_at,
        "pairing_code": bot.pairing_code,
        "pair_deep_link": f"https://t.me/{bot.bot_username}?start=pair_{bot.pairing_code}",
        "webhook_url": bot.webhook_url,
        "webhook_active": bot.webhook_active,
        "last_error": bot.last_error,
        "total_messages_handled": bot.total_messages_handled,
        "last_event_at": bot.last_event_at,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
    }


def _resolve_active_user_key(db: Session, bot: TelegramBot, user: Optional[User]) -> Tuple[Optional[ApiKey], Optional[str], Optional[str]]:
    """Return (ApiKey, plaintext_secret, error_message)."""
    if bot.api_key_id:
        bound = db.get(ApiKey, bot.api_key_id)
        if bound and bound.status == "active":
            raw = decrypt_secret(bound.encrypted_key)
            if raw:
                return bound, raw, None

    if user:
        candidate = db.scalar(
            select(ApiKey)
            .where(ApiKey.user_id == user.id, ApiKey.status == "active")
            .order_by(ApiKey.created_at.desc())
            .limit(1)
        )
        if candidate:
            raw = decrypt_secret(candidate.encrypted_key)
            if raw:
                return candidate, raw, None

    return None, None, "No active API key is bound yet. Use /keys to create a Free Sandbox key or select an active key on the web dashboard."


async def _run_gateway_for_bot(
    db: Session,
    *,
    bot: TelegramBot,
    actor_user: Optional[User],
    method: str,
    path: str,
    query_dict: Optional[Dict[str, str]] = None,
    body_obj: Optional[Any] = None,
) -> Tuple[int, Dict[str, str], str]:
    target_user = actor_user or (db.get(User, bot.owner_user_id) if bot.owner_user_id else None)
    key_row, raw_key, key_err = _resolve_active_user_key(db, bot, target_user)
    if not raw_key:
        return 400, {}, json.dumps({"error": "NO_ACTIVE_API_KEY", "message": key_err})

    normalized = _normalize_proxy_path(path)
    subpath = normalized[len("/v1/") :] if normalized.startswith("/v1/") else normalized.lstrip("/")
    qmap = {k: str(v) for k, v in (query_dict or {}).items() if v is not None}
    qstr = urlencode(qmap)
    body_bytes = b""
    headers = {"X-API-Key": raw_key, "X-Beta-Client": "telegram-bot"}
    if body_obj is not None and method.upper() in ("POST", "PUT", "PATCH"):
        if isinstance(body_obj, (bytes, bytearray)):
            body_bytes = bytes(body_obj)
        elif isinstance(body_obj, str):
            body_bytes = body_obj.encode("utf-8")
        else:
            body_bytes = json.dumps(body_obj).encode("utf-8")
        headers["Content-Type"] = "application/json"

    status_code, resp_headers, content, _ = await execute_gateway_core(
        db,
        method=method.upper(),
        subpath=subpath,
        query_dict=qmap,
        query_str=qstr,
        body_bytes=body_bytes,
        req_headers=headers,
        client_ip="telegram-bot",
        raw_api_key=raw_key,
    )
    text_out = content.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text_out)
        pretty = json.dumps(parsed, indent=2)
    except Exception:
        pretty = text_out
    return status_code, resp_headers, pretty


def _format_quota_card(db: Session, user: User, brand: Dict[str, str]) -> str:
    sub = get_active_subscription(db, user.id)
    if not sub:
        return (
            f"<b>📊 Quota &amp; Usage — {_e(brand['app_name'])}</b>\n\n"
            f"Account: <code>{_e(user.email)}</code>\n"
            "Status: <b>No Active Plan</b>\n\n"
            "Tap <b>💎 Plans &amp; Pricing</b> or use <b>🔑 API Keys → Create Key</b> to activate the Free Sandbox tier."
        )

    plan = db.get(SubscriptionPlan, sub.plan_id)
    today_str = utc_now().strftime("%Y-%m-%d")
    daily_used = sub.daily_requests_used if sub.daily_usage_date == today_str else 0
    total_calls = db.scalar(select(func.count(ApiRequestLog.id)).where(ApiRequestLog.user_id == user.id)) or 0
    ok_calls = (
        db.scalar(
            select(func.count(ApiRequestLog.id)).where(
                ApiRequestLog.user_id == user.id,
                ApiRequestLog.status_code >= 200,
                ApiRequestLog.status_code < 400,
            )
        )
        or 0
    )
    avg_lat = db.scalar(select(func.avg(ApiRequestLog.latency_ms)).where(ApiRequestLog.user_id == user.id)) or 0.0
    rate = round((ok_calls / total_calls) * 100, 1) if total_calls else 100.0
    days_left = max(0, (sub.expires_at.replace(tzinfo=None) - utc_now().replace(tzinfo=None)).days)

    return (
        f"<b>📊 Quota &amp; Live Telemetry</b>\n"
        f"Plan: <b>{_e(plan.name if plan else 'Unknown')}</b> ({days_left}d left)\n\n"
        f"<b>Daily Limit (UTC)</b>\n"
        f"<code>{_progress_bar(daily_used, plan.daily_request_limit if plan else 0)}</code>\n"
        f"Used: <b>{daily_used:,}</b> / {plan.daily_request_limit:,}\n\n"
        f"<b>Cycle Limit</b>\n"
        f"<code>{_progress_bar(sub.cycle_requests_used, plan.monthly_request_limit if plan else 0)}</code>\n"
        f"Used: <b>{sub.cycle_requests_used:,}</b> / {plan.monthly_request_limit:,}\n\n"
        f"⚡ Rate Cap: <b>{plan.rate_limit_per_minute if plan else 0} req/min</b>\n"
        f"✅ Health: <b>{rate}%</b> ({total_calls:,} calls · {round(float(avg_lat), 1)} ms avg)"
    )


def _format_keys_card(
    db: Session,
    user: User,
    bot: TelegramBot,
    *,
    notice: str = "",
) -> Tuple[str, Dict[str, Any]]:
    sub = get_active_subscription(db, user.id)
    plan = db.get(SubscriptionPlan, sub.plan_id) if sub else None
    keys = list_user_keys(db, user.id)
    active_keys = [k for k in keys if k.status == "active"]

    lines = ["<b>🔑 API Keys Vault</b>"]
    if notice:
        lines.append(f"\n<i>{_e(notice)}</i>")
    if plan:
        lines.append(f"Plan: <b>{_e(plan.name)}</b> ({len(active_keys)}/{plan.max_api_keys} active keys)")
    else:
        lines.append("Plan: <b>None</b> — create a key below to activate Free Sandbox if eligible.")

    kb_rows: List[List[Dict[str, str]]] = []
    if not keys:
        lines.append("\nNo API keys issued yet.")
    else:
        lines.append("")
        for k in keys[:6]:
            dot = "🟢" if k.status == "active" else "🔴"
            selected_tag = " ⭐" if bot.api_key_id == k.id else ""
            lines.append(
                f"{dot} <b>{_e(k.name)}</b>{_e(selected_tag)}\n"
                f"   <code>{_e(k.key_prefix)}••••{_e(k.key_last4)}</code> · {k.total_requests:,} calls"
            )
            if k.status == "active":
                row = [
                    {"text": f"👁 Reveal {k.key_last4}", "callback_data": f"k:rev:{k.id}"},
                    {"text": f"🔄 Rotate", "callback_data": f"k:rga:{k.id}"},
                    {"text": f"🗑 Revoke", "callback_data": f"k:rva:{k.id}"},
                ]
                if not bot.is_platform_bot and bot.api_key_id != k.id:
                    row.insert(0, {"text": "⭐ Bind", "callback_data": f"k:use:{k.id}"})
                kb_rows.append(row)

    actions_row: List[Dict[str, str]] = []
    if not sub or (plan and len(active_keys) < plan.max_api_keys):
        actions_row.append({"text": "➕ Create New Key", "callback_data": "k:new"})
    actions_row.append({"text": "« Menu", "callback_data": "m:home"})
    kb_rows.append(actions_row)
    return "\n".join(lines), {"inline_keyboard": kb_rows}


def _format_alerts_card(
    bot: TelegramBot,
    link: Optional[TelegramUserLink],
) -> Tuple[str, Dict[str, Any]]:
    if bot.is_platform_bot and link:
        text = (
            "<b>🔔 Real-Time Telegram Alerts</b>\n\n"
            f"• Quota Warnings (80% / 100%): <b>{'ON ✅' if link.notify_quota_alerts else 'OFF ⏸'}</b>\n"
            f"• Key Security Events: <b>{'ON ✅' if link.notify_security_alerts else 'OFF ⏸'}</b>\n"
            f"• Razorpay Billing Alerts: <b>{'ON ✅' if link.notify_payment_alerts else 'OFF ⏸'}</b>\n"
            f"• Gateway 5xx Errors: <b>{'ON ✅' if link.notify_gateway_errors else 'OFF ⏸'}</b>"
        )
        kb = {
            "inline_keyboard": [
                [
                    {"text": f"Quota: {'ON' if link.notify_quota_alerts else 'OFF'}", "callback_data": "a:tog:q"},
                    {"text": f"Security: {'ON' if link.notify_security_alerts else 'OFF'}", "callback_data": "a:tog:s"},
                ],
                [
                    {"text": f"Billing: {'ON' if link.notify_payment_alerts else 'OFF'}", "callback_data": "a:tog:p"},
                    {"text": f"5xx Errors: {'ON' if link.notify_gateway_errors else 'OFF'}", "callback_data": "a:tog:e"},
                ],
                [
                    {"text": "🔔 Send Test Alert", "callback_data": "a:test"},
                    {"text": "« Menu", "callback_data": "m:home"},
                ],
            ]
        }
        return text, kb

    text = (
        "<b>🔔 Bot Owner Notifications</b>\n\n"
        f"Automatic alerts on key events, quota thresholds, payments &amp; 5xx errors: "
        f"<b>{'ON ✅' if bot.notify_owner_alerts else 'OFF ⏸'}</b>\n"
        f"Paired Owner: <b>{'Yes (' + _e(bot.paired_telegram_username or bot.paired_telegram_user_id) + ')' if bot.paired_telegram_user_id else 'Not paired'}</b>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": f"Owner Alerts: {'ON ✅' if bot.notify_owner_alerts else 'OFF ⏸'}", "callback_data": "a:tog:o"},
                {"text": "🔔 Send Test Alert", "callback_data": "a:test"},
            ],
            [{"text": "« Menu", "callback_data": "m:home"}],
        ]
    }
    return text, kb


async def _reply_with_gateway_call(
    db: Session,
    responder: BotResponder,
    bot: TelegramBot,
    actor_user: Optional[User],
    chat_id: str,
    *,
    method: str,
    path: str,
    query_dict: Optional[Dict[str, str]] = None,
    body_obj: Optional[Any] = None,
    edit_message_id: Optional[int] = None,
) -> Tuple[str, str]:
    status_code, resp_headers, pretty_body = await _run_gateway_for_bot(
        db,
        bot=bot,
        actor_user=actor_user,
        method=method,
        path=path,
        query_dict=query_dict,
        body_obj=body_obj,
    )
    badge = "✅" if status_code < 400 else "⚠️" if status_code == 429 else "❌"
    mode = resp_headers.get("X-Gateway-Mode") or resp_headers.get("x-gateway-mode") or "gateway"
    daily_rem = resp_headers.get("X-Quota-Daily-Remaining") or resp_headers.get("x-quota-daily-remaining")
    quota_line = f"\nRemaining Today: <b>{_e(daily_rem)}</b>" if daily_rem is not None else ""
    snippet = pretty_body[:2800] + ("\n... (truncated)" if len(pretty_body) > 2800 else "")
    msg = (
        f"{badge} <b>{_e(method.upper())} {_e(path)}</b> → HTTP <b>{status_code}</b> (<code>{_e(mode)}</code>)"
        f"{quota_line}\n\n"
        f"<pre>{_e(snippet)}</pre>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": "🔄 Re-run Tools", "callback_data": "m:tools"},
                {"text": "« Menu", "callback_data": "m:home"},
            ]
        ]
    }
    if edit_message_id:
        await responder.edit_or_send(chat_id, edit_message_id, msg, reply_markup=kb)
    else:
        await responder.send(chat_id, msg, reply_markup=kb)
    return ("ok" if status_code < 400 else "error"), f"HTTP {status_code} {path}"


def _format_help_text(bot: TelegramBot, brand: Dict[str, str], is_privileged: bool) -> str:
    lines = [
        f"<b>❓ {_e(brand['app_name'])} Bot Commands</b>",
        "",
        "<b>Gateway Utility &amp; API Commands:</b>",
        "• <code>/status</code> — Gateway health &amp; plan telemetry",
        "• <code>/uuid [count]</code> — Generate UUIDv4 identifiers",
        "• <code>/hash [algo] &lt;text&gt;</code> — SHA-256 / SHA-512 / BLAKE2b digest",
        "• <code>/ip [addr]</code> — IPv4 / IPv6 inspector",
        "• <code>/dns &lt;domain&gt;</code> — Live DNS A/AAAA lookup",
        "• <code>/time</code> — Atomic UTC &amp; Unix timestamps",
        "• <code>/json &lt;payload&gt;</code> — Validate &amp; size JSON payload",
        "• <code>/call GET /v1/status</code> — Execute any /v1/* endpoint",
        "• <code>/ask &lt;query&gt;</code> — Call configured custom upstream route",
        "• <code>/plans</code> — View all plans &amp; quotas",
    ]
    if is_privileged:
        lines.extend(
            [
                "",
                "<b>Account &amp; Key Management:</b>",
                "• <code>/menu</code> — Interactive inline dashboard",
                "• <code>/quota</code> — Daily &amp; monthly quota meters",
                "• <code>/keys</code> — Manage, create, reveal &amp; rotate API keys",
                "• <code>/logs</code> — Latest gateway request telemetry",
                "• <code>/alerts</code> — Toggle push alerts",
                "• <code>/profile</code> — Account &amp; subscription status",
            ]
        )
    if bot.is_platform_bot:
        lines.extend(
            [
                "",
                "<b>Platform Linking &amp; Admin:</b>",
                "• <code>/link &lt;code&gt;</code> — Link Telegram to your Beta account",
                "• <code>/unlink</code> — Unlink your Telegram chat",
                "• <code>/adminstats</code> — Admin-only live platform KPIs",
            ]
        )
    if bot.custom_proxy_path:
        lines.append(
            f"\n🔗 Custom Route: <code>{_e(bot.custom_proxy_method)} {_e(bot.custom_proxy_path)}</code>"
            + (" (plain messages forwarded)" if bot.forward_plain_text else "")
        )
    return "\n".join(lines)


def _format_plans_card(db: Session, brand: Dict[str, str], frontend_url: str) -> Tuple[str, Dict[str, Any]]:
    plans = db.scalars(
        select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.sort_order.asc())
    ).all()
    lines = [f"<b>💎 {_e(brand['app_name'])} Plans &amp; Quotas</b>\n"]
    for p in plans:
        price = "Free" if p.price_paise == 0 else format_inr(p.price_paise)
        badge = f" [{_e(p.badge)}]" if p.badge else ""
        lines.append(
            f"<b>{_e(p.name)}</b>{_e(badge)} — <b>{_e(price)}</b> / {p.billing_cycle_days}d\n"
            f"   • {p.daily_request_limit:,}/day · {p.monthly_request_limit:,}/cycle · {p.rate_limit_per_minute}/min · {p.max_api_keys} keys"
        )
    rows: List[List[Dict[str, str]]] = [[{"text": "« Menu", "callback_data": "m:home"}]]
    if frontend_url and frontend_url.startswith("http"):
        rows[0].insert(0, {"text": "🚀 Upgrade on Website", "url": f"{frontend_url.rstrip('/')}/#dashboard"})
    return "\n".join(lines), {"inline_keyboard": rows}


def _create_or_activate_key_from_bot(db: Session, user: User) -> str:
    sub = get_active_subscription(db, user.id)
    if sub:
        try:
            key = create_additional_key(db, user, f"Telegram Key {utc_now().strftime('%m%d-%H%M')}")
        except HTTPException as exc:
            return f"⚠️ {_e(exc.detail)}"
        raw = decrypt_secret(key.encrypted_key) or ""
        return (
            f"✅ <b>New API Key Created!</b>\n\n"
            f"Name: <b>{_e(key.name)}</b>\n"
            f"Key (tap to reveal):\n<tg-spoiler><code>{_e(raw)}</code></tg-spoiler>"
        )

    free_plan = db.scalar(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active.is_(True), SubscriptionPlan.price_paise == 0)
        .limit(1)
    )
    if not free_plan:
        return "⚠️ No active subscription. Visit the web dashboard to purchase a plan first."

    prior_free = db.scalar(
        select(Subscription.id)
        .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .where(Subscription.user_id == user.id, SubscriptionPlan.price_paise == 0)
        .limit(1)
    )
    if prior_free:
        return "⚠️ Free trial already used and subscription expired. Upgrade via Razorpay on the website."

    _, api_key = provision_subscription_and_key(db, user, free_plan, action="new", key_name=f"{free_plan.name} Key")
    db.commit()
    raw = decrypt_secret(api_key.encrypted_key) or ""
    return (
        f"🎉 <b>{_e(free_plan.name)} Activated!</b>\n\n"
        f"Your new API key (tap to reveal):\n<tg-spoiler><code>{_e(raw)}</code></tg-spoiler>"
    )


async def process_telegram_update(
    db: Session,
    bot: TelegramBot,
    update: Dict[str, Any],
    *,
    responder: Optional[BotResponder] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Process one incoming Telegram Update (message or callback_query)."""
    started = time.perf_counter()
    cfg = settings or get_settings()
    if responder is None:
        responder = BotResponder(bot_token=_resolve_bot_token(bot, cfg), simulate=False, settings=cfg)

    brand = get_effective_branding(db, cfg)
    frontend_url = cfg.effective_frontend_url

    callback = update.get("callback_query")
    message = update.get("message") or update.get("edited_message")

    if not callback and not message:
        return {"ok": True, "ignored": True}

    is_callback = bool(callback)
    if is_callback:
        from_user = callback.get("from") or {}
        msg_obj = callback.get("message") or {}
        chat_obj = msg_obj.get("chat") or {}
        chat_id = str(chat_obj.get("id") or from_user.get("id") or "")
        message_id = msg_obj.get("message_id")
        raw_input = str(callback.get("data") or "")
        cb_id = str(callback.get("id") or "")
    else:
        from_user = message.get("from") or {}
        chat_obj = message.get("chat") or {}
        chat_id = str(chat_obj.get("id") or "")
        message_id = message.get("message_id")
        raw_input = str(message.get("text") or "").strip()
        cb_id = ""

    tg_uid = str(from_user.get("id") or "")
    tg_username = str(from_user.get("username") or "").lstrip("@")
    tg_first_name = str(from_user.get("first_name") or tg_username or "Developer")

    if not bot.is_active:
        if is_callback:
            await responder.answer_callback(cb_id, "This bot is currently paused by its owner.", show_alert=True)
        elif chat_id:
            await responder.send(chat_id, f"⏸ <b>{_e(bot.bot_name)}</b> is currently paused from the {_e(brand['app_name'])} dashboard.")
        return {"ok": True, "paused": True}

    # Resolve linked user / owner privilege
    actor_user: Optional[User] = None
    user_link: Optional[TelegramUserLink] = None
    is_owner = False

    if bot.is_platform_bot:
        user_link = db.scalar(
            select(TelegramUserLink).where(
                TelegramUserLink.bot_id == bot.id,
                TelegramUserLink.telegram_user_id == tg_uid,
                TelegramUserLink.is_active.is_(True),
            )
        )
        if user_link:
            actor_user = db.get(User, user_link.user_id)
            if actor_user and chat_id and user_link.chat_id != chat_id:
                user_link.chat_id = chat_id
    else:
        owner = db.get(User, bot.owner_user_id) if bot.owner_user_id else None
        is_owner = bool(bot.paired_telegram_user_id and tg_uid == bot.paired_telegram_user_id)
        if is_owner:
            actor_user = owner
            if chat_id and bot.paired_chat_id != chat_id:
                bot.paired_chat_id = chat_id

    is_privileged = bool(actor_user) if bot.is_platform_bot else is_owner
    event_type = "callback" if is_callback else ("command" if raw_input.startswith("/") else "message")
    cmd_label = raw_input[:100]
    ev_status = "ok"
    ev_detail = ""

    try:
        # Handle pairing or platform linking deep links on /start or /link first
        if not is_callback and raw_input.startswith("/start"):
            parts = raw_input.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""

            if not bot.is_platform_bot and arg.startswith("pair_"):
                code = arg[5:].strip()
                if code and secrets.compare_digest(code, bot.pairing_code):
                    bot.paired_telegram_user_id = tg_uid
                    bot.paired_chat_id = chat_id
                    bot.paired_telegram_username = tg_username or tg_first_name
                    bot.paired_at = utc_now()
                    bot.pairing_code = secrets.token_urlsafe(12)  # rotate after pairing
                    actor_user = db.get(User, bot.owner_user_id) if bot.owner_user_id else None
                    is_owner = True
                    is_privileged = True
                    ev_detail = f"Owner paired (@{tg_username or tg_uid})"
                    welcome = bot.welcome_message or (
                        f"🎉 <b>Bot Paired &amp; Active!</b>\n\n"
                        f"<b>@{_e(bot.bot_username)}</b> is now linked to your <b>{_e(brand['app_name'])}</b> account."
                    )
                    await responder.send(
                        chat_id,
                        welcome + "\n\nUse the interactive menu below or type <code>/help</code>.",
                        reply_markup=_build_main_menu_keyboard(
                            is_privileged=True,
                            frontend_url=frontend_url,
                            is_platform_bot=False,
                        ),
                    )
                    bot.total_messages_handled += 1
                    bot.last_event_at = utc_now()
                    _record_tg_event(
                        db,
                        bot_id=bot.id,
                        tg_user_id=tg_uid,
                        tg_username=tg_username,
                        chat_id=chat_id,
                        event_type="command",
                        command_or_action="/start pair",
                        status_val="ok",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        detail=ev_detail,
                    )
                    db.commit()
                    return {"ok": True, "paired": True}

                ev_status = "denied"
                ev_detail = "Invalid pairing code"
                await responder.send(
                    chat_id,
                    "❌ Invalid or expired pairing link. Copy the latest <b>Pair in Telegram</b> link from your Dashboard.",
                )
                bot.total_messages_handled += 1
                bot.last_event_at = utc_now()
                _record_tg_event(
                    db,
                    bot_id=bot.id,
                    tg_user_id=tg_uid,
                    tg_username=tg_username,
                    chat_id=chat_id,
                    event_type="command",
                    command_or_action="/start pair",
                    status_val="denied",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    detail=ev_detail,
                )
                db.commit()
                return {"ok": True, "paired": False}

            if bot.is_platform_bot and arg.startswith("link_"):
                token_str = arg[5:].strip()
                linked_ok, link_msg, linked_user, new_link = _verify_and_bind_platform_link(
                    db, bot, token_str, tg_uid, chat_id, tg_username, tg_first_name
                )
                if linked_ok and linked_user:
                    actor_user = linked_user
                    user_link = new_link
                    is_privileged = True
                    ev_detail = f"Linked user {linked_user.email}"
                    await responder.send(
                        chat_id,
                        link_msg,
                        reply_markup=_build_main_menu_keyboard(
                            is_privileged=True,
                            frontend_url=frontend_url,
                            is_platform_bot=True,
                        ),
                    )
                else:
                    ev_status = "denied"
                    ev_detail = "Expired link token"
                    await responder.send(chat_id, link_msg)
                bot.total_messages_handled += 1
                bot.last_event_at = utc_now()
                _record_tg_event(
                    db,
                    bot_id=bot.id,
                    tg_user_id=tg_uid,
                    tg_username=tg_username,
                    chat_id=chat_id,
                    event_type="command",
                    command_or_action="/start link",
                    status_val=ev_status,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    detail=ev_detail,
                )
                db.commit()
                return {"ok": True, "linked": linked_ok}

        if not is_callback and bot.is_platform_bot and raw_input.startswith("/link"):
            parts = raw_input.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            if not code:
                await responder.send(
                    chat_id,
                    "Usage: <code>/link &lt;code_from_dashboard&gt;</code>\nGenerate your connect link inside <b>Dashboard → Telegram Bot</b>.",
                )
                return {"ok": True}
            if code.startswith("link_"):
                code = code[5:].strip()
            linked_ok, link_msg, linked_user, new_link = _verify_and_bind_platform_link(
                db, bot, code, tg_uid, chat_id, tg_username, tg_first_name
            )
            ev_status = "ok" if linked_ok else "denied"
            ev_detail = link_msg[:120]
            await responder.send(
                chat_id,
                link_msg,
                reply_markup=_build_main_menu_keyboard(
                    is_privileged=linked_ok,
                    frontend_url=frontend_url,
                    is_platform_bot=True,
                ),
            )
            bot.total_messages_handled += 1
            bot.last_event_at = utc_now()
            _record_tg_event(
                db,
                bot_id=bot.id,
                tg_user_id=tg_uid,
                tg_username=tg_username,
                chat_id=chat_id,
                event_type="command",
                command_or_action="/link",
                status_val=ev_status,
                latency_ms=(time.perf_counter() - started) * 1000,
                detail=ev_detail,
            )
            db.commit()
            return {"ok": True, "linked": linked_ok}

        # Access control for custom bots in owner_only mode
        if not bot.is_platform_bot and bot.access_mode == "owner_only" and not is_owner:
            ev_status = "denied"
            ev_detail = "Unauthorized Telegram user in owner_only mode"
            denied_msg = (
                "🔒 <b>Private Bot Access</b>\n\n"
                "This bot is running in <b>Owner Only</b> mode.\n"
                "If you are the bot owner, open <b>Dashboard → Telegram Bot</b> on the website and click <b>Pair in Telegram</b>."
            )
            if is_callback:
                await responder.answer_callback(cb_id, "Owner pairing required.", show_alert=True)
            else:
                await responder.send(chat_id, denied_msg)
            _record_tg_event(
                db,
                bot_id=bot.id,
                tg_user_id=tg_uid,
                tg_username=tg_username,
                chat_id=chat_id,
                event_type=event_type,
                command_or_action=cmd_label,
                status_val="denied",
                latency_ms=(time.perf_counter() - started) * 1000,
                detail=ev_detail,
            )
            db.commit()
            return {"ok": True, "denied": True}

        # Handle Inline Callbacks
        if is_callback:
            ev_status, ev_detail = await _handle_callback(
                db,
                responder=responder,
                bot=bot,
                brand=brand,
                actor_user=actor_user,
                user_link=user_link,
                is_privileged=is_privileged,
                frontend_url=frontend_url,
                chat_id=chat_id,
                message_id=message_id,
                cb_id=cb_id,
                data=raw_input,
            )
        else:
            ev_status, ev_detail = await _handle_text_or_command(
                db,
                responder=responder,
                bot=bot,
                brand=brand,
                actor_user=actor_user,
                user_link=user_link,
                is_privileged=is_privileged,
                frontend_url=frontend_url,
                chat_id=chat_id,
                tg_first_name=tg_first_name,
                raw_input=raw_input,
            )

        bot.total_messages_handled += 1
        bot.last_event_at = utc_now()
        _record_tg_event(
            db,
            bot_id=bot.id,
            tg_user_id=tg_uid,
            tg_username=tg_username,
            chat_id=chat_id,
            event_type=event_type,
            command_or_action=cmd_label,
            status_val=ev_status,
            latency_ms=(time.perf_counter() - started) * 1000,
            detail=ev_detail,
        )
        db.commit()
        return {"ok": True, "status": ev_status, "detail": ev_detail}
    except Exception as exc:
        db.rollback()
        bot_ref = db.get(TelegramBot, bot.id)
        if bot_ref:
            bot_ref.last_error = f"{type(exc).__name__}: {exc}"[:500]
            _record_tg_event(
                db,
                bot_id=bot.id,
                tg_user_id=tg_uid,
                tg_username=tg_username,
                chat_id=chat_id,
                event_type="error",
                command_or_action=cmd_label,
                status_val="error",
                latency_ms=(time.perf_counter() - started) * 1000,
                detail=f"{type(exc).__name__}: {exc}",
            )
            db.commit()
        raise


def _verify_and_bind_platform_link(
    db: Session,
    bot: TelegramBot,
    token_str: str,
    tg_uid: str,
    chat_id: str,
    tg_username: str,
    tg_first_name: str,
) -> Tuple[bool, str, Optional[User], Optional[TelegramUserLink]]:
    data = verify_signed_state(token_str, salt="tg-user-link", max_age_seconds=900)
    if not data or data.get("bid") != bot.id:
        return False, "❌ Link code expired or invalid. Generate a fresh Connect link in <b>Dashboard → Telegram Bot</b>.", None, None

    user = db.get(User, data.get("uid", ""))
    if not user or not user.is_active or user.is_suspended:
        return False, "❌ Account not found or suspended.", None, None

    existing = db.scalar(
        select(TelegramUserLink).where(
            TelegramUserLink.bot_id == bot.id,
            TelegramUserLink.user_id == user.id,
        )
    )
    if existing:
        existing.telegram_user_id = tg_uid
        existing.chat_id = chat_id
        existing.telegram_username = tg_username
        existing.telegram_first_name = tg_first_name
        existing.is_active = True
        link_row = existing
    else:
        link_row = TelegramUserLink(
            bot_id=bot.id,
            user_id=user.id,
            telegram_user_id=tg_uid,
            chat_id=chat_id,
            telegram_username=tg_username,
            telegram_first_name=tg_first_name,
        )
        db.add(link_row)
    db.flush()
    msg = (
        f"✅ <b>Account Linked!</b>\n\n"
        f"Welcome, <b>{_e(user.full_name or user.email)}</b> (<code>{_e(user.email)}</code>).\n"
        f"You will now receive API key security updates, quota warnings &amp; Razorpay billing alerts right here."
    )
    return True, msg, user, link_row


QUICK_TOOL_ACTIONS: Dict[str, Tuple[str, str, Optional[Dict[str, str]]]] = {
    "t:status": ("GET", "/v1/status", None),
    "t:uuid": ("GET", "/v1/crypto/uuid", {"count": "3"}),
    "t:time": ("GET", "/v1/utils/timestamp", None),
    "t:ip8": ("GET", "/v1/geo/ip-parse", {"ip": "8.8.8.8"}),
    "t:dns": ("GET", "/v1/network/dns", {"domain": "example.com"}),
}


async def _handle_callback(
    db: Session,
    *,
    responder: BotResponder,
    bot: TelegramBot,
    brand: Dict[str, str],
    actor_user: Optional[User],
    user_link: Optional[TelegramUserLink],
    is_privileged: bool,
    frontend_url: str,
    chat_id: str,
    message_id: Optional[int],
    cb_id: str,
    data: str,
) -> Tuple[str, str]:
    privileged_only = {"m:quota", "m:keys", "m:logs", "m:alerts", "m:prof", "k:", "a:"}
    if not is_privileged and (data in privileged_only or data.startswith(("k:", "a:"))):
        await responder.answer_callback(cb_id, "Account link or owner pairing required.", show_alert=True)
        return "denied", f"Unauthorized callback {data}"

    await responder.answer_callback(cb_id)
    menu_kb = _build_main_menu_keyboard(
        is_privileged=is_privileged,
        frontend_url=frontend_url,
        is_platform_bot=bot.is_platform_bot,
    )

    if data == "m:home":
        title = f"🤖 <b>{_e(bot.bot_name)}</b> — {_e(brand['app_name'])}"
        sub = f"Linked as <code>{_e(actor_user.email)}</code>" if actor_user else "Public API Gateway Mode"
        await responder.edit_or_send(chat_id, message_id, f"{title}\n{sub}\n\nChoose an action below:", reply_markup=menu_kb)
        return "ok", "menu:home"

    if data == "m:help":
        await responder.edit_or_send(
            chat_id,
            message_id,
            _format_help_text(bot, brand, is_privileged),
            reply_markup={"inline_keyboard": [[{"text": "« Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "menu:help"

    if data == "m:plans":
        text, kb = _format_plans_card(db, brand, frontend_url)
        await responder.edit_or_send(chat_id, message_id, text, reply_markup=kb)
        return "ok", "menu:plans"

    if data == "m:tools":
        tools_kb = {
            "inline_keyboard": [
                [
                    {"text": "🟢 GET /v1/status", "callback_data": "t:status"},
                    {"text": "🆔 GET /v1/crypto/uuid", "callback_data": "t:uuid"},
                ],
                [
                    {"text": "🕒 GET /v1/utils/timestamp", "callback_data": "t:time"},
                    {"text": "🌐 IP 8.8.8.8", "callback_data": "t:ip8"},
                ],
                [
                    {"text": "📡 DNS example.com", "callback_data": "t:dns"},
                    {"text": "« Menu", "callback_data": "m:home"},
                ],
            ]
        }
        await responder.edit_or_send(
            chat_id,
            message_id,
            "<b>⚡ Quick Gateway API Runner</b>\n\nTap any endpoint to run a live gateway request using your bound API key:",
            reply_markup=tools_kb,
        )
        return "ok", "menu:tools"

    if data in QUICK_TOOL_ACTIONS:
        m, p, q = QUICK_TOOL_ACTIONS[data]
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method=m, path=p, query_dict=q, edit_message_id=message_id
        )

    # Privileged actions
    assert actor_user is not None
    if data == "m:quota":
        await responder.edit_or_send(
            chat_id,
            message_id,
            _format_quota_card(db, actor_user, brand),
            reply_markup={"inline_keyboard": [[{"text": "↻ Refresh", "callback_data": "m:quota"}, {"text": "« Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "menu:quota"

    if data == "m:prof":
        sub = get_active_subscription(db, actor_user.id)
        plan = db.get(SubscriptionPlan, sub.plan_id) if sub else None
        text = (
            f"<b>👤 Account Profile</b>\n\n"
            f"Name: <b>{_e(actor_user.full_name or 'Developer')}</b>\n"
            f"Email: <code>{_e(actor_user.email)}</code>\n"
            f"Role: <b>{_e(actor_user.role.upper())}</b>\n"
            f"Plan: <b>{_e(plan.name if plan else 'No active plan')}</b>\n"
            f"Verified: <b>{'Yes ✅' if actor_user.is_email_verified else 'Pending'}</b>"
        )
        await responder.edit_or_send(
            chat_id,
            message_id,
            text,
            reply_markup={"inline_keyboard": [[{"text": "« Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "menu:profile"

    if data == "m:logs":
        logs = db.scalars(
            select(ApiRequestLog)
            .where(ApiRequestLog.user_id == actor_user.id)
            .order_by(ApiRequestLog.created_at.desc())
            .limit(8)
        ).all()
        if not logs:
            text = "<b>📜 Recent Gateway Logs</b>\n\nNo API requests logged yet. Run <code>/status</code> to generate your first call!"
        else:
            lines = ["<b>📜 Recent Gateway Logs (Latest 8)</b>\n"]
            for entry in logs:
                mark = "✅" if entry.status_code < 400 else "⚠️" if entry.status_code == 429 else "❌"
                lines.append(
                    f"{mark} <code>{_e(entry.method)} {_e(entry.path)}</code> → <b>{entry.status_code}</b> ({round(entry.latency_ms, 1)}ms)"
                )
            text = "\n".join(lines)
        await responder.edit_or_send(
            chat_id,
            message_id,
            text,
            reply_markup={"inline_keyboard": [[{"text": "↻ Refresh", "callback_data": "m:logs"}, {"text": "« Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "menu:logs"

    if data == "m:keys":
        text, kb = _format_keys_card(db, actor_user, bot)
        await responder.edit_or_send(chat_id, message_id, text, reply_markup=kb)
        return "ok", "menu:keys"

    if data == "k:new":
        msg = _create_or_activate_key_from_bot(db, actor_user)
        await responder.send(
            chat_id,
            msg,
            reply_markup={"inline_keyboard": [[{"text": "🔑 Back to API Keys", "callback_data": "m:keys"}]]},
        )
        return "ok", "key:create"

    if data.startswith("k:use:"):
        kid = data[6:]
        key = db.get(ApiKey, kid)
        if not key or key.user_id != actor_user.id or key.status != "active":
            await responder.send(chat_id, "❌ Cannot bind key: inactive or not found.")
            return "error", "key:bind_failed"
        bot.api_key_id = key.id
        text, kb = _format_keys_card(db, actor_user, bot, notice=f"Bound {key.name} to @{bot.bot_username}")
        await responder.edit_or_send(chat_id, message_id, text, reply_markup=kb)
        return "ok", f"key:bind:{key.id}"

    if data.startswith("k:rev:"):
        kid = data[6:]
        try:
            plaintext = reveal_user_key(db, actor_user, kid)
        except HTTPException as exc:
            await responder.send(chat_id, f"❌ {_e(exc.detail)}")
            return "error", f"key:reveal_err:{kid}"
        await responder.send(
            chat_id,
            f"🔐 <b>API Key Secret</b> (tap spoiler to view):\n<tg-spoiler><code>{_e(plaintext)}</code></tg-spoiler>\n\n<i>Keep this secret safe.</i>",
        )
        return "ok", f"key:reveal:{kid}"

    if data.startswith("k:rga:"):
        kid = data[6:]
        key = db.get(ApiKey, kid)
        if not key or key.user_id != actor_user.id:
            await responder.send(chat_id, "❌ Key not found.")
            return "error", "key:not_found"
        await responder.edit_or_send(
            chat_id,
            message_id,
            f"⚠️ <b>Regenerate Key {_e(key.name)}?</b>\nYour old secret (<code>••••{_e(key.key_last4)}</code>) will stop working immediately.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "✅ Confirm Rotate", "callback_data": f"k:rgc:{kid}"},
                        {"text": "Cancel", "callback_data": "m:keys"},
                    ]
                ]
            },
        )
        return "ok", f"key:regen_confirm:{kid}"

    if data.startswith("k:rgc:"):
        kid = data[6:]
        try:
            key, new_raw = regenerate_user_key(db, actor_user, kid)
        except HTTPException as exc:
            await responder.send(chat_id, f"❌ {_e(exc.detail)}")
            return "error", f"key:regen_err:{kid}"
        await responder.send(
            chat_id,
            f"🔄 <b>Key Rotated!</b>\nNew secret for <b>{_e(key.name)}</b>:\n<tg-spoiler><code>{_e(new_raw)}</code></tg-spoiler>",
            reply_markup={"inline_keyboard": [[{"text": "🔑 API Keys", "callback_data": "m:keys"}]]},
        )
        return "ok", f"key:regenerated:{kid}"

    if data.startswith("k:rva:"):
        kid = data[6:]
        key = db.get(ApiKey, kid)
        if not key or key.user_id != actor_user.id:
            await responder.send(chat_id, "❌ Key not found.")
            return "error", "key:not_found"
        await responder.edit_or_send(
            chat_id,
            message_id,
            f"🗑 <b>Revoke Key {_e(key.name)}?</b>\nApplications using <code>••••{_e(key.key_last4)}</code> will immediately receive 403 KEY_REVOKED.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "🛑 Confirm Revoke", "callback_data": f"k:rvc:{kid}"},
                        {"text": "Cancel", "callback_data": "m:keys"},
                    ]
                ]
            },
        )
        return "ok", f"key:revoke_confirm:{kid}"

    if data.startswith("k:rvc:"):
        kid = data[6:]
        try:
            key = revoke_user_key(db, actor_user, kid)
        except HTTPException as exc:
            await responder.send(chat_id, f"❌ {_e(exc.detail)}")
            return "error", f"key:revoke_err:{kid}"
        if bot.api_key_id == key.id:
            bot.api_key_id = None
        text, kb = _format_keys_card(db, actor_user, bot, notice=f"Revoked {key.name}")
        await responder.edit_or_send(chat_id, message_id, text, reply_markup=kb)
        return "ok", f"key:revoked:{kid}"

    if data == "m:alerts":
        text, kb = _format_alerts_card(bot, user_link)
        await responder.edit_or_send(chat_id, message_id, text, reply_markup=kb)
        return "ok", "menu:alerts"

    if data.startswith("a:tog:"):
        which = data[6:]
        if bot.is_platform_bot and user_link:
            field_map = {
                "q": "notify_quota_alerts",
                "s": "notify_security_alerts",
                "p": "notify_payment_alerts",
                "e": "notify_gateway_errors",
            }
            attr = field_map.get(which)
            if attr:
                setattr(user_link, attr, not getattr(user_link, attr))
        elif which == "o":
            bot.notify_owner_alerts = not bot.notify_owner_alerts
        text, kb = _format_alerts_card(bot, user_link)
        await responder.edit_or_send(chat_id, message_id, text, reply_markup=kb)
        return "ok", f"alert:toggle:{which}"

    if data == "a:test":
        await responder.send(
            chat_id,
            f"🔔 <b>Test Notification — {_e(brand['app_name'])}</b>\nTelegram alert delivery is active for <code>{_e(actor_user.email)}</code>.",
        )
        return "ok", "alert:test"

    return "ok", f"cb:{data}"


async def _handle_text_or_command(
    db: Session,
    *,
    responder: BotResponder,
    bot: TelegramBot,
    brand: Dict[str, str],
    actor_user: Optional[User],
    user_link: Optional[TelegramUserLink],
    is_privileged: bool,
    frontend_url: str,
    chat_id: str,
    tg_first_name: str,
    raw_input: str,
) -> Tuple[str, str]:
    menu_kb = _build_main_menu_keyboard(
        is_privileged=is_privileged,
        frontend_url=frontend_url,
        is_platform_bot=bot.is_platform_bot,
    )

    if not raw_input:
        await responder.send(chat_id, "Send <code>/menu</code> or <code>/help</code> to see supported commands.", reply_markup=menu_kb)
        return "ok", "empty"

    if not raw_input.startswith("/"):
        if bot.custom_proxy_path and bot.forward_plain_text:
            body_obj = {"query": raw_input, "prompt": raw_input, "text": raw_input, "source": "telegram"}
            qdict = {"q": raw_input} if bot.custom_proxy_method.upper() == "GET" else None
            return await _reply_with_gateway_call(
                db,
                responder,
                bot,
                actor_user,
                chat_id,
                method=bot.custom_proxy_method,
                path=bot.custom_proxy_path,
                query_dict=qdict,
                body_obj=body_obj if bot.custom_proxy_method.upper() != "GET" else None,
            )
        await responder.send(
            chat_id,
            f"👋 Hi <b>{_e(tg_first_name)}</b>! Tap an action below or run <code>/help</code>.",
            reply_markup=menu_kb,
        )
        return "ok", "greeting"

    parts = raw_input.split(maxsplit=1)
    cmd = parts[0].split("@", 1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/menu"):
        if bot.is_platform_bot and not actor_user:
            welcome = bot.welcome_message or (
                f"👋 Welcome to <b>{_e(brand['app_name'])}</b> Official Bot!\n\n"
                "To manage API keys, view live quotas &amp; receive alerts here:\n"
                "1. Open <b>Dashboard → Telegram Bot</b> on the website\n"
                "2. Click <b>Connect Telegram</b> (or copy your <code>/link &lt;code&gt;</code>)."
            )
            await responder.send(chat_id, welcome, reply_markup=menu_kb)
            return "ok", "start:unlinked"

        intro = bot.welcome_message or f"🤖 <b>{_e(bot.bot_name)}</b> — {_e(brand['app_name'])}"
        acct = f"\nAccount: <code>{_e(actor_user.email)}</code>" if actor_user else "\nMode: <b>Public API Gateway</b>"
        await responder.send(chat_id, f"{intro}{acct}\n\nSelect an action below:", reply_markup=menu_kb)
        return "ok", cmd

    if cmd == "/help":
        await responder.send(
            chat_id,
            _format_help_text(bot, brand, is_privileged),
            reply_markup={"inline_keyboard": [[{"text": "« Open Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "help"

    if cmd == "/plans":
        text, kb = _format_plans_card(db, brand, frontend_url)
        await responder.send(chat_id, text, reply_markup=kb)
        return "ok", "plans"

    # Gateway API Commands (allowed for owner, linked users, or public_gateway mode)
    if cmd == "/status":
        return await _reply_with_gateway_call(db, responder, bot, actor_user, chat_id, method="GET", path="/v1/status")

    if cmd == "/time":
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method="GET", path="/v1/utils/timestamp"
        )

    if cmd == "/uuid":
        count = "1"
        if arg:
            try:
                count = str(min(25, max(1, int(arg.split()[0]))))
            except ValueError:
                await responder.send(chat_id, "Usage: <code>/uuid [count 1-25]</code>")
                return "error", "uuid:validation"
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method="GET", path="/v1/crypto/uuid", query_dict={"count": count}
        )

    if cmd == "/hash":
        if not arg:
            await responder.send(chat_id, "Usage: <code>/hash [sha256|sha512|blake2b] &lt;text&gt;</code>")
            return "error", "hash:validation"
        tokens = arg.split(maxsplit=1)
        algos = {"sha256", "sha512", "blake2b"}
        if len(tokens) == 2 and tokens[0].lower() in algos:
            algo, text_val = tokens[0].lower(), tokens[1]
        else:
            algo, text_val = "sha256", arg
        return await _reply_with_gateway_call(
            db,
            responder,
            bot,
            actor_user,
            chat_id,
            method="POST",
            path="/v1/crypto/hash",
            body_obj={"algorithm": algo, "text": text_val},
        )

    if cmd == "/ip":
        target_ip = arg.split()[0] if arg else "8.8.8.8"
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method="GET", path="/v1/geo/ip-parse", query_dict={"ip": target_ip}
        )

    if cmd == "/dns":
        domain = arg.split()[0] if arg else "example.com"
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method="GET", path="/v1/network/dns", query_dict={"domain": domain}
        )

    if cmd == "/json":
        if not arg:
            await responder.send(chat_id, "Usage: <code>/json {\"hello\":\"beta\"}</code>")
            return "error", "json:validation"
        try:
            parsed = json.loads(arg)
        except Exception:
            await responder.send(chat_id, "❌ That argument is not valid JSON. Example: <code>/json {\"ok\":true}</code>")
            return "error", "json:invalid"
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method="POST", path="/v1/utils/json-validate", body_obj=parsed
        )

    if cmd == "/call":
        # Format: /call GET /v1/crypto/uuid?count=2   OR /call POST /v1/network/echo {"ok":true}
        call_parts = arg.split(maxsplit=2)
        if len(call_parts) < 2:
            await responder.send(
                chat_id,
                "Usage: <code>/call &lt;METHOD&gt; &lt;/v1/path&gt; [json_body]</code>\nExample: <code>/call POST /v1/network/echo {\"ping\":true}</code>",
            )
            return "error", "call:usage"
        req_method = call_parts[0].upper()
        if req_method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            await responder.send(chat_id, "❌ Supported methods: GET, POST, PUT, PATCH, DELETE.")
            return "error", "call:bad_method"
        raw_path = call_parts[1]
        q_part = {}
        if "?" in raw_path:
            raw_path, qs = raw_path.split("?", 1)
            for item in qs.split("&"):
                if "=" in item:
                    k, v = item.split("=", 1)
                    q_part[k] = v
        body_payload: Any = None
        if len(call_parts) == 3 and call_parts[2].strip():
            try:
                body_payload = json.loads(call_parts[2].strip())
            except Exception:
                body_payload = call_parts[2].strip()
        return await _reply_with_gateway_call(
            db, responder, bot, actor_user, chat_id, method=req_method, path=raw_path, query_dict=q_part, body_obj=body_payload
        )

    if cmd == "/ask":
        if not bot.custom_proxy_path:
            await responder.send(
                chat_id,
                "⚙️ No custom upstream proxy endpoint is configured on this bot yet. Configure <b>Custom Proxy Path</b> in Dashboard → Telegram Bot.",
            )
            return "error", "ask:unconfigured"
        if not arg:
            await responder.send(chat_id, "Usage: <code>/ask &lt;your query or prompt&gt;</code>")
            return "error", "ask:empty"
        return await _reply_with_gateway_call(
            db,
            responder,
            bot,
            actor_user,
            chat_id,
            method=bot.custom_proxy_method,
            path=bot.custom_proxy_path,
            query_dict={"q": arg} if bot.custom_proxy_method.upper() == "GET" else None,
            body_obj={"query": arg, "prompt": arg, "text": arg, "source": "telegram"}
            if bot.custom_proxy_method.upper() != "GET"
            else None,
        )

    # Privileged commands
    if not is_privileged or not actor_user:
        msg = (
            "🔒 Connect your Beta account via <b>Dashboard → Telegram Bot</b> first."
            if bot.is_platform_bot
            else "🔒 Only the paired bot owner can run account management commands."
        )
        await responder.send(chat_id, msg)
        return "denied", f"unprivileged:{cmd}"

    if cmd in ("/quota", "/usage"):
        await responder.send(
            chat_id,
            _format_quota_card(db, actor_user, brand),
            reply_markup={"inline_keyboard": [[{"text": "🔑 Manage Keys", "callback_data": "m:keys"}, {"text": "« Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "quota"

    if cmd == "/keys":
        text, kb = _format_keys_card(db, actor_user, bot)
        await responder.send(chat_id, text, reply_markup=kb)
        return "ok", "keys"

    if cmd == "/logs":
        logs = db.scalars(
            select(ApiRequestLog)
            .where(ApiRequestLog.user_id == actor_user.id)
            .order_by(ApiRequestLog.created_at.desc())
            .limit(8)
        ).all()
        if not logs:
            await responder.send(chat_id, "<b>📜 Recent Gateway Logs</b>\n\nNo requests logged yet.")
        else:
            lines = ["<b>📜 Recent Gateway Logs (Latest 8)</b>\n"]
            for entry in logs:
                mark = "✅" if entry.status_code < 400 else "⚠️" if entry.status_code == 429 else "❌"
                lines.append(
                    f"{mark} <code>{_e(entry.method)} {_e(entry.path)}</code> → <b>{entry.status_code}</b> ({round(entry.latency_ms, 1)}ms)"
                )
            await responder.send(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": [[{"text": "« Menu", "callback_data": "m:home"}]]})
        return "ok", "logs"

    if cmd == "/profile":
        sub = get_active_subscription(db, actor_user.id)
        plan = db.get(SubscriptionPlan, sub.plan_id) if sub else None
        await responder.send(
            chat_id,
            f"<b>👤 Profile</b>\nName: <b>{_e(actor_user.full_name or 'Developer')}</b>\n"
            f"Email: <code>{_e(actor_user.email)}</code>\n"
            f"Role: <b>{_e(actor_user.role.upper())}</b>\n"
            f"Plan: <b>{_e(plan.name if plan else 'No active plan')}</b>",
            reply_markup={"inline_keyboard": [[{"text": "« Menu", "callback_data": "m:home"}]]},
        )
        return "ok", "profile"

    if cmd == "/alerts":
        text, kb = _format_alerts_card(bot, user_link)
        await responder.send(chat_id, text, reply_markup=kb)
        return "ok", "alerts"

    if cmd == "/unlink" and bot.is_platform_bot and user_link:
        user_link.is_active = False
        await responder.send(chat_id, "🔌 Your Telegram account has been unlinked. You can reconnect anytime from the dashboard.")
        return "ok", "unlink"

    if cmd == "/adminstats":
        if actor_user.role != "admin":
            await responder.send(chat_id, "🛑 Administrator privileges required.")
            return "denied", "adminstats:denied"
        total_users = db.scalar(select(func.count(User.id))) or 0
        active_subs = db.scalar(select(func.count(Subscription.id)).where(Subscription.status == "active")) or 0
        active_keys = db.scalar(select(func.count(ApiKey.id)).where(ApiKey.status == "active")) or 0
        revenue_paise = (
            db.scalar(select(func.coalesce(func.sum(PaymentOrder.amount_paise), 0)).where(PaymentOrder.status == "successful"))
            or 0
        )
        since_24h = utc_now() - timedelta(hours=24)
        reqs_24h = db.scalar(select(func.count(ApiRequestLog.id)).where(ApiRequestLog.created_at >= since_24h)) or 0
        linked_tg = db.scalar(select(func.count(TelegramUserLink.id)).where(TelegramUserLink.is_active.is_(True))) or 0
        gw = db.get(MasterGatewayConfig, 1)
        await responder.send(
            chat_id,
            f"<b>🛡 {_e(brand['company_name'])} Admin Telemetry</b>\n\n"
            f"• Verified Revenue: <b>{_e(format_inr(int(revenue_paise)))}</b>\n"
            f"• Total Users: <b>{total_users:,}</b> ({linked_tg:,} Telegram linked)\n"
            f"• Active Subscriptions: <b>{active_subs:,}</b>\n"
            f"• Active API Keys: <b>{active_keys:,}</b>\n"
            f"• Gateway Calls (24h): <b>{reqs_24h:,}</b>\n"
            f"• Gateway Mode: <code>{_e(gw.gateway_mode if gw else 'hybrid')}</code>",
        )
        return "ok", "adminstats"

    await responder.send(
        chat_id,
        f"❓ Unknown command <code>{_e(cmd)}</code>. Run <code>/help</code> to view all commands.",
        reply_markup=menu_kb,
    )
    return "ok", f"unknown:{cmd}"


async def simulate_bot_command(
    db: Session,
    bot: TelegramBot,
    owner: User,
    text: str,
    *,
    as_owner: bool = True,
) -> List[Dict[str, Any]]:
    """Run any command/message inside the website Simulator without sending external Telegram calls."""
    responder = BotResponder(simulate=True)
    sim_uid = bot.paired_telegram_user_id if (as_owner and bot.paired_telegram_user_id) else "9900001"
    if as_owner and not bot.is_platform_bot and not bot.paired_telegram_user_id:
        # Allow owner simulation in-browser using a synthetic paired match when not paired yet
        orig_uid = bot.paired_telegram_user_id
        bot.paired_telegram_user_id = sim_uid
        restore = True
    else:
        orig_uid = bot.paired_telegram_user_id
        restore = False

    update = {
        "update_id": 0,
        "message": {
            "message_id": 1,
            "from": {"id": int(sim_uid) if sim_uid.isdigit() else 9900001, "username": owner.email.split("@")[0], "first_name": owner.full_name or "Dev"},
            "chat": {"id": int(sim_uid) if sim_uid.isdigit() else 9900001, "type": "private"},
            "text": text,
        },
    }
    try:
        await process_telegram_update(db, bot, update, responder=responder)
    finally:
        if restore:
            bot.paired_telegram_user_id = orig_uid
            db.commit()
    return responder.captured


async def poll_bot_updates_once(
    db: Session,
    bot: TelegramBot,
    *,
    timeout_sec: int = 0,
    settings: Optional[Settings] = None,
) -> int:
    cfg = settings or get_settings()
    token = _resolve_bot_token(bot, cfg)
    updates = await telegram_api_call(
        token,
        "getUpdates",
        {
            "offset": (bot.last_update_id or 0) + 1,
            "limit": 25,
            "timeout": timeout_sec,
            "allowed_updates": ["message", "callback_query"],
        },
        timeout_sec=max(10.0, float(timeout_sec) + 8.0),
        settings=cfg,
    )
    if not isinstance(updates, list) or not updates:
        return 0

    processed = 0
    for upd in updates:
        uid = int(upd.get("update_id") or 0)
        if uid > (bot.last_update_id or 0):
            bot.last_update_id = uid
        try:
            await process_telegram_update(db, bot, upd, settings=cfg)
            processed += 1
        except Exception:
            pass
    db.commit()
    return processed


async def _deliver_bot_message(
    db: Session,
    bot: TelegramBot,
    chat_id: str,
    text: str,
    *,
    category: str,
    settings: Optional[Settings] = None,
) -> bool:
    cfg = settings or get_settings()
    try:
        responder = BotResponder(bot_token=_resolve_bot_token(bot, cfg), simulate=False, settings=cfg)
        await responder.send(chat_id, text)
        _record_tg_event(
            db,
            bot_id=bot.id,
            chat_id=chat_id,
            event_type="notification",
            command_or_action=category,
            status_val="ok",
            detail="Notification delivered",
        )
        db.commit()
        return True
    except Exception as exc:
        _record_tg_event(
            db,
            bot_id=bot.id,
            chat_id=chat_id,
            event_type="notification",
            command_or_action=category,
            status_val="error",
            detail=f"{type(exc).__name__}: {exc}",
        )
        db.commit()
        return False


async def notify_user_telegram(
    db: Session,
    user_id: str,
    *,
    category: str,  # quota | security | payment | error
    title: str,
    message_lines: List[str],
    settings: Optional[Settings] = None,
) -> int:
    """Deliver best-effort alert to linked platform bot chat and/or owner's paired custom bot."""
    cfg = settings or get_settings()
    delivered = 0
    body = f"<b>{_e(title)}</b>\n" + "\n".join(message_lines)

    # 1. Platform bot links
    pref_col_map = {
        "quota": TelegramUserLink.notify_quota_alerts,
        "security": TelegramUserLink.notify_security_alerts,
        "payment": TelegramUserLink.notify_payment_alerts,
        "error": TelegramUserLink.notify_gateway_errors,
    }
    pref_col = pref_col_map.get(category)
    if pref_col is not None:
        links = db.scalars(
            select(TelegramUserLink).where(
                TelegramUserLink.user_id == user_id,
                TelegramUserLink.is_active.is_(True),
                pref_col.is_(True),
            )
        ).all()
        for link in links:
            pbot = db.get(TelegramBot, link.bot_id)
            if pbot and pbot.is_active and await _deliver_bot_message(
                db, pbot, link.chat_id, body, category=f"alert:{category}", settings=cfg
            ):
                delivered += 1

    # 2. User's paired custom bots with owner alerts enabled
    custom_bots = db.scalars(
        select(TelegramBot).where(
            TelegramBot.owner_user_id == user_id,
            TelegramBot.is_platform_bot.is_(False),
            TelegramBot.is_active.is_(True),
            TelegramBot.notify_owner_alerts.is_(True),
            TelegramBot.paired_chat_id.is_not(None),
        )
    ).all()
    for cbot in custom_bots:
        if cbot.paired_chat_id and await _deliver_bot_message(
            db, cbot, cbot.paired_chat_id, body, category=f"alert:{category}", settings=cfg
        ):
            delivered += 1

    return delivered


async def notify_gateway_alerts(
    db: Session,
    *,
    user_id: str,
    full_path: str,
    status_code: int,
    error_code: Optional[str],
    plan_name: str,
    daily_limit: int,
    daily_rem: int,
    monthly_limit: int,
    monthly_rem: int,
) -> None:
    """Trigger Telegram notifications on 5xx upstream errors or 80%/100% quota milestones."""
    today_str = utc_now().strftime("%Y-%m-%d")

    if status_code >= 500:
        await notify_user_telegram(
            db,
            user_id,
            category="error",
            title="❌ Gateway Error Alert",
            message_lines=[
                f"Endpoint: <code>{_e(full_path)}</code>",
                f"Status: <b>HTTP {status_code}</b> ({_e(error_code or 'SERVER_ERROR')})",
            ],
        )

    daily_pct = ((daily_limit - daily_rem) / daily_limit * 100) if daily_limit > 0 else 0
    monthly_pct = ((monthly_limit - monthly_rem) / monthly_limit * 100) if monthly_limit > 0 else 0
    peak_pct = max(daily_pct, monthly_pct)
    if peak_pct < 80:
        return

    # Prevent duplicate quota alerts within the same UTC day per subscriber/bot
    links = db.scalars(
        select(TelegramUserLink).where(
            TelegramUserLink.user_id == user_id,
            TelegramUserLink.is_active.is_(True),
            TelegramUserLink.notify_quota_alerts.is_(True),
        )
    ).all()
    cbots = db.scalars(
        select(TelegramBot).where(
            TelegramBot.owner_user_id == user_id,
            TelegramBot.is_platform_bot.is_(False),
            TelegramBot.is_active.is_(True),
            TelegramBot.notify_owner_alerts.is_(True),
            TelegramBot.paired_chat_id.is_not(None),
        )
    ).all()

    already_sent = any(l.last_quota_alert_date == today_str for l in links) or any(
        b.last_quota_alert_date == today_str for b in cbots
    )
    if already_sent or (not links and not cbots):
        return

    for l in links:
        l.last_quota_alert_date = today_str
    for b in cbots:
        b.last_quota_alert_date = today_str
    db.commit()

    title = "⚠️ 100% Plan Quota Reached" if (daily_rem == 0 or monthly_rem == 0) else "⚠️ 80%+ Quota Threshold Reached"
    await notify_user_telegram(
        db,
        user_id,
        category="quota",
        title=title,
        message_lines=[
            f"Plan: <b>{_e(plan_name)}</b>",
            f"Daily remaining: <b>{daily_rem:,}</b> / {daily_limit:,}",
            f"Cycle remaining: <b>{monthly_rem:,}</b> / {monthly_limit:,}",
        ],
    )


async def disconnect_telegram_bot(db: Session, bot: TelegramBot, settings: Optional[Settings] = None) -> None:
    """Remove Telegram webhook best-effort and delete bot record cleanly."""
    cfg = settings or get_settings()
    try:
        token = _resolve_bot_token(bot, cfg)
        await telegram_api_call(token, "deleteWebhook", {"drop_pending_updates": False}, settings=cfg)
    except Exception:
        pass
    db.delete(bot)
    db.commit()


async def telegram_polling_loop(session_factory: Callable[[], Session]) -> None:
    """Background loop for bots configured in polling mode (e.g., local HTTP dev)."""
    while True:
        try:
            with session_factory() as db:
                polling_bots = db.scalars(
                    select(TelegramBot).where(
                        TelegramBot.is_active.is_(True),
                        TelegramBot.connection_mode == "polling",
                    )
                ).all()
                for bot in polling_bots:
                    try:
                        await poll_bot_updates_once(db, bot, timeout_sec=0)
                    except TelegramApiError as exc:
                        bot.last_error = str(exc)[:500]
                        db.commit()
                    except Exception:
                        db.rollback()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(3.0)
