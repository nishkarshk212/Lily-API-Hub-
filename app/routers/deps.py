"""Shared FastAPI authentication and authorization dependencies."""

from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User, UserSession
from app.services.auth_service import resolve_session_from_request


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> Tuple[User, UserSession]:
    return resolve_session_from_request(request, db)


def get_current_user(
    pair: Tuple[User, UserSession] = Depends(get_current_session),
) -> User:
    return pair[0]


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    try:
        user, _ = resolve_session_from_request(request, db)
        return user
    except HTTPException:
        return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return user

