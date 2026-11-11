"""API key vault routes: list, create, reveal, regenerate, revoke."""

import html

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.domain import ApiKeyCreateRequest
from app.services.auth_service import get_client_ip, record_audit
from app.services.key_service import (
    create_additional_key,
    get_single_key_usage_detail,
    get_user_keys_usage_map,
    list_user_keys,
    regenerate_user_key,
    reveal_user_key,
    revoke_user_key,
    serialize_api_key,
)
from app.services.telegram_service import notify_user_telegram

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


async def _notify_key_event(db: Session, user_id: str, title: str, key_name: str, key_last4: str) -> None:
    try:
        await notify_user_telegram(
            db,
            user_id,
            category="security",
            title=title,
            message_lines=[
                f"Key: <b>{html.escape(key_name)}</b> (<code>••••{html.escape(key_last4)}</code>)",
            ],
        )
    except Exception:
        pass


@router.get("")
def get_my_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = list_user_keys(db, user.id)
    usage_map = get_user_keys_usage_map(db, user.id)
    default_usage = {
        "today_requests": 0,
        "logged_requests": 0,
        "success_requests": 0,
        "error_requests": 0,
        "rate_limited_requests": 0,
        "success_rate": 100.0,
        "avg_latency_ms": 0.0,
    }
    return {"keys": [serialize_api_key(k, usage=usage_map.get(k.id, default_usage)) for k in keys]}


@router.get("/{key_id}/usage")
def get_key_usage(key_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    return {"key": serialize_api_key(key), "usage": get_single_key_usage_detail(db, key)}


@router.post("")
async def create_new_key(
    payload: ApiKeyCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = create_additional_key(db, user, payload.name)
    record_audit(
        db,
        "api_key.created",
        user.email,
        user.id,
        "api_key",
        key.id,
        {"name": key.name, "key_prefix": key.key_prefix},
        get_client_ip(request),
    )
    db.commit()
    await _notify_key_event(db, user.id, "🔑 New API Key Created", key.name, key.key_last4)
    return {"key": serialize_api_key(key), "message": "New API key created."}


@router.get("/{key_id}/reveal")
def reveal_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plaintext = reveal_user_key(db, user, key_id)
    record_audit(db, "api_key.revealed", user.email, user.id, "api_key", key_id, {}, get_client_ip(request))
    db.commit()
    return {"id": key_id, "api_key": plaintext}


@router.post("/{key_id}/regenerate")
async def regenerate_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key, new_raw = regenerate_user_key(db, user, key_id)
    record_audit(
        db,
        "api_key.regenerated",
        user.email,
        user.id,
        "api_key",
        key.id,
        {"new_prefix": key.key_prefix},
        get_client_ip(request),
    )
    db.commit()
    await _notify_key_event(db, user.id, "🔄 API Key Regenerated", key.name, key.key_last4)
    return {"key": serialize_api_key(key), "api_key": new_raw, "message": "API key regenerated successfully."}


@router.post("/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = revoke_user_key(db, user, key_id)
    record_audit(db, "api_key.revoked", user.email, user.id, "api_key", key.id, {}, get_client_ip(request))
    db.commit()
    await _notify_key_event(db, user.id, "🛑 API Key Revoked", key.name, key.key_last4)
    return {"key": serialize_api_key(key), "message": "API key revoked."}

