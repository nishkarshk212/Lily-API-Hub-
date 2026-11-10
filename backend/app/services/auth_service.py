"""Authentication, session management, email verification, password reset, and Google OAuth2."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response, status
import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.email_service import send_password_reset_email, send_verification_email
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_random_token,
    hash_password,
    sha256_hex,
    utc_now,
    verify_password,
)
from app.models.gateway import AuditLog
from app.models.user import EmailToken, User, UserSession

SESSION_COOKIE_NAME = "lily_session"


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded[:64]
    return (request.client.host if request.client else "127.0.0.1")[:64]


def _cookie_policy(cfg: Settings) -> Tuple[str, bool]:
    https_mode = cfg.COOKIE_SECURE or cfg.is_production or cfg.effective_frontend_url.startswith("https://")
    if cfg.is_cross_origin_frontend and https_mode:
        return "none", True
    return "lax", bool(cfg.COOKIE_SECURE or cfg.is_production)


def set_session_cookie(response: Response, token: str, settings: Optional[Settings] = None) -> None:
    cfg = settings or get_settings()
    samesite, secure = _cookie_policy(cfg)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=samesite,
        secure=secure,
        max_age=cfg.SESSION_EXPIRE_HOURS * 3600,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Optional[Settings] = None) -> None:
    cfg = settings or get_settings()
    samesite, secure = _cookie_policy(cfg)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite=samesite, secure=secure)


def create_session_for_user(db: Session, user: User, ip_address: str, user_agent: str) -> Tuple[UserSession, str]:
    cfg = get_settings()
    now = utc_now()
    session = UserSession(
        user_id=user.id,
        ip_address=ip_address[:64],
        user_agent=user_agent[:512],
        revoked=False,
        expires_at=now + timedelta(hours=cfg.SESSION_EXPIRE_HOURS),
        last_seen_at=now,
    )
    db.add(session)
    user.last_login_at = now
    db.flush()
    jwt_token = create_access_token(user.id, session.id, user.role, cfg.SESSION_EXPIRE_HOURS, cfg)
    return session, jwt_token


def issue_email_token(db: Session, user: User, purpose: str, ttl_minutes: int) -> str:
    # Invalidate prior unused tokens for same user + purpose
    db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .values(used_at=utc_now())
    )
    raw_token = generate_random_token(32)
    record = EmailToken(
        user_id=user.id,
        token_hash=sha256_hex(raw_token),
        purpose=purpose,
        expires_at=utc_now() + timedelta(minutes=ttl_minutes),
    )
    db.add(record)
    db.flush()
    return raw_token


def record_audit(
    db: Session,
    action: str,
    actor_email: str,
    actor_user_id: Optional[str] = None,
    target_type: str = "",
    target_id: str = "",
    details: Optional[Dict[str, Any]] = None,
    ip_address: str = "",
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details_json=details or {},
            ip_address=ip_address,
        )
    )


def register_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    company: str,
    ip_address: str,
    user_agent: str,
) -> Tuple[User, str, str]:
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        company=company.strip(),
        role="user",
        is_email_verified=False,
        is_active=True,
        is_suspended=False,
        auth_provider="email",
    )
    db.add(user)
    db.flush()

    raw_verify_token = issue_email_token(db, user, "verify_email", ttl_minutes=60 * 24)
    send_verification_email(db, user.email, user.full_name, raw_verify_token)
    _, jwt_token = create_session_for_user(db, user, ip_address, user_agent)
    record_audit(db, "user.register", user.email, user.id, "user", user.id, {"provider": "email"}, ip_address)
    db.commit()
    db.refresh(user)
    return user, jwt_token, raw_verify_token


def authenticate_user(
    db: Session,
    email: str,
    password: str,
    ip_address: str,
    user_agent: str,
    require_admin: bool = False,
) -> Tuple[User, str]:
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google Sign-In. Please continue with Google or reset your password.",
        )

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is deactivated.")

    if user.is_suspended:
        cfg = get_settings()
        reason = user.suspension_reason or f"Contact {cfg.COMPANY_NAME} support for details."
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account suspended: {reason}")

    if require_admin and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required.")

    _, jwt_token = create_session_for_user(db, user, ip_address, user_agent)
    record_audit(db, "user.login", user.email, user.id, "user", user.id, {"admin_portal": require_admin}, ip_address)
    db.commit()
    db.refresh(user)
    return user, jwt_token


def resolve_session_from_request(request: Request, db: Session) -> Tuple[User, UserSession]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    payload = decode_access_token(token)
    if not payload or not payload.get("sub") or not payload.get("sid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")

    session = db.get(UserSession, payload["sid"])
    now = utc_now()
    if not session or session.revoked or as_utc(session.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or logged out.")

    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable.")

    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is suspended.")

    session.last_seen_at = now
    db.commit()
    return user, session


def verify_email_with_token(db: Session, raw_token: str) -> User:
    token_hash = sha256_hex(raw_token.strip())
    record = db.scalar(
        select(EmailToken).where(EmailToken.token_hash == token_hash, EmailToken.purpose == "verify_email")
    )
    now = utc_now()
    if not record or record.used_at is not None or as_utc(record.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification link is invalid or expired.")

    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    record.used_at = now
    user.is_email_verified = True
    record_audit(db, "user.email_verified", user.email, user.id, "user", user.id)
    db.commit()
    db.refresh(user)
    return user


def request_password_reset(db: Session, email: str) -> Optional[str]:
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if not user or not user.is_active:
        # Always return cleanly to avoid leaking registered emails
        return None
    raw_token = issue_email_token(db, user, "reset_password", ttl_minutes=30)
    send_password_reset_email(db, user.email, user.full_name, raw_token)
    record_audit(db, "user.password_reset_requested", user.email, user.id, "user", user.id)
    db.commit()
    return raw_token


def reset_password_with_token(db: Session, raw_token: str, new_password: str) -> User:
    token_hash = sha256_hex(raw_token.strip())
    record = db.scalar(
        select(EmailToken).where(EmailToken.token_hash == token_hash, EmailToken.purpose == "reset_password")
    )
    now = utc_now()
    if not record or record.used_at is not None or as_utc(record.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link is invalid or expired.")

    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    record.used_at = now
    user.password_hash = hash_password(new_password)
    if user.auth_provider == "google":
        user.auth_provider = "both"

    # Security best practice: revoke all active sessions after password reset
    db.execute(update(UserSession).where(UserSession.user_id == user.id).values(revoked=True))
    record_audit(db, "user.password_reset_completed", user.email, user.id, "user", user.id)
    db.commit()
    db.refresh(user)
    return user


async def exchange_google_code_and_login(
    db: Session,
    code: str,
    ip_address: str,
    user_agent: str,
    settings: Optional[Settings] = None,
) -> Tuple[User, str]:
    cfg = settings or get_settings()
    if not cfg.google_oauth_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google OAuth is not configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": cfg.GOOGLE_CLIENT_ID,
                "client_secret": cfg.GOOGLE_CLIENT_SECRET,
                "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token exchange failed.")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Google access token.")

        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to load Google profile.")
        profile = userinfo_resp.json()

    email = (profile.get("email") or "").strip().lower()
    sub = profile.get("sub")
    if not email or not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google profile missing email or sub.")

    email_verified = bool(profile.get("email_verified", False))
    full_name = (profile.get("name") or email.split("@")[0])[:120]
    avatar_url = (profile.get("picture") or "")[:500]

    user = db.scalar(select(User).where(User.google_sub == sub))
    if not user:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.google_sub = sub
            if user.auth_provider == "email":
                user.auth_provider = "both"
            if email_verified:
                user.is_email_verified = True
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
        else:
            user = User(
                email=email,
                password_hash=None,
                full_name=full_name,
                avatar_url=avatar_url,
                role="user",
                is_email_verified=email_verified,
                is_active=True,
                is_suspended=False,
                google_sub=sub,
                auth_provider="google",
            )
            db.add(user)
            db.flush()

    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been suspended.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is inactive.")

    _, jwt_token = create_session_for_user(db, user, ip_address, user_agent)
    record_audit(db, "user.google_oauth_login", user.email, user.id, "user", user.id, {}, ip_address)
    db.commit()
    db.refresh(user)
    return user, jwt_token

