"""Transactional email service with SMTP delivery and local dev outbox capture."""

from email.message import EmailMessage
import logging
import smtplib
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.gateway import EmailOutbox
from app.services.branding_service import get_effective_branding

logger = logging.getLogger("lily.email")


def _wrap_email_html(
    title: str,
    intro: str,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    footer: str = "",
    settings: Optional[Settings] = None,
    branding: Optional[dict] = None,
) -> str:
    cfg = settings or get_settings()
    b = branding or {"app_name": cfg.APP_NAME, "company_name": cfg.COMPANY_NAME}
    cta_block = ""
    if cta_label and cta_url:
        cta_block = f"""
        <div style="margin:28px 0;">
          <a href="{cta_url}" style="display:inline-block;padding:13px 26px;background:#0a0a0a;color:#ffffff;text-decoration:none;border-radius:10px;font-weight:600;font-size:15px;">{cta_label}</a>
        </div>
        <p style="font-size:12px;color:#64748b;word-break:break-all;">Or open this link: <a href="{cta_url}" style="color:#2563eb;">{cta_url}</a></p>
        """
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:32px 16px;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid rgba(15,23,42,0.12);border-radius:16px;padding:32px;">
    <div style="font-size:12px;letter-spacing:1.4px;text-transform:uppercase;color:#2563eb;font-weight:700;margin-bottom:8px;">{b['app_name']} · {b['company_name']}</div>
    <h1 style="margin:0 0 14px;font-size:22px;color:#0a0a0a;">{title}</h1>
    <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#334155;">{intro}</p>
    {cta_block}
    <hr style="border:none;border-top:1px solid rgba(15,23,42,0.1);margin:24px 0;">
    <p style="margin:0;font-size:12px;color:#64748b;">{footer or f"{b['company_name']} Security · Automated transactional notification."}</p>
  </div>
</body>
</html>"""


def send_transactional_email(
    db: Session,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    purpose: str = "general",
    settings: Optional[Settings] = None,
) -> str:
    cfg = settings or get_settings()
    sent_via = "local_outbox"

    if cfg.SMTP_HOST.strip():
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{cfg.effective_from_name} <{cfg.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        try:
            with smtplib.SMTP(cfg.SMTP_HOST.strip(), cfg.SMTP_PORT, timeout=10) as server:
                if cfg.SMTP_USE_TLS:
                    server.starttls()
                if cfg.SMTP_USERNAME.strip():
                    server.login(cfg.SMTP_USERNAME.strip(), cfg.SMTP_PASSWORD)
                server.send_message(msg)
            sent_via = "smtp"
        except Exception as exc:
            logger.warning("SMTP send failed (%s); falling back to outbox log.", exc)

    if not cfg.is_production or sent_via == "local_outbox":
        outbox = EmailOutbox(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            purpose=purpose,
            sent_via=sent_via,
        )
        db.add(outbox)
        db.flush()

    return sent_via


def send_verification_email(db: Session, to_email: str, full_name: str, token: str, settings: Optional[Settings] = None) -> str:
    cfg = settings or get_settings()
    b = get_effective_branding(db, cfg)
    verify_url = f"{cfg.effective_frontend_url}/#verify-email?token={token}"
    greeting = full_name or "Developer"
    html = _wrap_email_html(
        title="Verify your email address",
        intro=f"Hi {greeting}, welcome to {b['app_name']} by {b['company_name']}. Confirm your email address within 24 hours to activate full account billing and security alerts.",
        cta_label="Verify Email Address",
        cta_url=verify_url,
        settings=cfg,
        branding=b,
    )
    text = f"Hi {greeting},\n\nVerify your {b['app_name']} email: {verify_url}\n\nThis link expires in 24 hours."
    return send_transactional_email(db, to_email, f"Verify your {b['app_name']} account", html, text, "verify_email", cfg)


def send_password_reset_email(db: Session, to_email: str, full_name: str, token: str, settings: Optional[Settings] = None) -> str:
    cfg = settings or get_settings()
    b = get_effective_branding(db, cfg)
    reset_url = f"{cfg.effective_frontend_url}/#reset-password?token={token}"
    greeting = full_name or "Developer"
    html = _wrap_email_html(
        title="Reset your password",
        intro=f"Hi {greeting}, we received a request to reset your {b['app_name']} password. Use the button below within 30 minutes. If you did not request this, safely ignore this message.",
        cta_label="Reset Password",
        cta_url=reset_url,
        settings=cfg,
        branding=b,
    )
    text = f"Hi {greeting},\n\nReset your {b['app_name']} password: {reset_url}\n\nThis link expires in 30 minutes."
    return send_transactional_email(db, to_email, f"Reset your {b['app_name']} password", html, text, "reset_password", cfg)


def send_payment_receipt_email(
    db: Session,
    to_email: str,
    full_name: str,
    plan_name: str,
    receipt_number: str,
    amount_display: str,
    key_prefix: str,
    settings: Optional[Settings] = None,
) -> str:
    cfg = settings or get_settings()
    b = get_effective_branding(db, cfg)
    dash_url = f"{cfg.effective_frontend_url}/#dashboard"
    greeting = full_name or "Developer"
    html = _wrap_email_html(
        title="Payment Confirmed & API Key Provisioned",
        intro=(
            f"Hi {greeting}, your payment of <strong>{amount_display}</strong> for <strong>{plan_name}</strong> "
            f"(Receipt: <code>{receipt_number}</code>) has been verified. Your API key starting with <code>{key_prefix}...</code> "
            "is active in your dashboard."
        ),
        cta_label="Open Developer Dashboard",
        cta_url=dash_url,
        settings=cfg,
        branding=b,
    )
    text = (
        f"Hi {greeting},\n\nYour payment of {amount_display} for {plan_name} (Receipt {receipt_number}) is verified. "
        f"Open your dashboard: {dash_url}"
    )
    return send_transactional_email(db, to_email, f"Receipt {receipt_number} — {plan_name} Activated", html, text, "payment_receipt", cfg)

