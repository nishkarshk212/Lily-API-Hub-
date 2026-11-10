"""API key vault routes: list, create, reveal, regenerate, revoke."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.domain import ApiKeyCreateRequest
from app.services.auth_service import get_client_ip, record_audit
from app.services.key_service import (
    create_additional_key,
    list_user_keys,
    regenerate_user_key,
    reveal_user_key,
    revoke_user_key,
    serialize_api_key,
)

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


@router.get("")
def get_my_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = list_user_keys(db, user.id)
    return {"keys": [serialize_api_key(k) for k in keys]}


@router.post("")
def create_new_key(
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
def regenerate_key(
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
    return {"key": serialize_api_key(key), "api_key": new_raw, "message": "API key regenerated successfully."}


@router.post("/{key_id}/revoke")
def revoke_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = revoke_user_key(db, user, key_id)
    record_audit(db, "api_key.revoked", user.email, user.id, "api_key", key.id, {}, get_client_ip(request))
    db.commit()
    return {"key": serialize_api_key(key), "message": "API key revoked."}

