"""Authentication lifecycle tests: register, verify email, login, sessions, password reset, logout."""

from urllib.parse import parse_qs, urlparse


def test_full_auth_lifecycle(client):
    # Optional session endpoint returns unauthenticated cleanly without 401
    opt = client.get("/api/auth/session")
    assert opt.status_code == 200
    assert opt.json()["authenticated"] is False

    # Protected endpoint requires authentication
    unauth = client.get("/api/auth/me")
    assert unauth.status_code == 401

    # Register new user
    reg = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "password": "Password123",
            "full_name": "Alice Developer",
            "company": "Sonic Labs",
        },
    )
    assert reg.status_code == 200
    reg_data = reg.json()
    assert reg_data["user"]["email"] == "alice@example.com"
    assert reg_data["user"]["is_email_verified"] is False
    hint = reg_data["dev_verification_hint"]
    verify_token = parse_qs(urlparse(hint.replace("/#", "/")).query)["token"][0]

    # Duplicate email returns 409
    dup = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "Password123", "full_name": "Alice"},
    )
    assert dup.status_code == 409

    # Authenticated /me works
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["full_name"] == "Alice Developer"

    # Verify email token (single-use)
    ver = client.post("/api/auth/verify-email", json={"token": verify_token})
    assert ver.status_code == 200
    assert ver.json()["user"]["is_email_verified"] is True

    ver_again = client.post("/api/auth/verify-email", json={"token": verify_token})
    assert ver_again.status_code == 400

    # Update profile
    prof = client.patch(
        "/api/auth/profile",
        json={"full_name": "Alice Updated", "company": "Sonic Core", "phone": "+919999999999"},
    )
    assert prof.status_code == 200
    assert prof.json()["user"]["company"] == "Sonic Core"

    # Logout revokes session cookie server-side
    out = client.post("/api/auth/logout")
    assert out.status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    # Login again
    login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "Password123"})
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    # Forgot & Reset password revokes existing sessions
    forgot = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert forgot.status_code == 200
    reset_hint = forgot.json()["dev_reset_hint"]
    reset_token = parse_qs(urlparse(reset_hint.replace("/#", "/")).query)["token"][0]

    reset = client.post("/api/auth/reset-password", json={"token": reset_token, "new_password": "NewPassword456"})
    assert reset.status_code == 200

    # Prior session must now be invalidated
    assert client.get("/api/auth/me").status_code == 401

    # Login with new password succeeds
    login_new = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "NewPassword456"})
    assert login_new.status_code == 200


def test_google_oauth_flow_and_state_validation(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
    from app.core.config import get_settings
    get_settings.cache_clear()

    # 1. Start OAuth redirect and extract signed state parameter
    login_redir = client.get("/api/auth/google/login", follow_redirects=False)
    assert login_redir.status_code == 307
    location = login_redir.headers["location"]
    assert "accounts.google.com/o/oauth2/v2/auth" in location
    state_val = parse_qs(urlparse(location).query)["state"][0]

    # 2. Invalid state rejected cleanly
    bad_cb = client.get("/api/auth/google/callback?code=fake&state=tampered", follow_redirects=False)
    assert bad_cb.status_code == 307
    assert "auth_error=invalid_oauth_state" in bad_cb.headers["location"]

    # 3. Valid callback exchanges code, creates verified user, and sets session cookie
    import httpx

    class MockGoogleClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data=None):
            return httpx.Response(200, json={"access_token": "google_access_tok_123"})

        async def get(self, url, headers=None):
            return httpx.Response(
                200,
                json={
                    "sub": "google-sub-999111",
                    "email": "oauthdev@sonic.dev",
                    "email_verified": True,
                    "name": "OAuth Builder",
                    "picture": "https://example.com/avatar.png",
                },
            )

    monkeypatch.setattr("app.services.auth_service.httpx.AsyncClient", MockGoogleClient)
    ok_cb = client.get(f"/api/auth/google/callback?code=authcode123&state={state_val}", follow_redirects=False)
    assert ok_cb.status_code == 307
    assert ok_cb.headers["location"] == "/#dashboard"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "oauthdev@sonic.dev"
    assert me.json()["user"]["is_email_verified"] is True
    assert me.json()["user"]["auth_provider"] == "google"


