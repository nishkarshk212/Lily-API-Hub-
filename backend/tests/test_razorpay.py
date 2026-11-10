"""Razorpay Payment Gateway tests: Order creation, HMAC verification, webhooks, idempotency, receipts."""

import hashlib
import hmac
import json

from app.models.api_key import ApiKey
from app.models.payment import PaymentOrder
from app.models.plan import Subscription


def _sign_checkout(order_id: str, payment_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def _sign_webhook(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def test_razorpay_checkout_hmac_and_webhook_idempotency(client, test_env, monkeypatch):
    client.post(
        "/api/auth/register",
        json={"email": "buyer@example.com", "password": "Password123", "full_name": "Buyer Pro"},
    )
    plans = client.get("/api/plans").json()
    pro_plan = next(p for p in plans if p["slug"] == "pro-velocity")

    async def fake_razorpay_api(method, path, json_payload=None, settings=None):
        if method == "POST" and path == "/orders":
            return {"id": "order_RzpTest001", "amount": pro_plan["price_paise"], "currency": "INR"}
        if method == "GET" and path.startswith("/payments/"):
            return {
                "id": "pay_RzpTest001",
                "order_id": "order_RzpTest001",
                "amount": pro_plan["price_paise"],
                "status": "captured",
                "method": "upi",
            }
        raise AssertionError(f"Unexpected Razorpay call: {method} {path}")

    monkeypatch.setattr("app.services.razorpay_service.razorpay_api_request", fake_razorpay_api)

    # 1. Create order from authoritative DB price
    order_resp = client.post("/api/payments/create-order", json={"plan_id": pro_plan["id"], "action": "new"})
    assert order_resp.status_code == 200
    order_data = order_resp.json()
    assert order_data["razorpay_order_id"] == "order_RzpTest001"
    assert order_data["amount_paise"] == pro_plan["price_paise"]

    # 2. Tampered signature MUST be rejected (400) and NOT issue any API key
    bad_verify = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": "order_RzpTest001",
            "razorpay_payment_id": "pay_RzpTest001",
            "razorpay_signature": "0" * 64,
        },
    )
    assert bad_verify.status_code == 400
    assert len(client.get("/api/keys").json()["keys"]) == 0

    # 3. Valid HMAC-SHA256 signature succeeds & auto-generates unique API key
    good_sig = _sign_checkout("order_RzpTest001", "pay_RzpTest001", "rzp_test_secret_abc987")
    ok_verify = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": "order_RzpTest001",
            "razorpay_payment_id": "pay_RzpTest001",
            "razorpay_signature": good_sig,
        },
    )
    assert ok_verify.status_code == 200
    verify_json = ok_verify.json()
    assert verify_json["status"] == "successful"
    assert verify_json["api_key"]["key_prefix"].startswith("lily_live_")
    payment_record_id = verify_json["payment_id"]

    # 4. Receipt HTML & JSON downloadable
    rcpt_html = client.get(f"/api/payments/{payment_record_id}/receipt?format=html")
    assert rcpt_html.status_code == 200
    assert verify_json["receipt_number"] in rcpt_html.text

    rcpt_json = client.get(f"/api/payments/{payment_record_id}/receipt?format=json")
    assert rcpt_json.status_code == 200
    assert rcpt_json.json()["payment_method"] == "upi"

    # 5. Webhook verification: invalid signature rejected
    webhook_payload = json.dumps(
        {
            "event": "payment.captured",
            "created_at": 1762780000,
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_RzpTest001",
                        "order_id": "order_RzpTest001",
                        "amount": pro_plan["price_paise"],
                        "method": "upi",
                    }
                }
            },
        }
    ).encode("utf-8")

    bad_wh = client.post(
        "/api/payments/webhook/razorpay",
        content=webhook_payload,
        headers={"X-Razorpay-Signature": "bad_sig", "X-Razorpay-Event-Id": "evt_001"},
    )
    assert bad_wh.status_code == 401

    # Valid webhook after /verify does NOT create duplicate API keys or subscriptions
    good_wh_sig = _sign_webhook(webhook_payload, "rzp_webhook_secret_xyz654")
    wh1 = client.post(
        "/api/payments/webhook/razorpay",
        content=webhook_payload,
        headers={"X-Razorpay-Signature": good_wh_sig, "X-Razorpay-Event-Id": "evt_001"},
    )
    assert wh1.status_code == 200
    assert wh1.json()["result"] == "already_fulfilled"

    # Duplicate webhook event_id ignored idempotently
    wh2 = client.post(
        "/api/payments/webhook/razorpay",
        content=webhook_payload,
        headers={"X-Razorpay-Signature": good_wh_sig, "X-Razorpay-Event-Id": "evt_001"},
    )
    assert wh2.status_code == 200
    assert wh2.json()["status"] == "duplicate_ignored"

    with test_env() as db:
        assert db.query(Subscription).count() == 1
        assert db.query(ApiKey).count() == 1
        assert db.query(PaymentOrder).filter(PaymentOrder.status == "successful").count() == 1


def test_webhook_fulfills_when_browser_closed_before_verify(client, test_env, monkeypatch):
    client.post(
        "/api/auth/register",
        json={"email": "upiuser@example.com", "password": "Password123", "full_name": "UPI User"},
    )
    plans = client.get("/api/plans").json()
    starter = next(p for p in plans if p["slug"] == "starter-pulse")

    async def fake_create(method, path, json_payload=None, settings=None):
        return {"id": "order_UpiDrop002", "amount": starter["price_paise"], "currency": "INR"}

    monkeypatch.setattr("app.services.razorpay_service.razorpay_api_request", fake_create)
    client.post("/api/payments/create-order", json={"plan_id": starter["id"], "action": "new"})

    # Webhook arrives without frontend /verify ever running
    wh_body = json.dumps(
        {
            "event": "order.paid",
            "created_at": 1762780500,
            "payload": {
                "order": {"entity": {"id": "order_UpiDrop002", "amount_paid": starter["price_paise"]}},
                "payment": {"entity": {"id": "pay_UpiDrop002", "order_id": "order_UpiDrop002", "amount": starter["price_paise"], "method": "netbanking"}},
            },
        }
    ).encode("utf-8")
    wh_sig = _sign_webhook(wh_body, "rzp_webhook_secret_xyz654")
    res = client.post(
        "/api/payments/webhook/razorpay",
        content=wh_body,
        headers={"X-Razorpay-Signature": wh_sig, "X-Razorpay-Event-Id": "evt_upi_002"},
    )
    assert res.status_code == 200
    assert res.json()["result"] == "fulfilled"

    keys = client.get("/api/keys").json()["keys"]
    assert len(keys) == 1
    assert keys[0]["status"] == "active"

    # Refund webhook revokes subscription & key
    refund_body = json.dumps(
        {
            "event": "payment.refunded",
            "created_at": 1762780900,
            "payload": {"payment": {"entity": {"id": "pay_UpiDrop002", "order_id": "order_UpiDrop002"}}},
        }
    ).encode("utf-8")
    refund_sig = _sign_webhook(refund_body, "rzp_webhook_secret_xyz654")
    ref_res = client.post(
        "/api/payments/webhook/razorpay",
        content=refund_body,
        headers={"X-Razorpay-Signature": refund_sig, "X-Razorpay-Event-Id": "evt_ref_002"},
    )
    assert ref_res.status_code == 200
    assert client.get("/api/keys").json()["keys"][0]["status"] == "revoked"


def test_razorpay_renewal_cancel_and_reconciliation(client, test_env, monkeypatch):
    client.post(
        "/api/auth/register",
        json={"email": "renew@example.com", "password": "Password123", "full_name": "Renew User"},
    )
    plans = client.get("/api/plans").json()
    starter = next(p for p in plans if p["slug"] == "starter-pulse")

    order_counter = {"n": 0}

    async def fake_rzp(method, path, json_payload=None, settings=None):
        if method == "POST" and path == "/orders":
            order_counter["n"] += 1
            return {"id": f"order_Renew_{order_counter['n']}", "amount": starter["price_paise"], "currency": "INR"}
        if method == "GET" and path.endswith("/payments"):
            return {
                "items": [
                    {
                        "id": "pay_Reconciled_3",
                        "order_id": "order_Renew_3",
                        "amount": starter["price_paise"],
                        "status": "captured",
                        "method": "card",
                    }
                ]
            }
        if method == "GET" and path.startswith("/payments/"):
            pid = path.split("/")[-1]
            oid = "order_Renew_1" if pid == "pay_Renew_1" else "order_Renew_2"
            return {"id": pid, "order_id": oid, "amount": starter["price_paise"], "status": "captured", "method": "upi"}
        raise AssertionError(f"Unexpected call {method} {path}")

    monkeypatch.setattr("app.services.razorpay_service.razorpay_api_request", fake_rzp)

    # 1. Initial purchase
    o1 = client.post("/api/payments/create-order", json={"plan_id": starter["id"], "action": "new"}).json()
    s1 = _sign_checkout(o1["razorpay_order_id"], "pay_Renew_1", "rzp_test_secret_abc987")
    v1 = client.post(
        "/api/payments/verify",
        json={"razorpay_order_id": o1["razorpay_order_id"], "razorpay_payment_id": "pay_Renew_1", "razorpay_signature": s1},
    )
    assert v1.status_code == 200
    exp_before = client.get("/api/subscriptions/current").json()["subscription"]["expires_at"]

    # 2. Renewal extends expiry by billing_cycle_days without revoking existing key
    o2 = client.post("/api/payments/create-order", json={"plan_id": starter["id"], "action": "renew"}).json()
    s2 = _sign_checkout(o2["razorpay_order_id"], "pay_Renew_2", "rzp_test_secret_abc987")
    v2 = client.post(
        "/api/payments/verify",
        json={"razorpay_order_id": o2["razorpay_order_id"], "razorpay_payment_id": "pay_Renew_2", "razorpay_signature": s2},
    )
    assert v2.status_code == 200
    exp_after = client.get("/api/subscriptions/current").json()["subscription"]["expires_at"]
    assert exp_after > exp_before

    # 3. Pending order -> reconcile recovers captured payment
    o3 = client.post("/api/payments/create-order", json={"plan_id": starter["id"], "action": "renew"}).json()
    rec = client.post(f"/api/payments/reconcile/{o3['payment_record_id']}")
    assert rec.status_code == 200
    assert rec.json()["reconciled_status"] == "successful"

    # 4. Cancelled checkout marks order cancelled
    o4 = client.post("/api/payments/create-order", json={"plan_id": starter["id"], "action": "renew"}).json()
    can = client.post("/api/payments/cancel", json={"razorpay_order_id": o4["razorpay_order_id"], "reason": "Dismissed"})
    assert can.status_code == 200
    assert can.json()["status"] == "cancelled"

