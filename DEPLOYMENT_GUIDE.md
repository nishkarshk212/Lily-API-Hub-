# Production Deployment Guide — Lily API Hub

Complete deployment playbook for **VPS (Docker Compose + Nginx + SSL)**, **Vercel / Cloudflare Pages (Frontend)**, and **Render / Railway (Backend)**, configured via environment variables.

---

## 1. Environment Variables & Secrets Checklist

Copy the template into `backend/.env` and generate strong secrets:

```bash
cp backend/.env.example backend/.env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Required production values (`backend/.env`):
- `APP_ENV=production`
- `APP_PUBLIC_URL=https://api.yourdomain.com` *(or `https://yourdomain.com` for single-domain VPS)*
- `FRONTEND_URL=https://your-site.vercel.app` *(or `https://yourdomain.com` if unified)*
- `COOKIE_SECURE=true`
- `CORS_ORIGINS=https://your-site.vercel.app`
- `DATABASE_URL=postgresql+psycopg://lily_user:STRONG_PASSWORD@db:5432/lily_hub`
- `INITIAL_ADMIN_EMAIL` & `INITIAL_ADMIN_PASSWORD` *(rotate right after first login)*
- `MASTER_API_KEY` & `UPSTREAM_API_BASE_URL` *(your Cloudflare Worker or private Master API)*
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`

> Brand customization (`APP_NAME`, `COMPANY_NAME`, `SUPPORT_EMAIL`, `BRAND_BADGE_LETTER`, `API_KEY_PREFIX_LIVE`, `API_KEY_PREFIX_TEST`, `RECEIPT_PREFIX`) can also be updated from `.env` or live inside **Admin Portal → Site & API Branding**.

---

## 2. Master API Gateway Architecture

Lily API Hub never exposes `MASTER_API_KEY` or `UPSTREAM_API_BASE_URL` to any browser or customer endpoint:
1. Customers authenticate against `<APP_PUBLIC_URL>/v1/*` with their unique key (`X-API-Key` or `Authorization: Bearer`).
2. `backend/app/services/gateway_service.py` checks:
   - Key hash (`SHA-256`) & active status
   - User not suspended
   - Subscription active & not expired (automatic expiration transition)
   - Plan HTTP method & endpoint permissions
   - Per-minute sliding-window rate limit
   - Atomic daily (UTC) & billing-cycle quota update
3. In `hybrid` or `proxy` mode, the gateway decrypts `MASTER_API_KEY` server-side and injects `{UPSTREAM_AUTH_HEADER}: {UPSTREAM_AUTH_SCHEME} {MASTER_API_KEY}` before forwarding to `UPSTREAM_API_BASE_URL`.
4. Administrators can rotate `MASTER_API_KEY`, switch routing modes (`hybrid`/`proxy`/`builtin`), and test upstream connectivity from **Admin Portal → Master API Config**.

---

## 3. VPS Deployment (Recommended All-in-One via Docker Compose)

This repo includes [`docker-compose.yml`](docker-compose.yml) and [`deploy/nginx.conf`](deploy/nginx.conf), running **PostgreSQL 15** (`db`), **FastAPI** (`backend:8000`), and **Nginx** (`frontend:3000`) which reverse-proxies `/api/*`, `/v1/*`, `/healthz`, `/docs`, and `/favicon.svg` on the same origin.

### Step 1 — Install Dependencies on Ubuntu/Debian VPS
```bash
sudo apt update && sudo apt install -y git curl nginx certbot python3-certbot-nginx docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

### Step 2 — Clone, Configure & Start Containers
```bash
git clone https://github.com/nishkarshk212/Lily-API-Hub-.git
cd Lily-API-Hub-
cp backend/.env.example backend/.env
# Edit backend/.env with production domain, secrets, Razorpay, OAuth, and Upstream Master API keys

export POSTGRES_PASSWORD="use_a_strong_db_password"
FRONTEND_HTTP_PORT=3000 docker compose up -d --build
docker compose ps
curl -s http://127.0.0.1:3000/healthz
```

### Step 3 — Host Nginx Reverse Proxy + Let's Encrypt HTTPS
Create `/etc/nginx/sites-available/lily-api-hub`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable HTTPS & firewall:
```bash
sudo ln -s /etc/nginx/sites-available/lily-api-hub /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

---

## 4. Split Deployment: Static Frontend (Vercel / Cloudflare Pages) + Backend (Render / Railway / VPS)

### Frontend (`frontend/` on Vercel or Cloudflare Pages)
- **Vercel**: Connected via root [`vercel.json`](vercel.json) (`framework: null`, `outputDirectory: "frontend"`) OR deploy with **Root Directory:** `frontend` (uses [`frontend/vercel.json`](frontend/vercel.json)).
- **Cloudflare Pages / Netlify**: Set **Root Directory** to `frontend` (`frontend/_redirects` and `frontend/_headers` handle SPA fallback & cache headers).
- Set Environment Variable `API_BASE_URL=https://api.yourdomain.com` (build runs `sh build-config.sh` to inject it into `frontend/config.js`).

### Option A — Backend on Render (1-Click Blueprint)
1. Push this repository to GitHub (`.gitignore` and `backend/.dockerignore` exclude `.env` and local `*.db` files).
2. In **Render Dashboard → New → Blueprint**, select this repo — Render reads [`render.yaml`](render.yaml) (`rootDir: backend`) and provisions both `lily-api-hub-backend` and `lily-hub-db` (PostgreSQL).
3. Set `APP_PUBLIC_URL=https://api.yourdomain.com`, `FRONTEND_URL=https://your-site.vercel.app`, `CORS_ORIGINS=https://your-site.vercel.app`, `MASTER_API_KEY`, `RAZORPAY_*`, and `GOOGLE_*`.

### Option B — Backend on Railway
1. Create a **New Project → Deploy from GitHub repo** in Railway with **Root Directory** set to `backend` (uses [`backend/railway.toml`](backend/railway.toml) + [`backend/Dockerfile`](backend/Dockerfile)).
2. Add a **PostgreSQL** service in the same Railway project and link `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
3. Add `APP_ENV=production`, `COOKIE_SECURE=true`, `SECRET_KEY`, `ENCRYPTION_KEY`, `APP_PUBLIC_URL`, `FRONTEND_URL`, `CORS_ORIGINS`, `RAZORPAY_*`, `GOOGLE_*`, `UPSTREAM_API_BASE_URL`, `MASTER_API_KEY`, `UPSTREAM_AUTH_HEADER=X-API-Key`, `UPSTREAM_AUTH_SCHEME=`, `GATEWAY_MODE=hybrid`.

### Option C — Hybrid (Vercel Frontend + VPS Backend Only)
1. Run `export POSTGRES_PASSWORD="strong_pw" && docker compose up -d --build db backend` on your VPS.
2. Proxy `api.yourdomain.com` on VPS Nginx to `http://127.0.0.1:8000` with `certbot --nginx -d api.yourdomain.com`.
3. Set `FRONTEND_URL=https://your-site.vercel.app` & `CORS_ORIGINS=https://your-site.vercel.app` in `backend/.env`, and `API_BASE_URL=https://api.yourdomain.com` on Vercel.

---

## 5. Cloudflare DNS + Upstream Worker Lockdown

1. In Cloudflare DNS, add a **CNAME** or **A** record (`api.yourdomain.com` → your VPS IP / Render / Railway host) with **Proxy Status: Proxied (Orange Cloud)** and **SSL/TLS → Full (strict)**.
2. Use a strong random master secret on your upstream Cloudflare Worker and configure it inside `backend/.env` or **Admin Portal → Master API Config** so all customer calls pass through Lily API Hub quotas & key checks.

---

## 6. Google OAuth 2.0 Setup

1. Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials).
2. Create an **OAuth 2.0 Client ID** (Web application).
3. Add **Authorized JavaScript origins** (your frontend URL, e.g. `https://your-site.vercel.app` or `https://yourdomain.com`).
4. Add **Authorized redirect URIs** (your backend callback URL):
   - Local: `http://localhost:8000/api/auth/google/callback`
   - Production: `https://api.yourdomain.com/api/auth/google/callback` *(or `https://yourdomain.com/api/auth/google/callback` for single-domain VPS)*
5. Set matching `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in `backend/.env`.

---

## 7. SMTP Email Setup

For email verification links, password reset emails, and payment receipts, configure in `backend/.env`:
```env
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=re_your_api_key
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_USE_TLS=true
```
In local development when `SMTP_HOST` is blank, outgoing emails are safely captured in the `email_outbox` table and viewable under **Admin Portal → Support, Audit & Outbox**.
