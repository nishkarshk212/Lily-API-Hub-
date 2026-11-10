# Production Deployment Guide — Lily API Hub by Sonic Network

## 1. Environment Variables & Secrets Checklist

Copy `.env.example` to `.env` and set strong random secrets:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Required production values:
- `APP_ENV=production`
- `APP_PUBLIC_URL=https://api.yourdomain.com`
- `COOKIE_SECURE=true`
- `CORS_ORIGINS=https://api.yourdomain.com`
- `DATABASE_URL=postgresql+psycopg://lily_user:STRONG_PASSWORD@db:5432/lily_hub`
- `INITIAL_ADMIN_EMAIL` & `INITIAL_ADMIN_PASSWORD` (rotate right after first login)
- `MASTER_API_KEY` & `UPSTREAM_API_BASE_URL` (your backend master API service)
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`

---

## 2. Master API Gateway Architecture

Lily API Hub never exposes `MASTER_API_KEY` or `UPSTREAM_API_BASE_URL` to any browser or customer endpoint:
1. Customers authenticate against `<APP_PUBLIC_URL>/v1/*` with their unique `lily_live_*` key (`X-API-Key` or `Authorization: Bearer`).
2. `app/services/gateway_service.py` checks:
   - Key hash (`SHA-256`) & active status
   - User not suspended
   - Subscription active & not expired (automatic expiration transition)
   - Plan HTTP method & endpoint permissions
   - Per-minute sliding-window rate limit
   - Atomic daily (UTC) & billing-cycle quota update
3. In `hybrid` or `proxy` mode, the gateway decrypts `MASTER_API_KEY` server-side and injects `{UPSTREAM_AUTH_HEADER}: {UPSTREAM_AUTH_SCHEME} {MASTER_API_KEY}` before forwarding to `UPSTREAM_API_BASE_URL`.
4. Administrators can rotate `MASTER_API_KEY`, change `UPSTREAM_API_BASE_URL`, switch between `hybrid`/`proxy`/`builtin`, and test upstream connectivity from **Admin Portal → Master API Config**.

---

## 3. Deploying with Docker Compose & PostgreSQL 15

```bash
cp .env.example .env
# Edit .env with production credentials
export POSTGRES_PASSWORD="use_a_strong_db_password"
docker compose up -d --build
```

Check container health:
```bash
docker compose ps
curl -s http://localhost:8000/healthz
```

---

## 4. Recommended Cloud Setup (Railway / Render + PostgreSQL + Cloudflare DNS)

Both [`render.yaml`](render.yaml) (Render Blueprint) and [`railway.toml`](railway.toml) (Railway) are pre-configured to build [`Dockerfile`](Dockerfile) cleanly with dynamic `$PORT`, `--proxy-headers`, and `/healthz` health checks.

### Option A — Deploy on Render (1-Click Blueprint)
1. Push this repository to GitHub (`.gitignore` and `.dockerignore` ensure `.env` and local `*.db` files stay excluded).
2. In **Render Dashboard → New → Blueprint**, select your repo — Render detects [`render.yaml`](render.yaml) and provisions both `lily-api-hub` (Docker) and `lily-hub-db` (PostgreSQL).
3. Fill in the prompted `sync: false` environment variables:
   - `APP_PUBLIC_URL=https://api.yourdomain.com` (or your `https://lily-api-hub.onrender.com` URL)
   - `CORS_ORIGINS=https://api.yourdomain.com`
   - `MASTER_API_KEY` (your Cloudflare Worker master secret)
   - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=https://api.yourdomain.com/api/auth/google/callback`

### Option B — Deploy on Railway
1. Push this repository to GitHub and create a **New Project → Deploy from GitHub repo** in Railway (uses [`railway.toml`](railway.toml) + [`Dockerfile`](Dockerfile)).
2. Add a **PostgreSQL** service in the same Railway project (or paste a Neon/Supabase URL) and link `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
3. Add the production environment variables (`APP_ENV=production`, `COOKIE_SECURE=true`, `SECRET_KEY`, `ENCRYPTION_KEY`, `APP_PUBLIC_URL`, `CORS_ORIGINS`, `RAZORPAY_*`, `GOOGLE_*`, `UPSTREAM_API_BASE_URL=https://your-worker.your-subdomain.workers.dev`, `MASTER_API_KEY`, `UPSTREAM_AUTH_HEADER=X-API-Key`, `UPSTREAM_AUTH_SCHEME=`, `GATEWAY_MODE=hybrid`).

### Cloudflare DNS + Worker Lockdown
1. In Cloudflare DNS, add a **CNAME** record (`api.yourdomain.com` → your Render/Railway domain) with **Proxy Status: Proxied (Orange Cloud)** and **SSL/TLS → Full (strict)**.
2. In **Google Cloud Console**, add `https://api.yourdomain.com` (Authorised JavaScript origin) and `https://api.yourdomain.com/api/auth/google/callback` (Authorised redirect URI).
3. In **Razorpay Dashboard → Webhooks**, register `https://api.yourdomain.com/api/payments/webhook/razorpay`.
4. Use a strong random master secret on your Cloudflare Worker and set it in **Admin Portal → Master API Config** so callers must authenticate through **Lily API Hub**.

---

## 5. Deploying on Vercel (Alternative Serverless Option)

Vercel serverless functions cannot persist local SQLite files, so you must attach a hosted PostgreSQL database:

1. Create a free PostgreSQL database on **Neon** or **Supabase** and copy its pooled connection string (e.g. `postgresql://...`). `app/core/config.py` automatically normalizes `postgres://` and `postgresql://` to `postgresql+psycopg://...`.
2. In **Vercel Project → Settings → Environment Variables**, add:
   - `APP_ENV=production`
   - `COOKIE_SECURE=true`
   - `APP_PUBLIC_URL=https://your-project.vercel.app`
   - `CORS_ORIGINS=https://your-project.vercel.app`
   - `DATABASE_URL=postgresql://...` (your Neon/Supabase URL)
   - `SECRET_KEY` and `ENCRYPTION_KEY` (generated above)
   - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI=https://your-project.vercel.app/api/auth/google/callback`
   - `UPSTREAM_API_BASE_URL`, `MASTER_API_KEY`, `UPSTREAM_AUTH_HEADER`, `UPSTREAM_AUTH_SCHEME`, `GATEWAY_MODE`
3. Add `https://your-project.vercel.app` (Authorised JavaScript origin) and `https://your-project.vercel.app/api/auth/google/callback` (Authorised redirect URI) in Google Cloud Console.
4. Deploy with `vercel --prod` (configured via `vercel.json` and `api/index.py`).

> **Note:** On Vercel, `SlidingWindowRateLimiter` tracks per-minute bursts per serverless instance, while daily and monthly quotas are enforced globally inside PostgreSQL. For shared multi-worker rate limiting, deploy via `Dockerfile` on Railway, Render, Fly.io, or a VPS.

---

## 6. Reverse Proxy with Nginx + Let's Encrypt SSL

Always terminate TLS in front of Uvicorn so `HttpOnly; Secure` session cookies, Google OAuth callbacks, and Razorpay webhooks travel over HTTPS:

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 5. Google OAuth 2.0 Setup

1. Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials).
2. Create an **OAuth 2.0 Client ID** (Web application).
3. Under **Authorized redirect URIs**, add:
   - Local: `http://localhost:8000/api/auth/google/callback`
   - Production: `https://api.yourdomain.com/api/auth/google/callback`
4. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and matching `GOOGLE_REDIRECT_URI` in `.env`.

---

## 6. SMTP Email Setup

For email verification links, password reset emails, and payment receipts, configure:
```env
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=re_your_api_key
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_USE_TLS=true
```
In local development when `SMTP_HOST` is blank, outgoing emails are safely captured in the `email_outbox` table and viewable under **Admin Portal → Support, Audit & Outbox**.

