"""Authentication, Google OAuth2, email verification, password reset, profile, and session routes."""

from typing import Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.email_service import send_verification_email
from app.core.security import (
    create_signed_state,
    hash_password,
    utc_now,
    verify_password,
    verify_signed_state,
)
from app.models.plan import SubscriptionPlan
from app.models.user import User, UserSession
from app.routers.deps import get_current_session, get_current_user, get_optional_user
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services.auth_service import (
    authenticate_user,
    clear_session_cookie,
    exchange_google_code_and_login,
    get_client_ip,
    issue_email_token,
    record_audit,
    register_user,
    request_password_reset,
    reset_password_with_token,
    set_session_cookie,
    verify_email_with_token,
)
from app.services.key_service import get_latest_subscription

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register")
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    cfg = get_settings()
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    user, jwt_token, raw_verify_token = register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        company=payload.company,
        ip_address=ip,
        user_agent=ua,
    )
    set_session_cookie(response, jwt_token, cfg)
    result = {
        "user": UserOut.model_validate(user),
        "message": "Account created. Please verify your email using the verification link sent to your inbox.",
    }
    if not cfg.is_production and not cfg.SMTP_HOST.strip():
        result["dev_verification_hint"] = f"/#verify-email?token={raw_verify_token}"
    return result


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    user, jwt_token = authenticate_user(db, payload.email, payload.password, ip, ua, require_admin=False)
    set_session_cookie(response, jwt_token)
    return {"user": UserOut.model_validate(user), "message": "Signed in successfully."}


@router.post("/logout")
def logout(
    response: Response,
    pair: Tuple[User, UserSession] = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    user, session = pair
    session.revoked = True
    record_audit(db, "user.logout", user.email, user.id, "session", session.id)
    db.commit()
    clear_session_cookie(response)
    return {"message": "Logged out successfully."}


def _build_user_context(request: Request, user: User, db: Session) -> dict:
    sub = get_latest_subscription(db, user.id)
    plan = db.get(SubscriptionPlan, sub.plan_id) if sub else None
    cfg = get_settings()
    base_url = cfg.resolve_api_base_url(request)
    return {
        "authenticated": True,
        "user": UserOut.model_validate(user),
        "api_base_url": base_url,
        "subscription": {
            "id": sub.id,
            "status": sub.status,
            "starts_at": sub.starts_at,
            "expires_at": sub.expires_at,
            "daily_requests_used": sub.daily_requests_used if sub.daily_usage_date == utc_now().strftime("%Y-%m-%d") else 0,
            "cycle_requests_used": sub.cycle_requests_used,
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "slug": plan.slug,
                "price_paise": plan.price_paise,
                "daily_request_limit": plan.daily_request_limit,
                "monthly_request_limit": plan.monthly_request_limit,
                "rate_limit_per_minute": plan.rate_limit_per_minute,
                "max_api_keys": plan.max_api_keys,
                "allowed_methods": plan.allowed_methods,
            }
            if plan
            else None,
        }
        if sub
        else None,
    }


@router.get("/session")
def get_optional_session(request: Request, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    if not user:
        return {"authenticated": False, "user": None, "subscription": None}
    return _build_user_context(request, user, db)


@router.get("/me")
def me(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _build_user_context(request, user, db)


@router.patch("/profile")
def update_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.full_name = payload.full_name.strip()
    user.company = payload.company.strip()
    user.phone = payload.phone.strip()
    record_audit(db, "user.profile_updated", user.email, user.id, "user", user.id)
    db.commit()
    db.refresh(user)
    return {"user": UserOut.model_validate(user), "message": "Profile updated."}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    pair: Tuple[User, UserSession] = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    user, current_session = pair
    if user.password_hash:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    user.password_hash = hash_password(payload.new_password)
    if user.auth_provider == "google":
        user.auth_provider = "both"

    # Revoke all other sessions for security
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.id != current_session.id)
        .values(revoked=True)
    )
    record_audit(db, "user.password_changed", user.email, user.id, "user", user.id)
    db.commit()
    return {"message": "Password updated and other sessions logged out."}


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = verify_email_with_token(db, payload.token)
    return {"user": UserOut.model_validate(user), "message": "Email verified successfully."}


@router.post("/resend-verification")
def resend_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.is_email_verified:
        return {"message": "Email is already verified."}
    cfg = get_settings()
    raw_token = issue_email_token(db, user, "verify_email", ttl_minutes=60 * 24)
    send_verification_email(db, user.email, user.full_name, raw_token, cfg)
    db.commit()
    resp = {"message": "Verification email dispatched."}
    if not cfg.is_production and not cfg.SMTP_HOST.strip():
        resp["dev_verification_hint"] = f"/#verify-email?token={raw_token}"
    return resp


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    cfg = get_settings()
    raw_token = request_password_reset(db, payload.email)
    resp = {"message": "If an account exists for that email, a password reset link has been sent."}
    if raw_token and not cfg.is_production and not cfg.SMTP_HOST.strip():
        resp["dev_reset_hint"] = f"/#reset-password?token={raw_token}"
    return resp


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    reset_password_with_token(db, payload.token, payload.new_password)
    return {"message": "Password reset successfully. You can now sign in with your new password."}


@router.get("/sessions")
def list_sessions(
    pair: Tuple[User, UserSession] = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    user, current_session = pair
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked.is_(False))
        .order_by(UserSession.last_seen_at.desc())
    ).all()
    return {
        "sessions": [
            {
                "id": s.id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at,
                "last_seen_at": s.last_seen_at,
                "expires_at": s.expires_at,
                "is_current": s.id == current_session.id,
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    pair: Tuple[User, UserSession] = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    user, _ = pair
    target = db.get(UserSession, session_id)
    if not target or target.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    target.revoked = True
    db.commit()
    return {"message": "Session revoked."}


@router.get("/google/login")
def google_oauth_login(next_route: str = Query(default="/#dashboard")):
    cfg = get_settings()
    if not cfg.google_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )

    state = create_signed_state({"next": next_route}, salt="google-oauth-state", settings=cfg)
    params = urlencode(
        {
            "client_id": cfg.GOOGLE_CLIENT_ID,
            "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": state,
        }
    )
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: Session = Depends(get_db),
):
    cfg = get_settings()
    if error:
        return RedirectResponse(url=f"/?auth_error={error}#login")
    state_data = verify_signed_state(state, salt="google-oauth-state", max_age_seconds=600, settings=cfg)
    if not state_data or not code:
        return RedirectResponse(url="/?auth_error=invalid_oauth_state#login")

    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    try:
        _, jwt_token = await exchange_google_code_and_login(db, code, ip, ua, cfg)
    except HTTPException as exc:
        return RedirectResponse(url=f"/?auth_error={exc.detail}#login")

    next_target = state_data.get("next") or "/#dashboard"
    if not next_target.startswith("/"):
        next_target = "/#dashboard"
    resp = RedirectResponse(url=next_target)
    set_session_cookie(resp, jwt_token, cfg)
    return resp

