"""Gateway middleware tests: key validation, quotas, rate limits, expiry, revocation, Master proxy isolation."""

from datetime import timedelta

from app.core.security import utc_now
from app.models.gateway import MasterGatewayConfig
from app.models.plan import Subscription, SubscriptionPlan


def _register_and_activate_free(client):
    client.post(
        "/api/auth/register",
        json={"email": "gwuser@example.com", "password": "Password123", "full_name": "GW User"},
    )
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    act = client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}")
    assert act.status_code == 200
    key_id = act.json()["api_key"]["id"]
    revealed = client.get(f"/api/keys/{key_id}/reveal").json()["api_key"]
    return free_plan, key_id, revealed


def test_gateway_key_management_and_builtin_endpoints(client):
    _, key_id, raw_key = _register_and_activate_free(client)

    # Duplicate free claim is blocked
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    assert client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}").status_code == 409

    # Missing key -> 401
    assert client.get("/v1/status").status_code == 401

    # Invalid key -> 401
    assert client.get("/v1/status", headers={"X-API-Key": "beta_live_invalid_key"}).status_code == 401

    # Root /v1 without trailing slash responds directly without 307 redirect
    root_v1 = client.get("/v1", headers={"X-API-Key": raw_key}, follow_redirects=False)
    assert root_v1.status_code == 200
    assert root_v1.json()["status"] == "operational"

    # Valid key -> 200 + quota headers + master link tag (NEVER exposing raw MASTER_API_KEY)
    resp = client.get("/v1/status", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "operational"
    assert "sn_master_ultra_secret_test_key_9988" not in resp.text
    assert "X-Quota-Daily-Remaining" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers

    # Free Sandbox only permits GET,POST -> DELETE must be blocked (403)
    denied_method = client.delete("/v1/network/echo", headers={"Authorization": f"Bearer {raw_key}"})
    assert denied_method.status_code == 403
    assert denied_method.json()["error"] == "METHOD_NOT_ALLOWED_FOR_PLAN"

    # Playground executes through real gateway
    pg = client.post(
        "/api/playground/execute",
        json={
            "api_key_id": key_id,
            "method": "POST",
            "endpoint": "/v1/crypto/hash",
            "body": {"text": "sonic", "algorithm": "sha256"},
        },
    )
    assert pg.status_code == 200
    assert pg.json()["status_code"] == 200
    assert len(pg.json()["body"]["digest_hex"]) == 64

    # Regenerate rotates secret immediately
    regen = client.post(f"/api/keys/{key_id}/regenerate")
    assert regen.status_code == 200
    new_key = regen.json()["api_key"]
    assert new_key != raw_key
    assert client.get("/v1/status", headers={"X-API-Key": raw_key}).status_code == 401
    assert client.get("/v1/status", headers={"X-API-Key": new_key}).status_code == 200

    # Revoke blocks immediately
    assert client.post(f"/api/keys/{key_id}/revoke").status_code == 200
    revoked_call = client.get("/v1/status", headers={"X-API-Key": new_key})
    assert revoked_call.status_code == 403
    assert revoked_call.json()["error"] == "KEY_REVOKED"


def test_quota_rate_limit_and_auto_expiry_enforcement(client, test_env):
    free_plan, _, raw_key = _register_and_activate_free(client)

    with test_env() as db:
        plan = db.get(SubscriptionPlan, free_plan["id"])
        plan.daily_request_limit = 3
        plan.rate_limit_per_minute = 2
        db.commit()

    # 2 calls succeed, 3rd hits rate limit (2/min)
    assert client.get("/v1/utils/timestamp", headers={"X-API-Key": raw_key}).status_code == 200
    assert client.get("/v1/utils/timestamp", headers={"X-API-Key": raw_key}).status_code == 200
    rl_resp = client.get("/v1/utils/timestamp", headers={"X-API-Key": raw_key})
    assert rl_resp.status_code == 429
    assert rl_resp.json()["error"] == "RATE_LIMIT_EXCEEDED"

    # Raise rate limit and test daily quota cap (3/day; 2 already consumed -> 1 left, then 429)
    with test_env() as db:
        plan = db.get(SubscriptionPlan, free_plan["id"])
        plan.rate_limit_per_minute = 100
        db.commit()

    assert client.get("/v1/utils/timestamp", headers={"X-API-Key": raw_key}).status_code == 200
    dq_resp = client.get("/v1/utils/timestamp", headers={"X-API-Key": raw_key})
    assert dq_resp.status_code == 429
    assert dq_resp.json()["error"] == "DAILY_QUOTA_EXCEEDED"

    # Simulate subscription past expiry date -> auto-expires on gateway call (403 SUBSCRIPTION_EXPIRED)
    with test_env() as db:
        sub = db.query(Subscription).first()
        sub.expires_at = utc_now() - timedelta(minutes=5)
        db.commit()

    exp_resp = client.get("/v1/utils/timestamp", headers={"X-API-Key": raw_key})
    assert exp_resp.status_code == 403
    assert exp_resp.json()["error"] == "SUBSCRIPTION_EXPIRED"


def test_upstream_master_proxy_injection(client, test_env, monkeypatch):
    _, _, raw_key = _register_and_activate_free(client)
    captured_headers = {}

    with test_env() as db:
        gw = db.get(MasterGatewayConfig, 1)
        gw.gateway_mode = "hybrid"
        gw.upstream_base_url = "https://upstream.sonic-internal.test"
        db.commit()

    import httpx

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, content=None):
            captured_headers.update(headers or {})
            return httpx.Response(
                200,
                json={"upstream": "ok", "received_url": url},
                headers={"content-type": "application/json"},
            )

    monkeypatch.setattr("app.services.gateway_service.httpx.AsyncClient", MockAsyncClient)

    resp = client.get("/v1/custom/orders?limit=5", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    assert resp.json()["upstream"] == "ok"
    assert resp.headers["X-Gateway-Mode"] == "proxy"
    # Master API key injected upstream while customer key is stripped!
    assert captured_headers.get("Authorization") == "Bearer sn_master_ultra_secret_test_key_9988"
    assert "x-api-key" not in {k.lower() for k in captured_headers.keys()}
    # Master API key NEVER appears in response returned to client
    assert "sn_master_ultra_secret_test_key_9988" not in resp.text


def test_max_api_keys_limit_and_frontend_assets(client):
    # Check SPA & static assets load cleanly
    assert client.get("/").status_code == 200
    assert "Beta API Hub" in client.get("/").text
    assert client.get("/favicon.svg").status_code == 200
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/css/tokens.css").status_code == 200
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/healthz").json()["status"] == "ok"

    # Register & activate Free Sandbox (max_api_keys = 1)
    _, _, _ = _register_and_activate_free(client)
    create_second = client.post("/api/keys", json={"name": "Second Key"})
    assert create_second.status_code == 403
    assert "allows up to 1 active API keys" in create_second.json()["detail"]

    # Public support ticket submission
    sup = client.post(
        "/api/public/support",
        json={
            "name": "Dev Support",
            "email": "gwuser@example.com",
            "subject": "Need higher burst rate",
            "message": "Please enable 2000 req/min on our enterprise workspace.",
        },
    )
    assert sup.status_code == 200
    assert "ticket_id" in sup.json()

