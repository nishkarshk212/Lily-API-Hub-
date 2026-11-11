"""Comprehensive Telegram Bot integration tests: onboarding, webhooks, pairing, commands, RBAC, and alerts."""

from app.core.config import get_settings
from app.models.telegram import TelegramBot
from app.services.telegram_service import TelegramApiError


def _make_fake_telegram_api(monkeypatch, calls_log=None, updates_queue=None):
    sent = calls_log if calls_log is not None else []
    queue = updates_queue if updates_queue is not None else []

    async def fake_tg_call(bot_token, method, payload=None, *, timeout_sec=15.0, settings=None):
        if bot_token.startswith("invalid"):
            raise TelegramApiError("Unauthorized", status_code=400)
        sent.append({"token": bot_token, "method": method, "payload": payload or {}})
        if method == "getMe":
            tg_id = 777001 if "custom" in bot_token else 888001
            uname = "sonic_custom_test_bot" if "custom" in bot_token else "beta_platform_test_bot"
            fname = "Sonic Custom Bot" if "custom" in bot_token else "Beta Official Bot"
            return {"id": tg_id, "is_bot": True, "first_name": fname, "username": uname}
        if method == "getWebhookInfo":
            return {"url": payload.get("url", "") if payload else "", "pending_update_count": 0}
        if method == "getUpdates":
            batch = list(queue)
            queue.clear()
            return batch
        return True

    monkeypatch.setattr("app.services.telegram_service.telegram_api_call", fake_tg_call)
    monkeypatch.setattr("app.routers.telegram.telegram_api_call", fake_tg_call)
    return sent


def test_user_connect_bot_pairing_commands_and_access_modes(client, test_env, monkeypatch):
    monkeypatch.setenv("APP_PUBLIC_URL", "https://beta.13.54.201.131.sslip.io")
    get_settings.cache_clear()
    tg_calls = _make_fake_telegram_api(monkeypatch)

    # Register developer and activate free tier so an active key exists
    reg = client.post(
        "/api/auth/register",
        json={"email": "tgdev@example.com", "password": "Password123", "full_name": "TG Dev"},
    )
    assert reg.status_code == 200
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    act = client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}")
    assert act.status_code == 200
    key_id = act.json()["api_key"]["id"]

    # Reject invalid token cleanly
    bad = client.post(
        "/api/telegram/bots",
        json={"bot_token": "invalid_000000:AAF_bad_token_123456"},
    )
    assert bad.status_code == 400

    # Connect custom bot via website (auto-picks HTTPS webhook!)
    conn = client.post(
        "/api/telegram/bots",
        json={
            "bot_token": "777001000:custom_AAF_secret_token_987654321",
            "bot_name": "My Sonic Helper",
            "api_key_id": key_id,
            "access_mode": "owner_only",
            "custom_proxy_path": "/v1/network/echo",
            "custom_proxy_method": "POST",
            "forward_plain_text": True,
        },
    )
    assert conn.status_code == 201
    bot_info = conn.json()["bot"]
    bot_id = bot_info["id"]
    pair_code = bot_info["pairing_code"]

    assert bot_info["bot_username"] == "sonic_custom_test_bot"
    assert bot_info["connection_mode"] == "webhook"
    assert bot_info["webhook_active"] is True
    assert f"/api/telegram/webhook/{bot_id}" in bot_info["webhook_url"]
    assert "custom_AAF_secret_token_987654321" not in str(bot_info)
    assert any(c["method"] == "setWebhook" for c in tg_calls)
    assert any(c["method"] == "setMyCommands" for c in tg_calls)

    # Read secret from DB to post simulated Telegram webhook updates
    with test_env() as db:
        bot_row = db.get(TelegramBot, bot_id)
        secret_hdr = bot_row.webhook_secret

    # Webhook without or with wrong secret header must be rejected (403)
    assert (
        client.post(f"/api/telegram/webhook/{bot_id}", json={"update_id": 1}).status_code == 403
    )
    assert (
        client.post(
            f"/api/telegram/webhook/{bot_id}",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            json={"update_id": 1},
        ).status_code
        == 403
    )

    # Unauthorized stranger rejected before pairing
    tg_calls.clear()
    stranger_msg = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 2,
            "message": {
                "message_id": 10,
                "from": {"id": 55555, "username": "stranger", "first_name": "Stranger"},
                "chat": {"id": 55555, "type": "private"},
                "text": "/status",
            },
        },
    )
    assert stranger_msg.status_code == 200
    assert stranger_msg.json().get("denied") is True
    assert "Owner Only" in tg_calls[-1]["payload"]["text"]

    # Owner clicks /start pair_<code> deep link
    tg_calls.clear()
    pair_res = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 3,
            "message": {
                "message_id": 11,
                "from": {"id": 10001, "username": "tgdev_owner", "first_name": "TG Dev"},
                "chat": {"id": 10001, "type": "private"},
                "text": f"/start pair_{pair_code}",
            },
        },
    )
    assert pair_res.status_code == 200
    assert pair_res.json().get("paired") is True
    assert "Bot Paired" in tg_calls[-1]["payload"]["text"]
    assert "reply_markup" in tg_calls[-1]["payload"]

    # Pairing code should rotate cleanly after pairing
    st_after = client.get("/api/telegram/status").json()
    assert st_after["bots"][0]["is_paired"] is True
    assert st_after["bots"][0]["pairing_code"] != pair_code

    # Owner executes gateway commands via Telegram webhook: /hash and plain text forward to /ask route
    tg_calls.clear()
    hash_res = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 4,
            "message": {
                "message_id": 12,
                "from": {"id": 10001, "username": "tgdev_owner"},
                "chat": {"id": 10001, "type": "private"},
                "text": "/hash sha256 hello-beta",
            },
        },
    )
    assert hash_res.status_code == 200
    assert "HTTP <b>200</b>" in tg_calls[-1]["payload"]["text"]
    assert "sha256" in tg_calls[-1]["payload"]["text"]

    tg_calls.clear()
    plain_proxy = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 5,
            "message": {
                "message_id": 13,
                "from": {"id": 10001, "username": "tgdev_owner"},
                "chat": {"id": 10001, "type": "private"},
                "text": "hello custom gateway",
            },
        },
    )
    assert plain_proxy.status_code == 200
    assert "hello custom gateway" in tg_calls[-1]["payload"]["text"]

    # Callback queries for quota & keys work cleanly
    tg_calls.clear()
    cb_quota = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 6,
            "callback_query": {
                "id": "cb_1",
                "from": {"id": 10001, "username": "tgdev_owner"},
                "message": {"message_id": 11, "chat": {"id": 10001, "type": "private"}},
                "data": "m:quota",
            },
        },
    )
    assert cb_quota.status_code == 200
    edit_calls = [c for c in tg_calls if c["method"] == "editMessageText"]
    assert edit_calls and "Quota &amp; Live Telemetry" in edit_calls[-1]["payload"]["text"]

    # Switch bot to public_gateway: stranger CAN call /time, but CANNOT open /keys or k:rev
    upd = client.patch(f"/api/telegram/bots/{bot_id}", json={"access_mode": "public_gateway"})
    assert upd.status_code == 200
    assert upd.json()["bot"]["access_mode"] == "public_gateway"

    tg_calls.clear()
    stranger_time = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 7,
            "message": {
                "message_id": 14,
                "from": {"id": 55555, "username": "stranger"},
                "chat": {"id": 55555, "type": "private"},
                "text": "/time",
            },
        },
    )
    assert stranger_time.status_code == 200
    assert "HTTP <b>200</b>" in tg_calls[-1]["payload"]["text"]

    tg_calls.clear()
    stranger_keys = client.post(
        f"/api/telegram/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_hdr},
        json={
            "update_id": 8,
            "message": {
                "message_id": 15,
                "from": {"id": 55555, "username": "stranger"},
                "chat": {"id": 55555, "type": "private"},
                "text": "/keys",
            },
        },
    )
    assert stranger_keys.status_code == 200
    assert "paired bot owner" in tg_calls[-1]["payload"]["text"]

    # Browser Simulator endpoint works without calling external Telegram API
    tg_calls.clear()
    sim = client.post(f"/api/telegram/bots/{bot_id}/simulate", json={"text": "/keys", "as_owner": True})
    assert sim.status_code == 200
    assert "API Keys Vault" in sim.json()["replies"][0]["text"]
    assert tg_calls == []

    # Security alert fires when user creates a key via website if paired & alerts enabled
    # First grant user Starter plan limits so they can create a 2nd key cleanly, or revoke/check events
    ev_res = client.get(f"/api/telegram/bots/{bot_id}/events")
    assert ev_res.status_code == 200
    assert len(ev_res.json()["events"]) >= 4

    # Delete bot cleanly triggers deleteWebhook
    tg_calls.clear()
    dele = client.delete(f"/api/telegram/bots/{bot_id}")
    assert dele.status_code == 200
    assert any(c["method"] == "deleteWebhook" for c in tg_calls)
    assert client.get("/api/telegram/status").json()["bots"] == []


def test_platform_bot_admin_linking_alerts_polling_and_broadcast(client, test_env, monkeypatch):
    # Force local HTTP mode -> Polling mode auto-selected
    monkeypatch.setenv("APP_PUBLIC_URL", "http://localhost:8000")
    get_settings.cache_clear()
    queue = []
    tg_calls = _make_fake_telegram_api(monkeypatch, updates_queue=queue)

    # Admin connects Official Platform Bot
    assert (
        client.post(
            "/api/admin/login",
            json={"email": "admin@sonicnetwork.dev", "password": "SonicAdmin!2026"},
        ).status_code
        == 200
    )
    setup = client.put(
        "/api/admin/telegram/platform-bot",
        json={
            "bot_token": "888001000:platform_AAF_official_bot_token_12345",
            "bot_name": "Beta Hub Official Bot",
            "welcome_message": "Welcome to Beta Official Hub!",
        },
    )
    assert setup.status_code == 200
    pbot = setup.json()["platform_bot"]
    assert pbot["is_platform_bot"] is True
    assert pbot["connection_mode"] == "polling"

    # Verify /api/public/overview reports platform bot enabled
    overview = client.get("/api/public/overview").json()
    assert overview["telegram_platform_bot_enabled"] is True
    assert overview["telegram_platform_bot_username"] == "beta_platform_test_bot"

    # Unlinked stranger on Platform Bot CANNOT run /status (blocked until account linked)
    queue.append(
        {
            "update_id": 499,
            "message": {
                "message_id": 1,
                "from": {"id": 444444, "username": "unlinked_guy", "first_name": "Unlinked"},
                "chat": {"id": 444444, "type": "private"},
                "text": "/status",
            },
        }
    )
    tg_calls.clear()
    unlinked_poll = client.post("/api/admin/telegram/platform-bot/poll")
    assert unlinked_poll.status_code == 200
    assert any("Link your Beta account first" in c["payload"].get("text", "") for c in tg_calls if c["method"] == "sendMessage")

    # Admin logs out, normal user registers & requests platform link token
    client.post("/api/auth/logout")
    reg = client.post(
        "/api/auth/register",
        json={"email": "alertuser@example.com", "password": "Password123", "full_name": "Alert User"},
    )
    assert reg.status_code == 200

    st = client.get("/api/telegram/status").json()
    assert st["platform_bot"]["configured"] is True
    assert st["platform_bot"]["linked"] is False
    link_cmd = st["platform_bot"]["manual_link_command"]
    assert link_cmd.startswith("/link ")

    # Simulate polling pickup of user sending /start link_...
    deep_code = link_cmd.split(" ", 1)[1]
    queue.append(
        {
            "update_id": 500,
            "message": {
                "message_id": 1,
                "from": {"id": 998877, "username": "alert_dev", "first_name": "Alert"},
                "chat": {"id": 998877, "type": "private"},
                "text": f"/start link_{deep_code}",
            },
        }
    )

    # Also test admin poll endpoint processes the queued update cleanly
    client.post("/api/auth/logout")
    client.post("/api/admin/login", json={"email": "admin@sonicnetwork.dev", "password": "SonicAdmin!2026"})
    poll = client.post("/api/admin/telegram/platform-bot/poll")
    assert poll.status_code == 200
    assert poll.json()["processed_count"] == 1
    assert any("Account Linked!" in c["payload"].get("text", "") for c in tg_calls if c["method"] == "sendMessage")

    # Broadcast message reaches linked user
    tg_calls.clear()
    bcast = client.post(
        "/api/admin/telegram/platform-bot/broadcast",
        json={"message": "🚀 New endpoint launched on Beta API Hub!", "test_only": False},
    )
    assert bcast.status_code == 200
    assert bcast.json()["sent"] == 1
    assert any("New endpoint launched" in c["payload"].get("text", "") for c in tg_calls if c["method"] == "sendMessage")

    # Log back in as alertuser, check linked state, toggle preference, trigger key event notification!
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "alertuser@example.com", "password": "Password123"})
    st2 = client.get("/api/telegram/status").json()
    assert st2["platform_bot"]["linked"] is True

    pref = client.patch("/api/telegram/platform/preferences", json={"notify_security_alerts": True})
    assert pref.status_code == 200

    # Create free plan + test key revoke notification & 80% quota alert
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    act = client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}")
    key_id = act.json()["api_key"]["id"]

    tg_calls.clear()
    rev = client.post(f"/api/keys/{key_id}/revoke")
    assert rev.status_code == 200
    assert any("API Key Revoked" in c["payload"].get("text", "") for c in tg_calls if c["method"] == "sendMessage")

    # Test 80%+ quota milestone alert trigger cleanly
    from app.core.security import utc_now
    from app.models.api_key import ApiKey
    from app.models.plan import Subscription

    with test_env() as db:
        sub = db.query(Subscription).order_by(Subscription.created_at.desc()).first()
        sub.status = "active"
        sub.daily_requests_used = 159  # daily_request_limit for Free Sandbox is 200 -> next hit is 160 (80%)
        sub.daily_usage_date = utc_now().strftime("%Y-%m-%d")
        krow = db.get(ApiKey, key_id)
        krow.status = "active"
        db.commit()
    raw_after = client.get(f"/api/keys/{key_id}/reveal").json()["api_key"]
    tg_calls.clear()
    st_call = client.get("/v1/status", headers={"X-API-Key": raw_after})
    assert st_call.status_code == 200
    assert any("80%+ Quota Threshold" in c["payload"].get("text", "") for c in tg_calls if c["method"] == "sendMessage")
