"""Official Razorpay API client, HMAC verification, idempotent webhook handler, and receipt builder."""

from datetime import datetime
import hashlib
import hmac
import html
import secrets
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.email_service import send_payment_receipt_email
from app.core.security import utc_now, verify_hmac_sha256_hex
from app.models.api_key import ApiKey
from app.models.payment import PaymentOrder, WebhookEvent
from app.models.plan import Subscription, SubscriptionPlan
from app.models.user import User
from app.services.auth_service import record_audit
from app.services.branding_service import get_effective_branding
from app.services.key_service import provision_subscription_and_key


def _generate_receipt_number(db: Optional[Session] = None) -> str:
    brand = get_effective_branding(db)
    prefix = brand["receipt_prefix"]
    date_part = utc_now().strftime("%Y%m%d")
    rand_part = secrets.token_hex(3).upper()
    return f"{prefix}-{date_part}-{rand_part}"


def format_inr(amount_paise: int) -> str:
    rupees = amount_paise / 100.0
    return f"₹{rupees:,.2f}"


async def razorpay_api_request(
    method: str,
    path: str,
    json_payload: Optional[Dict[str, Any]] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    cfg = settings or get_settings()
    if not cfg.razorpay_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay is not configured on the server. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.",
        )

    url = f"{cfg.RAZORPAY_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.request(
            method,
            url,
            auth=(cfg.RAZORPAY_KEY_ID.strip(), cfg.RAZORPAY_KEY_SECRET.strip()),
            json=json_payload,
        )

    if resp.status_code >= 400:
        detail = "Razorpay gateway error"
        try:
            err_body = resp.json()
            detail = err_body.get("error", {}).get("description") or detail
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Razorpay error: {detail}")

    return resp.json()


async def create_razorpay_order_for_user(
    db: Session,
    user: User,
    plan: SubscriptionPlan,
    action: str = "new",
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    cfg = settings or get_settings()
    if not plan.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected plan is not currently active.")
    if plan.price_paise <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Free plans do not require Razorpay checkout. Use free plan activation.",
        )

    brand = get_effective_branding(db, cfg)
    receipt_number = _generate_receipt_number(db)
    notes = {
        "user_id": user.id,
        "user_email": user.email,
        "plan_id": plan.id,
        "plan_slug": plan.slug,
        "action": action,
        "platform": f"{brand['app_name']} by {brand['company_name']}",
    }

    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan.id,
        action=action,
        amount_paise=plan.price_paise,
        currency=plan.currency or "INR",
        status="pending",
        receipt_number=receipt_number,
        notes_json=notes,
    )
    db.add(order)
    db.flush()

    try:
        rzp_order = await razorpay_api_request(
            "POST",
            "/orders",
            json_payload={
                "amount": plan.price_paise,
                "currency": plan.currency or "INR",
                "receipt": receipt_number,
                "notes": notes,
            },
            settings=cfg,
        )
    except HTTPException:
        db.rollback()
        raise

    order.razorpay_order_id = rzp_order["id"]
    record_audit(
        db,
        "payment.order_created",
        user.email,
        user.id,
        "payment_order",
        order.id,
        {"razorpay_order_id": order.razorpay_order_id, "plan_slug": plan.slug, "amount_paise": order.amount_paise},
    )
    db.commit()
    db.refresh(order)

    return {
        "payment_record_id": order.id,
        "razorpay_order_id": order.razorpay_order_id,
        "key_id": cfg.RAZORPAY_KEY_ID.strip(),
        "amount_paise": order.amount_paise,
        "currency": order.currency,
        "receipt_number": order.receipt_number,
        "plan_name": plan.name,
        "plan_description": f"{plan.name} ({plan.billing_cycle_days} days API access)",
        "prefill": {
            "name": user.full_name,
            "email": user.email,
            "contact": user.phone or "",
        },
    }


def verify_checkout_signature(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    if not secret or not order_id or not payment_id or not signature:
        return False
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def fulfill_payment_order_idempotent(
    db: Session,
    order: PaymentOrder,
    payment_id: Optional[str],
    signature: Optional[str],
    payment_method: Optional[str],
    verified_via: str,
) -> Tuple[PaymentOrder, Subscription, Optional[ApiKey]]:
    """Idempotently mark payment successful and provision subscription + API key exactly once."""
    if order.status == "successful" and order.subscription_id:
        sub = db.get(Subscription, order.subscription_id)
        existing_key = db.scalar(
            select(ApiKey)
            .where(ApiKey.subscription_id == order.subscription_id, ApiKey.status == "active")
            .order_by(ApiKey.created_at.desc())
            .limit(1)
        )
        return order, sub, existing_key

    user = db.get(User, order.user_id)
    plan = db.get(SubscriptionPlan, order.plan_id)
    if not user or not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order user or plan missing.")

    sub, api_key = provision_subscription_and_key(
        db,
        user=user,
        plan=plan,
        action=order.action or "new",
        key_name=f"{plan.name} Key",
    )

    order.status = "successful"
    if payment_id:
        order.razorpay_payment_id = payment_id
    if signature:
        order.razorpay_signature = signature
    if payment_method:
        order.payment_method = payment_method
    order.subscription_id = sub.id
    order.verified_via = verified_via
    order.paid_at = order.paid_at or utc_now()
    order.failure_reason = None

    record_audit(
        db,
        "payment.verified_and_provisioned",
        user.email,
        user.id,
        "payment_order",
        order.id,
        {
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": order.razorpay_payment_id,
            "subscription_id": sub.id,
            "key_prefix": api_key.key_prefix,
            "verified_via": verified_via,
        },
    )

    send_payment_receipt_email(
        db,
        to_email=user.email,
        full_name=user.full_name,
        plan_name=plan.name,
        receipt_number=order.receipt_number,
        amount_display=format_inr(order.amount_paise),
        key_prefix=api_key.key_prefix,
    )

    db.commit()
    db.refresh(order)
    db.refresh(sub)
    db.refresh(api_key)
    return order, sub, api_key


async def verify_razorpay_checkout_payment(
    db: Session,
    user: User,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    fetch_remote: bool = True,
    settings: Optional[Settings] = None,
) -> Tuple[PaymentOrder, Subscription, Optional[ApiKey]]:
    cfg = settings or get_settings()
    if not cfg.RAZORPAY_KEY_SECRET.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAZORPAY_KEY_SECRET is not configured on the server.",
        )

    order = db.scalar(select(PaymentOrder).where(PaymentOrder.razorpay_order_id == razorpay_order_id))
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment order not found.")

    if not verify_checkout_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature, cfg.RAZORPAY_KEY_SECRET.strip()
    ):
        order.status = "failed"
        order.failure_reason = "Invalid Razorpay HMAC-SHA256 payment signature."
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment signature verification failed.")

    payment_method = None
    if fetch_remote and cfg.razorpay_configured:
        remote_payment = await razorpay_api_request("GET", f"/payments/{razorpay_payment_id}", settings=cfg)
        if remote_payment.get("order_id") != razorpay_order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment order mismatch.")
        if int(remote_payment.get("amount", 0)) != order.amount_paise:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount mismatch.")
        remote_status = remote_payment.get("status")
        if remote_status not in ("captured", "authorized"):
            order.status = "failed"
            order.failure_reason = f"Unexpected gateway status: {remote_status}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment is not captured (status: {remote_status}).",
            )
        payment_method = remote_payment.get("method")

    return fulfill_payment_order_idempotent(
        db,
        order=order,
        payment_id=razorpay_payment_id,
        signature=razorpay_signature,
        payment_method=payment_method,
        verified_via="checkout_verify",
    )


def handle_razorpay_webhook(
    db: Session,
    raw_body: bytes,
    signature_header: Optional[str],
    event_id_header: Optional[str],
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    cfg = settings or get_settings()
    webhook_secret = cfg.RAZORPAY_WEBHOOK_SECRET.strip()
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAZORPAY_WEBHOOK_SECRET is not configured.",
        )

    if not signature_header or not verify_hmac_sha256_hex(webhook_secret, raw_body, signature_header):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Razorpay webhook signature.")

    import json

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook JSON payload.")

    event_type = payload.get("event", "")
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}
    order_entity = payload.get("payload", {}).get("order", {}).get("entity", {}) or {}
    refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {}) or {}

    rzp_order_id = payment_entity.get("order_id") or order_entity.get("id")
    rzp_payment_id = payment_entity.get("id") or refund_entity.get("payment_id")

    # Deterministic fallback event_id if x-razorpay-event-id is absent
    derived_id = event_id_header or hashlib.sha256(
        f"{event_type}:{rzp_order_id}:{rzp_payment_id}:{payload.get('created_at', '')}".encode("utf-8")
    ).hexdigest()

    existing_event = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == derived_id))
    if existing_event and existing_event.processed:
        return {"status": "duplicate_ignored", "event_id": derived_id, "event_type": event_type}

    if not existing_event:
        event_row = WebhookEvent(
            provider="razorpay",
            event_id=derived_id,
            event_type=event_type,
            razorpay_order_id=rzp_order_id,
            razorpay_payment_id=rzp_payment_id,
            payload_json=payload,
            processed=False,
        )
        db.add(event_row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return {"status": "duplicate_ignored", "event_id": derived_id, "event_type": event_type}
    else:
        event_row = existing_event

    result_msg = "ignored_unhandled_event"
    order = None
    if rzp_order_id:
        order = db.scalar(select(PaymentOrder).where(PaymentOrder.razorpay_order_id == rzp_order_id))
    elif rzp_payment_id:
        order = db.scalar(select(PaymentOrder).where(PaymentOrder.razorpay_payment_id == rzp_payment_id))

    if event_type in ("payment.captured", "order.paid") and order:
        if order.status != "successful":
            paid_amount = int(payment_entity.get("amount") or order_entity.get("amount_paid") or order.amount_paise)
            if paid_amount != order.amount_paise:
                result_msg = "amount_mismatch"
            else:
                event_row.processed = True
                event_row.processing_result = "fulfilled"
                fulfill_payment_order_idempotent(
                    db,
                    order=order,
                    payment_id=rzp_payment_id,
                    signature=None,
                    payment_method=payment_entity.get("method"),
                    verified_via="webhook",
                )
                return {"status": "processed", "event_id": derived_id, "result": "fulfilled"}
        else:
            result_msg = "already_fulfilled"

    elif event_type == "payment.failed" and order:
        if order.status == "pending":
            order.status = "failed"
            order.razorpay_payment_id = rzp_payment_id or order.razorpay_payment_id
            order.failure_reason = (
                payment_entity.get("error_description")
                or payment_entity.get("error_reason")
                or "Payment failed via webhook"
            )
            result_msg = "marked_failed"
        else:
            result_msg = f"skipped_status_{order.status}"

    elif event_type in ("refund.created", "payment.refunded") and order:
        order.status = "refunded"
        order.refunded_at = utc_now()
        if order.subscription_id:
            sub = db.get(Subscription, order.subscription_id)
            if sub and sub.status == "active":
                sub.status = "cancelled"
                sub.cancelled_at = utc_now()
                keys = db.scalars(select(ApiKey).where(ApiKey.subscription_id == sub.id, ApiKey.status == "active")).all()
                for k in keys:
                    k.status = "revoked"
                    k.revoked_at = utc_now()
        result_msg = "marked_refunded_and_revoked"

    event_row.processed = True
    event_row.processing_result = result_msg
    db.commit()
    return {"status": "processed", "event_id": derived_id, "result": result_msg}


async def reconcile_payment_order(
    db: Session,
    order: PaymentOrder,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Query Razorpay directly for an order's payments to reconcile pending states."""
    cfg = settings or get_settings()
    if not order.razorpay_order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order has no Razorpay Order ID.")

    payments_resp = await razorpay_api_request("GET", f"/orders/{order.razorpay_order_id}/payments", settings=cfg)
    items = payments_resp.get("items", [])

    captured = next((p for p in items if p.get("status") == "captured"), None)
    if captured:
        fulfill_payment_order_idempotent(
            db,
            order=order,
            payment_id=captured.get("id"),
            signature=None,
            payment_method=captured.get("method"),
            verified_via="reconciliation",
        )
        return {"reconciled_status": "successful", "payment_id": captured.get("id")}

    refunded = next((p for p in items if p.get("status") == "refunded"), None)
    if refunded:
        order.status = "refunded"
        order.refunded_at = utc_now()
        db.commit()
        return {"reconciled_status": "refunded", "payment_id": refunded.get("id")}

    failed = next((p for p in items if p.get("status") == "failed"), None)
    if failed and order.status == "pending":
        order.status = "failed"
        order.razorpay_payment_id = failed.get("id")
        order.failure_reason = failed.get("error_description") or "Failed on Razorpay"
        db.commit()
        return {"reconciled_status": "failed", "payment_id": failed.get("id")}

    return {"reconciled_status": order.status, "payments_checked": len(items)}


def render_receipt_html(order: PaymentOrder, user: User, plan: SubscriptionPlan, db: Optional[Session] = None) -> str:
    brand = get_effective_branding(db)
    esc = html.escape
    paid_dt = (order.paid_at or order.created_at).strftime("%d %b %Y, %H:%M UTC")
    amount_str = format_inr(order.amount_paise)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Receipt {esc(order.receipt_number)} — {esc(brand['app_name'])}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#070b14; color:#e2e8f0; margin:0; padding:40px 16px; }}
  .sheet {{ max-width:680px; margin:0 auto; background:#0c1424; border:1px solid rgba(56,189,248,0.28); border-radius:16px; padding:36px; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid rgba(148,163,184,0.18); padding-bottom:20px; margin-bottom:24px; }}
  .brand {{ font-size:20px; font-weight:700; color:#f8fafc; }}
  .sub {{ font-size:12px; color:#38bdf8; letter-spacing:1.2px; text-transform:uppercase; margin-top:4px; }}
  .badge {{ padding:6px 14px; border-radius:999px; font-size:12px; font-weight:700; text-transform:uppercase; background:rgba(16,185,129,0.16); color:#34d399; border:1px solid rgba(16,185,129,0.4); }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:28px; font-size:14px; }}
  .label {{ color:#94a3b8; font-size:12px; margin-bottom:4px; }}
  table {{ width:100%; border-collapse:collapse; margin-bottom:24px; }}
  th, td {{ text-align:left; padding:12px 10px; border-bottom:1px solid rgba(148,163,184,0.15); font-size:14px; }}
  th {{ color:#94a3b8; font-weight:600; font-size:12px; text-transform:uppercase; }}
  .total {{ font-size:18px; font-weight:700; color:#38bdf8; text-align:right; }}
  .actions {{ margin-top:24px; display:flex; gap:12px; }}
  button {{ background:#2563eb; color:#fff; border:none; border-radius:8px; padding:10px 18px; cursor:pointer; font-weight:600; }}
  @media print {{ body {{ background:#fff; color:#111; }} .sheet {{ background:#fff; border:1px solid #ddd; }} .actions {{ display:none; }} }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="head">
      <div>
        <div class="brand">{esc(brand['app_name'])}</div>
        <div class="sub">by {esc(brand['company_name'])} · Payment Receipt</div>
      </div>
      <div class="badge">{esc(order.status)}</div>
    </div>
    <div class="grid">
      <div><div class="label">Receipt Number</div><div><strong>{esc(order.receipt_number)}</strong></div></div>
      <div><div class="label">Payment Date</div><div>{esc(paid_dt)}</div></div>
      <div><div class="label">Billed To</div><div>{esc(user.full_name or user.email)}<br><span style="color:#94a3b8;">{esc(user.email)}</span></div></div>
      <div><div class="label">Razorpay References</div><div>Order: {esc(order.razorpay_order_id or 'N/A')}<br>Payment: {esc(order.razorpay_payment_id or 'N/A')}</div></div>
    </div>
    <table>
      <thead><tr><th>Plan / Service</th><th>Billing Cycle</th><th>Method</th><th style="text-align:right;">Amount</th></tr></thead>
      <tbody>
        <tr>
          <td><strong>{esc(plan.name)}</strong><br><span style="color:#94a3b8;font-size:12px;">{plan.daily_request_limit:,}/day · {plan.monthly_request_limit:,}/cycle · {plan.rate_limit_per_minute} req/min</span></td>
          <td>{plan.billing_cycle_days} days ({esc(order.action)})</td>
          <td>{esc((order.payment_method or 'Razorpay').upper())}</td>
          <td style="text-align:right;">{esc(amount_str)}</td>
        </tr>
      </tbody>
    </table>
    <div class="total">Total Paid ({esc(order.currency)}): {esc(amount_str)}</div>
    <div class="actions"><button onclick="window.print()">Print / Save as PDF</button></div>
  </div>
</body>
</html>"""

