"""Admin RBAC isolation, user suspension, plan management, and Master API config masking tests."""


def test_admin_rbac_and_controls(client):
    # Register normal user
    client.post(
        "/api/auth/register",
        json={"email": "normal@example.com", "password": "Password123", "full_name": "Normal Dev"},
    )
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    act = client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}")
    key_id = act.json()["api_key"]["id"]
    raw_key = client.get(f"/api/keys/{key_id}/reveal").json()["api_key"]
    user_id = client.get("/api/auth/me").json()["user"]["id"]

    # Normal user blocked from admin endpoints (403)
    assert client.get("/api/admin/analytics").status_code == 403
    assert client.get("/api/admin/master-config").status_code == 403

    # Separate admin login rejects normal user
    assert (
        client.post("/api/admin/login", json={"email": "normal@example.com", "password": "Password123"}).status_code
        == 403
    )

    # Admin login succeeds
    adm_login = client.post(
        "/api/admin/login",
        json={"email": "admin@sonicnetwork.dev", "password": "SonicAdmin!2026"},
    )
    assert adm_login.status_code == 200
    assert adm_login.json()["user"]["role"] == "admin"

    # Admin master config NEVER returns plaintext master key
    mc = client.get("/api/admin/master-config").json()
    assert mc["has_master_key"] is True
    assert "sn_master_ultra_secret_test_key_9988" not in str(mc)

    # Admin creates a new plan
    new_plan = client.post(
        "/api/admin/plans",
        json={
            "name": "Turbo Custom",
            "slug": "turbo-custom",
            "tagline": "Custom tier",
            "price_paise": 299900,
            "currency": "INR",
            "billing_cycle_days": 30,
            "daily_request_limit": 80000,
            "monthly_request_limit": 2000000,
            "rate_limit_per_minute": 500,
            "max_api_keys": 8,
            "allowed_methods": "GET,POST,PUT",
            "allowed_endpoints": "*",
            "features_json": ["2M calls/month"],
            "is_active": True,
            "is_featured": False,
            "sort_order": 5,
        },
    )
    assert new_plan.status_code == 201
    assert any(p["slug"] == "turbo-custom" for p in client.get("/api/plans").json())

    # Admin suspends normal user -> user's gateway API key immediately fails with 403
    susp = client.patch(
        f"/api/admin/users/{user_id}",
        json={"is_suspended": True, "suspension_reason": "Abuse investigation"},
    )
    assert susp.status_code == 200
    gw_check = client.get("/v1/status", headers={"X-API-Key": raw_key})
    assert gw_check.status_code == 403
    assert gw_check.json()["error"] == "ACCOUNT_SUSPENDED"


def test_database_url_normalization_and_vercel_entry():
    from app.core.config import normalize_database_url
    from api.index import app as vercel_app

    assert normalize_database_url("postgres://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url("sqlite:///./lily_hub.db") == "sqlite:///./lily_hub.db"
    assert vercel_app is not None


def test_admin_branding_override_and_reset(client):
    adm = client.post(
        "/api/admin/login",
        json={"email": "admin@sonicnetwork.dev", "password": "SonicAdmin!2026"},
    )
    assert adm.status_code == 200

    initial = client.get("/api/admin/branding")
    assert initial.status_code == 200
    default_app_name = initial.json()["app_name"]
    assert initial.json()["has_db_override"] is False

    upd = client.put(
        "/api/admin/branding",
        json={
            "app_name": "Nova API Cloud",
            "company_name": "Nova Labs",
            "brand_badge_letter": "N",
            "support_email": "help@novacloud.io",
            "site_description": "Custom Nova API gateway platform",
            "api_key_prefix_live": "nova_live_",
            "api_key_prefix_test": "nova_test_",
            "receipt_prefix": "NOVA",
        },
    )
    assert upd.status_code == 200
    assert upd.json()["branding"]["has_db_override"] is True
    assert upd.json()["branding"]["app_name"] == "Nova API Cloud"

    ov = client.get("/api/public/overview")
    assert ov.status_code == 200
    ov_data = ov.json()
    assert ov_data["brand"] == "Nova API Cloud"
    assert ov_data["company"] == "Nova Labs"
    assert ov_data["brand_letter"] == "N"
    assert ov_data["support_email"] == "help@novacloud.io"
    assert ov_data["key_prefix_live"] == "nova_live_"
    assert ov_data["key_prefix_test"] == "nova_test_"

    spa = client.get("/")
    assert spa.status_code == 200
    assert "<title>Nova API Cloud by Nova Labs" in spa.text
    assert "Custom Nova API gateway platform" in spa.text

    fav = client.get("/favicon.svg")
    assert fav.status_code == 200
    assert ">N</text>" in fav.text

    # Developer signup + free key uses updated prefix and /v1/status reflects custom branding
    client.post(
        "/api/auth/register",
        json={"email": "nova-dev@example.com", "password": "Password123", "full_name": "Nova Dev"},
    )
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    act = client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}")
    assert act.status_code == 200
    key_id = act.json()["api_key"]["id"]
    raw_key = client.get(f"/api/keys/{key_id}/reveal").json()["api_key"]
    assert raw_key.startswith("nova_")

    st = client.get("/v1/status", headers={"X-API-Key": raw_key})
    assert st.status_code == 200
    assert st.json()["service"] == "Nova API Cloud Gateway"
    assert st.json()["provider"] == "Nova Labs"

    # Re-login as admin and reset branding back to .env defaults
    client.post(
        "/api/admin/login",
        json={"email": "admin@sonicnetwork.dev", "password": "SonicAdmin!2026"},
    )
    rst = client.post("/api/admin/branding/reset")
    assert rst.status_code == 200
    assert rst.json()["branding"]["has_db_override"] is False
    assert rst.json()["branding"]["app_name"] == default_app_name
    assert client.get("/api/public/overview").json()["brand"] == default_app_name



