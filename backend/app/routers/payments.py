"""Razorpay Checkout order creation, HMAC verification, webhook processing, history, and receipts."""

import html

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.payment import PaymentOrder
from app.models.plan import SubscriptionPlan
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.domain import (
    CancelOrderRequest,
    CreateOrderRequest,
    MarkFailedRequest,
    VerifyPaymentRequest,
)
from app.services.key_service import serialize_api_key
from app.services.razorpay_service import (
    create_razorpay_order_for_user,
    format_inr,
    handle_razorpay_webhook,
    reconcile_payment_order,
    render_receipt_html,
    verify_razorpay_checkout_payment,
)
from app.services.telegram_service import notify_user_telegram

router = APIRouter(prefix="/api/payments", tags=["Payments & Razorpay"])


@router.get("/config")
def get_payment_config():
    cfg = get_settings()
    return {
        "razorpay_configured": cfg.razorpay_configured,
        "key_id": cfg.RAZORPAY_KEY_ID.strip() if cfg.razorpay_configured else "",
        "currency": "INR",
        "mode": "live" if cfg.RAZORPAY_KEY_ID.startswith("rzp_live_") else "test",
    }


@router.post("/create-order")
async def create_order(
    payload: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = db.get(SubscriptionPlan, payload.plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription plan not found.")
    return await create_razorpay_order_for_user(db, user, plan, action=payload.action)


@router.post("/verify")
async def verify_payment(
    payload: VerifyPaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order, sub, api_key = await verify_razorpay_checkout_payment(
        db,
        user=user,
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
        fetch_remote=True,
    )
    try:
        plan = db.get(SubscriptionPlan, order.plan_id)
        await notify_user_telegram(
            db,
            user.id,
            category="payment",
            title="💳 Payment Verified & Plan Activated",
            message_lines=[
                f"Plan: <b>{html.escape(plan.name if plan else 'API Plan')}</b>",
                f"Amount: <b>{html.escape(format_inr(order.amount_paise))}</b>",
                f"Receipt: <code>{html.escape(order.receipt_number)}</code>",
            ],
        )
    except Exception:
        pass
    return {
        "status": "successful",
        "message": "Payment verified and API key provisioned.",
        "payment_id": order.id,
        "receipt_number": order.receipt_number,
        "subscription_id": sub.id,
        "api_key": serialize_api_key(api_key) if api_key else None,
    }


@router.post("/cancel")
def cancel_pending_order(
    payload: CancelOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.scalar(select(PaymentOrder).where(PaymentOrder.razorpay_order_id == payload.razorpay_order_id))
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment order not found.")
    if order.status == "pending":
        order.status = "cancelled"
        order.failure_reason = payload.reason
        db.commit()
    return {"status": order.status, "message": "Order marked as cancelled."}


@router.post("/mark-failed")
def mark_payment_failed(
    payload: MarkFailedRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.scalar(select(PaymentOrder).where(PaymentOrder.razorpay_order_id == payload.razorpay_order_id))
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment order not found.")
    if order.status == "pending":
        order.status = "failed"
        if payload.razorpay_payment_id:
            order.razorpay_payment_id = payload.razorpay_payment_id
        order.failure_reason = payload.reason
        db.commit()
    return {"status": order.status}


@router.post("/reconcile/{order_id}")
async def reconcile_my_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(PaymentOrder, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")
    return await reconcile_payment_order(db, order)


@router.get("/history")
def payment_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.scalars(
        select(PaymentOrder).where(PaymentOrder.user_id == user.id).order_by(PaymentOrder.created_at.desc())
    ).all()
    plan_ids = {o.plan_id for o in orders}
    plans = {p.id: p for p in db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.id.in_(plan_ids))).all()} if plan_ids else {}

    return {
        "payments": [
            {
                "id": o.id,
                "receipt_number": o.receipt_number,
                "plan_id": o.plan_id,
                "plan_name": plans[o.plan_id].name if o.plan_id in plans else "API Plan",
                "action": o.action,
                "razorpay_order_id": o.razorpay_order_id,
                "razorpay_payment_id": o.razorpay_payment_id,
                "amount_paise": o.amount_paise,
                "amount_display": format_inr(o.amount_paise),
                "currency": o.currency,
                "status": o.status,
                "payment_method": o.payment_method,
                "verified_via": o.verified_via,
                "failure_reason": o.failure_reason,
                "paid_at": o.paid_at,
                "created_at": o.created_at,
            }
            for o in orders
        ]
    }


@router.get("/{payment_id}/receipt")
def get_receipt(
    payment_id: str,
    format: str = Query(default="html", pattern=r"^(html|json)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(PaymentOrder, payment_id)
    if not order or (order.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")
    owner = db.get(User, order.user_id)
    plan = db.get(SubscriptionPlan, order.plan_id)

    if format == "json":
        return {
            "receipt_number": order.receipt_number,
            "status": order.status,
            "customer_name": owner.full_name,
            "customer_email": owner.email,
            "plan_name": plan.name,
            "action": order.action,
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": order.razorpay_payment_id,
            "payment_method": order.payment_method,
            "amount_paise": order.amount_paise,
            "amount_display": format_inr(order.amount_paise),
            "currency": order.currency,
            "paid_at": order.paid_at,
            "created_at": order.created_at,
        }

    return HTMLResponse(content=render_receipt_html(order, owner, plan, db))


@router.post("/webhook/razorpay")
async def razorpay_webhook_endpoint(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    event_id = request.headers.get("x-razorpay-event-id")
    return handle_razorpay_webhook(db, raw_body, signature, event_id)

